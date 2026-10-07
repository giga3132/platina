"""The JVS corpus: 100 professional speakers (voice actors/actresses).

  parallel100  every speaker reads the same 100 sentences (JSUT voiceactress100)
  nonpara30    30 different sentences per speaker, taken from JSUT; the
               BASIC5000_* ones have exact accent labels in jsut-label

JVS is free for non-commercial research. Download jvs_ver1.zip yourself
(https://sites.google.com/site/shinnosuketakamichi/research-topics/jvs_corpus),
then convert the normal-voice parts to 16 kHz FLAC:

  ../.venv/bin/python -m tools.jvs prepare jvs_ver1.zip OUT_DIR
"""

from __future__ import annotations

import argparse
import io
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path

PARTS = ("parallel100", "nonpara30")


@dataclass
class Clip:
    speaker: str  # jvs001 ... jvs100
    part: str  # parallel100 | nonpara30
    utt: str  # e.g. VOICEACTRESS100_001, BASIC5000_1356
    text: str
    path: Path


def split_of(speaker: str) -> str:
    """Speaker-disjoint split, stable across runs: 80/10/10."""
    h = zlib.crc32(speaker.encode()) % 10
    return "test" if h == 0 else "dev" if h == 1 else "train"


def clips(root: Path) -> list[Clip]:
    out = []
    for spk in sorted(p for p in root.iterdir() if p.is_dir()):
        for part in PARTS:
            tr = spk / part / "transcripts_utf8.txt"
            if not tr.exists():
                continue
            for line in tr.read_text().splitlines():
                utt, _, text = line.partition(":")
                path = spk / part / f"{utt}.flac"
                if path.exists():
                    out.append(Clip(spk.name, part, utt, text.strip(), path))
    return out


def prepare(zip_path: Path, out: Path) -> None:
    import numpy as np
    import soundfile as sf

    from app.audio.pitch import load_audio

    zf = zipfile.ZipFile(zip_path)
    names = zf.namelist()
    for name in names:
        parts = name.split("/")
        if len(parts) < 4 or parts[2] not in PARTS:
            continue
        spk, part = parts[1], parts[2]
        dst_dir = out / spk / part
        dst_dir.mkdir(parents=True, exist_ok=True)
        if name.endswith("transcripts_utf8.txt"):
            (dst_dir / "transcripts_utf8.txt").write_bytes(zf.read(name))
        elif name.endswith(".wav") and "/wav24kHz16bit/" in name:
            dst = dst_dir / (Path(name).stem + ".flac")
            if not dst.exists():
                wav = load_audio(zf.read(name))
                sf.write(dst, np.clip(wav, -1, 1), 16000, subtype="PCM_16")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("zip", type=Path)
    p.add_argument("out", type=Path)
    args = ap.parse_args()
    prepare(args.zip, args.out)


if __name__ == "__main__":
    main()
