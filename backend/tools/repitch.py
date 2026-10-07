"""Re-pitched training data: native recordings given a new accent.

Praat's PSOLA replaces the pitch of an utterance with one built from the
H/L pattern of a chosen accent for every phrase, in the speaker's own pitch
range, keeping timing, voice and micro-prosody (the original's small pitch
wiggles around its mora levels). Because the pattern is imposed, its label
is exact. One or two phrases per utterance get a learner-like mistake (flat
for accented, accented for flat, 1 or 2 moras off); an "identity" copy
re-imposes the original's own measured levels, so resynthesis artifacts
can't tell the model which copy is which.

Each output is re-tracked; a phrase whose measured pitch misses the imposed
pattern is dropped from the labels (kind "repitch" only where it landed).

Usage (from backend/):
  ../.venv/bin/python -m tools.repitch CACHE.pkl --out OUT.pkl [--split train] [--max 4000] [--jobs 8]
      [--wav-dir DIR]
"""

from __future__ import annotations

import argparse
import pickle
import random
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from app.accent.features import possible
from app.accent.notation import pitch_pattern

# shape parameters, sampled per utterance (semitones / seconds)
STEP = (2.5, 6.0)  # high vs low
INITIAL = (0.4, 0.8)  # depth of the phrase-initial low, as a share of STEP
DOWNSTEP = (0.5, 2.0)  # lowering after a phrase with a drop
DECLINATION = (0.0, 1.0)  # lowering per phrase
DELAY = (0.0, 0.35)  # the step lands this share into the next mora (peak delay)
SMOOTH_S = 0.05
# local: only the mistake phrases are re-pitched, the rest keeps its natural
# pitch; global: every phrase gets a synthetic contour (too clean: models
# learn the synthetic style instead of the accent)
MODE = "local"
WAV_DIR: Path | None = None  # --wav-dir: keep the re-pitched audio (for speech-model features)


def _mora_medians(times, st, spans):
    out = []
    for s, e in spans:
        v = st[(times >= s) & (times < e)]
        v = v[~np.isnan(v)]
        out.append(float(np.median(v)) if len(v) else np.nan)
    return np.array(out)


def mistake(n: int, special: list[bool], said: int, rng: random.Random) -> int | None:
    """A learner-like wrong accent for a phrase whose right accent is `said`."""
    ok = possible(n, special)
    accented = [a for a in range(1, n) if ok[a - 1]]
    flat = said in (0, n)
    kinds = []
    if not flat:
        kinds.append(0)  # said flat
        kinds += [a for a in accented if abs(a - said) == 1]
        kinds += [a for a in accented if abs(a - said) >= 2]
    else:
        kinds += accented  # added a drop
    return rng.choice(kinds) if kinds else None


def local_levels(rec, accents, wrong, measured, rng):
    """The speaker's own measured pitch everywhere, except the phrases in
    `wrong`, which get the new accent's H/L pattern built from that phrase's
    own high and low levels (with natural per-mora jitter)."""
    levels = measured.copy()
    voiced = measured[~np.isnan(measured)]
    if len(voiced) < 4:
        return None
    spread = float(np.clip(np.percentile(voiced, 85) - np.percentile(voiced, 15), 1.5, 8.0))
    for k in wrong:
        ph, acc = rec["phrases"][k], accents[k]
        n = ph["e"] - ph["s"]
        seg = measured[ph["s"]:ph["e"]]
        hi = np.nanmax(seg) if not np.all(np.isnan(seg)) else np.nanmedian(voiced)
        step = rng.uniform(0.6, 1.1) * spread
        init = rng.uniform(*INITIAL) * step
        pat = pitch_pattern(n, acc)
        for i in range(n):
            lv = hi if pat[i] else hi - step
            if i == 0 and not pat[0]:
                lv = hi - init
            levels[ph["s"] + i] = lv + rng.gauss(0, 0.3)
    return np.where(np.isnan(levels), 0.0, levels)


