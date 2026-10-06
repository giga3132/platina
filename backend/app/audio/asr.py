"""Speech → utterances with transcripts.

silero-vad cuts the recording at pauses into utterances of at most
MAX_UTTERANCE_S; kotoba-whisper (Whisper distilled for Japanese) transcribes
each one. Short utterances keep the forced alignment reliable.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from .pitch import SAMPLE_RATE

ASR_MODEL = "kotoba-tech/kotoba-whisper-v2.0"
MAX_UTTERANCE_S = 15.0
PAD_S = 0.15  # keep a little audio around each speech region
MERGE_GAP_S = 0.35  # shorter pauses than this stay inside one utterance


@dataclass
class Utterance:
    start: float
    end: float
    wav: np.ndarray
    text: str = ""


@lru_cache(maxsize=1)
def _vad():
    from silero_vad import load_silero_vad
    return load_silero_vad()


@lru_cache(maxsize=1)
def _asr():
    import torch
    from transformers import pipeline

    cuda = torch.cuda.is_available()
    return pipeline(
        "automatic-speech-recognition", model=ASR_MODEL,
        dtype=torch.float16 if cuda else torch.float32,
        device="cuda:0" if cuda else "cpu",
    )


def segment(wav: np.ndarray) -> list[Utterance]:
    """Split at pauses into utterances no longer than MAX_UTTERANCE_S."""
    import torch
    from silero_vad import get_speech_timestamps

    regions = get_speech_timestamps(torch.from_numpy(wav), _vad(),
                                    sampling_rate=SAMPLE_RATE, return_seconds=True,
                                    min_silence_duration_ms=300)
    merged: list[list[float]] = []
    for r in regions:
        s, e = r["start"], r["end"]
        if merged and e - merged[-1][0] <= MAX_UTTERANCE_S and s - merged[-1][1] < MERGE_GAP_S:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    total = len(wav) / SAMPLE_RATE
    out = []
    for s, e in merged:
        s, e = max(0.0, s - PAD_S), min(total, e + PAD_S)
        out.append(Utterance(s, e, wav[int(s * SAMPLE_RATE):int(e * SAMPLE_RATE)]))
    return out


def transcribe(wav: np.ndarray) -> str:
    out = _asr()({"raw": wav, "sampling_rate": SAMPLE_RATE},
                 generate_kwargs={"language": "ja", "task": "transcribe"})
    return out["text"].strip()


def recognize(wav: np.ndarray) -> list[Utterance]:
    utterances = segment(wav)
    for u in utterances:
        u.text = transcribe(u.wav)
    return [u for u in utterances if u.text]
