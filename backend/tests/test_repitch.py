"""Re-pitching closed loop: impose an accent on a voice-like signal with
Praat PSOLA, re-track it, and check the pitch moves the way the accent says."""

import numpy as np
import soundfile as sf

from app.audio.pitch import f0_track
from tools import repitch


def _voice(path, seconds=1.0, f0=150.0, sr=16000):
    t = np.arange(int(sr * seconds)) / sr
    wav = sum(np.sin(2 * np.pi * f0 * k * t) / k for k in range(1, 12)) * 0.1
    sf.write(path, wav.astype(np.float32), sr)


def test_imposed_accent_lands(tmp_path, monkeypatch):
    path = tmp_path / "v.wav"
    _voice(path)
    times, f0 = f0_track(sf.read(path)[0].astype(np.float32))
    spans = [(0.1 + 0.2 * i, 0.3 + 0.2 * i) for i in range(4)]
    rec = {"path": str(path), "moras": ["ア", "メ", "ガ", "ア"], "special": [False] * 4,
           "spans": spans, "scores": [0.0] * 4, "times": times, "f0": f0, "src": "t", "utt": "u",
           "phrases": [{"s": 0, "e": 4, "labels": [0], "kind": "exact", "conf": "exact",
                        "final": True, "question": False, "last_word": ""}]}
    monkeypatch.setattr(repitch, "MODE", "global")
    out = None
    for seed in range(10):  # one sampled mistake for a flat phrase: some drop position
        out = repitch.make((rec, seed, False))
        if out and out["phrases"][0]["kind"] == "repitch":
            break
    assert out is not None and out["phrases"][0]["kind"] == "repitch"
    acc = out["phrases"][0]["labels"][0]
    assert 1 <= acc <= 3  # a drop was imposed on the flat phrase
    meas = repitch._mora_medians(out["times"], 12 * np.log2(out["f0"] / np.nanmedian(out["f0"])), spans)
    assert meas[acc - 1] - meas[acc] > 1.0  # pitch really falls after the nucleus
