"""Build the "Review native recordings" queue (Practice tab): held-out
corpus phrases that the current detector + verdict would flag as a mistake,
although a native said them. Your answers (native variant / Platina
misheard / dictionary wrong) split false alarms by cause.

Usage (from backend/):
  ../.venv/bin/python -m tools.review_queue CACHE.pkl [...] [--split dev] [--max 150]
"""

from __future__ import annotations

import argparse
import json
import pickle
import random
from pathlib import Path
from types import SimpleNamespace

from app.accent.notation import phrase_notation
from app.analyze import _status
from app.main import REVIEW

from .add_f0 import use_f0
from .evaluate import new_detector, old_detector, phrases, reliable_moras


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("caches", type=Path, nargs="+")
    ap.add_argument("--split", default="dev")
    ap.add_argument("--max", type=int, default=150)
    ap.add_argument("--detector", choices=["old", "new"], default="new")
    ap.add_argument("--f0", default="praat")
    args = ap.parse_args()
    detect = old_detector() if args.detector == "old" else new_detector()
    if args.detector == "old":
        import app.analyze as analyze
        analyze._thresholds = lambda: (analyze.ERROR_P_FLAT, analyze.ERROR_P_ACCENTED, analyze.HEARD_P)
    recs = [r for p in args.caches for r in pickle.loads(p.read_bytes())
            if r["split"] == args.split and "#" not in r["utt"]]
    use_f0(recs, args.f0)
    items = []
    for rec, ph in phrases(recs, {"exact", "label", "agree", "nhk"}):
        n = ph["e"] - ph["s"]
        rel = reliable_moras(rec, ph)
        det = detect(rec, ph, rel)
        labels = sorted({0 if a == n else a for a in ph["labels"]})
        truth = SimpleNamespace(alternatives=labels, moras=[""] * n, accent=labels[0], confidence="agree")
        status, _, _ = _status(truth, det, rel)
        if status != "error":
            continue
        moras = rec["moras"][ph["s"]:ph["e"]]
        items.append({"id": f"{rec['utt']}:{rec['phrases'].index(ph)}", "path": rec["path"],
                      "text": rec["text"] or "".join(rec["moras"]), "spk": rec["spk"],
                      "phrase": rec["phrases"].index(ph), "moras": moras, "expected": labels,
                      "heard": det.accent, "heard_notation": phrase_notation(moras, det.accent),
                      "start": rec["spans"][ph["s"]][0], "end": rec["spans"][ph["e"] - 1][1]})
    random.Random(0).shuffle(items)
    REVIEW.write_text(json.dumps(items[:args.max], ensure_ascii=False, indent=1))
    print(f"{len(items)} flagged native phrases; wrote {min(len(items), args.max)} to {REVIEW}")


if __name__ == "__main__":
    main()
