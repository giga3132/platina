"""Audio + transcript → per-phrase verdict on the speaker's pitch accent."""

from __future__ import annotations

import numpy as np

from .accent.detect import detect_accent
from .accent.engine import Phrase, analyze_text
from .accent.kana import special_moras, strip_reading_hints
from .accent.notation import phrase_notation, pitch_pattern
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
# An error also needs one other accent to be heard clearly: low P(expected)
# alone (a narrow-range or unclear contour) is "unclear", not a mistake.
HEARD_P = 0.6
MIN_ALIGN_SCORE = -3.0  # peak log-prob per mora below this = misaligned
MIN_MORA_S = 0.03  # shorter aligned moras are alignment failures
# Sentence-final particles carry boundary tones (rises) that aren't accent.
FINAL_PARTICLES = {"ね", "よ", "か", "な", "わ", "ぞ", "さ", "ねえ", "よね"}
QUESTION = set("？?")

SENTENCE_BREAKS = set("。、．，！？!?,.…「」『』（）() 　\n")

# status: correct | error | uncertain (couldn't tell) | unverified
# (sounded different, but the expected accent itself isn't confident)


def _special(p: Phrase) -> list[bool]:
    starts, k = set(), 0
    for w in p.words:
        starts.add(k)
        k += w.n_moras
    return special_moras(p.moras, starts)


def _reliable(p: Phrase, spans, text: str, final: bool) -> list[bool]:
    """Per mora: may its pitch count as evidence? Not if badly aligned, and
    not the last mora before a question mark or a sentence-final particle
    (boundary rise)."""
    out = [s.score > MIN_ALIGN_SCORE and s.end - s.start >= MIN_MORA_S for s in spans]
    if out and final:
        after = text[p.end:p.end + 2]
        last_word = p.words[-1].surface if p.words else ""
        if any(c in QUESTION for c in after) or last_word in FINAL_PARTICLES:
            out[-1] = False
    return out


def _heard(p: Phrase, det) -> tuple[list[int], float]:
    """The most likely accent class that is not an acceptable one."""
    best, best_p = [], 0.0
    for cls, prob in zip(det.classes, det.posterior):
        if not set(cls) & set(p.alternatives) and prob > best_p:
            best, best_p = cls, prob
    return best, best_p


def _thresholds() -> tuple[float, float, float]:
    """(ERROR_P_FLAT, ERROR_P_ACCENTED, HEARD_P) for the detector in use: the
    learned model carries its own, tuned on held-out speakers."""
    from .accent import model as learned
    t = learned.thresholds() if learned.available() else {}
    return (t.get("ERROR_P_FLAT", ERROR_P_FLAT), t.get("ERROR_P_ACCENTED", ERROR_P_ACCENTED),
            t.get("HEARD_P", HEARD_P))


def _status(p: Phrase, det, reliable: list[bool]) -> tuple[str, float | None, str]:
    """(status, P(expected), reason when unclear)."""
    if det.accent is None:
        return "uncertain", None, "no-pitch"
    p_exp = det.prob_of(p.alternatives)
    if p_exp >= CORRECT_P:
        return "correct", p_exp, ""
    flat = any(a in (0, len(p.moras)) for a in p.alternatives)
    heard, p_heard = _heard(p, det)
    err_flat, err_acc, heard_p = _thresholds()
    if p_exp >= (err_flat if flat else err_acc) or p_heard < heard_p:
        return "uncertain", p_exp, "unclear"
    # the moras that decide between expected and heard must be well aligned
    n = len(p.moras)
    exp_pat, heard_pat = pitch_pattern(n, p.accent), pitch_pattern(n, heard[0])
    deciding = {j for i in range(n) if exp_pat[i] != heard_pat[i]
                for j in (i - 1, i, i + 1) if 0 <= j < n}
    if any(not reliable[i] for i in deciding):
        return "uncertain", p_exp, "alignment"
    if set(heard) & set(getattr(p, "proposed_variants", [])):
        return "unverified", p_exp, "native-variant"  # natives say it this way too; not yet reviewed
    return ("unverified" if p.confidence == "uncertain" else "error"), p_exp, ""


