"""User overrides: accents checked by the user in the NHK dictionary.

Stored per lexeme (dictionary form + reading), e.g. 聞く / キク → [0]. The
engine derives inflected forms and phrase accents from them with the usual
rules, so one entry covers 聞いた, 聞きます, 聞いて, ...

A few words take a different accent depending on use, and NHK lists each
use separately: 人 ヒト━ (人を呼ぶ) but ヒト＼ after a modifier (優しい人に),
昨日 キノ＼ー as a noun but キノー━ as an adverb (昨日会った). Those rows
carry a context (one of CONTEXTS); the engine works out the token's uses
and the plain row ('') covers every other use.

Compounds NHK lists as one word (日本語 ニホンゴ━) are stored like any other
word; the engine matches them across UniDic's split (日本 + 語) with
lookup_compound, since the compound rules don't always give NHK's accent.

NHK also lists whole forms (高い: タ＼カク, タカ＼ク, タ＼カカッタ; 学ぶ:
マナバナイ━, マナビマ＼ス; 駅: エ＼キオ). Those go in the forms table and
win over the rules when a phrase is exactly that form.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

from .kana import same_moras, split_moras, to_katakana
from .sources import Morph

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "overrides.sqlite"

CONTEXTS = ("", "modified", "unmodified", "noun", "adverb")


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
            " context TEXT NOT NULL DEFAULT '',"
            " PRIMARY KEY (lemma, reading, context))"
        )
        cols = [r[1] for r in self._db.execute("PRAGMA table_info(overrides)")]
        if "context" not in cols:
            # older stores: the primary key has to grow, so copy into a new table
            self._db.executescript(
                "ALTER TABLE overrides RENAME TO overrides_old;"
                "CREATE TABLE overrides ("
                " lemma TEXT NOT NULL, reading TEXT NOT NULL, accents TEXT NOT NULL,"
                " note TEXT NOT NULL DEFAULT '', updated_at REAL NOT NULL,"
                " context TEXT NOT NULL DEFAULT '',"
                " PRIMARY KEY (lemma, reading, context));"
                "INSERT INTO overrides (lemma, reading, accents, note, updated_at)"
                " SELECT lemma, reading, accents, note, updated_at FROM overrides_old;"
                "DROP TABLE overrides_old;")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS forms ("
            " lemma TEXT NOT NULL, reading TEXT NOT NULL, form TEXT NOT NULL,"
            " accents TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',"
            " PRIMARY KEY (lemma, reading, form))"
        )
        self._db.commit()

    def put(self, lemma: str, reading: str, accents: list[int], note: str = "",
            context: str = "") -> None:
        if context not in CONTEXTS:
            raise ValueError(f"unknown context {context!r}")
        self._db.execute(
            "INSERT OR REPLACE INTO overrides (lemma, reading, accents, note, updated_at, context)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (lemma, to_katakana(reading), json.dumps(accents), note, time.time(), context),
        )
        self._db.commit()

    def delete(self, lemma: str, reading: str, context: str | None = None) -> None:
        """Delete one use's row, or every row of the word if context is None."""
        sql, args = "DELETE FROM overrides WHERE lemma = ? AND reading = ?", [lemma, to_katakana(reading)]
        if context is not None:
            sql, args = sql + " AND context = ?", args + [context]
        self._db.execute(sql, args)
        self._db.commit()

    def all(self) -> list[dict]:
        rows = self._db.execute(
            "SELECT lemma, reading, accents, note, context FROM overrides ORDER BY updated_at DESC")
        return [{"lemma": l, "reading": r, "accents": json.loads(a), "note": n, "context": c}
                for l, r, a, n, c in rows]

    def put_form(self, lemma: str, reading: str, form: str, accents: list[int], note: str = "") -> None:
        """Accents of one whole form of a word, e.g. 高い / タカイ / タカク → [1, 2]."""
        self._db.execute("INSERT OR REPLACE INTO forms VALUES (?, ?, ?, ?, ?)",
                         (lemma, to_katakana(reading), to_katakana(form), json.dumps(accents), note))
        self._db.commit()

    def delete_forms(self, note_prefix: str) -> None:
        self._db.execute("DELETE FROM forms WHERE note LIKE ?", (note_prefix + "%",))
        self._db.commit()

    def all_forms(self) -> list[dict]:
        rows = self._db.execute("SELECT lemma, reading, form, accents, note FROM forms ORDER BY lemma, form")
        return [{"lemma": l, "reading": r, "form": f, "accents": json.loads(a), "note": n}
                for l, r, f, a, n in rows]

    def forms(self, m: Morph) -> list[tuple[str, list[int]]]:
        """The NHK forms stored for a token's word: (form in katakana, accents)."""
        if not m.lemma_reading:
            return []
        own = "".join(m.moras) if m.ctype == "*" else m.lemma_reading
        rows = self._db.execute(
            "SELECT form, accents FROM forms WHERE reading IN (?, ?) AND lemma IN (?, ?)",
            (m.lemma_reading, own, m.lemma, m.surface))
        return [(f, json.loads(a)) for f, a in rows]

    def lookup(self, m: Morph, uses: tuple[str, ...] = ()) -> list[int] | None:
        """Override for a token: matched on its dictionary reading and its
        lemma or surface (the user may type 掛ける or かける). A row for one of
        the token's uses (contexts, e.g. ("modified", "noun")) wins over the
        plain one."""
        hit = self.lookup_use(m, uses)
        return hit[0] if hit else None

    def has_reading(self, m: Morph) -> bool:
        """Some row (any use) exists for this token's word and reading: the
        user has it from NHK, so the reading is a real one."""
        return self.lookup_use(m, CONTEXTS[1:]) is not None

    def lookup_compound(self, surface: str, reading: str) -> list[int] | None:
        """Plain row for a compound stored whole (日本語 / ニホンゴ); NHK's
        ー matches a spelled-out long vowel (ガッコー / ガッコウ)."""
        want = split_moras(to_katakana(reading))
        for stored, accents in self._db.execute(
                "SELECT reading, accents FROM overrides WHERE lemma = ? AND context = ''", (surface,)):
            if same_moras(split_moras(stored), want):
                return json.loads(accents)
        return None

    def compounds_in(self, text: str) -> dict[tuple[int, int], str]:
        """Every place a word stored with a single plain reading appears in
        the text, with that reading: (start, end) → katakana."""
        out = {}
        for lemma, readings in self._db.execute(
                "SELECT lemma, group_concat(DISTINCT reading) FROM overrides"
                " WHERE context = '' AND length(lemma) > 1 AND instr(?, lemma) > 0"
                " GROUP BY lemma HAVING count(DISTINCT reading) = 1", (text,)):
            i = text.find(lemma)
            while i >= 0:
                out[(i, i + len(lemma))] = readings
                i = text.find(lemma, i + 1)
        return out

    def lookup_use(self, m: Morph, uses: tuple[str, ...] = ()) -> tuple[list[int], str] | None:
        """Like lookup, also returning which row matched ('' = the plain one)."""
        if not m.lemma_reading:
            return None
        hira = "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c
                       for c in m.lemma_reading)
        # uninflected words can be stored under their own reading when the
        # lemma's differs (みんな is tagged 皆 / ミナ; NHK lists ミンナ apart)
        own = "".join(m.moras) if m.ctype == "*" else m.lemma_reading
        rows: dict[tuple[str, str], str] = {}
        for reading, use, accents in self._db.execute(
                "SELECT reading, context, accents FROM overrides"
                " WHERE reading IN (?, ?) AND lemma IN (?, ?, ?)",
                (m.lemma_reading, own, m.lemma, m.surface, hira)):
            rows[(reading, use)] = accents
        for reading in dict.fromkeys((own, m.lemma_reading)):
            for use in (*uses, ""):
                if (reading, use) in rows:
                    return json.loads(rows[(reading, use)]), use
        return None
