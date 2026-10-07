"""Lesson metrics: the level, what counts as judged, mistake lists, and
progress across lessons."""

from app.progress import MIN_JUDGED, lesson_summary, overview, wilson


def phrase(status="correct", accent=2, observed=None, moras=("オ", "ト", "オ"), lemma="音", conf=0.9, p_exp=0.9,
           t=0.0):
    return {"text": lemma, "moras": list(moras), "accent": accent, "status": status,
            "observed": observed if observed is not None else (accent if status == "correct" else None),
            "detect_confidence": conf, "p_expected": p_exp, "mora_times": [[t, t + 0.1], [t + 0.1, t + 0.3]],
            "words": [{"lemma": lemma, "reading": "オト", "pos": "名詞"}, {"lemma": "を", "reading": "ヲ", "pos": "助詞"}]}


def utt(idx, phrases, start=None, length=2.0):
    start = idx * length if start is None else start
    return {"idx": idx, "start": start, "end": start + length, "text": "…", "skipped": None,
            "result": {"phrases": phrases}}


def test_wilson_level_rewards_saying_enough():
    assert round(wilson(2, 2)[0], 2) == 0.42
    assert round(wilson(19, 20)[0], 2) == 0.80
    assert round(wilson(285, 300)[0], 3) == 0.925
    assert wilson(0, 0) == (0.0, 1.0)


def test_two_perfect_words_score_below_a_long_good_lesson():
    short = lesson_summary([utt(0, [phrase(), phrase()])])
    long = lesson_summary([utt(i, [phrase("correct" if i % 20 else "error", observed=0)]) for i in range(200)])
    assert short["accuracy"] == 1.0 and long["accuracy"] == 0.95
    assert short["level"] < long["level"]
    assert not short["reliable"] and long["reliable"]


def test_only_correct_and_mistakes_are_judged():
    s = lesson_summary([utt(0, [phrase(), phrase("error", observed=0), phrase("uncertain"), phrase("unverified")]),
                        {"idx": 1, "start": 9, "end": 11, "text": "Hello", "skipped": "not Japanese", "result": None}])
    assert (s["judged"], s["correct"], s["mistakes"]) == (2, 1, 1)
    assert s["counts"] == {"correct": 1, "error": 1, "uncertain": 1, "unverified": 1}
    assert s["speaking_s"] == 2.0  # the skipped English line isn't your Japanese speech
    assert s["kinds"] == {"flat for accented": 1}
    assert s["by_type"]["accented"] == {"correct": 1, "judged": 2}


def test_obvious_and_repeated_mistakes():
    us = [utt(0, [phrase("error", observed=0, conf=0.6, p_exp=0.3, t=0.0)]),
          utt(1, [phrase("error", observed=0, conf=0.99, p_exp=0.01, t=2.0)]),
          utt(2, [phrase("error", observed=1, lemma="橋", moras=("ハ", "シ"), accent=2, t=4.0)])]
    s = lesson_summary(us)
    assert [o["utterance"] for o in s["obvious"]] == [1, 0, 2]  # surest first
    assert s["obvious"][0]["start"] == 2.0
    assert len(s["repeated"]) == 1  # 音 said flat twice; 橋 only once
    rep = s["repeated"][0]
    assert rep["count"] == 2 and rep["said"] == 0 and [o["utterance"] for o in rep["occurrences"]] == [0, 1]


def test_overview_trend_words_and_fixed():
    def lesson(i, acc):
        n = MIN_JUDGED + 40
        us = [utt(j, [phrase("error" if j < (1 - acc) * n else "correct", observed=0)]) for j in range(n)]
        return {"id": f"L{i}", "title": f"L{i}", "created_at": i, "status": "done", "summary": lesson_summary(us),
                "outdated": False}, us

    built = [lesson(i, a) for i, a in enumerate([0.7, 0.75, 0.8, 0.9, 0.95])]
    short = {"id": "S", "title": "S", "created_at": 9, "status": "done", "outdated": True,
             "summary": lesson_summary([utt(0, [phrase()])])}
    lessons = [b[0] for b in built] + [short]
    utts = {b[0]["id"]: b[1] for b in built} | {"S": [utt(0, [phrase()])]}
    o = overview(lessons, utts.__getitem__)
    assert o["reliable_lessons"] == 5
    levels = [s["level"] for s in o["lessons"][:5]]
    assert o["current_level"] == round(sum(levels[-3:]) / 3, 1)
    assert o["change"] > 0
    assert o["outdated"] == 1
    # 音 is wrong in every lesson, but correct in its last occurrences → fixed
    assert [w["lemma"] for w in o["fixed"]] == ["音"] and not o["work_on"]
    # a word still wrong at the end of the last lesson is one to work on
    utts["L4"][-1]["result"]["phrases"].append(phrase("error", observed=1, lemma="橋", moras=("ハ", "シ")))
    utts["L3"][-1]["result"]["phrases"].append(phrase("error", observed=1, lemma="橋", moras=("ハ", "シ")))
    o = overview(lessons, utts.__getitem__)
    assert [w["lemma"] for w in o["work_on"]] == ["橋"]
    assert o["work_on"][0]["lessons"] == 2 and o["work_on"][0]["last_wrong"]["lesson"] == "L4"
