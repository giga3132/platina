"""Align and pitch-track a corpus once, so detectors can be trained and
evaluated without re-running the speech models.

One record per utterance (accent phrases need their neighbours as context):

  src, spk, split, utt, path, text
  moras, special            per mora (special = syllable tail, kana.special_moras)
  phrases                   [{s, e, labels, kind, conf, final, question, last_word}]
                            moras s..e-1; labels = acceptable accents;
                            kind "exact" (jsut-label) or "engine" (Platina's
                            expected accent, possibly not what was said)
  spans, scores             per mora, from our CTC aligner (as at runtime)
  times, f0, energy         10 ms frames; f0 in Hz, NaN = unvoiced; energy dB

Usage (from backend/):
  ../.venv/bin/python -m tools.build_cache jsut WAV_DIR LABEL_DIR OUT.pkl
  ../.venv/bin/python -m tools.build_cache jvs JVS16K_DIR LABEL_DIR OUT.pkl
  ../.venv/bin/python -m tools.build_cache user - - OUT.pkl      # your labelled recordings
"""

from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path

import numpy as np

from app.analyze import SENTENCE_BREAKS, QUESTION
from app.audio.align import align_moras
from app.audio.pitch import energy_db, f0_track, load_audio

from .jsut import read_lab, romaji_to_kana, special_romaji
from .jvs import clips as jvs_clips, split_of


def jsut_split(utt: str) -> str:
    """By sentence: the shipped detector was trained on BASIC5000_0001–2000."""
    i = int(utt.split("_")[1])
    return "test" if i > 4500 else "dev" if i > 4000 else "train"


def from_lab(lab: Path, table: dict) -> dict | None:
    """Moras and exact accents from a jsut-label file."""
    phrases = read_lab(lab)
    kana = [table.get(m) for ph in phrases for m in ph.kana]
    if None in kana or not phrases:
        return None
    special = [s for ph in phrases for s in special_romaji(ph.kana)]
    out, k = [], 0
    for ph in phrases:
        n = len(ph.moras)
        out.append({"s": k, "e": k + n, "labels": [ph.accent], "kind": "exact", "conf": "exact",
                     "final": ph.final, "question": False, "last_word": ""})
        k += n
    if out:
        out[-1]["final"] = True
    return {"moras": kana, "special": special, "phrases": out}


def from_text(text: str) -> dict | None:
    """Moras and expected accents from Platina's engine."""
    from app.accent.engine import analyze_text
    from app.analyze import _special

    phrases = [p for p in analyze_text(text) if p.moras]
    if not phrases:
        return None
    moras, special, out = [], [], []
    for p in phrases:
        s = len(moras)
        moras += p.moras
        special += _special(p)
        after = text[p.end:p.end + 2]
        out.append({"s": s, "e": len(moras), "labels": list(p.alternatives), "kind": "engine",
                    "conf": p.confidence,
                    "final": p.end >= len(text) or text[p.end] in SENTENCE_BREAKS,
                    "question": any(c in QUESTION for c in after),
                    "last_word": p.words[-1].surface if p.words else ""})
    return {"moras": moras, "special": special, "phrases": out}


def process(path: Path, rec: dict, f0_method: str | None = None) -> dict | None:
    wav = load_audio(path)
    spans = align_moras(wav, rec["moras"])
    if not spans:
        return None
    times, f0 = f0_track(wav, method=f0_method)
    rec.update(path=str(path), spans=[(s.start, s.end) for s in spans],
               scores=[s.score for s in spans], times=times.astype(np.float32),
               f0=f0.astype(np.float32), energy=energy_db(wav, times).astype(np.float32))
    return rec


def user_items():
    """Your labelled recordings (app/labels.py). Sessions split train/test:
    every third session (by date) is held out."""
    import zlib

    from app.labels import LabelStore

    store = LabelStore()
    for r in store.all():
        if r["source"] not in ("practice", "report") or r["said"] is None:
            continue
        rec = from_text(r["text"])
        if not rec:
            continue
        from app.accent.engine import analyze_text
        full = analyze_text(r["text"])
        if r["phrase_index"] >= len(full) or not full[r["phrase_index"]].moras:
            continue
        k = sum(1 for q in full[:r["phrase_index"]] if q.moras)  # index among phrases with moras
        ph = rec["phrases"][k]
        if ph["e"] - ph["s"] != len(r["moras"]):
            continue  # the engine's phrasing changed since recording
        n = ph["e"] - ph["s"]
        ph.update(labels=[r["said"] or n], kind="user", conf="user", expected=r["expected"])
        split = "test" if zlib.crc32(r["session"].encode()) % 3 == 0 else "train"
        yield store.clips / r["clip"], {"src": "user", "spk": r["speaker"], "split": split,
                                         "utt": r["id"], "text": r["text"], **rec}


def items(kind: str, data: Path, labels: Path):
    if kind == "user":
        yield from user_items()
        return
    table = romaji_to_kana()
    if kind == "jsut":
        for wav in sorted(data.glob("*.flac")):
            lab = labels / (wav.stem + ".lab")
            rec = from_lab(lab, table) if lab.exists() else None
            if rec:
                yield wav, {"src": "jsut", "spk": "jsut", "split": jsut_split(wav.stem),
                            "utt": wav.stem, "text": "", **rec}
    else:
        for c in jvs_clips(data):
            lab = labels / (c.utt + ".lab")
            rec = from_lab(lab, table) if lab.exists() else from_text(c.text)
            if rec and lab.exists():  # JSUT's speaker said it so; this speaker probably too
                for ph in rec["phrases"]:
                    ph["kind"] = ph["conf"] = "label"
            if rec:
                yield c.path, {"src": "jvs", "spk": c.speaker, "split": split_of(c.speaker),
                               "utt": f"{c.speaker}/{c.utt}", "part": c.part, "text": c.text, **rec}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["jsut", "jvs", "user"])
    ap.add_argument("data", type=Path)
    ap.add_argument("labels", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--f0", default=None, help="pitch tracker (default: PLATINA_F0 or praat); "
                    "use the one the accent model was trained with")
    args = ap.parse_args()

    done = pickle.loads(args.out.read_bytes()) if args.out.exists() else []
    seen = {r["utt"] for r in done}
    for i, (path, rec) in enumerate(items(args.kind, args.data, args.labels)):
        if rec["utt"] in seen:
            continue
        try:
            r = process(path, rec, args.f0)
        except Exception as e:  # noqa: BLE001 - keep going over a long corpus
            print("skip", rec["utt"], e, file=sys.stderr)
            continue
        if r:
            done.append(r)
        if len(done) % 500 == 0:
            args.out.write_bytes(pickle.dumps(done))
            print(len(done), flush=True)
    args.out.write_bytes(pickle.dumps(done))
    print("records:", len(done))


if __name__ == "__main__":
    main()
