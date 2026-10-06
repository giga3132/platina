"""F0 extraction (Praat autocorrelation via parselmouth) and per-mora pitch."""

from __future__ import annotations

import numpy as np
import parselmouth

SAMPLE_RATE = 16000


def load_audio(path_or_bytes, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Decode any audio ffmpeg understands (wav, webm/opus from browsers,
    m4a, mp3, ...) — a path or raw bytes — to mono float32 at sr."""
    import subprocess

    src = "pipe:0" if isinstance(path_or_bytes, (bytes, bytearray)) else str(path_or_bytes)
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", src,
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


def f0_track(wav: np.ndarray, sr: int = SAMPLE_RATE) -> tuple[np.ndarray, np.ndarray]:
    """(times in s, F0 in Hz with NaN where unvoiced)."""
    snd = parselmouth.Sound(wav.astype(np.float64), sampling_frequency=sr)
    pitch = snd.to_pitch_ac(time_step=0.01, pitch_floor=60.0, pitch_ceiling=500.0)
    f0 = pitch.selected_array["frequency"].astype(np.float64)
    f0[f0 <= 0] = np.nan
    return pitch.xs(), f0


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
