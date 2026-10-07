"""Recorded lessons: pieces appended in order, background analysis that
resumes, re-analysis after a model change, fixing a line, and the API."""

import io
import json

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from app import main
from app.labels import LabelStore
from app.lessons import LessonJobs, LessonStore, skip_reason


def wav_bytes(seconds=2.0):
    buf = io.BytesIO()
    t = np.arange(int(16000 * seconds)) / 16000
    sf.write(buf, 0.1 * np.sin(2 * np.pi * 150 * t), 16000, format="WAV")
    return buf.getvalue()


def fake_result(text, offset):
    status = "error" if "橋" in text else "correct"
    return {"text": text, "phrases": [{
        "text": text, "moras": ["ハ", "シ"], "accent": 1, "status": status,
        "observed": 0 if status == "error" else 1, "detect_confidence": 0.9, "p_expected": 0.1,
        "mora_times": [[offset, offset + 0.2], [offset + 0.2, offset + 0.4]],
        "words": [{"lemma": "箸", "reading": "ハシ", "pos": "名詞"}]}]}


class Fakes:
    def __init__(self, texts):
        self.texts = list(texts)
        self.transcribed, self.analyzed = [], []
        self.version = "v1"
        self.fail_at = None

    def jobs(self, store):
        return LessonJobs(store, segment=lambda wav: [(0.0, 0.8), (0.8, 2.0)], transcribe=self.transcribe,
                          analyze=self.analyze, version=lambda: self.version)

    def transcribe(self, wav):
        text = self.texts[0 if len(wav) < 16000 else 1]  # the short first utterance, the long second one
        self.transcribed.append(text)
        return text

    def analyze(self, wav, text, offset):
        if self.fail_at is not None and len(self.analyzed) == self.fail_at:
            raise RuntimeError("crash")
        self.analyzed.append((text, offset, len(wav)))
        return fake_result(text, offset)


@pytest.fixture
def store(tmp_path):
    return LessonStore(tmp_path / "lessons.sqlite", tmp_path / "audio")


def recorded(store):
    lid = store.create("test")
    store.append_chunk(lid, 0, wav_bytes())
    store.finish(lid)
    return lid


def test_pieces_append_in_order(store):
    lid = store.create()
    assert store.append_chunk(lid, 0, b"ab") == 1
    assert store.append_chunk(lid, 0, b"ab") == 1  # sent again after a timeout: ignored
    with pytest.raises(ValueError):
        store.append_chunk(lid, 2, b"ef")  # piece 1 is missing
    assert store.append_chunk(lid, 1, b"cd") == 2
    assert (store.dir(lid) / "raw").read_bytes() == b"abcd"


def test_finish_makes_seekable_audio(store):
    lid = recorded(store)
    assert store.audio(lid).exists() and not (store.dir(lid) / "raw").exists()
    assert store.get(lid)["status"] == "queued"
    with pytest.raises(ValueError):
        store.finish(store.create())  # nothing recorded


def test_job_analyzes_resumes_and_redoes_old_versions(store):
    lid = recorded(store)
    f = Fakes(["お箸を使う。", "橋を渡る。"])
    f.fail_at = 1  # the app stops after the first utterance
    with pytest.raises(RuntimeError):
        f.jobs(store).run(lid)
    assert [u["idx"] for u in store.utterances(lid)] == [0]

    f.fail_at = None
    f.jobs(store).run(lid)  # restart: the first utterance isn't done again
    assert f.transcribed == ["お箸を使う。", "橋を渡る。", "橋を渡る。"]
    lesson = store.get(lid)
    assert lesson["status"] == "done" and lesson["done"] == lesson["total"] == 2
    assert lesson["summary"]["judged"] == 2 and lesson["summary"]["mistakes"] == 1
    assert lesson["duration"] == pytest.approx(2.0, abs=0.05)
    us = store.utterances(lid)
    assert us[1]["start"] == 0.8 and us[1]["result"]["phrases"][0]["mora_times"][0][0] == 0.8

    f.version = "v2"  # new model: judged again, transcripts kept
    f.analyzed.clear()
    f.jobs(store).run(lid)
    assert len(f.transcribed) == 3 and len(f.analyzed) == 2
    assert {u["version"] for u in store.utterances(lid)} == {"v2"}


