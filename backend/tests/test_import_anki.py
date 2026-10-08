from tools.import_anki import head_context, modified_note, parse_head, resolve


def test_card_context():
    assert head_context("ひと【人】<div>（〜を呼ぶ）</div>") == ""
    assert head_context("ひと【人】<div>（「話題の〜が」「優しい〜に」など修飾語を伴って）</div>") == "modified"
    assert head_context("した【下】<div>（「〜におりる」など修飾語を伴わないで）</div>") == "unmodified"
    assert head_context("きのう［名詞］<div>（〜まで留守にしていた）</div>") == "noun"
    assert head_context("きのう［副詞］<div>（〜渋谷で会った）</div>") == "adverb"
    assert head_context("そう《×然》［感動詞］<div>（あ，〜）</div>") == ""


def test_modified_use_in_a_note():
    back = "<div>ウチ━</div><div>（「彼の〜に行く」など，修飾語を伴った場合は「…ウチ＼（ニ）…」）</div>"
    assert modified_note(back) == ("ウチ", 2)
    assert modified_note("<div>ウチ━</div>") is None


def test_parse_head_forms():
    assert parse_head("うえ【上，うえ】<div>（…）</div>") == (["上", "うえ"], "うえ")
    assert parse_head("きのう［名詞］<div>（…）</div>") == (["きのう"], None)
    assert parse_head("いぬ【犬《×狗》】") == (["犬"], "いぬ")


def test_inflected_token_is_not_taken_for_its_lemma():
    # いい is tagged as 言う's 連用形; イー must not land on 言う (イウ)
    assert resolve(["いい"], None, [("イー", 1)])[0] != "言う"
    assert resolve(["言う"], "いう", [("イー", 0)])[:2] == ("言う", "イウ")


def test_form_lines():
    from tools.import_anki import form_lines
    parsed = [("タカイ", 2), ("タカカッタ", 1), ("タカク", 1), ("タカク", 2), ("オモイ", 0)]
    assert form_lines(parsed, "タカイ", "タカイ", True) == [("タカカッタ", 1), ("タカク", 1), ("タカク", 2)]
    # a noun's forms start with the whole word
    assert form_lines([("エキ", 1), ("エキオ", 1), ("エイ", 1)], "エキ", "エキ", False) == [("エキオ", 1)]
