"""Labelled recordings of the user's voice (and reviews of native phrases).

Each label says which accent was really said in one accent phrase of a
recording. They come from three places:
  practice   the Practice tab: the user imitated a target accent (correct or a
             deliberate mistake) and kept the take
  report     "Wrong verdict?" in the phrase details
  review     the user's verdict on a native corpus phrase the detector flagged

Clips live in backend/data/recordings/, rows in backend/data/labels.sqlite
(both gitignored). tools/build_cache.py turns them into a cache for
training and evaluation.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
DEFAULT_DB = DATA / "labels.sqlite"
CLIPS = DATA / "recordings"


class LabelStore:
    def __init__(self, path: str | os.PathLike | None = None, clips: Path | None = None):
        self.path = str(path or os.environ.get("PLATINA_LABELS_DB", DEFAULT_DB))
        self.clips = Path(clips or CLIPS)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.clips.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS labels ("
            " id TEXT PRIMARY KEY, created_at REAL NOT NULL, source TEXT NOT NULL,"
            " session TEXT NOT NULL, speaker TEXT NOT NULL, clip TEXT NOT NULL, text TEXT NOT NULL,"
            " phrase_index INTEGER NOT NULL, moras TEXT NOT NULL, expected TEXT NOT NULL,"
            " said INTEGER, verdict TEXT, answer TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '')"
        )
        self._db.commit()

    def save_clip(self, wav, sr: int = 16000) -> str:
        """Store one utterance (float mono) as 16 kHz FLAC; returns its name."""
        import numpy as np
        import soundfile as sf

        name = uuid.uuid4().hex + ".flac"
        sf.write(self.clips / name, np.clip(wav, -1, 1), sr, subtype="PCM_16")
        return name

    def add(self, *, source: str, clip: str, text: str, phrase_index: int, moras: list[str],
            expected: list[int], said: int | None, verdict: str | None = None, answer: str = "",
            session: str = "", speaker: str = "me", note: str = "") -> str:
        """said = the accent really said (0 = flat); None = the user wasn't sure."""
        lid = uuid.uuid4().hex
        self._db.execute(
            "INSERT INTO labels VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (lid, time.time(), source, session or time.strftime("%Y-%m-%d"), speaker, clip, text,
             phrase_index, json.dumps(moras, ensure_ascii=False), json.dumps(expected), said, verdict,
             answer, note))
        self._db.commit()
        return lid

    def all(self) -> list[dict]:
        cols = [d[1] for d in self._db.execute("PRAGMA table_info(labels)")]
        rows = self._db.execute("SELECT * FROM labels ORDER BY created_at")
        out = []
        for row in rows:
            r = dict(zip(cols, row))
            r["moras"], r["expected"] = json.loads(r["moras"]), json.loads(r["expected"])
            out.append(r)
        return out

    def stats(self) -> dict:
        rows = self.all()
        mine = [r for r in rows if r["source"] in ("practice", "report") and r["said"] is not None]
        wrong = sum(1 for r in mine if not _accepts(r["expected"], r["said"], len(r["moras"])))
        by_source: dict[str, int] = {}
        for r in rows:
            by_source[r["source"]] = by_source.get(r["source"], 0) + 1
        return {"total": len(rows), "by_source": by_source, "your_phrases": len(mine),
                "your_correct": len(mine) - wrong, "your_mistakes": wrong,
                "sessions": len({r["session"] for r in mine})}


def _accepts(expected: list[int], said: int, n: int) -> bool:
    flat = {0, n}
    return said in expected or (said in flat and bool(flat & set(expected)))
