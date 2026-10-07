"""Train the native contour model (app/accent/contour.py) on native phrases
with trusted accents (jsut-label exact accents; JVS phrases labelled from
jsut-label), from tools/build_cache.py caches.

Usage (from backend/):
  ../.venv/bin/python -m tools.train_contour CACHE.pkl [...] [--save]
"""

from __future__ import annotations

import argparse
import pickle
from pathlib import Path

import joblib
import numpy as np
from sklearn.neural_network import MLPRegressor

from app.accent.contour import MODEL, POINTS, mora_inputs
from app.accent.model import utterance_features


def dataset(recs):
    X, Y, W = [], [], []
    for r in recs:
        if "#" in r["utt"]:
            continue  # re-pitched copies aren't native contours
        feats, voiced = utterance_features(r)
        pitch, mask = feats[:, :POINTS], feats[:, POINTS:2 * POINTS]
        prev_drop = False
        for ph in r["phrases"]:
            s, e = ph["s"], ph["e"]
            n = e - s
            if ph["kind"] not in ("exact", "label") or n < 2 or voiced[s:e].mean() < 0.6:
                prev_drop = False
                continue
            acc = ph["labels"][0]
            acc = 0 if acc == n else acc
            m = mask[s:e]
            if m.mean() < 0.6:
                continue
            p = pitch[s:e].copy()
            p -= p[m > 0].mean()
            X.append(mora_inputs(n, acc, list(r["special"][s:e]), prev_drop, ph["final"],
                                 ph.get("question", False)))
            Y.append(p)
            W.append(m)
            prev_drop = 0 < acc < n
            if ph["final"]:
                prev_drop = False
    return np.vstack(X), np.vstack(Y), np.vstack(W)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("caches", type=Path, nargs="+")
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()
    recs = [r for p in args.caches for r in pickle.loads(p.read_bytes())]
    tr = [r for r in recs if r["split"] == "train"]
    te = [r for r in recs if r["split"] != "train"]
    Xtr, Ytr, Wtr = dataset(tr)
    Xte, Yte, Wte = dataset(te)
    # unvoiced points: train on the mora's voiced points' mean instead
    def fill(Y, W):
        Y = Y.copy()
        for k in range(len(Y)):
            if W[k].sum() and W[k].sum() < POINTS:
                Y[k][W[k] == 0] = Y[k][W[k] > 0].mean()
        return Y
    reg = MLPRegressor(hidden_layer_sizes=(64, 64), max_iter=300, early_stopping=True, random_state=0)
    reg.fit(Xtr, fill(Ytr, Wtr))
    pred = reg.predict(Xte)
    err = np.sqrt(np.sum(((pred - Yte) ** 2) * Wte) / Wte.sum())
    base = np.sqrt(np.sum((Yte ** 2) * Wte) / Wte.sum())
    print(f"{len(Xtr)} train / {len(Xte)} held-out moras; RMSE {err:.3f} range units "
          f"(predicting the phrase mean: {base:.3f})")
    if args.save:
        joblib.dump(reg, MODEL)
        print("saved", MODEL)


if __name__ == "__main__":
    main()
