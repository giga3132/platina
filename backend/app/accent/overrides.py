"""User overrides: accents checked by the user in the NHK dictionary.

Stored per lexeme (dictionary form + reading), e.g. 聞く / キク → [0]. The
engine derives inflected forms and phrase accents from them with the usual
rules, so one entry covers 聞いた, 聞きます, 聞いて, ...
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

from .kana import to_katakana
from .sources import Morph

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "overrides.sqlite"


class OverrideStore:
    def __init__(self, path: str | os.PathLike | None = None):
        self.path = str(path or os.environ.get("PLATINA_OVERRIDES_DB", DEFAULT_DB))
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS overrides ("
            " lemma TEXT NOT NULL, reading TEXT NOT NULL, accents TEXT NOT NULL,"
            " note TEXT NOT NULL DEFAULT '', updated_at REAL NOT NULL,"
            " PRIMARY KEY (lemma, reading))"
        )
        self._db.commit()

    def put(self, lemma: str, reading: str, accents: list[int], note: str = "") -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO overrides VALUES (?, ?, ?, ?, ?)",
            (lemma, to_katakana(reading), json.dumps(accents), note, time.time()),
        )
        self._db.commit()

    def delete(self, lemma: str, reading: str) -> None:
        self._db.execute("DELETE FROM overrides WHERE lemma = ? AND reading = ?",
                         (lemma, to_katakana(reading)))
        self._db.commit()

    def all(self) -> list[dict]:
        rows = self._db.execute(
            "SELECT lemma, reading, accents, note FROM overrides ORDER BY updated_at DESC")
        return [{"lemma": l, "reading": r, "accents": json.loads(a), "note": n}
                for l, r, a, n in rows]

    def lookup(self, m: Morph) -> list[int] | None:
        """Override for a token: matched on its dictionary reading and its
        lemma or surface (the user may type 掛ける or かける)."""
        if not m.lemma_reading:
            return None
        hira = "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c
                       for c in m.lemma_reading)
        row = self._db.execute(
            "SELECT accents FROM overrides WHERE reading = ? AND lemma IN (?, ?, ?)",
            (m.lemma_reading, m.lemma, m.surface, hira),
        ).fetchone()
        return json.loads(row[0]) if row else None
