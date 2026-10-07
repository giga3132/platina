"""Find accents natives actually use that the dictionaries don't list.

Runs the learned detector over native corpus recordings (JVS parallel100:
100 speakers reading the same sentences; nonpara30; ...). Where at least
MIN_SPEAKERS speakers and MIN_SHARE of the speakers heard clearly use an
accent the engine doesn't accept, it is stored as a *proposed* variant
(app/accent/variants.py): a learner using it is never told it's a mistake,
and the user can approve (accepted like a dictionary alternative) or reject
it. Phrases where most natives disagree with the dictionary are printed:
check those words in NHK.

Usage (from backend/):
  ../.venv/bin/python -m tools.mine_variants CACHE.pkl [...] [--f0 praat]
"""

from __future__ import annotations

import argparse
import pickle
from collections import defaultdict
from pathlib import Path

from app.accent.engine import analyze_text
from app.accent.notation import phrase_notation
from app.accent.variants import VariantStore, phrase_key

from .add_f0 import use_f0
from .evaluate import new_detector, reliable_moras

MIN_SPEAKERS = 3
MIN_SHARE = 0.25
SURE = 0.9


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("caches", type=Path, nargs="+")
    ap.add_argument("--f0", default="praat")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    detect = new_detector()
    heard = defaultdict(lambda: defaultdict(set))  # key → accent → speakers
    total = defaultdict(set)
    meta = {}
    texts: dict[str, list] = {}
    for path in args.caches:
        recs = [r for r in pickle.loads(path.read_bytes()) if "#" not in r["utt"] and r["text"]]
        use_f0(recs, args.f0)
        for rec in recs:
            if not all(ph["kind"] == "engine" for ph in rec["phrases"]):
                continue
            if rec["text"] not in texts:
                texts[rec["text"]] = [p for p in analyze_text(rec["text"]) if p.moras]
            eng = texts[rec["text"]]
            if len(eng) != len(rec["phrases"]):
                continue
            for p, ph in zip(eng, rec["phrases"]):
                n = len(p.moras)
                if n < 2:
                    continue
                det = detect(rec, ph, reliable_moras(rec, ph))
                if det.accent is None or det.confidence < SURE:
                    continue
                key = phrase_key([w.lemma for w in p.words], p.moras)
                meta[key] = (p.moras, p.alternatives, p.text)
                total[key].add(rec["spk"])
                cls = det.candidates
                if not set(cls) & set(p.alternatives) and not ({0, n} & set(cls) and {0, n} & set(p.alternatives)):
                    heard[key][cls[0] if cls[0] != n else 0].add(rec["spk"])
    store = None if args.dry_run else VariantStore()
    proposed = 0
    for key, by_acc in sorted(heard.items()):
        moras, alts, text = meta[key]
        for acc, spk in by_acc.items():
            share = len(spk) / len(total[key])
            if len(spk) >= MIN_SPEAKERS and share >= MIN_SHARE:
                proposed += 1
                mark = "  ← most natives: check in NHK" if share > 0.5 else ""
                print(f"{text}  dictionary {phrase_notation(moras, alts[0])}  natives "
                      f"{phrase_notation(moras, acc)}  {len(spk)}/{len(total[key])} speakers{mark}")
                if store:
                    store.propose(key, acc, len(spk), len(total[key]), sorted(spk))
    print(f"{proposed} variants proposed from {len(total)} phrases")


if __name__ == "__main__":
    main()
