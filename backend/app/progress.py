"""Lesson metrics: how one lesson went, and progress across lessons.

Only phrases Platina could judge count: "correct" and "error". Unclear
phrases, phrases whose dictionary accent is unsure, and native variants
count for nothing either way.

The level is the lower end of a 90 % confidence range for the share of
judged phrases said correctly (Wilson lower bound), times 100. With little
speech the range is wide and the level low (2 of 2 correct ≈ 42, 19 of 20
≈ 80, 285 of 300 ≈ 92): staying quiet can't score high, and talking more
doesn't help if the accent is wrong. Lessons too short to be reliable are
shown but left out of the trend.
"""

from __future__ import annotations

import math
from collections import defaultdict

from .accent.variants import phrase_key

Z = 1.645  # 90 % two-sided
MIN_JUDGED = 60  # judged phrases for a lesson to count in the trend
MIN_SPEAKING_S = 180.0
TOP_OBVIOUS = 10
FUNCTION_POS = {"助詞", "助動詞", "記号"}


def wilson(correct: int, n: int, z: float = Z) -> tuple[float, float]:
    """Confidence range (low, high) for a proportion correct/n."""
    if n == 0:
        return 0.0, 1.0
    p = correct / n
    centre = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    denom = 1 + z * z / n
    return max(0.0, (centre - half) / denom), min(1.0, (centre + half) / denom)


def kind_of(expected: int, said: int, n: int) -> str:
    """The kind of mistake: accent `said` where `expected` was right."""
    e_flat, s_flat = expected in (0, n), said in (0, n)
    if e_flat and not s_flat:
        return "accented for flat"
    if s_flat and not e_flat:
        return "flat for accented"
    return "1 mora off" if abs(expected - said) == 1 else "2+ moras off"


def _judged(utterances: list[dict]):
    """(utterance, phrase index, phrase) for every judged phrase."""
    for u in utterances:
        for k, p in enumerate((u.get("result") or {}).get("phrases", [])):
            if p.get("status") in ("correct", "error"):
                yield u, k, p


def _flat(p: dict) -> bool:
    return p["accent"] in (0, len(p["moras"]))


def lesson_summary(utterances: list[dict]) -> dict:
    """Metrics of one lesson from its analyzed utterances
    ({idx, start, end, text, skipped, result: {phrases}})."""
    spoken = [u for u in utterances if u.get("result") and not u.get("skipped")]
    speaking_s = sum(u["end"] - u["start"] for u in spoken)
    statuses: dict[str, int] = defaultdict(int)
    for u in spoken:
        for p in u["result"]["phrases"]:
            if p.get("moras"):
                statuses[p["status"]] += 1
    judged = list(_judged(spoken))
    correct = sum(p["status"] == "correct" for _, _, p in judged)
    lo, hi = wilson(correct, len(judged))

    by_type = {"flat": [0, 0], "accented": [0, 0]}  # [correct, judged]
    kinds: dict[str, int] = defaultdict(int)
    obvious, groups = [], {}
    for u, k, p in judged:
        t = by_type["flat" if _flat(p) else "accented"]
        t[1] += 1
        if p["status"] == "correct":
            t[0] += 1
            continue
        n = len(p["moras"])
        said = p.get("observed")
        if said is None:
            continue
        kinds[kind_of(p["accent"], said, n)] += 1
        at = _occurrence(u, k, p)
        obvious.append({**at, "text": p["text"], "moras": p["moras"], "accent": p["accent"], "said": said,
                        "score": round((p.get("detect_confidence") or 0) * (1 - (p.get("p_expected") or 0)), 3)})
        key = (phrase_key([w["lemma"] for w in p.get("words", [])], p["moras"]), 0 if said == n else said)
        g = groups.setdefault(key, {"text": p["text"], "moras": p["moras"], "accent": p["accent"], "said": said,
                                    "occurrences": []})
        g["occurrences"].append(at)
    obvious.sort(key=lambda o: -o["score"])
    repeated = sorted((dict(g, count=len(g["occurrences"])) for g in groups.values() if len(g["occurrences"]) >= 2),
                      key=lambda g: -g["count"])
    return {
        "speaking_s": round(speaking_s, 1),
        "utterances": len(spoken),
        "counts": dict(statuses),
        "judged": len(judged),
        "correct": correct,
        "mistakes": len(judged) - correct,
        "accuracy": round(correct / len(judged), 4) if judged else None,
        "level": round(100 * lo, 1),
        "level_range": [round(100 * lo, 1), round(100 * hi, 1)],
        "reliable": len(judged) >= MIN_JUDGED and speaking_s >= MIN_SPEAKING_S,
        "by_type": {t: {"correct": c, "judged": n} for t, (c, n) in by_type.items()},
        "kinds": dict(kinds),
        "obvious": obvious[:TOP_OBVIOUS],
        "repeated": repeated,
    }


