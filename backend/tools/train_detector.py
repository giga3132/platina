"""Train the accent detector's boundary model on JSUT and report how it does
on held-out sentences.

Usage (from backend/):
  ../.venv/bin/python -m tools.train_detector WAV_DIR LABEL_DIR [--n 2000] [--save]

Every JSUT phrase is spoken correctly, so on held-out data:
  false alarm = the correct (labelled) accent would be flagged as a mistake
  catch rate  = pretending the expected accent were each *other* accent,
                how often the phrase would be flagged
--save trains on all sentences and writes app/accent/detector_model.joblib.
"""

from __future__ import annotations

import argparse
import pickle
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

from app.accent.detect import MODEL, posterior
from app.accent.features import boundary_features, mora_levels, possible
from app.audio.pitch import f0_track, load_audio, semitones

from .jsut import read_lab, romaji_to_kana, special_romaji

# A phrase is flagged as wrong when P(expected) < ERROR_P_* (see analyze.py).
THRESHOLDS = {"flat": [0.1, 0.2, 0.3, 0.4], "drop": [0.01, 0.02, 0.05, 0.1]}


def _aligned_spans(wav, lab_phrases, table):
    """Re-time the labelled moras with our own CTC aligner, as at runtime.
    None for phrases whose alignment would be rejected at runtime."""
    from app.analyze import MIN_ALIGN_SCORE
    from app.audio.align import align_moras

    kana = [table.get(m) for ph in lab_phrases for m in ph.kana]
    if None in kana:
        return [None] * len(lab_phrases)
    spans = align_moras(wav, kana) or []
    out, k = [], 0
    for ph in lab_phrases:
        ps = spans[k:k + len(ph.moras)]
        k += len(ph.moras)
        ok = len(ps) == len(ph.moras) and min(s.score for s in ps) > MIN_ALIGN_SCORE
        out.append([(s.start, s.end) for s in ps] if ok else None)
    return out


def load(wav_dir: Path, label_dir: Path, n: int, cache: Path | None, timing: str):
    if cache and cache.exists():
        return pickle.loads(cache.read_bytes())
    labs = [p for p in sorted(label_dir.glob("*.lab"))
            if (wav_dir / (p.stem + ".wav")).exists()][:n]
    table = romaji_to_kana()
    phrases = []  # (sentence index, accent, n, special, levels, voiced, final)
    for k, lab in enumerate(labs):
        wav = load_audio(wav_dir / (lab.stem + ".wav"))
        times, f0 = f0_track(wav)
        st = semitones(f0)
        lab_phrases = read_lab(lab)
        spans = (_aligned_spans(wav, lab_phrases, table) if timing == "aligner"
                 else [ph.moras for ph in lab_phrases])
        for ph, sp_times in zip(lab_phrases, spans):
            if len(ph.moras) < 2 or sp_times is None:
                continue
            sp = special_romaji(ph.kana)
            levels, voiced = mora_levels(times, st, sp_times)
            phrases.append((k, ph.accent, len(ph.moras), sp, levels, voiced, ph.final))
    if cache:
        cache.write_bytes(pickle.dumps(phrases))
    return phrases


def dataset(phrases):
    X, y = [], []
    for _, acc, n, sp, levels, voiced, final in phrases:
        ok = possible(n, sp)
        if 0 < acc < n and not ok[acc - 1]:
            continue  # label disagrees with our syllable heuristic
        f = boundary_features(levels, voiced, sp, final)[ok]
        X.append(f)
        y.append((np.arange(1, n)[ok] == acc).astype(int))
    return np.vstack(X), np.concatenate(y)


def fit(X, y):
    return HistGradientBoostingClassifier(
        learning_rate=0.1, max_iter=300, max_leaf_nodes=15, l2_regularization=1.0,
        random_state=0).fit(X, y)


def evaluate(phrases, clf):
    """Top-1 accuracy, and false alarms vs catch rate per threshold, split
    by whether the expected accent is flat (heiban / odaka at phrase end) or
    has a drop, as analyze.py does."""
    hits = total = 0
    probs = {"flat": ([], []), "drop": ([], [])}  # (P when expected is right, P when wrong)
    for _, acc, n, sp, levels, voiced, final in phrases:
        ok = possible(n, sp)
        if 0 < acc < n and not ok[acc - 1]:
            continue
        p = clf.predict_proba(boundary_features(levels, voiced, sp, final))[:, 1]
        classes, post = posterior(p, ok, n)
        true_cls = next(i for i, c in enumerate(classes) if acc in c)
        total += 1
        hits += int(np.argmax(post)) == true_cls
        for j, cls in enumerate(classes):
            probs["flat" if 0 in cls else "drop"][j != true_cls].append(post[j])
    print(f"held-out phrases: {total}, top-1 accuracy: {hits / total:.1%}")
    for kind, (right, wrong) in probs.items():
        right, wrong = np.array(right), np.array(wrong)
        print(f"  expected {kind}: flag when P(expected) <   false alarm   catch rate")
        for th in THRESHOLDS[kind]:
            print(f"  {th:>38}   {np.mean(right < th):9.1%}   {np.mean(wrong < th):9.1%}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("wav_dir", type=Path)
    ap.add_argument("label_dir", type=Path)
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--cache", type=Path)
    ap.add_argument("--timing", choices=["aligner", "label"], default="aligner",
                    help="mora timings from our CTC aligner (as at runtime) or the labels")
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()

    phrases = load(args.wav_dir, args.label_dir, args.n, args.cache, args.timing)
    n_sent = phrases[-1][0] + 1
    split = int(n_sent * 0.8)
    train = [p for p in phrases if p[0] < split]
    test = [p for p in phrases if p[0] >= split]
    print(f"{n_sent} sentences: {len(train)} train phrases, {len(test)} test phrases")

    evaluate(test, fit(*dataset(train)))

    if args.save:
        joblib.dump(fit(*dataset(phrases)), MODEL)  # final model on everything
        print("saved", MODEL)


if __name__ == "__main__":
    main()
