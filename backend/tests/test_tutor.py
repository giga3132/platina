import io
import re
import wave

import httpx
import pytest

from app import tutor
from app.accent.engine import analyze_text
from app.accent.overrides import OverrideStore
from app.tutor import phrase_kana, to_kana

from .test_engine import GOLD


def kana(text, store=None):
    return to_kana(analyze_text(text, store), text)


def test_user_example():
    assert kana("音を聞いた。") == "オト'オ/キイタ'"


def test_phrase_kana():
    assert phrase_kana(["ハ", "シ"], 1) == "ハ'シ"
    assert phrase_kana(["ハ", "シ", "オ"], 2) == "ハシ'オ"
    assert phrase_kana(["ハ", "シ", "オ"], 0) == "ハシオ'"
    with pytest.raises(ValueError):
        phrase_kana(["ハ"], 2)
    with pytest.raises(ValueError):
        phrase_kana([], 0)


def test_long_vowel_mark_becomes_vowel():
    assert phrase_kana(["コ", "ー", "ヒ", "ー", "オ"], 3) == "コオヒ'イオ"
    assert phrase_kana(["キョ", "ー"], 1) == "キョ'オ"


def test_punctuation_is_a_pause_and_question_rises():
    assert kana("今日は雨です。明日は晴れ。").count("、") == 1
    assert kana("東京へ行きましょう、ね？").endswith("？")
    assert "、" in kana("東京へ行きましょう、ね？")


def test_override_changes_what_the_tutor_says():
    store = OverrideStore(":memory:")
    store.put("聞く", "きく", [1])
    assert kana("音を聞いた。", store) == "オト'オ/キ'イタ"


@pytest.mark.parametrize("entry", GOLD, ids=[e["text"] for e in GOLD])
def test_kana_follows_engine(entry):
    """Every phrase the tutor says has its nucleus where the engine puts it."""
    phrases = [p for p in analyze_text(entry["text"]) if p.moras]
    said = re.split("[/、]", kana(entry["text"]).rstrip("？"))
    assert len(said) == len(phrases)
    for p, k in zip(phrases, said):
        assert k.count("'") == 1
        before = k.split("'")[0]
        n_before = len([c for c in before if c not in "ャュョァィゥェォヮ"])
        assert n_before == (p.accent or len(p.moras))


def _engine_up() -> bool:
    try:
        return httpx.get(f"{tutor.VOICEVOX_URL}/version", timeout=1).status_code == 200
    except httpx.TransportError:
        return False


@pytest.mark.skipif(not _engine_up(), reason="VOICEVOX engine not running")
def test_api_speak_returns_wav():
    from fastapi.testclient import TestClient

    from app import main

    client = TestClient(main.app)
    r = client.post("/speak", json={"text": "音を聞いた。"})
    assert r.status_code == 200, r.text
    with wave.open(io.BytesIO(r.content)) as w:
        assert w.getnframes() / w.getframerate() > 0.5
    r = client.post("/speak/phrase", json={"moras": ["キ", "イ", "タ"], "accent": 1})
    assert r.status_code == 200
    assert client.get("/speak/credit").json()["credit"].startswith("VOICEVOX:")


def test_api_speak_unavailable(monkeypatch):
    from fastapi.testclient import TestClient

    from app import main

    monkeypatch.setattr(tutor, "VOICEVOX_URL", "http://127.0.0.1:9")
    tutor.synthesize.cache_clear()
    r = TestClient(main.app).post("/speak", json={"text": "音を聞いた。"})
    assert r.status_code == 503


def _phrase(n, accent, pause=False):
    return {"accent": accent, "pause_mora": {"vowel_length": 0.3} if pause else None,
            "moras": [{"pitch": 5.0} for _ in range(n)]}


def test_shape_pitch_follows_accent():
    aps = [_phrase(3, 2), _phrase(3, 3), _phrase(3, 1)]  # オト'オ/キイタ'/...
    aps[1]["moras"][2]["pitch"] = 0.0  # devoiced stays devoiced
    tutor.shape_pitch(aps)
    p = [[m["pitch"] for m in ap["moras"]] for ap in aps]
    assert p[0][0] < p[0][1] > p[0][2]           # L H L
    assert p[1][0] < p[1][1] and p[1][2] == 0.0  # L H (devoiced)
    assert p[2][0] > p[2][1] == p[2][2]          # H L L
    assert p[1][1] < p[0][1]                     # downstep after a drop


def test_shape_pitch_pause_resets_declination():
    aps = [_phrase(2, 1, pause=True), _phrase(2, 1)]
    tutor.shape_pitch(aps)
    assert aps[0]["moras"][0]["pitch"] == aps[1]["moras"][0]["pitch"]
