"""Mora-level forced alignment with a Japanese hiragana CTC model.

The expected mora sequence comes from the accent engine, so alignment only
has to find *where* each mora is, not *what* was said.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from .pitch import SAMPLE_RATE

MODEL_ID = "vumichien/wav2vec2-large-xlsr-japanese-hiragana"
FRAME_S = 0.02  # wav2vec2 frame stride (320 samples at 16 kHz)


@dataclass
class MoraSpan:
    start: float
    end: float
    score: float  # peak log-probability of the mora's tokens (CTC spikes)


@lru_cache(maxsize=1)
def _model():
    import torch
    from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

    device = "cuda" if torch.cuda.is_available() else "cpu"
    processor = Wav2Vec2Processor.from_pretrained(MODEL_ID)
    model = Wav2Vec2ForCTC.from_pretrained(
        MODEL_ID, torch_dtype=torch.float16 if device == "cuda" else torch.float32
    ).to(device).eval()
    return processor, model, device


def _hira(kana: str) -> str:
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in kana)


# The model was trained on spelling, we know pronunciation: let each kana
# also match the spellings it is commonly written with (particles は/を/へ,
# long vowels せい/とう/ー, ず/づ, じ/ぢ).
SPELLINGS = {
    "お": "おをう", "わ": "わは", "え": "えへい", "う": "うおー", "い": "いえー",
    "ー": "ーういあえお", "ず": "ずづ", "じ": "じぢ", "あ": "あー",
}


def emissions(wav: np.ndarray) -> tuple[np.ndarray, dict[str, int], int]:
    """(log-probs [T, V], vocab, blank id)."""
    import torch

    processor, model, device = _model()
    inputs = processor(wav, sampling_rate=SAMPLE_RATE, return_tensors="pt")
    with torch.inference_mode():
        logits = model(inputs.input_values.to(device, model.dtype)).logits[0]
    logp = torch.log_softmax(logits.float(), dim=-1).cpu().numpy()
    vocab = processor.tokenizer.get_vocab()
    return logp, vocab, processor.tokenizer.pad_token_id


def ctc_forced_align(logp: np.ndarray, targets: list[list[int]], blank: int) -> list[int]:
    """Viterbi CTC alignment. Each target position accepts any of its token
    ids. Returns, for each frame, the index of the target it is aligned to,
    or -1 for blank."""
    T, L = len(logp), len(targets)
    S = 2 * L + 1
    emit = np.empty((T, S))
    emit[:, 0::2] = logp[:, [blank]]
    for j, ids in enumerate(targets):
        emit[:, 2 * j + 1] = logp[:, ids].max(axis=1)
    skip_ok = np.zeros(S, dtype=bool)
    for j in range(1, L):  # CTC needs a blank between repeats of the same token
        skip_ok[2 * j + 1] = not set(targets[j]) & set(targets[j - 1])

    NEG = -1e30
    dp = np.full(S, NEG)
    dp[0], dp[1] = emit[0, 0], emit[0, 1] if S > 1 else NEG
    back = np.zeros((T, S), dtype=np.int8)  # 0 stay, 1 from s-1, 2 from s-2
    for t in range(1, T):
        stay = dp
        prev1 = np.concatenate(([NEG], dp[:-1]))
        prev2 = np.where(skip_ok, np.concatenate(([NEG, NEG], dp[:-2])), NEG)
        cand = np.stack([stay, prev1, prev2])
        back[t] = cand.argmax(axis=0)
        dp = cand.max(axis=0) + emit[t]

    s = S - 1 if S == 1 or dp[S - 1] >= dp[S - 2] else S - 2
    path = np.empty(T, dtype=np.int64)
    for t in range(T - 1, -1, -1):
        path[t] = s
        s -= int(back[t, s])
    return [int(p // 2) if p % 2 == 1 else -1 for p in path]


def align_moras(wav: np.ndarray, moras: list[str]) -> list[MoraSpan] | None:
    """Time span of every mora. Each mora runs from its first token's onset
    to the next mora's onset, so the spans tile the speech. None when the
    audio is too short for the token sequence."""
    logp, vocab, blank = emissions(wav)
    targets, owner = [], []
    for i, mora in enumerate(moras):
        for ch in _hira(mora):
            ids = [vocab[c] for c in SPELLINGS.get(ch, ch) if c in vocab]
            if ids:
                targets.append(ids)
                owner.append(i)
    if not targets or len(logp) < len(targets):
        return None

    frame_token = ctc_forced_align(logp, targets, blank)
    first, last, scores = {}, {}, {}
    for t, j in enumerate(frame_token):
        if j < 0:
            continue
        i = owner[j]
        first.setdefault(i, t)
        last[i] = t
        scores.setdefault(i, []).append(logp[t, targets[j]].max())

    spans: list[MoraSpan] = []
    for i in range(len(moras)):
        if i not in first:  # mora with no alignable kana: give it a zero span
            t = first.get(i + 1, last.get(i - 1, 0))
            spans.append(MoraSpan(t * FRAME_S, t * FRAME_S, float("-inf")))
            continue
        nxt = next((first[k] for k in range(i + 1, len(moras)) if k in first), None)
        end_frame = nxt if nxt is not None else min(last[i] + 8, len(logp))
        spans.append(MoraSpan(first[i] * FRAME_S, end_frame * FRAME_S,
                              float(np.max(scores[i]))))
    return spans
