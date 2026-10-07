"""Learned utterance model: feature shapes, class layout and the forward
pass (an untrained net; accuracy is measured by tools/evaluate.py)."""

import numpy as np
import pytest

from app.accent.model import N_FEATURES, batch_index, phrase_classes, utterance_features
from app.accent.notation import pitch_pattern

torch = pytest.importorskip("torch")


def fake_rec(accents=(2, 0), n=(3, 3)):
    """Two phrases with ideal H/L pitch, 0.12 s per mora."""
    moras = ["オ", "ト", "オ", "キ", "イ", "タ"][:sum(n)]
    times = np.arange(0, 0.12 * sum(n) + 0.2, 0.01)
    f0 = np.full(len(times), np.nan)
    spans, phrases, k = [], [], 0
    for acc, m in zip(accents, n):
        for i, high in enumerate(pitch_pattern(m, acc)):
            s = 0.1 + 0.12 * (k + i)
            spans.append((s, s + 0.12))
            f0[(times >= s) & (times < s + 0.12)] = 220 if high else 170
        phrases.append({"s": k, "e": k + m, "final": False, "question": False, "last_word": ""})
        k += m
    phrases[-1]["final"] = True
    return {"moras": moras, "special": [False] * sum(n), "phrases": phrases, "spans": spans,
            "scores": [0.0] * sum(n), "times": times, "f0": f0, "energy": np.zeros(len(times))}


def test_features_shape_and_mask():
    x, voiced = utterance_features(fake_rec())
    assert x.shape == (6, N_FEATURES)
    assert np.all(voiced > 0.9)
    assert np.isfinite(x).all()


def test_phrase_classes_match_posterior_layout():
    # 3rd mora is a syllable tail (e.g. セン＼セイ's イ): no nucleus there
    classes, land = phrase_classes(4, [False, False, True, False])
    assert classes[0] == [0, 4, 3]
    assert [c[0] for c in classes[1:]] == [1, 2]
    assert land == [-1, 1, 3]  # after ン the fall shows up past the tail


def test_forward_gives_one_distribution_per_phrase():
    from app.accent.model import _torch_model

    rec = fake_rec()
    x, _ = utterance_features(rec)
    net = _torch_model()(N_FEATURES, 16).eval()
    items = [(0, ph["s"], ph["e"], [False] * 3) for ph in rec["phrases"]]
    logits = net(torch.from_numpy(x)[None], torch.tensor([len(x)]), batch_index(items))
    p = torch.softmax(logits, -1)
    assert p.shape == (2, 3)
    assert torch.allclose(p.sum(-1), torch.ones(2))


def test_speech_model_features_join_the_pitch_features(monkeypatch):
    from app.accent import model as M
    from app.audio.ssl import pool, project

    # 4 layers, 8 dims, a 10-frame utterance: pooled per mora, then projected
    frames = np.random.default_rng(0).normal(size=(4, 60, 8)).astype(np.float32)
    rec = fake_rec()
    pooled = pool(frames, rec["spans"])
    assert pooled.shape == (6, 4, 8)
    pca = {"mean": np.zeros((4, 8), np.float32), "comp": np.tile(np.eye(8, 3, dtype=np.float32), (4, 1, 1)),
           "scale": np.ones((4, 1), np.float32)}
    rec["ssl"] = project(pooled, pca)
    assert rec["ssl"].shape == (6, 12)
    monkeypatch.setattr(M, "ssl_pca", lambda: pca)
    x, _ = M.model_input(rec)
    assert x.shape == (6, N_FEATURES + 12)

    net = M._torch_model()(N_FEATURES, 16, d_ssl=12, n_layers=4).eval()
    items = [(0, ph["s"], ph["e"], [False] * 3) for ph in rec["phrases"]]
    logits = net(torch.from_numpy(x)[None], torch.tensor([len(x)]), batch_index(items))
    assert torch.isfinite(torch.softmax(logits, -1)).all()
