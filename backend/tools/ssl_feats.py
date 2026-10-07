"""Per-mora HuBERT features (app/audio/ssl.py) for cached utterances.

  fit      fits the per-layer PCA basis on a sample of training utterances
  extract  writes CACHE.ssl.pkl next to each cache: {utt: [n_moras, dims] float16}

Usage (from backend/):
  ../.venv/bin/python -m tools.ssl_feats fit CACHE.pkl [...] --pca PCA.npz [--k 96]
  ../.venv/bin/python -m tools.ssl_feats extract CACHE.pkl [...] --pca PCA.npz
Then train with tools/train_accent.py --ssl PCA.npz.
"""

from __future__ import annotations

import argparse
import pickle
import random
from pathlib import Path

import numpy as np

from app.audio.pitch import load_audio
from app.audio.ssl import layer_frames, pool, project


def ssl_path(cache: Path) -> Path:
    return cache.with_suffix(".ssl.pkl")


def attach(recs: list[dict], cache: Path) -> None:
    """Put each utterance's precomputed features (if any) in rec["ssl"]."""
    if ssl_path(cache).exists():
        feats = pickle.loads(ssl_path(cache).read_bytes())
        for r in recs:
            if r["utt"] in feats:
                r["ssl"] = feats[r["utt"]]


def load_pca(path: Path) -> dict:
    with np.load(path) as z:
        return {k: z[k] for k in z.files}


def fit(caches, out: Path, k: int, n_utts: int):
    recs = [r for p in caches for r in pickle.loads(p.read_bytes()) if r["split"] == "train"]
    random.Random(0).shuffle(recs)
    rows = []
    for i, r in enumerate(recs[:n_utts]):
        rows.append(pool(layer_frames(load_audio(r["path"])), r["spans"]))
        if i % 200 == 0:
            print("fit", i, flush=True)
    X = np.concatenate(rows)  # [N, L, D]
    mean = X.mean(axis=0)
    comps, scales = [], []
    for li in range(X.shape[1]):
        xc = X[:, li] - mean[li]
        _, _, vt = np.linalg.svd(xc[::max(1, len(xc) // 40000)], full_matrices=False)
        c = vt[:k].T  # [D, k]
        comps.append(c)
        scales.append((xc @ c).std())
    pca = {"mean": mean.astype(np.float32), "comp": np.stack(comps).astype(np.float32),
           "scale": np.array(scales, dtype=np.float32)[:, None]}
    np.savez(out, **pca)
    print(f"PCA from {len(X)} moras saved to {out}")


def extract(caches, pca_path: Path):
    pca = load_pca(pca_path)
    for p in caches:
        out_path = ssl_path(p)
        feats = pickle.loads(out_path.read_bytes()) if out_path.exists() else {}
        recs = pickle.loads(p.read_bytes())
        for i, r in enumerate(recs):
            if r["utt"] in feats:
                continue
            try:
                f = project(pool(layer_frames(load_audio(r["path"])), r["spans"]), pca)
            except Exception as e:  # noqa: BLE001 - e.g. GPU memory taken by the app; rerun resumes
                print("skip", r["utt"], e, flush=True)
                continue
            feats[r["utt"]] = f.astype(np.float16)
            if i % 1000 == 0:
                print(p.name, i, len(recs), flush=True)
        out_path.write_bytes(pickle.dumps(feats))
        print(f"{out_path}: {len(feats)} of {len(recs)} utterances")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["fit", "extract"])
    ap.add_argument("caches", type=Path, nargs="+")
    ap.add_argument("--pca", type=Path, required=True)
    ap.add_argument("--k", type=int, default=96, help="PCA dimensions per layer")
    ap.add_argument("--utts", type=int, default=1500, help="utterances to fit the PCA on")
    args = ap.parse_args()
    if args.action == "fit":
        fit(args.caches, args.pca, args.k, args.utts)
    else:
        extract(args.caches, args.pca)


if __name__ == "__main__":
    main()