def _occurrence(u: dict, k: int, p: dict) -> dict:
    times = p.get("mora_times") or [[u["start"], u["end"]]]
    return {"utterance": u["idx"], "phrase": k, "start": times[0][0], "end": times[-1][1]}


def overview(lessons: list[dict], utterances_of) -> dict:
    """Progress across lessons (oldest first). `utterances_of(lesson_id)`
    gives a lesson's utterances, for words that keep going wrong."""
    done = [ls for ls in lessons if ls["status"] == "done" and ls.get("summary")]
    series = [{"id": ls["id"], "title": ls["title"], "created_at": ls["created_at"],
               "level": ls["summary"]["level"], "level_range": ls["summary"]["level_range"],
               "accuracy": ls["summary"]["accuracy"], "judged": ls["summary"]["judged"],
               "speaking_s": ls["summary"]["speaking_s"], "reliable": ls["summary"]["reliable"],
               "by_type": ls["summary"]["by_type"], "kinds": ls["summary"]["kinds"],
               "outdated": ls.get("outdated", False)}
              for ls in done]
    reliable = [s["level"] for s in series if s["reliable"]]
    current = sum(reliable[-3:]) / len(reliable[-3:]) if reliable else None
    change = (current - sum(reliable[:3]) / 3) if len(reliable) >= 4 else None

    # every judged occurrence of each content word, oldest first
    seen: dict[tuple[str, str], list[tuple[str, bool, dict]]] = defaultdict(list)
    for ls in done:
        for u, k, p in _judged(utterances_of(ls["id"])):
            words = {(w["lemma"], w["reading"]) for w in p.get("words", []) if w.get("pos") not in FUNCTION_POS}
            for w in words:
                seen[w].append((ls["id"], p["status"] == "correct", {"lesson": ls["id"], **_occurrence(u, k, p),
                                                                      "text": p["text"]}))
    work_on, fixed = [], []
    for (lemma, reading), occ in seen.items():
        wrong = [o for o in occ if not o[1]]
        if not wrong:
            continue
        entry = {"lemma": lemma, "reading": reading, "wrong": len(wrong), "total": len(occ),
                 "lessons": len({o[0] for o in wrong}), "last_wrong": wrong[-1][2]}
        if all(o[1] for o in occ[-3:]) and len(occ) - len(wrong) >= 3:
            fixed.append(entry)
        elif len(wrong) >= 3 or entry["lessons"] >= 2:
            work_on.append(entry)
    work_on.sort(key=lambda e: (-e["wrong"], -e["lessons"]))
    fixed.sort(key=lambda e: -e["wrong"])
    return {
        "lessons": series,
        "current_level": None if current is None else round(current, 1),
        "change": None if change is None else round(change, 1),
        "speaking_s": round(sum(s["speaking_s"] for s in series), 1),
        "reliable_lessons": len(reliable),
        "min_judged": MIN_JUDGED,
        "min_speaking_s": MIN_SPEAKING_S,
        "work_on": work_on[:15],
        "fixed": fixed[:15],
        "outdated": sum(s["outdated"] for s in series),
    }
