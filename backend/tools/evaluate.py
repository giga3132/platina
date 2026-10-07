"""Evaluate an accent detector + Platina's verdict rule on cached corpora
(tools/build_cache.py), per held-out speaker set.

Every corpus phrase was said by a native, so with its label as the expected
accent:
  false alarm  the phrase is judged a mistake (error/unverified)
  unclear      the phrase is judged "uncertain"
and pretending the dictionary expected each *other* accent simulates a
learner mistake:
  caught       that pretend mistake is judged an error
broken down by kind: flat for accented, accented for flat, 1 mora off, 2+ off.

Usage (from backend/):
  ../.venv/bin/python -m tools.evaluate CACHE.pkl [CACHE2.pkl ...] [--split test]
      [--detector old|new] [--kinds exact,label,agree]
"""

from __future__ import annotations

import argparse
import json
import pickle
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from app.accent.features import possible
from app.analyze import FINAL_PARTICLES, MIN_ALIGN_SCORE, MIN_MORA_S, _status
from app.audio.pitch import semitones

from .add_f0 import use_f0
from .ssl_feats import attach


def reliable_moras(rec: dict, ph: dict) -> list[bool]:
    out = [rec["scores"][i] > MIN_ALIGN_SCORE and
           rec["spans"][i][1] - rec["spans"][i][0] >= MIN_MORA_S
           for i in range(ph["s"], ph["e"])]
    if out and ph["final"] and (ph["question"] or ph["last_word"] in FINAL_PARTICLES):
        out[-1] = False
    return out


def phrases(recs, kinds):
    """(record, phrase) pairs worth scoring."""
    for rec in recs:
        for ph in rec["phrases"]:
            if ph["e"] - ph["s"] < 2:
                continue
            if ph["kind"] in kinds or ph["conf"] in kinds:
                yield rec, ph


def legacy_status(p, det, rel):
    """The verdict rule before this work: P(expected) thresholds only, and
    every mora's alignment must be good."""
    from app.analyze import CORRECT_P, ERROR_P_ACCENTED, ERROR_P_FLAT
    if det.accent is None or not all(rel):
        return "uncertain", None, ""
    p_exp = det.prob_of(p.alternatives)
    flat = any(a in (0, len(p.moras)) for a in p.alternatives)
    if p_exp >= CORRECT_P:
        return "correct", p_exp, ""
    if p_exp >= (ERROR_P_FLAT if flat else ERROR_P_ACCENTED):
        return "uncertain", p_exp, ""
    return "error", p_exp, ""


def old_detector(legacy: bool = False):
    from app.accent.detect import detect_accent

    def detect(rec, ph, rel):
        if legacy:
            st = rec.get("_st")
            if st is None:
                st = rec["_st"] = semitones(rec["f0"].astype(np.float64))
            s, e = ph["s"], ph["e"]
            return detect_accent(rec["times"], st, rec["spans"][s:e], rec["special"][s:e],
                                 ph["final"], merge=False)
        st = rec.get("_st")
        if st is None:
            st = rec["_st"] = semitones(rec["f0"].astype(np.float64))
        s, e = ph["s"], ph["e"]
        if sum(rel) < 2:
            return detect_accent(rec["times"], st, [])
        return detect_accent(rec["times"], st, rec["spans"][s:e], rec["special"][s:e],
                             ph["final"], rel)
    return detect


def new_detector():
    from app.accent.model import detect_phrases
    cache: dict = {}

    def detect(rec, ph, rel):
        key = id(rec)
        if key not in cache:
            cache.clear()
            cache[key] = detect_phrases(rec)
        return cache[key][rec["phrases"].index(ph)]
    return detect


def kind_of(expected: int, said: int, n: int) -> str:
    e_flat, s_flat = expected in (0, n), said in (0, n)
    if e_flat and not s_flat:
        return "accented for flat"
    if s_flat and not e_flat:
        return "flat for accented"
    return "1 mora off" if abs(expected - said) == 1 else "2+ moras off"


