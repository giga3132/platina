from pathlib import Path

import pytest
import yaml

from app.accent.engine import analyze_text, notation
from app.accent.notation import phrase_notation, pitch_pattern
from app.accent.overrides import OverrideStore

GOLD = yaml.safe_load((Path(__file__).parent / "gold" / "sentences.yaml").read_text())


@pytest.mark.parametrize("entry", [
    pytest.param(e, id=e["text"], marks=pytest.mark.xfail(reason=e["known_issue"], strict=True))
    if "known_issue" in e else pytest.param(e, id=e["text"])
    for e in GOLD
])
def test_gold(entry):
    assert notation(analyze_text(entry["text"])) == entry["expected"]


def test_gold_match_rate(capsys):
    hits = sum(notation(analyze_text(e["text"])) == e["expected"] for e in GOLD)
    verified = sum(e.get("verified", False) for e in GOLD)
    with capsys.disabled():
        print(f"\ngold: {hits}/{len(GOLD)} match ({verified} NHK-verified entries)")


def test_known_issue_is_flagged_uncertain():
    phrases = analyze_text("日本語を話す。")
    assert phrases[0].confidence == "uncertain"


def test_notation_and_pitch():
    assert phrase_notation(["オ", "ト", "オ"], 2) == "オト＼オ"
    assert phrase_notation(["キ", "イ", "タ"], 0) == "キイタ━"
    assert pitch_pattern(3, 0) == [False, True, True]
    assert pitch_pattern(3, 1) == [True, False, False]
    assert pitch_pattern(4, 2) == [False, True, False, False]


def test_override_wins_and_marks_nhk():
    store = OverrideStore(":memory:")
    store.put("聞く", "きく", [1], note="deliberately wrong, to see it applied")
    phrases = analyze_text("音を聞いた。", store)
    assert phrases[1].notation == "キ＼イタ"
    assert phrases[1].confidence == "nhk"
    assert phrases[0].confidence == "agree"  # 音 has no override


def test_override_multiple_accents_are_alternatives():
    store = OverrideStore(":memory:")
    store.put("音", "おと", [2, 0])
    assert analyze_text("音を聞いた。", store)[0].alternatives == [2, 0]


def test_api_expected(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import main

    monkeypatch.setattr(main, "overrides", OverrideStore(tmp_path / "o.sqlite"))
    client = TestClient(main.app)
    r = client.post("/expected", json={"text": "音を聞いた。"})
    assert r.status_code == 200
    assert r.json()["notation"] == "オト＼オ キイタ━"

    client.put("/overrides", json={"lemma": "音", "reading": "おと", "accents": [2]})
    assert client.get("/overrides").json()[0]["reading"] == "オト"
    assert client.post("/expected", json={"text": "音を聞いた。"}).json()["phrases"][0]["confidence"] == "nhk"


def test_api_add_gold(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import main

    gold = tmp_path / "gold.yaml"
    gold.write_text("- {text: 音を聞いた。, expected: オト＼オ キイタ━, verified: true}\n")
    monkeypatch.setattr(main, "GOLD", gold)
    TestClient(main.app).post("/gold", json={"text": "橋を渡る。", "expected": "ハシ＼オ  ワタル━"})
    entries = yaml.safe_load(gold.read_text())
    assert entries[-1] == {"text": "橋を渡る。", "expected": "ハシ＼オ ワタル━", "verified": True}
