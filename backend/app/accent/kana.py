"""Kana helpers: hiragana→katakana, mora splitting, particle pronunciation,
reading hints."""

import re

_SMALL = set("ァィゥェォャュョヮ")

# Particles written with one kana but pronounced with another.
PARTICLE_PRON = {"ヲ": "オ", "ハ": "ワ", "ヘ": "エ"}


def to_katakana(text: str) -> str:
    return "".join(
        chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c
        for c in text
    )


def to_hiragana(text: str) -> str:
    return "".join(
        chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c
        for c in text
    )


def is_kana(text: str) -> bool:
    return bool(text) and all(
        "ぁ" <= c <= "ゖ" or "ァ" <= c <= "ヺ" or c == "ー" for c in text
    )


def split_moras(kana: str) -> list[str]:
    """Split katakana into moras. Small ャュョ etc. merge with the previous
    kana; ッ, ン and ー each count as a mora of their own."""
    moras: list[str] = []
    for c in kana:
        if c in _SMALL and moras:
            moras[-1] += c
        elif "ァ" <= c <= "ヺ" or c == "ー":
            moras.append(c)
    return moras


def same_moras(a: list[str], b: list[str]) -> bool:
    """Same reading, allowing for long vowels written as ー (NHK イーマス,
    OpenJTalk キョー) where others spell them out, and ヲ said as オ."""
    return len(a) == len(b) and all(x == y or "ー" in (x, y) or {x, y} <= {"ヲ", "オ"}
                                    for x, y in zip(a, b))


# A reading the user gives for the kanji right before it: 日本{にっぽん}語,
# 行{おこな}った. Full-width braces too, as a Japanese IME types them.
_HINT = re.compile(r"([\u3400-\u9fff\uf900-\ufaff々〆ヶ]+)[{｛]([ぁ-ゖァ-ヺー]+)[}｝]")


def strip_reading_hints(text: str) -> tuple[str, dict[tuple[int, int], str]]:
    """Text without its reading hints, and each hint as {(start, end) of the
    kanji in the plain text: reading in katakana}."""
    plain, hints, last = [], {}, 0
    n = 0
    for m in _HINT.finditer(text):
        before = text[last:m.start()] + m.group(1)
        start = n + len(before) - len(m.group(1))
        plain.append(before)
        n += len(before)
        hints[(start, n)] = to_katakana(m.group(2))
        last = m.end()
    plain.append(text[last:])
    return "".join(plain), hints


def with_reading_hint(text: str, start: int, end: int, reading: str) -> str:
    """``text`` (which may hold hints) with a hint reading plain-text span
    [start, end) as ``reading``, replacing any hint overlapping it."""
    plain, hints = strip_reading_hints(text)
    hints = {(s, e): r for (s, e), r in hints.items() if e <= start or s >= end}
    hints[(start, end)] = to_katakana(reading)
    out = plain
    for (s, e), r in sorted(hints.items(), reverse=True):
        out = out[:e] + "{" + to_hiragana(r) + "}" + out[e:]
    return out


_VOWEL_ROWS = {
    "a": "アカサタナハマヤラワガザダバパャァ",
    "i": "イキシチニヒミリギジヂビピィ",
    "u": "ウクスツヌフムユルグズヅブプュゥヴ",
    "e": "エケセテネヘメレゲゼデベペェ",
    "o": "オコソトノホモヨロヲゴゾドボポョォ",
}
_VOWEL = {c: v for v, row in _VOWEL_ROWS.items() for c in row}
# second half of a long vowel or diphthong: (previous vowel, this mora)
_SYLLABLE_TAILS = {("a", "ア"), ("a", "イ"), ("i", "イ"), ("u", "イ"), ("e", "イ"), ("o", "イ"),
                   ("u", "ウ"), ("o", "ウ"), ("e", "エ"), ("o", "オ")}


def vowel_of(mora: str) -> str | None:
    return _VOWEL.get(mora[-1]) if mora else None


def special_moras(moras: list[str], word_starts: set[int] | None = None) -> list[bool]:
    """True for moras that can't start a syllable: ー ン ッ and the second
    half of a long vowel / diphthong (セ[イ], ナ[イ], コ[ウ]). Pitch keeps the
    previous mora's level through them. A mora that starts a new word (e.g.
    the particle を after オト) is never a tail."""
    out = []
    for i, m in enumerate(moras):
        if i == 0 or (word_starts and i in word_starts):
            out.append(False)
        elif m in ("ー", "ン", "ッ"):
            out.append(True)
        else:
            out.append((vowel_of(moras[i - 1]), m) in _SYLLABLE_TAILS)
    return out