def target_levels(rec, accents, rng, measured=None):
    """Per-mora target pitch (semitones vs the utterance median)."""
    step = rng.uniform(*STEP)
    init = rng.uniform(*INITIAL) * step
    down, decl = rng.uniform(*DOWNSTEP), rng.uniform(*DECLINATION)
    top = step / 2
    levels = np.zeros(len(rec["moras"]))
    for ph, acc in zip(rec["phrases"], accents):
        n = ph["e"] - ph["s"]
        pat = pitch_pattern(n, acc)
        for i in range(n):
            lv = top if pat[i] else top - step
            if i == 0 and not pat[0]:
                lv = top - init
            levels[ph["s"] + i] = lv
        top -= decl + (down if 0 < acc < n else 0)
        if ph["final"]:
            top = step / 2
    if measured is not None:  # identity copy: the speaker's own levels
        levels = np.where(np.isnan(measured), levels, measured)
    return levels


def contour(rec, levels, times, st, rng):
    """Frame-level target pitch: levels stepped at mora boundaries (late by
    a sampled delay), smoothed, plus the original's micro-prosody."""
    spans = rec["spans"]
    delay = rng.uniform(*DELAY)
    idx = np.zeros(len(times), dtype=int)
    for i, (s, e) in enumerate(spans):
        idx[times >= s + delay * (e - s)] = i
    target = levels[idx]
    k = max(1, int(SMOOTH_S / 0.01))
    target = np.convolve(np.pad(target, k, mode="edge"), np.ones(2 * k + 1) / (2 * k + 1), "same")[k:-k]
    orig_lv = _mora_medians(times, st, spans)
    resid = st - np.nan_to_num(orig_lv[idx], nan=0.0)
    resid = np.clip(np.nan_to_num(resid), -1.5, 1.5)
    return target + resid


def resynth(path, times, f0_hz, ok):
    import parselmouth
    from parselmouth.praat import call

    from app.audio.pitch import load_audio

    wav = load_audio(path)
    snd = parselmouth.Sound(wav.astype(np.float64), sampling_frequency=16000)
    manip = call(snd, "To Manipulation", 0.01, 60, 500)
    tier = call("Create PitchTier", "target", 0, snd.duration)
    for t, hz in zip(times[ok], f0_hz[ok]):
        call(tier, "Add point", float(t), float(hz))
    call([tier, manip], "Replace pitch tier")
    out = call(manip, "Get resynthesis (overlap-add)")
    return out.values[0].astype(np.float32)


def landed(rec, levels, times, st_new, accents) -> list[bool]:
    """Did the imposed pattern come out? Per phrase: adjacent moras whose
    targets differ by ≥ 1.5 st must move the same way by ≥ 1 st."""
    meas = _mora_medians(times, st_new, rec["spans"])
    out = []
    for ph in rec["phrases"]:
        good = total = 0
        for i in range(ph["s"], ph["e"] - 1):
            d_t = levels[i + 1] - levels[i]
            if abs(d_t) < 1.5 or np.isnan(meas[i]) or np.isnan(meas[i + 1]):
                continue
            total += 1
            good += np.sign(meas[i + 1] - meas[i]) == np.sign(d_t) and abs(meas[i + 1] - meas[i]) >= 1.0
        out.append(total == 0 or good / total >= 0.8)
    return out


