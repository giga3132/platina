"""Fetch JSUT basic5000 wavs without downloading the whole 2.7 GB zip.

The JSUT zip is served with HTTP range support, so zipfile can read the
central directory and individual members through a seekable HTTP file.
Each wav is stored as 16 kHz mono FLAC (what Platina uses anyway).

Usage (from backend/):
  ../.venv/bin/python -m tools.fetch_jsut OUT_DIR [--n 5000]
"""

from __future__ import annotations

import argparse
import io
import time
import zipfile
from pathlib import Path

import httpx
import numpy as np
import soundfile as sf

URL = "http://ss-takashi.sakura.ne.jp/corpus/jsut_ver1.1.zip"


class HTTPFile(io.RawIOBase):
    """Read-only, seekable file over HTTP range requests."""

    def __init__(self, url: str):
        self.url, self.pos = url, 0
        self.client = httpx.Client(timeout=60, follow_redirects=True)
        self.size = int(self.client.head(url).headers["content-length"])

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=io.SEEK_SET):
        self.pos = {io.SEEK_SET: 0, io.SEEK_CUR: self.pos, io.SEEK_END: self.size}[whence] + offset
        return self.pos

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        if n == 0 or self.pos >= self.size:
            return b""
        end = min(self.pos + n, self.size) - 1
        for attempt in range(8):  # the server drops connections now and then
            try:
                r = self.client.get(self.url, headers={"Range": f"bytes={self.pos}-{end}"})
                r.raise_for_status()
                break
            except httpx.HTTPError:
                if attempt == 7:
                    raise
                time.sleep(2 ** attempt)
                self.client = httpx.Client(timeout=60, follow_redirects=True)
        self.pos += len(r.content)
        return r.content

    def readinto(self, b):
        data = self.read(len(b))
        b[:len(data)] = data
        return len(data)


def main():
    from app.audio.pitch import load_audio

    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--n", type=int, default=5000)
    ap.add_argument("--shard", default="0/1", help="i/k: fetch every k-th file from i (parallel runs)")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    zf = zipfile.ZipFile(io.BufferedReader(HTTPFile(URL), buffer_size=1 << 20))
    names = sorted(n for n in zf.namelist() if "/basic5000/wav/" in n and n.endswith(".wav"))[:args.n]
    i0, k = map(int, args.shard.split("/"))
    for i, name in enumerate(names):
        if i % k != i0:
            continue
        dst = args.out / (Path(name).stem + ".flac")
        if dst.exists():
            continue
        wav = load_audio(zf.read(name))
        sf.write(dst, np.clip(wav, -1, 1), 16000, subtype="PCM_16")
        if i % 100 == 0:
            print(f"{i}/{len(names)}", flush=True)


if __name__ == "__main__":
    main()
