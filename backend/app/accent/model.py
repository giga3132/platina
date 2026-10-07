"""Learned accent detector over a whole utterance (replaces the per-boundary
gradient-boosted model in detect.py when accent_model.pt exists).

Every mora becomes a feature row (pitch shape in the speaker's own range,
voicing, duration, energy, phonetic class, position); a bidirectional GRU
reads the utterance, so each phrase is judged with its neighbours in view
(downstep, declination, final intonation). For each phrase the network
scores "no fall" and "fall after mora a" for every possible a, and a softmax
over those gives the accent classes detect.posterior() would give, which are
then merged where the audio can't tell them apart (detect.merge_classes).

Trained by tools/train_accent.py.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import numpy as np

from .detect import MIN_VOICED, Detection, merge_classes
from .features import _next_head, possible
from .kana import vowel_of

# PLATINA_ACCENT_MODEL points at an experimental checkpoint (tools/train_accent.py --out)
MODEL = Path(os.environ.get("PLATINA_ACCENT_MODEL", Path(__file__).with_name("accent_model.pt")))
POINTS = 5  # pitch samples per mora

_VOICELESS = set("カキクケコサシスセソタチツテトハヒフヘホパピプペポ")
_VOICED_OBS = set("ガギグゲゴザジズゼゾダヂヅデドバビブベボヴ")
_SONORANT = set("ナニヌネノマミムメモヤユヨラリルレロワヲ")
_VOWELS = "aiueo"


def _phon(mora: str) -> list[float]:
    """Vowel one-hot (a i u e o, N, Q, ー) + consonant class (none, voiceless
    obstruent, voiced obstruent, sonorant)."""
    v = [0.0] * 8
    if mora == "ン":
        v[5] = 1
    elif mora == "ッ":
        v[6] = 1
    elif mora == "ー":
        v[7] = 1
    else:
        vw = vowel_of(mora)
        if vw:
            v[_VOWELS.index(vw)] = 1
    c = mora[:1]
    cons = [float(c in "アイウエオ" or not c), float(c in _VOICELESS), float(c in _VOICED_OBS),
            float(c in _SONORANT)]
    return v + cons


N_FEATURES = 2 * POINTS + 4 + 12 + 10


def speaker_range(st: np.ndarray, times: np.ndarray, spans) -> float:
    """Spread of the speaker's voiced mora pitch (semitones), robust."""
    meds = []
    for s, e in spans:
        v = st[(times >= s) & (times < e)]
        v = v[~np.isnan(v)]
        if len(v):
            meds.append(np.median(v))
    if len(meds) < 4:
        return 4.0
    return float(np.clip(np.percentile(meds, 90) - np.percentile(meds, 10), 2.0, 12.0))


def utterance_features(rec: dict, profile_range: float | None = None) -> tuple[np.ndarray, np.ndarray]:
    """[n_moras, N_FEATURES] features and per-mora voiced fraction."""
    times = np.asarray(rec["times"], dtype=np.float64)
    f0 = np.asarray(rec["f0"], dtype=np.float64)
    ok = ~np.isnan(f0) & (f0 > 0)
    ref = np.median(f0[ok]) if ok.any() else 100.0
    st = 12.0 * np.log2(np.where(ok, f0, np.nan) / ref)
    spans = rec["spans"]
    rng = speaker_range(st, times, spans)
    if profile_range:  # short recordings: lean on the speaker's calibrated range
        w = min(1.0, len(spans) / 40)
        rng = w * rng + (1 - w) * profile_range
    energy = np.asarray(rec.get("energy", np.zeros(len(times))), dtype=np.float64)
    emax = np.max(energy) if len(energy) else 0.0
    durs = np.array([max(e - s, 0.01) for s, e in spans])
    logd = np.log(durs)
    logd -= np.mean(logd)

    n = len(spans)
    phrase_of = np.zeros(n, dtype=int)
    starts, ends = np.zeros(n), np.zeros(n)
    pos, plen = np.zeros(n), np.zeros(n)
    final_f, question_f, particle_f = np.zeros(n), np.zeros(n), np.zeros(n)
    from ..analyze import FINAL_PARTICLES  # noqa: PLC0415 - avoid import cycle at load
    for k, ph in enumerate(rec["phrases"]):
        s, e = ph["s"], ph["e"]
        phrase_of[s:e] = k
        starts[s], ends[e - 1] = 1, 1
        pos[s:e] = (np.arange(e - s) + 0.5) / (e - s)
        plen[s:e] = (e - s) / 10
        final_f[s:e] = float(ph["final"])
        question_f[s:e] = float(ph.get("question", False))
        particle_f[s:e] = float(ph.get("last_word", "") in FINAL_PARTICLES)

    rows, voiced = [], np.zeros(n)
    for i, (s, e) in enumerate(spans):
        sel = (times >= s) & (times < e)
        seg = st[sel]
        voiced[i] = float(np.mean(~np.isnan(seg))) if len(seg) else 0.0
        pts, mask = [], []
        for j in range(POINTS):
            lo = s + j * (e - s) / POINTS
            hi = s + (j + 1) * (e - s) / POINTS
            v = st[(times >= lo - 0.005) & (times < hi + 0.005)]
            v = v[~np.isnan(v)]
            pts.append(float(np.median(v)) / rng if len(v) else 0.0)
            mask.append(float(len(v) > 0))
        en = energy[sel]
        mora = rec["moras"][i]
        nxt = rec["moras"][i + 1] if i + 1 < n else ""
        vw = vowel_of(mora)
        devoice = float(vw in ("i", "u") and mora[:1] in _VOICELESS and
                        (not nxt or nxt[:1] in _VOICELESS))
        rows.append(pts + mask + [voiced[i], logd[i], (np.mean(en) - emax) / 20 if len(en) else -3.0,
                                  float(rec["special"][i])] + _phon(mora) +
                    [starts[i], ends[i], pos[i], plen[i], final_f[i], question_f[i], particle_f[i],
                     devoice, rng / 10, n / 50])
    return np.asarray(rows, dtype=np.float32).reshape(n, N_FEATURES), voiced