def make(args):
    rec, seed, identity = args
    from app.audio.pitch import energy_db, f0_track

    rng = random.Random(seed)
    times = np.asarray(rec["times"], dtype=np.float64)
    f0 = np.asarray(rec["f0"], dtype=np.float64)
    ok = ~np.isnan(f0) & (f0 > 0)
    if ok.sum() < 20:
        return None
    ref = np.median(f0[ok])
    st = 12 * np.log2(np.where(ok, f0, np.nan) / ref)

    accents, changed = [], []
    candidates = [k for k, ph in enumerate(rec["phrases"]) if ph["e"] - ph["s"] >= 2]
    wrong = set(rng.sample(candidates, min(len(candidates), rng.choice([1, 1, 2])))) if not identity else set()
    for k, ph in enumerate(rec["phrases"]):
        n = ph["e"] - ph["s"]
        said = ph["labels"][0]
        said = 0 if said == n else said
        acc = said
        if k in wrong:
            m = mistake(n, rec["special"][ph["s"]:ph["e"]], said, rng)
            if m is not None:
                acc = m
        accents.append(acc)
        changed.append(acc != said)
    measured = _mora_medians(times, st, rec["spans"])
    if MODE == "local":
        levels = local_levels(rec, accents, [] if identity else
                              [k for k, c in enumerate(changed) if c], measured, rng)
        if levels is None:
            return None
    else:
        levels = target_levels(rec, accents, rng, measured if identity else None)
    tgt = contour(rec, levels, times, st, rng)
    new_wav = resynth(rec["path"], times, ref * 2 ** (tgt / 12), ok)
    t2, f2 = f0_track(new_wav)
    ok2 = ~np.isnan(f2)
    if ok2.sum() < 20:
        return None
    st2 = 12 * np.log2(f2 / np.median(f2[ok2]))
    hit = landed(rec, levels - np.nanmedian(levels), t2, st2, accents) if not identity else [True] * len(accents)

    out = {k: v for k, v in rec.items() if k not in ("times", "f0", "energy", "_st")}
    out.update(src=rec["src"] + "-repitch", utt=rec["utt"] + ("#id" if identity else f"#{seed}"),
               times=t2.astype(np.float32), f0=f2.astype(np.float32),
               energy=energy_db(new_wav, t2).astype(np.float32))
    phrases = []
    for ph, acc, h, ch in zip(rec["phrases"], accents, hit, changed):
        ph = dict(ph)
        n = ph["e"] - ph["s"]
        if identity or (MODE == "local" and not ch):
            pass  # natural pitch kept: the original label (trusted or not)
        elif h:
            ph.update(labels=[acc if acc else n], kind="repitch", conf="repitch")
        else:
            ph.update(kind="dropped", conf="dropped")
        ph["mistake"] = ch
        phrases.append(ph)
    out["phrases"] = phrases
    if WAV_DIR is not None:
        import soundfile as sf

        path = WAV_DIR / (out["utt"].replace("/", "_").replace("#", "_") + ".flac")
        sf.write(path, new_wav, 16000)
        out["path"] = str(path)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cache", type=Path, nargs="+")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--split", default="train")
    ap.add_argument("--max", type=int, default=4000)
    ap.add_argument("--identity", type=float, default=0.5, help="share of utterances also copied as-is")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--mode", choices=["local", "global"], default="local")
    ap.add_argument("--wav-dir", type=Path, help="also save the re-pitched audio here")
    args = ap.parse_args()
    global MODE, WAV_DIR
    MODE = args.mode
    if args.wav_dir:
        args.wav_dir.mkdir(parents=True, exist_ok=True)
        WAV_DIR = args.wav_dir
    rng = random.Random(args.seed)
    recs = [r for p in args.cache for r in pickle.loads(p.read_bytes()) if r["split"] == args.split]
    # only utterances whose original accents are trusted: the pattern
    # imposed on the other phrases is the original label
    recs = [r for r in recs if all(ph["kind"] in ("exact", "label") or ph["conf"] in ("agree", "nhk")
                                   for ph in r["phrases"])]
    rng.shuffle(recs)
    recs = recs[:args.max]
    jobs = [(r, rng.randrange(1 << 30), False) for r in recs]
    jobs += [(r, rng.randrange(1 << 30), True) for r in recs if rng.random() < args.identity]
    out = []
    with ProcessPoolExecutor(args.jobs) as ex:
        for i, r in enumerate(ex.map(make, jobs, chunksize=8)):
            if r:
                out.append(r)
            if i % 500 == 0:
                print(i, len(jobs), flush=True)
    args.out.write_bytes(pickle.dumps(out))
    n_ph = sum(ph["kind"] == "repitch" for r in out for ph in r["phrases"])
    n_mis = sum(ph["kind"] == "repitch" and ph["mistake"] for r in out for ph in r["phrases"])
    n_drop = sum(ph["kind"] == "dropped" for r in out for ph in r["phrases"])
    print(f"{len(out)} utterances; {n_ph} re-pitched phrases ({n_mis} mistakes), {n_drop} dropped")


if __name__ == "__main__":
    main()
