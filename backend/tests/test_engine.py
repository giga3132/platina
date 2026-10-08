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


def test_te_iru_can_be_said_as_one_phrase():
    phrases = analyze_text("本を読んでいます。")
    yonde = phrases[1]
    assert yonde.notation == "ヨ＼ンデ"
    assert yonde.merge_accents == [1]  # ヨ＼ンデイマス: the first drop wins


def test_approved_native_variant_is_accepted(tmp_path):
    from app.accent.variants import VariantStore, phrase_key

    store = VariantStore(tmp_path / "v.sqlite")
    p = analyze_text("音を聞いた。")[1]
    key = phrase_key([w.lemma for w in p.words], p.moras)
    store.propose(key, 1, speakers=12, total=40, examples=["jvs001"])
    p = analyze_text("音を聞いた。", variants=store)[1]
    assert p.proposed_variants == [1] and 1 not in p.alternatives
    store.set_status(key, 1, "approved")
    p = analyze_text("音を聞いた。", variants=store)[1]
    assert p.native_variants == [1] and 1 in p.alternatives and p.accent == 0


def test_te_mo_after_heiban_verb_also_falls_after_te():
    # イワレテモ and the newer イワレテ＼モ are both standard
    assert analyze_text("言われても。")[0].alternatives == [0, 4]
    assert analyze_text("遊んでも。")[0].alternatives == [0, 4]
    assert analyze_text("書いても。")[0].alternatives == [1]


def test_accented_te_form_keeps_its_drop():
    assert notation(analyze_text("持ってきてない。")) == "モ＼ッテ キ＼テナイ"
    assert notation(analyze_text("書いてない。")) == "カ＼イテナイ"
    assert notation(analyze_text("遊んでない。")) == "アソンデナイ━"


def _deck_store():
    # rows as tools/import_anki.py stores the NHK cards for 人 and 昨日
    store = OverrideStore(":memory:")
    store.put("人", "ひと", [0])
    store.put("人", "ひと", [2], context="modified")
    store.put("昨日", "きのう", [2, 0])
    store.put("昨日", "きのう", [2], context="noun")
    store.put("昨日", "きのう", [0], context="adverb")
    return store


@pytest.mark.parametrize("text, expected", [
    ("人を呼ぶ。", "ヒトオ━ ヨブ━"),
    ("優しい人に会った。", "ヤサシイ━ ヒト＼ニ ア＼ッタ"),
    ("話題の人が来た。", "ワダイノ━ ヒト＼ガ キ＼タ"),
    ("あの人が来た。", "アノ━ ヒト＼ガ キ＼タ"),
    ("昨日まで留守にしていた。", "キノ＼ウマデ ル＼スニ シテ━ イタ━"),
    ("昨日渋谷で会った。", "キノウ━ シブヤデ━ ア＼ッタ"),
    ("昨日、会った。", "キノウ━ ア＼ッタ"),
])
def test_override_for_one_use(text, expected):
    assert notation(analyze_text(text, _deck_store())) == expected


def test_override_for_one_use_is_explained_and_exclusive():
    p = analyze_text("優しい人に会った。", _deck_store())[1]
    assert p.alternatives == [2]
    assert p.reasons == ["NHK modified use of 人"]
    assert p.confidence == "nhk"


def test_override_store_migrates_and_deletes_per_use(tmp_path):
    import sqlite3
    path = tmp_path / "o.sqlite"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE overrides (lemma TEXT NOT NULL, reading TEXT NOT NULL, accents TEXT NOT NULL,"
               " note TEXT NOT NULL DEFAULT '', updated_at REAL NOT NULL, PRIMARY KEY (lemma, reading))")
    db.execute("INSERT INTO overrides VALUES ('人', 'ヒト', '[0, 2]', '', 0)")
    db.commit()
    db.close()
    store = OverrideStore(path)
    assert store.all()[0]["context"] == ""
    store.put("人", "ひと", [2], context="modified")
    assert len(store.all()) == 2
    store.delete("人", "ひと", "modified")
    assert [o["accents"] for o in store.all()] == [[0, 2]]
    with pytest.raises(ValueError):
        store.put("人", "ひと", [2], context="sometimes")


@pytest.mark.parametrize("text, alternatives", [
    ("高く", [2, 1]),        # タカ＼ク, タ＼カク (NHK lists both)
    ("高かった", [2, 1]),
    ("小さく", [3, 1]),      # チ＼ーサク: not on the long vowel's tail
    ("酸っぱく", [3]),       # never on ッ
    ("赤かった", [2]),       # a flat adjective has one かった form
    ("高くない。", [2, 1]),  # not UniDic's タカク＼ナイ
    ("赤くない。", [4, 3]),  # アカクナ＼イ, newer アカク＼ナイ
    ("高くなる。", [2, 1]),
])
def test_adjective_forms(text, alternatives):
    assert analyze_text(text)[0].alternatives == alternatives


def test_adjective_listed_flat_first_conjugates_as_flat():
    store = OverrideStore(":memory:")
    store.put("甘い", "あまい", [0, 2])
    assert analyze_text("甘くて", store)[0].alternatives == [2]
    assert analyze_text("甘く", store)[0].alternatives == [0]


def test_nhk_forms_win_over_the_rules():
    store = OverrideStore(":memory:")
    store.put("難しい", "むずかしい", [0, 4])
    store.put_form("難しい", "むずかしい", "ムズカシカッタ", [4, 3])
    store.put_form("高い", "たかい", "タカク", [1, 2])
    store.put_form("駅", "えき", "エキオ", [1])
    assert analyze_text("難しかった。", store)[0].alternatives == [4, 3]
    assert analyze_text("高く", store)[0].alternatives == [1, 2]
    # a longer phrase starting with a form that has its drop keeps it
    assert analyze_text("高くない。", store)[0].alternatives == [1, 2]
    p = analyze_text("駅を探す。", store)[0]
    assert (p.alternatives, p.reasons) == ([1], ["NHK form of 駅"])


def test_flat_nhk_form_does_not_decide_a_longer_phrase():
    store = OverrideStore(":memory:")
    store.put_form("赤い", "あかい", "アカク", [0])
    assert analyze_text("赤くない。", store)[0].alternatives == [4, 3]