def evaluate(recs, detect, kinds, status=_status) -> dict:
    n_ph = fa = unclear = top1 = 0
    real_tried = real_caught = 0  # your deliberate mistakes, judged against the dictionary
    caught, tried = defaultdict(int), defaultdict(int)
    per_spk = defaultdict(lambda: [0, 0])
    p_true = []
    for rec, ph in phrases(recs, kinds):
        n = ph["e"] - ph["s"]
        rel = reliable_moras(rec, ph)
        det = detect(rec, ph, rel)
        if "expected" in ph:
            exp = ph["expected"]
            said = ph["labels"][0]
            if not ({said, 0 if said == n else said} & set(exp) or ({0, n} & {said} and {0, n} & set(exp))):
                rel_ = reliable_moras(rec, ph)
                fake = SimpleNamespace(alternatives=exp, moras=[""] * n, accent=exp[0], confidence="agree")
                real_tried += 1
                real_caught += status(fake, detect(rec, ph, rel_), rel_)[0] == "error"
        labels = [n if a == 0 else a for a in ph["labels"]]
        labels = sorted(set(labels) | ({0} if n in labels else set()))
        moras = [""] * n
        truth = SimpleNamespace(alternatives=labels, moras=moras, accent=labels[0], confidence="agree")
        if status is legacy_status:  # old rule: whole-phrase alignment check only
            rel = [rec["scores"][i] > MIN_ALIGN_SCORE for i in range(ph["s"], ph["e"])]
        status_, p, _ = status(truth, det, rel)
        n_ph += 1
        per_spk[rec["spk"]][1] += 1
        if status_ in ("error", "unverified"):
            fa += 1
            per_spk[rec["spk"]][0] += 1
        unclear += status_ == "uncertain"
        if det.accent is not None:
            top1 += bool(set(det.candidates) & set(labels))
            p_true.append(det.prob_of(labels))
        special = rec["special"][ph["s"]:ph["e"]]
        ok = possible(n, special)
        said = labels[0] if labels[0] not in (0, n) else 0
        for e in [0] + [a for a in range(1, n) if ok[a - 1]]:
            if e in labels or (e == 0 and n in labels):
                continue
            k = kind_of(e, said, n)
            fake = SimpleNamespace(alternatives=[e], moras=moras, accent=e, confidence="agree")
            tried[k] += 1
            caught[k] += status(fake, det, rel)[0] == "error"
    rates = sorted(f / t for f, t in per_spk.values() if t >= 20)
    return {
        "phrases": n_ph,
        "false_alarm": fa / max(n_ph, 1),
        "unclear": unclear / max(n_ph, 1),
        "top1_when_decided": top1 / max(len(p_true), 1),
        "caught": sum(caught.values()) / max(sum(tried.values()), 1),
        "caught_by_kind": {k: caught[k] / tried[k] for k in sorted(tried)},
        "your_real_mistakes_caught": (real_caught / real_tried) if real_tried else None,
        "speaker_false_alarm": ({"median": float(np.median(rates)),
                                 "p90": float(np.percentile(rates, 90)),
                                 "max": float(max(rates)), "speakers": len(rates)}
                                if rates else None),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("caches", type=Path, nargs="+")
    ap.add_argument("--split", default="test")
    ap.add_argument("--detector", choices=["legacy", "old", "new"], default="old",
                    help="legacy = old model + old verdict rule; old = old model + new rule")
    ap.add_argument("--kinds", default="exact,label,agree,nhk,user")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--f0", default="praat", help="pitch track to read (tools/add_f0.py)")
    args = ap.parse_args()
    detect = (old_detector(args.detector == "legacy") if args.detector != "new" else new_detector())
    status = legacy_status if args.detector == "legacy" else _status
    if args.detector != "new":  # the old model's own thresholds, not the learned model's
        import app.analyze as analyze
        analyze._thresholds = lambda: (analyze.ERROR_P_FLAT, analyze.ERROR_P_ACCENTED, analyze.HEARD_P)
    kinds = set(args.kinds.split(","))
    report = {}
    for path in args.caches:
        recs = [r for r in pickle.loads(path.read_bytes()) if r["split"] == args.split]
        attach(recs, path)
        use_f0(recs, args.f0)
        by_src = defaultdict(list)
        for r in recs:
            by_src[r["src"] + ("/" + r["part"] if "part" in r else "")].append(r)
        for src, rs in sorted(by_src.items()):
            report[src] = evaluate(rs, detect, kinds, status)
            print(f"\n== {src} ({args.split}, {args.detector}) ==")
            print(json.dumps(report[src], indent=1, ensure_ascii=False))
    if args.out:
        args.out.write_text(json.dumps(report, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
