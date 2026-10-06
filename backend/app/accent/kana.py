"""Kana helpers: hiragana→katakana, mora splitting, particle pronunciation."""

_SMALL = set("ァィゥェォャュョヮ")

# Particles written with one kana but pronounced with another.
PARTICLE_PRON = {"ヲ": "オ", "ハ": "ワ", "ヘ": "エ"}


def to_katakana(text: str) -> str:
    return "".join(
        chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c
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
