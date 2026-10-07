"""F0 extraction (Praat autocorrelation via parselmouth) and per-mora pitch."""

from __future__ import annotations

import os
from functools import lru_cache

import numpy as np
import parselmouth

SAMPLE_RATE = 16000
# Pitch tracker: praat (autocorrelation) or fcpe (torchfcpe, neural).
# Chosen with tools/evaluate.py on caches built with each.
F0_METHOD = os.environ.get("PLATINA_F0", "praat")


def load_audio(path_or_bytes, sr: int = SAMPLE_RATE, start: float | None = None,
               end: float | None = None) -> np.ndarray:
    """Decode any audio ffmpeg understands (wav, webm/opus from browsers,
    m4a, mp3, ...) — a path or raw bytes — to mono float32 at sr. With
    start/end (seconds), only that slice of a file."""
    import subprocess

    src = "pipe:0" if isinstance(path_or_bytes, (bytes, bytearray)) else str(path_or_bytes)
    span = []
    if start is not None:
        span += ["-ss", f"{start:.3f}"]
    if end is not None:
        span += ["-to", f"{end:.3f}"]
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", *span, "-i", src,
         "-f", "f32le", "-ac", "1", "-ar", str(sr), "pipe:1"],
        input=path_or_bytes if src == "pipe:0" else None,
        capture_output=True, check=True,
    )
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()


def to_mono_16k(values: np.ndarray, src_sr: float, sr: int = SAMPLE_RATE) -> np.ndarray:
    values = np.atleast_2d(np.asarray(values, dtype=np.float64))
    snd = parselmouth.Sound(values.mean(axis=0), sampling_frequency=src_sr)
    if int(src_sr) != sr:
        snd = snd.resample(sr)
    return snd.values[0].astype(np.float32)


def f0_track(wav: np.ndarray, sr: int = SAMPLE_RATE,
             method: str | None = None) -> tuple[np.ndarray, np.ndarray]:
    """(times in s, F0 in Hz with NaN where unvoiced), 10 ms frames."""
    method = method or F0_METHOD
    if method == "fcpe":
        return _fcpe(wav, sr)
    snd = parselmouth.Sound(wav.astype(np.float64), sampling_frequency=sr)
    pitch = snd.to_pitch_ac(time_step=0.01, pitch_floor=60.0, pitch_ceiling=500.0)
    f0 = pitch.selected_array["frequency"].astype(np.float64)
    f0[f0 <= 0] = np.nan
    return pitch.xs(), f0


def _device():
    import torch
    return "cuda" if torch.cuda.is_available() else "cpu"


@lru_cache(maxsize=1)
def _fcpe_model():
    from torchfcpe import spawn_bundled_infer_model
    return spawn_bundled_infer_model(device=_device())


def _fcpe(wav: np.ndarray, sr: int):
    import torch

    n = int(len(wav) / sr / 0.01)
    audio = torch.from_numpy(wav.astype(np.float32))[None, :, None].to(_device())
    with torch.no_grad():
        f0 = _fcpe_model().infer(audio, sr=sr, decoder_mode="local_argmax", threshold=0.006,
                                 f0_min=60, f0_max=500, interp_uv=False,
                                 output_interp_target_length=n)
    f0 = f0.squeeze().float().cpu().numpy().astype(np.float64)
    f0[f0 <= 0] = np.nan
    return (np.arange(n) + 0.5) * 0.01, f0



def semitones(f0: np.ndarray) -> np.ndarray:
    """F0 in semitones relative to the speaker's median for this recording."""
    ref = np.nanmedian(f0) if np.any(~np.isnan(f0)) else 100.0
    return 12.0 * np.log2(f0 / ref)


def mora_pitch(times: np.ndarray, st: np.ndarray,
               spans: list[tuple[float, float]]) -> list[float | None]:
    """Median pitch of each mora, skipping its first quarter (consonant onset).
    None where the mora is (mostly) unvoiced, e.g. devoiced キ in キタ."""
    out: list[float | None] = []
    for s, e in spans:
        lo = s + 0.25 * (e - s)
        sel = st[(times >= lo) & (times < e)]
        sel = sel[~np.isnan(sel)]
        out.append(float(np.median(sel)) if len(sel) >= 2 else None)
    return out

def energy_db(wav: np.ndarray, times: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Frame energy (dB) around each time, 25 ms window."""
    win = int(0.025 * sr)
    out = np.empty(len(times))
    for k, t in enumerate(times):
        c = int(t * sr)
        seg = wav[max(0, c - win // 2):c + win // 2]
        out[k] = 10 * np.log10(np.mean(seg.astype(np.float64) ** 2) + 1e-10) if len(seg) else -100
    return out
