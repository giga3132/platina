"""Closed-loop check of the tutor voice: synthesize every gold sentence with
VOICEVOX and measure it two ways.

  pitch fidelity  Praat F0 of each mora vs. the pitch we asked VOICEVOX for
                  (VOICEVOX's own mora timings). The direct test of a voice.
  detector        run the audio back through Platina's accent detector and
                  count phrases judged correct (≈81% top-1 on native speech,
                  so misses can be the detector's; listen to the WAVs).

Usage (from backend/, with the VOICEVOX engine running):
  ../.venv/bin/python -m tools.check_tutor [--speaker 30 13 ...] [--out DIR] [--no-detector]
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import numpy as np
import yaml

from app import tutor
from app.accent.engine import analyze_text
from app.analyze import analyze_audio
from app.audio.pitch import f0_track, load_audio

GOLD = Path(__file__).resolve().parents[1] / "tests" / "gold" / "sentences.yaml"


def pitch_errors(query: dict, wav: np.ndarray) -> list[float]:
    """Rendered minus requested pitch, in semitones, per voiced mora."""
    t, f0 = f0_track(wav)
    pos, out = query["prePhonemeLength"] / query["speedScale"], []
    for ap in query["accent_phrases"]:
        for m in ap["moras"]:
            start = pos + (m["consonant_length"] or 0) / query["speedScale"]
            pos = start + m["vowel_length"] / query["speedScale"]
            sel = (t >= start) & (t < pos) & (f0 > 0)
            if m["pitch"] > 0 and sel.sum() >= 3:
                out.append(12 * np.log2(np.median(f0[sel]) / np.exp(m["pitch"])))
        if ap["pause_mora"]:
            pos += ap["pause_mora"]["vowel_length"] / query["speedScale"]
    return out


def check(speaker: int, speed: float, out: Path | None, detector: bool) -> None:
    counts: Counter[str] = Counter()
    errors: list[float] = []
    for i, e in enumerate(yaml.safe_load(GOLD.read_text())):
        text = e["text"]
        kana = tutor.to_kana(analyze_text(text), text)
        query = tutor.audio_query(kana, speed, speaker)
        wav = tutor.render(query, speaker)
        if out:
            (out / f"{speaker}-{i:02d}.wav").write_bytes(wav)
        audio = load_audio(wav)
        errs = pitch_errors(query, audio)
        errors += errs
        worst = max(errs, key=abs, default=0.0)
        line = []
        if detector:
            for p in analyze_audio(audio, text)["phrases"]:
                counts[p["status"]] += 1
                mark = {"correct": "✓", "error": "✗", "unverified": "?", "uncertain": "·"}[p["status"]]
                heard = (f"(heard {p['observed_notation']})"
                         if p["status"] in ("error", "unverified") else "")
                line.append(f"{mark}{p['notation']}{heard}")
        print(f"{i:02d} {text}  {kana}  worst mora {worst:+.1f} st\n     {' '.join(line)}")

    err = np.abs(errors)
    print(f"\nspeaker {speaker} ({tutor.speaker_name(speaker)}): pitch off by "
          f"{np.mean(err):.1f} st on average, {np.mean(err > 2):.0%} of moras > 2 st")
    judged = counts["correct"] + counts["error"]
    if judged:
        print(f"detector: {dict(counts)}; correct on {counts['correct']}/{judged} "
              f"confident phrases ({counts['correct'] / judged:.0%})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--speaker", type=int, nargs="+", default=[tutor.SPEAKER])
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--out", type=Path, help="save each sentence's WAV here")
    ap.add_argument("--no-detector", action="store_true", help="pitch fidelity only (fast)")
    args = ap.parse_args()
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
    for speaker in args.speaker:
        check(speaker, args.speed, args.out, not args.no_detector)


if __name__ == "__main__":
    main()
