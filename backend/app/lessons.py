"""Recorded lessons: a whole class recorded in pieces, analyzed afterwards.

While recording, the browser uploads a piece every few seconds (appended in
order to raw audio), so a crash loses at most one piece. On finish the
recording becomes a seekable Opus file and a background worker analyzes it:
split at pauses, transcribe, judge every accent phrase. Each utterance is
saved as soon as it is done, so a restart resumes where it stopped.

Rows live in backend/data/lessons.sqlite, audio in backend/data/lessons/<id>/
(both gitignored).
"""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import sqlite3
import subprocess
import threading
import time
import traceback
import uuid
from pathlib import Path

from .labels import DATA
from .progress import lesson_summary

DEFAULT_DB = DATA / "lessons.sqlite"
AUDIO_ROOT = DATA / "lessons"

# Whisper's well-known inventions on silence and noise (not things said in class)
HALLUCINATIONS = ("ご視聴ありがとうございました", "ご清聴ありがとうございました", "チャンネル登録",
                  "字幕", "最後までご視聴")
_JAPANESE = re.compile(r"[぀-ヿ㐀-鿿]")
_LATIN = re.compile(r"[A-Za-z]")


def skip_reason(text: str) -> str | None:
    """Why an utterance isn't judged: nothing Japanese was said."""
    t = text.strip()
    if not t or any(h in t for h in HALLUCINATIONS):
        return "no speech"
    if re.search(r"(.)\1{9,}", t):
        return "no speech"
    jp, latin = len(_JAPANESE.findall(t)), len(_LATIN.findall(t))
    if jp == 0 or latin > jp:
        return "not Japanese"
    return None


class LessonStore:
    def __init__(self, path: str | os.PathLike | None = None, root: Path | None = None):
        self.path = str(path or os.environ.get("PLATINA_LESSONS_DB", DEFAULT_DB))
        self.root = Path(root or os.environ.get("PLATINA_LESSONS_DIR", AUDIO_ROOT))
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.root.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._lock = threading.Lock()
        self._db.executescript(
            "CREATE TABLE IF NOT EXISTS lessons ("
            " id TEXT PRIMARY KEY, created_at REAL NOT NULL, title TEXT NOT NULL,"
            " status TEXT NOT NULL, chunks INTEGER NOT NULL DEFAULT 0,"
            " done INTEGER NOT NULL DEFAULT 0, total INTEGER NOT NULL DEFAULT 0,"
            " duration REAL, segments TEXT, version TEXT NOT NULL DEFAULT '',"
            " summary TEXT, error TEXT);"
            "CREATE TABLE IF NOT EXISTS utterances ("
            " lesson_id TEXT NOT NULL, idx INTEGER NOT NULL, start REAL NOT NULL, end REAL NOT NULL,"
            " text TEXT NOT NULL, edited INTEGER NOT NULL DEFAULT 0, skipped TEXT,"
            " version TEXT NOT NULL, result TEXT, PRIMARY KEY (lesson_id, idx));"
        )
        self._db.commit()

    # --- lessons ---------------------------------------------------------------

    def create(self, title: str = "") -> str:
        lid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        with self._lock:
            self._db.execute("INSERT INTO lessons (id, created_at, title, status) VALUES (?,?,?,?)",
                             (lid, time.time(), title or time.strftime("Lesson %Y-%m-%d %H:%M"), "recording"))
            self._db.commit()
        self.dir(lid).mkdir(parents=True, exist_ok=True)
        return lid

    def dir(self, lid: str) -> Path:
        if not re.fullmatch(r"[\w-]+", lid):
            raise KeyError(lid)
        return self.root / lid

    def audio(self, lid: str) -> Path:
        return self.dir(lid) / "audio.webm"

    def get(self, lid: str) -> dict | None:
        cur = self._db.execute("SELECT * FROM lessons WHERE id = ?", (lid,))
        row = cur.fetchone()
        if row is None:
            return None
        r = dict(zip([d[0] for d in cur.description], row))
        r["summary"] = json.loads(r["summary"]) if r["summary"] else None
        r["segments"] = json.loads(r["segments"]) if r["segments"] else None
        return r

    def all(self) -> list[dict]:
        ids = [r[0] for r in self._db.execute("SELECT id FROM lessons ORDER BY created_at")]
        return [self.get(i) for i in ids]

    def update(self, lid: str, **fields) -> None:
        for k in ("summary", "segments"):
            if k in fields and fields[k] is not None:
                fields[k] = json.dumps(fields[k], ensure_ascii=False)
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self._lock:
            self._db.execute(f"UPDATE lessons SET {cols} WHERE id = ?", (*fields.values(), lid))
            self._db.commit()

    def delete(self, lid: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM utterances WHERE lesson_id = ?", (lid,))
            self._db.execute("DELETE FROM lessons WHERE id = ?", (lid,))
            self._db.commit()
        shutil.rmtree(self.dir(lid), ignore_errors=True)

    # --- recording ---------------------------------------------------------------

    def append_chunk(self, lid: str, seq: int, data: bytes) -> int:
        """Append piece `seq` (0, 1, 2, ...). A piece sent again is ignored;
        a gap raises ValueError. Returns how many pieces are saved."""
        lesson = self.get(lid)
        if lesson is None:
            raise KeyError(lid)
        if lesson["status"] != "recording":
            raise ValueError("this lesson is no longer recording")
        if seq < lesson["chunks"]:
            return lesson["chunks"]
        if seq > lesson["chunks"]:
            raise ValueError(f"piece {lesson['chunks']} is missing")
        with (self.dir(lid) / "raw").open("ab") as fh:
            fh.write(data)
        self.update(lid, chunks=seq + 1)
        return seq + 1

    def save_upload(self, lid: str, data: bytes) -> None:
        (self.dir(lid) / "raw").write_bytes(data)

    def finish(self, lid: str) -> None:
        """Turn the raw recording into a seekable mono Opus file and queue it."""
        raw = self.dir(lid) / "raw"
        if not raw.exists() or raw.stat().st_size == 0:
            raise ValueError("nothing was recorded")
        subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(raw), "-vn", "-ac", "1",
                        "-c:a", "libopus", "-b:a", "40k", str(self.audio(lid))], check=True, capture_output=True)
        raw.unlink()
        self.update(lid, status="queued", error=None)

    # --- utterances ----------------------------------------------------------------

    def put_utterance(self, lid: str, idx: int, start: float, end: float, text: str, version: str,
                      result: dict | None, skipped: str | None = None, edited: bool = False) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO utterances VALUES (?,?,?,?,?,?,?,?,?)",
                (lid, idx, start, end, text, int(edited), skipped, version,
                 json.dumps(result, ensure_ascii=False) if result is not None else None))
            self._db.commit()

    def utterances(self, lid: str) -> list[dict]:
        cur = self._db.execute("SELECT * FROM utterances WHERE lesson_id = ? ORDER BY idx", (lid,))
        cols = [d[0] for d in cur.description]
        out = []
        for row in cur:
            r = dict(zip(cols, row))
            r["result"] = json.loads(r["result"]) if r["result"] else None
            r["edited"] = bool(r["edited"])
            del r["lesson_id"]
            out.append(r)
        return out

    def summarize(self, lid: str) -> dict:
        summary = lesson_summary(self.utterances(lid))
        self.update(lid, summary=summary)
        return summary


