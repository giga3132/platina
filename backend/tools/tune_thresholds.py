"""Choose the verdict thresholds (analyze.py: ERROR_P_FLAT, ERROR_P_ACCENTED,
HEARD_P) for a detector: the setting that catches the most (pretend) mistakes
while false alarms on correctly said phrases stay under --max-fa, on dev data
with trusted labels.

Usage (from backend/):
  PLATINA_ACCENT_MODEL=... ../.venv/bin/python -m tools.tune_thresholds CACHE.pkl [...] \\
      [--detector new] [--max-fa 0.02]
"""

from __future__ import annotations

import argparse
import itertools
import pickle
from pathlib import Path

import numpy as np

from app.accent.features import possible
from app.accent.notation import pitch_pattern
from app.analyze import CORRECT_P

from .add_f0 import use_f0
from .ssl_feats import attach
from .evaluate import new_detector, old_detector, phrases, reliable_moras


def decision_inputs(det, alternatives, n, rel):
    """(p_expected, expected is flat, p of the most likely other class,
    deciding moras well aligned) — everything analyze._status looks at."""
    if det.accent is None:
        return None
    p_exp = det.prob_of(alternatives)
    flat = any(a in (0, n) for a in alternatives)
    heard, p_heard = [], 0.0
    for cls, p in zip(det.classes, det.posterior):
        if not set(cls) & set(alternatives) and p > p_heard:
            heard, p_heard = cls, p
    ok = True
    if heard:
        e, h = pitch_pattern(n, alternatives[0]), pitch_pattern(n, heard[0])
        deciding = {j for i in range(n) if e[i] != h[i] for j in (i - 1, i, i + 1) if 0 <= j < n}
        ok = all(rel[i] for i in deciding)
    return p_exp, flat, p_heard, ok


def collect(recs, detect, kinds):
    right, wrong = [], []  # decision inputs for correct speech / pretend mistakes
    for rec, ph in phrases(recs, kinds):
        n = ph["e"] - ph["s"]
        rel = reliable_moras(rec, ph)
        det = detect(rec, ph, rel)
        labels = sorted({0 if a == n else a for a in ph["labels"]})
        right.append(decision_inputs(det, labels, n, rel))
        ok = possible(n, rec["special"][ph["s"]:ph["e"]])
        for e in [0] + [a for a in range(1, n) if ok[a - 1]]:
            if e not in labels:
                wrong.append(decision_inputs(det, [e], n, rel))
    return right, wrong


def flags(items, err_flat, err_acc, heard_p):
    out = []
    for it in items:
        if it is None:
            out.append(False)
            continue
        p_exp, flat, p_heard, ok = it
        out.append(p_exp < CORRECT_P and p_exp < (err_flat if flat else err_acc)
                   and p_heard >= heard_p and ok)
    return np.array(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("caches", type=Path, nargs="+")
    ap.add_argument("--split", default="dev")
    ap.add_argument("--detector", choices=["old", "new"], default="new")
    ap.add_argument("--kinds", default="exact,label")
    ap.add_argument("--max-fa", type=float, default=0.02)
    ap.add_argument("--f0", default="praat")
    args = ap.parse_args()
    detect = old_detector() if args.detector == "old" else new_detector()
    recs = []
    for p in args.caches:
        part = [r for r in pickle.loads(p.read_bytes()) if r["split"] == args.split]
        attach(part, p)
        recs += part
    use_f0(recs, args.f0)
    right, wrong = collect(recs, detect, set(args.kinds.split(",")))
    print(f"{len(right)} correctly said phrases, {len(wrong)} pretend mistakes")
    grid = itertools.product([0.05, 0.1, 0.2, 0.3, 0.4, 0.5], [0.01, 0.02, 0.05, 0.1, 0.2, 0.3],
                             [0.3, 0.4, 0.5, 0.6, 0.7])
    rows = []
    for ef, ea, hp in grid:
        fa = flags(right, ef, ea, hp).mean()
        caught = flags(wrong, ef, ea, hp).mean()
        rows.append((fa, caught, ef, ea, hp))
    ok = [r for r in rows if r[0] <= args.max_fa]
    print("best within the false-alarm budget:")
    for fa, caught, ef, ea, hp in sorted(ok, key=lambda r: -r[1])[:8]:
        print(f"  ERROR_P_FLAT={ef} ERROR_P_ACCENTED={ea} HEARD_P={hp}:  false alarms {fa:.3f}  caught {caught:.3f}")


if __name__ == "__main__":
    main()