def phrase_classes(n: int, special: list[bool]) -> tuple[list[list[int]], list[int]]:
    """Accent classes as detect.posterior() builds them, and for each class
    the mora index the fall lands on (-1 = no fall)."""
    ok = possible(n, special)
    classes = [[0, n] + [a for a in range(1, n) if not ok[a - 1]]]
    land = [-1]
    for a in range(1, n):
        if ok[a - 1]:
            classes.append([a])
            land.append(min(_next_head(a, special), n - 1))
    return classes, land


def _torch_model():
    import torch
    from torch import nn

    class AccentNet(nn.Module):
        def __init__(self, d_in: int = N_FEATURES, h: int = 64, d_ssl: int = 0, n_layers: int = 1,
                     ssl_drop: float = 0.0):
            super().__init__()
            self.d_in, self.d_ssl, self.n_layers, self.ssl_drop = d_in, d_ssl, n_layers, ssl_drop
            self.inp = nn.Sequential(nn.Linear(d_in, h), nn.GELU())
            if d_ssl:  # speech-model features: a learned mix of layers, then a projection
                self.mix = nn.Parameter(torch.zeros(n_layers))
                self.ssl = nn.Sequential(nn.Dropout(0.1), nn.Linear(d_ssl // n_layers, h), nn.GELU())
            self.gru = nn.GRU(h, h, num_layers=2, batch_first=True, bidirectional=True, dropout=0.1)
            self.fall = nn.Sequential(nn.Linear(4 * 2 * h, h), nn.GELU(), nn.Linear(h, 1))
            self.flat = nn.Sequential(nn.Linear(3 * 2 * h, h), nn.GELU(), nn.Linear(h, 1))

        def forward(self, x, lengths, cand):
            """x [B, T, F]; cand: dict of index tensors (see batch_index).
            Returns logits [P, C] with -inf padding."""
            h = self.inp(x[..., :self.d_in])
            if self.d_ssl:
                z = x[..., self.d_in:].reshape(*x.shape[:2], self.n_layers, -1)
                z = (z * torch.softmax(self.mix, 0)[:, None]).sum(-2)
                z = self.ssl(z)
                if self.training and self.ssl_drop:  # whole utterances without it: keeps the pitch path strong
                    z = z * (torch.rand(len(z), 1, 1, device=z.device) >= self.ssl_drop)
                h = h + z
            h = nn.utils.rnn.pack_padded_sequence(h, lengths.cpu(), batch_first=True, enforce_sorted=False)
            h, _ = self.gru(h)
            h, _ = nn.utils.rnn.pad_packed_sequence(h, batch_first=True)
            b = cand["b"]
            fall_in = torch.cat([h[b, cand["nuc"]], h[b, cand["land"]], h[b, cand["first"]],
                                 h[b, cand["last"]]], dim=-1)
            fall = self.fall(fall_in).squeeze(-1)
            fb = cand["flat_b"]
            seg = torch.zeros(len(fb), h.shape[-1], device=h.device)
            seg = seg.index_add(0, cand["mean_phrase"], h[cand["mean_b"], cand["mean_t"]])
            seg = seg / cand["phrase_len"].unsqueeze(-1)
            flat = self.flat(torch.cat([seg, h[fb, cand["flat_first"]], h[fb, cand["flat_last"]]],
                                       dim=-1)).squeeze(-1)
            logits = torch.full(cand["shape"], float("-inf"), device=h.device)
            logits[cand["flat_row"], 0] = flat
            logits[cand["row"], cand["col"]] = fall
            return logits

    return AccentNet


def batch_index(items: list[tuple[int, int, int, list[bool]]]):
    """items: (batch index, phrase start, phrase end, special) per phrase.
    Builds the gather indices AccentNet.forward needs."""
    import torch

    b, nuc, land, first, last, row, col = [], [], [], [], [], [], []
    flat_b, flat_first, flat_last, mean_b, mean_t, mean_phrase, plen = [], [], [], [], [], [], []
    width = 1
    for r, (bi, s, e, special) in enumerate(items):
        n = e - s
        classes, lands = phrase_classes(n, special)
        width = max(width, len(classes))
        flat_b.append(bi)
        flat_first.append(s)
        flat_last.append(e - 1)
        plen.append(float(n))
        for t in range(s, e):
            mean_b.append(bi)
            mean_t.append(t)
            mean_phrase.append(r)
        for c in range(1, len(classes)):
            a = classes[c][0]
            b.append(bi)
            nuc.append(s + a - 1)
            land.append(s + lands[c])
            first.append(s)
            last.append(e - 1)
            row.append(r)
            col.append(c)
    t = lambda v: torch.tensor(v, dtype=torch.long)  # noqa: E731
    return {"b": t(b), "nuc": t(nuc), "land": t(land), "first": t(first), "last": t(last),
            "row": t(row), "col": t(col), "flat_b": t(flat_b), "flat_first": t(flat_first),
            "flat_last": t(flat_last), "flat_row": t(list(range(len(items)))),
            "mean_b": t(mean_b), "mean_t": t(mean_t), "mean_phrase": t(mean_phrase),
            "phrase_len": torch.tensor(plen), "shape": (len(items), width)}


@lru_cache(maxsize=1)
def _checkpoint():
    import torch
    return torch.load(MODEL, map_location="cpu", weights_only=False)


@lru_cache(maxsize=1)
def load():
    ckpt = _checkpoint()
    net = _torch_model()(**ckpt["config"])
    net.load_state_dict(ckpt["state"])
    net.eval()
    return net, float(ckpt.get("temperature", 1.0))


def ssl_pca() -> dict | None:
    """PCA basis of the speech-model features, when the model uses them."""
    return _checkpoint().get("ssl_pca")


def model_input(rec: dict, profile_range: float | None = None) -> tuple[np.ndarray, np.ndarray]:
    """utterance_features, plus the speech-model features when the model
    uses them: rec["ssl"] if precomputed, else from rec["wav"] (or the file
    at rec["path"])."""
    x, voiced = utterance_features(rec, profile_range)
    pca = ssl_pca()
    if pca is None:
        return x, voiced
    z = rec.get("ssl")
    if z is None:
        from ..audio.ssl import mora_features
        wav = rec.get("wav")
        if wav is None:
            from ..audio.pitch import load_audio
            wav = load_audio(rec["path"])
        z = mora_features(wav, rec["spans"], pca)
    return np.concatenate([x, np.asarray(z, dtype=np.float32)], axis=1), voiced


def thresholds() -> dict:
    """Verdict thresholds tuned for this model (tools/tune_thresholds.py)."""
    return _checkpoint().get("thresholds", {})


def f0_method() -> str:
    """The pitch tracker the model was trained on."""
    return _checkpoint().get("f0", "praat")


def available() -> bool:
    return MODEL.exists()


def detect_phrases(rec: dict, reliable=None, profile_range: float | None = None) -> list[Detection]:
    """One Detection per phrase of the utterance record. `reliable(rec, ph)`
    gives per-mora reliability (alignment, final boundary rise)."""
    import torch

    net, temp = load()
    x, voiced = model_input(rec, profile_range)
    items, idx = [], []
    for k, ph in enumerate(rec["phrases"]):
        if ph["e"] - ph["s"] >= 2:
            items.append((0, ph["s"], ph["e"], list(rec["special"][ph["s"]:ph["e"]])))
            idx.append(k)
    out = [Detection(None, 0.0) for _ in rec["phrases"]]
    if not items:
        return out
    with torch.no_grad():
        logits = net(torch.from_numpy(x)[None], torch.tensor([len(x)]), batch_index(items))
        probs = torch.softmax(logits / temp, dim=-1).numpy()
    for (_, s, e, special), k, p in zip(items, idx, probs):
        n = e - s
        ph = rec["phrases"][k]
        v = voiced[s:e]
        if v.mean() < 0.2:
            continue
        observable = v >= MIN_VOICED
        if reliable is not None:
            observable &= np.asarray(reliable(rec, ph), dtype=bool)
        if observable.sum() < 2:
            continue
        classes, _ = phrase_classes(n, special)
        post = [float(p[c]) for c in range(len(classes))]
        classes, post = merge_classes(classes, post, n, observable)
        if len(classes) == 1:
            out[k] = Detection(None, 0.0, classes, post)
            continue
        best = int(np.argmax(post))
        out[k] = Detection(classes[best][0], post[best], classes, post)
    return out
