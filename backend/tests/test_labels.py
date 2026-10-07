import io
import json

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

from app import main
from app.labels import LabelStore


def _wav_bytes(seconds=1.0):
    buf = io.BytesIO()
    t = np.arange(int(16000 * seconds)) / 16000
    sf.write(buf, 0.1 * np.sin(2 * np.pi * 150 * t), 16000, format="WAV")
    return buf.getvalue()


def test_store_counts_your_mistakes(tmp_path):
    store = LabelStore(tmp_path / "l.sqlite", tmp_path / "clips")
    store.add(source="practice", clip="a.flac", text="音を聞いた。", phrase_index=0,
              moras=["オ", "ト", "オ"], expected=[2], said=2)
    store.add(source="practice", clip="b.flac", text="音を聞いた。", phrase_index=1,
              moras=["キ", "イ", "タ"], expected=[0], said=3)  # odaka = flat inside the phrase
    store.add(source="practice", clip="c.flac", text="音を聞いた。", phrase_index=1,
              moras=["キ", "イ", "タ"], expected=[0], said=1)
    s = store.stats()
    assert (s["your_phrases"], s["your_correct"], s["your_mistakes"]) == (3, 2, 1)


def test_api_label_and_practice(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "labels", LabelStore(tmp_path / "l.sqlite", tmp_path / "clips"))
    client = TestClient(main.app)
    item = client.get("/practice/next", params={"text": "音を聞いた。"}).json()
    assert item["text"] == "音を聞いた。" and item["kind"]
    meta = {"source": "practice", "text": item["text"], "phrase_index": item["phrase_index"],
            "said": item["target"]}
    r = client.post("/labels", files={"audio": ("r.wav", _wav_bytes())}, data={"meta": json.dumps(meta)})
    assert r.status_code == 200, r.text
    assert r.json()["stats"]["your_phrases"] == 1
    assert len(list((tmp_path / "clips").iterdir())) == 1
    bad = {**meta, "phrase_index": 99}
    assert client.post("/labels", files={"audio": ("r.wav", _wav_bytes())},
                       data={"meta": json.dumps(bad)}).status_code == 422


def test_review_queue_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "labels", LabelStore(tmp_path / "l.sqlite", tmp_path / "clips"))
    review = tmp_path / "review.json"
    clip = tmp_path / "x.wav"
    clip.write_bytes(_wav_bytes())
    review.write_text(json.dumps([{"id": "jvs001/X:0", "path": str(clip), "text": "あめ", "spk": "jvs001",
                                   "phrase": 0, "moras": ["ア", "メ"], "expected": [1], "heard": 0,
                                   "heard_notation": "アメ━", "start": 0.0, "end": 0.5}]))
    monkeypatch.setattr(main, "REVIEW", review)
    client = TestClient(main.app)
    assert client.get("/review/next").json()["id"] == "jvs001/X:0"
    assert client.get("/review/audio/jvs001/X:0").status_code == 200
    assert client.post("/review", json={"id": "jvs001/X:0", "answer": "misheard"}).status_code == 200
    assert client.get("/review/next").json()["remaining"] == 0