def test_fixing_a_line_judges_only_that_slice(store):
    lid = recorded(store)
    f = Fakes(["お箸を使う。", "橋を渡る。"])
    jobs = f.jobs(store)
    jobs.run(lid)
    f.analyzed.clear()
    u = jobs.reanalyze_line(lid, 1, "箸を渡す。")
    assert u["edited"] and u["text"] == "箸を渡す。"
    (text, offset, n), = f.analyzed
    assert offset == 0.8 and n == pytest.approx(1.2 * 16000, rel=0.05)  # that slice, not the whole lesson
    assert store.get(lid)["summary"]["mistakes"] == 0


def test_skip_reason():
    assert skip_reason("ご視聴ありがとうございました") == "no speech"
    assert skip_reason("Okay, so the homework is page five") == "not Japanese"
    assert skip_reason("宿題はpage 5です") is None
    assert skip_reason("音を聞いた。") is None


def test_api_lesson_flow(tmp_path, monkeypatch):
    store = LessonStore(tmp_path / "lessons.sqlite", tmp_path / "audio")
    f = Fakes(["お箸を使う。", "橋を渡る。"])
    jobs = f.jobs(store)
    monkeypatch.setattr(jobs, "submit", jobs.run)  # synchronous in tests
    monkeypatch.setattr(main, "lessons", store)
    monkeypatch.setattr(main, "jobs", jobs)
    monkeypatch.setattr(main, "labels", LabelStore(tmp_path / "l.sqlite", tmp_path / "clips"))
    client = TestClient(main.app)

    lid = client.post("/lessons", json={"title": "Monday"}).json()["id"]
    assert client.post(f"/lessons/{lid}/chunk?seq=0", content=wav_bytes()).json() == {"saved": 1}
    assert client.post(f"/lessons/{lid}/chunk?seq=5", content=b"x").status_code == 409
    assert client.post(f"/lessons/{lid}/finish").status_code == 200

    listed = client.get("/lessons").json()
    assert listed[0]["id"] == lid and listed[0]["status"] == "done" and listed[0]["title"] == "Monday"
    lesson = client.get(f"/lessons/{lid}").json()
    assert len(lesson["utterances"]) == 2 and lesson["summary"]["mistakes"] == 1
    assert client.get(f"/lessons/{lid}/audio").status_code == 200

    r = client.put(f"/lessons/{lid}/utterances/1", json={"text": "箸を渡す。"})
    assert r.status_code == 200 and r.json()["summary"]["mistakes"] == 0

    meta = {"source": "report", "lesson": lid, "text": "箸を渡す。", "phrase_index": 0, "said": 1,
            "start": 0.8, "end": 2.0}
    r = client.post("/labels", data={"meta": json.dumps(meta)})
    assert r.status_code == 200, r.text

    progress = client.get("/progress").json()
    assert progress["lessons"][0]["id"] == lid

    assert client.patch(f"/lessons/{lid}", json={"title": "Tuesday"}).status_code == 200
    assert client.get(f"/lessons/{lid}").json()["title"] == "Tuesday"
    assert client.delete(f"/lessons/{lid}").status_code == 200
    assert client.get(f"/lessons/{lid}").status_code == 404
    assert client.get("/lessons/../etc").status_code == 404


def test_api_upload(tmp_path, monkeypatch):
    store = LessonStore(tmp_path / "lessons.sqlite", tmp_path / "audio")
    f = Fakes(["お箸を使う。", "橋を渡る。"])
    jobs = f.jobs(store)
    monkeypatch.setattr(jobs, "submit", jobs.run)
    monkeypatch.setattr(main, "lessons", store)
    monkeypatch.setattr(main, "jobs", jobs)
    client = TestClient(main.app)
    r = client.post("/lessons/upload", files={"audio": ("class.wav", wav_bytes())})
    assert r.status_code == 200
    assert client.get(f"/lessons/{r.json()['id']}").json()["title"] == "class"
    r = client.post("/lessons/upload", files={"audio": ("notes.txt", b"not audio")})
    assert r.status_code == 422
    assert len(client.get("/lessons").json()) == 1
