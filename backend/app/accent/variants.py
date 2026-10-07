"""Accent variants natives actually use, mined from corpus recordings
(tools/mine_variants.py) and reviewed by the user.

Keyed by the phrase's words (lemmas) and reading, e.g. 確か|に / タシカニ.
  approved  accepted like a dictionary alternative ("Natives also say")
  proposed  not yet reviewed: a speaker using it is never told it's a mistake
            (verdict "unverified", grey)
  rejected  ignored
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "variants.sqlite"


def phrase_key(lemmas: list[str], moras: list[str]) -> str:
    return "|".join(lemmas) + "/" + "".join(moras)


class VariantStore:
    def __init__(self, path: str | os.PathLike | None = None):
        self.path = str(path or os.environ.get("PLATINA_VARIANTS_DB", DEFAULT_DB))
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS variants ("
            " key TEXT NOT NULL, accent INTEGER NOT NULL, status TEXT NOT NULL,"
            " speakers INTEGER NOT NULL, total INTEGER NOT NULL, examples TEXT NOT NULL,"
            " updated_at REAL NOT NULL, PRIMARY KEY (key, accent))")
        self._db.commit()

    def propose(self, key: str, accent: int, speakers: int, total: int, examples: list[str]) -> None:
        """Insert or refresh counts; keeps a status the user already set."""
        row = self._db.execute("SELECT status FROM variants WHERE key=? AND accent=?", (key, accent)).fetchone()
        status = row[0] if row else "proposed"
        self._db.execute("INSERT OR REPLACE INTO variants VALUES (?,?,?,?,?,?,?)",
                         (key, accent, status, speakers, total, json.dumps(examples[:5], ensure_ascii=False),
                          time.time()))
        self._db.commit()

    def set_status(self, key: str, accent: int, status: str) -> None:
        self._db.execute("UPDATE variants SET status=?, updated_at=? WHERE key=? AND accent=?",
                         (status, time.time(), key, accent))
        self._db.commit()

    def lookup(self, key: str) -> dict[str, list[int]]:
        out: dict[str, list[int]] = {"approved": [], "proposed": []}
        for accent, status in self._db.execute("SELECT accent, status FROM variants WHERE key=?", (key,)):
            if status in out:
                out[status].append(accent)
        return out

    def all(self) -> list[dict]:
        rows = self._db.execute("SELECT key, accent, status, speakers, total, examples FROM variants"
                                " ORDER BY status, speakers DESC")
        return [{"key": k, "accent": a, "status": s, "speakers": n, "total": t, "examples": json.loads(e)}
                for k, a, s, n, t, e in rows]
