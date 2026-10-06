"""Audio + transcript → per-phrase verdict on the speaker's pitch accent."""

from __future__ import annotations

import numpy as np

from .accent.detect import detect_accent
from .accent.engine import Phrase, analyze_text
from .accent.kana import special_moras
from .accent.notation import phrase_notation
from .accent.overrides import OverrideStore
from .audio.align import align_moras
from .audio.pitch import f0_track, mora_pitch, semitones

# Flag a mistake when the detector gives the expected accent less than this
# probability. Tuned on 400 held-out JSUT sentences (tools/train_detector.py):
#   expected flat (heiban, or odaka with nothing after it):
#                  2.6% false alarms, catches 75% of added drops
#   expected drop: 3.3% false alarms, catches 71% of missing/misplaced drops
ERROR_P_FLAT = 0.3
ERROR_P_ACCENTED = 0.02
CORRECT_P = 0.5  # at least this likely → correct; in between → uncertain
MIN_ALIGN_SCORE = -3.0  # peak log-prob per mora below this = misaligned

SENTENCE_BREAKS = set("。、．，！？!?,.…「」『』（）() 　\n")

# status: correct | error | uncertain (couldn't tell) | unverified
# (sounded different, but the expected accent itself isn't confident)


def _special(p: Phrase) -> list[bool]:
    starts, k = set(), 0
    for w in p.words:
        starts.add(k)
        k += w.n_moras
    return special_moras(p.moras, starts)


def _status(p: Phrase, det, align_ok: bool) -> tuple[str, float | None]:
    if det.accent is None or not align_ok:
        return "uncertain", None
    p_exp = det.prob_of(p.alternatives)
    flat = any(a in (0, len(p.moras)) for a in p.alternatives)
    if p_exp >= CORRECT_P:
        return "correct", p_exp
    if p_exp >= (ERROR_P_FLAT if flat else ERROR_P_ACCENTED):
        return "uncertain", p_exp
    return ("unverified" if p.confidence == "uncertain" else "error"), p_exp


def analyze_audio(wav: np.ndarray, text: str, overrides: OverrideStore | None = None,
                  offset: float = 0.0) -> dict:
    phrases = analyze_text(text, overrides)
    moras = [m for p in phrases for m in p.moras]
    spans = align_moras(wav, moras) if moras else None
    times, f0 = f0_track(wav)
    st = semitones(f0)

    out, k = [], 0
    for p in phrases:
        d = p.to_dict()
        n = len(p.moras)
        ps = spans[k:k + n] if spans else []
        k += n
        mora_spans = [(s.start, s.end) for s in ps]
        final = p.end >= len(text) or text[p.end] in SENTENCE_BREAKS
        det = detect_accent(times, st, mora_spans, _special(p), final) if ps else detect_accent(times, st, [])
        align_ok = bool(ps) and min(s.score for s in ps) > MIN_ALIGN_SCORE
        status, p_exp = _status(p, det, align_ok)

        d.update(
            status=status,
            observed=det.accent,
            observed_notation=phrase_notation(p.moras, det.accent) if det.accent is not None else None,
            p_expected=None if p_exp is None else round(p_exp, 3),
            detect_confidence=round(det.confidence, 3),
            mora_times=[(round(s + offset, 3), round(e + offset, 3)) for s, e in mora_spans],
            mora_pitch=[None if v is None else round(v, 2)
                        for v in (mora_pitch(times, st, mora_spans) if ps else [None] * n)],
        )
        out.append(d)
    return {"text": text, "phrases": out}
