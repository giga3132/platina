"""Add another pitch tracker's track to a cache (fields f0_<method>,
times_<method>), so trackers can be compared on the same alignments.

Usage (from backend/):
  ../.venv/bin/python -m tools.add_f0 CACHE.pkl fcpe
Then train/evaluate with --f0 fcpe.
"""

from __future__ import annotations

import argparse
import pickle
from pathlib import Path

import numpy as np

from app.audio.pitch import f0_track, load_audio


def use_f0(recs: list[dict], method: str) -> None:
    """Make `method`'s track the one detectors read."""
    if method == "praat":
        return
    for r in recs:
        if f"f0_{method}" in r:
            new_t = r[f"times_{method}"]
            if "energy" in r and len(r["energy"]) != len(new_t):  # other frame grid
                r["energy"] = np.interp(new_t, r["times"], r["energy"]).astype(np.float32)
            r["f0"], r["times"] = r[f"f0_{method}"], new_t
            r.pop("_st", None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cache", type=Path)
    ap.add_argument("method")
    ap.add_argument("--out", type=Path, help="write here instead of overwriting the cache")
    args = ap.parse_args()
    recs = pickle.loads(args.cache.read_bytes())
    for i, r in enumerate(recs):
        if f"f0_{args.method}" in r or "#" in r["utt"]:
            continue
        t, f = f0_track(load_audio(r["path"]), method=args.method)
        r[f"f0_{args.method}"], r[f"times_{args.method}"] = f.astype(np.float32), t.astype(np.float32)
        if i % 1000 == 0:
            print(i, len(recs), flush=True)
    (args.out or args.cache).write_bytes(pickle.dumps(recs))


if __name__ == "__main__":
    main()
