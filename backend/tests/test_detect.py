"""Accent detection tests.

Real-speech accuracy is measured with tools/train_detector.py on held-out
JSUT sentences (not in the repo). These tests check the detector on clean,
idealized contours, and run the full pipeline once end to end.
"""

import numpy as np
import pytest

from app.accent.detect import detect_accent, posterior
from app.accent.notation import pitch_pattern

MORA_S = 0.12


def contour(accent: int, n: int, final: bool = False, delay: float = 0.4):
    """Pitch track for n moras with the given accent: L/H levels 5 semitones
    apart, steps arriving `delay` of a mora late, mild declination."""
    spans = [(0.1 + i * MORA_S, 0.1 + (i + 1) * MORA_S) for i in range(n)]
    times = np.arange(0.0, 0.2 + n * MORA_S, 0.01)
    levels = np.array(pitch_pattern(n, accent), dtype=float) * 5.0
    st = np.full_like(times, np.nan)
    for k, t in enumerate(times):
        i = int((t - 0.1) / MORA_S - delay)
        if 0.1 <= t < spans[-1][1]:
            st[k] = levels[min(max(i, 0), n - 1)] - 2.0 * (t - 0.1)
    if final:
        st[times > spans[-1][1] - 0.04] = np.nan
    return times, st, spans


@pytest.mark.parametrize("n,accent", [(3, 1), (3, 2), (4, 1), (4, 2), (4, 3), (5, 2), (5, 3)])
def test_clean_contour_detected(n, accent):
    times, st, spans = contour(accent, n)
    det = detect_accent(times, st, spans, [False] * n)
    assert det.accent == accent, (det.classes, det.posterior)
    assert det.prob_of([accent]) > 0.5


@pytest.mark.parametrize("n", [3, 4, 5])
def test_heiban_contour_detected(n):
    times, st, spans = contour(0, n)
    det = detect_accent(times, st, spans, [False] * n)
    assert 0 in det.candidates and n in det.candidates


def test_wrong_expectation_gets_low_probability():
    times, st, spans = contour(1, 4)  # speaker says ア＼メガ-like accent 1
    det = detect_accent(times, st, spans, [False] * 4)
    assert det.prob_of([0, 4]) < 0.2  # expected heiban → flagged
    assert det.prob_of([1]) > 0.5


def test_unvoiced_phrase_is_undecided():
    times, st, spans = contour(2, 4)
    det = detect_accent(times, np.full_like(st, np.nan), spans, [False] * 4)
    assert det.accent is None


def test_posterior_classes():
    # 4 moras, mora 2 is a syllable tail (e.g. ナイママ): accent 2 impossible,
    # so it merges into the no-fall class with 0 and 4
    p = np.array([0.9, 0.5, 0.1])
    ok = np.array([True, False, True])
    classes, post = posterior(p, ok, 4)
    assert classes == [[0, 4, 2], [1], [3]]
    assert abs(sum(post) - 1) < 1e-9
    assert int(np.argmax(post)) == 1


def test_pipeline_end_to_end():
    """TTS audio → alignment → pitch → verdict. The TTS voice is not very
    intelligible to the CTC model, so only structure and sanity are checked."""
    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    import pyopenjtalk

    from app.analyze import analyze_audio
    from app.audio.pitch import to_mono_16k

    text = "橋を渡る。"
    feats = pyopenjtalk.run_frontend(text)
    feats[0]["acc"], feats[2]["acc"] = 2, 0  # ハシ＼オ ワタル━
    wav, sr = pyopenjtalk.synthesize(pyopenjtalk.make_label(feats))
    res = analyze_audio(to_mono_16k(wav / 32768.0, sr), text)

    assert [p["notation"] for p in res["phrases"]] == ["ハシ＼オ", "ワタル━"]
    for p in res["phrases"]:
        assert p["status"] in {"correct", "error", "uncertain", "unverified"}
        assert len(p["mora_times"]) == len(p["moras"])
    assert res["phrases"][0]["status"] == "correct"