class LessonJobs:
    """One worker thread analyzing queued lessons, one at a time.

    `segment(wav)` → [(start, end)], `transcribe(wav)` → text and
    `analyze(wav, text, offset)` → {"phrases": ...} are injected (the speech
    models in the app, fakes in tests); `gpu` is the app's lock, taken per
    utterance so other requests get their turn. `version()` names the current
    model + NHK overrides: utterances analyzed under another version are
    re-analyzed (with their transcript kept)."""

    def __init__(self, store: LessonStore, *, segment, transcribe, analyze, version, gpu=None):
        self.store = store
        self.segment, self.transcribe, self.analyze, self.version = segment, transcribe, analyze, version
        self.gpu = gpu or threading.Lock()
        self._queue: queue.Queue[str] = queue.Queue()
        self._thread: threading.Thread | None = None

    def submit(self, lid: str) -> None:
        self.store.update(lid, status="queued")
        self._queue.put(lid)
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._loop, daemon=True, name="lessons")
            self._thread.start()

    def resume(self) -> None:
        """After a restart: continue lessons that were queued or half done."""
        for ls in self.store.all():
            if ls["status"] in ("queued", "processing"):
                self.submit(ls["id"])

    def _loop(self) -> None:
        while True:
            lid = self._queue.get()
            try:
                self.run(lid)
            except Exception:  # noqa: BLE001 - shown in the lesson list, the worker keeps going
                if self.store.get(lid):
                    self.store.update(lid, status="failed", error=traceback.format_exc(limit=3))

    def run(self, lid: str) -> None:
        from .audio.pitch import SAMPLE_RATE, load_audio

        lesson = self.store.get(lid)
        if lesson is None:
            return
        version = self.version()
        self.store.update(lid, status="processing", error=None, done=0)
        wav = load_audio(self.store.audio(lid))
        segments = lesson["segments"]
        if segments is None:
            segments = [[round(s, 3), round(e, 3)] for s, e in self.segment(wav)]
            self.store.update(lid, segments=segments, total=len(segments),
                              duration=round(len(wav) / SAMPLE_RATE, 3))
        have = {u["idx"]: u for u in self.store.utterances(lid)}
        for idx, (s, e) in enumerate(segments):
            if self.store.get(lid) is None:
                return  # deleted meanwhile
            u = have.get(idx)
            if u is not None and (u["version"] == version or u["skipped"]):
                self.store.update(lid, done=idx + 1)
                continue
            piece = wav[int(s * SAMPLE_RATE):int(e * SAMPLE_RATE)]
            if u is None:
                with self.gpu:
                    text = self.transcribe(piece)
            else:
                text = u["text"]
            skipped = skip_reason(text)
            result = None
            if skipped is None:
                with self.gpu:
                    result = self.analyze(piece, text, s)
            self.store.put_utterance(lid, idx, s, e, text, version, result, skipped,
                                     edited=bool(u and u["edited"]))
            self.store.update(lid, done=idx + 1)
        self.store.summarize(lid)
        self.store.update(lid, status="done", done=len(segments), version=version)

    def reanalyze_line(self, lid: str, idx: int, text: str) -> dict:
        """Corrected transcript for one utterance: judge just that slice again."""
        from .audio.pitch import load_audio

        u = next((x for x in self.store.utterances(lid) if x["idx"] == idx), None)
        if u is None:
            raise KeyError(idx)
        wav = load_audio(self.store.audio(lid), start=u["start"], end=u["end"])
        skipped = skip_reason(text)
        result = None
        if skipped is None:
            with self.gpu:
                result = self.analyze(wav, text, u["start"])
        self.store.put_utterance(lid, idx, u["start"], u["end"], text, self.version(), result, skipped, edited=True)
        self.store.summarize(lid)
        return next(x for x in self.store.utterances(lid) if x["idx"] == idx)
