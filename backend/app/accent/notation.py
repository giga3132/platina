"""Accent notation: ＼ after the accent nucleus, ━ at the end of a heiban phrase.

    音を聞いた。 → オト＼オ キイタ━
"""


def phrase_notation(moras: list[str], accent: int) -> str:
    if accent == 0:
        return "".join(moras) + "━"
    return "".join(moras[:accent]) + "＼" + "".join(moras[accent:])


def pitch_pattern(n_moras: int, accent: int) -> list[bool]:
    """High (True) / low (False) per mora, phrase-initially."""
    if n_moras == 0:
        return []
    if accent == 1:
        return [True] + [False] * (n_moras - 1)
    end = n_moras if accent == 0 else accent
    return [False] + [i < end for i in range(1, n_moras)]