def analyze_audio(wav: np.ndarray, text: str, overrides: OverrideStore | None = None,
                  offset: float = 0.0, variants=None) -> dict:
    from .accent import model as learned

    phrases = analyze_text(text, overrides, variants)
    text = strip_reading_hints(text)[0]  # phrase offsets are into the text without hints
    moras = [m for p in phrases for m in p.moras]
    spans = align_moras(wav, moras) if moras else None
    use_model = learned.available() and spans is not None
    times, f0 = f0_track(wav, method=learned.f0_method() if use_model else None)
    st = semitones(f0)
    model_dets = _model_detections(wav, text, phrases, spans, times, f0) if use_model else None

    from .accent import contour

    out, k = [], 0
    prev_drop = False
    for i, p in enumerate(phrases):
        d = p.to_dict()
        n = len(p.moras)
        ps = spans[k:k + n] if spans else []
        k += n
        mora_spans = [(s.start, s.end) for s in ps]
        final = p.end >= len(text) or text[p.end] in SENTENCE_BREAKS
        reliable = _reliable(p, ps, text, final) if ps else []
        if model_dets is not None and ps:
            det = model_dets[i]
        elif ps and sum(reliable) >= 2:
            det = detect_accent(times, st, mora_spans, _special(p), final, reliable)
        else:
            det = detect_accent(times, st, [])
        status, p_exp, reason = _status(p, det, reliable)
        # what the speaker said is only reported when it was heard clearly
        observed = det.accent if status != "uncertain" else None

        d.update(
            status=status,
            unclear_reason=reason or None,
            observed=observed,
            observed_notation=phrase_notation(p.moras, observed) if observed is not None else None,
            p_expected=None if p_exp is None else round(p_exp, 3),
            detect_confidence=round(det.confidence, 3),
            mora_times=[(round(s + offset, 3), round(e + offset, 3)) for s, e in mora_spans],
            mora_pitch=[None if v is None else round(v, 2)
                        for v in (mora_pitch(times, st, mora_spans) if ps else [None] * n)],
        )
        if contour.available() and n >= 1:
            d["expected_contour"] = contour.predict(
                n, p.accent, _special(p), prev_drop, final,
                any(c in QUESTION for c in text[p.end:p.end + 2])).round(3).tolist()
        prev_drop = (0 < p.accent < n) and not final
        out.append(d)
    _rescue_merged(phrases, out, spans, text, times, st,
                   (wav, f0) if use_model else None)
    return {"text": text, "phrases": out}


def _rescue_merged(phrases, out, spans, text, times, st, model_input) -> None:
    """Natives often say two phrases in one breath (読んで|います as
    ヨ＼ンデイマス). When a phrase pair flagged as a mistake is explained by
    that phrasing, it isn't a mistake: mark both correct, "said as one"."""
    if not spans:
        return
    starts, k = [], 0
    for p in phrases:
        starts.append(k)
        k += len(p.moras)
    for i, p in enumerate(phrases[:-1]):
        q = phrases[i + 1]
        if not p.merge_accents or not q.moras or "error" not in (out[i]["status"], out[i + 1]["status"]):
            continue
        s, e = starts[i], starts[i + 1] + len(q.moras)
        ps = spans[s:e]
        final = q.end >= len(text) or text[q.end] in SENTENCE_BREAKS
        special = _special(p) + _special(q)
        reliable = _reliable(p, spans[s:starts[i + 1]], text, False) + _reliable(q, spans[starts[i + 1]:e], text, final)
        if sum(reliable) < 2:
            continue
        if model_input is not None:
            from .accent.model import detect_phrases
            from .audio.pitch import energy_db
            wav, f0 = model_input
            rec = {"moras": p.moras + q.moras, "special": special, "spans": [(x.start, x.end) for x in ps],
                   "scores": [x.score for x in ps], "times": times, "f0": f0, "energy": energy_db(wav, times),
                   "wav": wav, "phrases": [{"s": 0, "e": e - s, "final": final, "question": False, "last_word": ""}]}
            det = detect_phrases(rec, lambda r, ph: reliable)[0]
        else:
            det = detect_accent(times, st, [(x.start, x.end) for x in ps], special, final, reliable)
        if det.accent is not None and det.prob_of(p.merge_accents) >= CORRECT_P:
            for j in (i, i + 1):
                out[j].update(status="correct", unclear_reason=None, observed=None, observed_notation=None,
                              said_as_one=True)


def _model_detections(wav, text, phrases, spans, times, f0):
    """Run the learned utterance model (accent/model.py) over all phrases."""
    from .accent.model import detect_phrases
    from .audio.pitch import energy_db

    rec = {"moras": [], "special": [], "phrases": [], "spans": [(s.start, s.end) for s in spans],
           "scores": [s.score for s in spans], "times": times, "f0": f0,
           "energy": energy_db(wav, times), "wav": wav}
    index = []  # phrase → its record phrase (None for phrases without moras)
    for p in phrases:
        if not p.moras:
            index.append(None)
            continue
        s = len(rec["moras"])
        rec["moras"] += p.moras
        rec["special"] += _special(p)
        final = p.end >= len(text) or text[p.end] in SENTENCE_BREAKS
        index.append(len(rec["phrases"]))
        rec["phrases"].append({"s": s, "e": len(rec["moras"]), "final": final, "_phrase": p,
                               "question": any(c in QUESTION for c in text[p.end:p.end + 2]),
                               "last_word": p.words[-1].surface if p.words else ""})

    def reliable(r, ph):
        return _reliable(ph["_phrase"], spans[ph["s"]:ph["e"]], text, ph["final"])

    dets = detect_phrases(rec, reliable)
    from .accent.detect import Detection
    return [dets[j] if j is not None else Detection(None, 0.0) for j in index]
