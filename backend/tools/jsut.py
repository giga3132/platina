"""Reading the JSUT corpus (one native Tokyo-dialect speaker) with the
jsut-label phoneme timings and accent annotations.

JSUT is licensed for non-commercial research use; it is NOT part of this
repo. Download it yourself:
  audio:  http://ss-takashi.sakura.ne.jp/corpus/jsut_ver1.1.zip  (basic5000/wav)
  labels: https://github.com/sarulab-speech/jsut-label           (labels/basic5000)

Note: jsut-label writes heiban as accent = mora count (no 0), so heiban and
odaka phrases are indistinguishable in these labels.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LabPhrase:
    accent: int
    moras: list[tuple[float, float]]  # mora time spans (s)
    kana: list[str]
    final: bool = False  # followed by a pause / end of sentence


_LAB = re.compile(r"\^(?P<p2>[^-]+)-(?P<p>[^+]+)\+.*?/A:(?P<a1>[-\dx]+)\+(?P<a2>[\dx]+)\+"
                  r".*?/F:(?P<f1>[\dx]+)_(?P<f2>[\dx]+)")


def read_lab(path: Path) -> list[LabPhrase]:
    phrases: list[LabPhrase] = []
    prev_key = None
    for line in path.read_text().splitlines():
        s, e, lab = line.split(maxsplit=2)
        s, e = int(s) * 1e-7, int(e) * 1e-7
        m = _LAB.search(lab)
        if not m or m["p"] in ("sil", "pau") or m["a2"] == "xx":
            if phrases:
                phrases[-1].final = True
            prev_key = None
            continue
        a2, n, acc = int(m["a2"]), int(m["f1"]), int(m["f2"])
        if a2 == 1 and (prev_key is None or prev_key[1] != 1):
            phrases.append(LabPhrase(acc, [], []))
        elif not phrases:
            continue
        ph = phrases[-1]
        if prev_key is None or prev_key[1] != a2 or len(ph.moras) < a2:
            ph.moras.append((s, e))
            ph.kana.append(m["p"])
        else:
            ph.moras[-1] = (ph.moras[-1][0], e)
            ph.kana[-1] += m["p"]
        prev_key = (n, a2)
    return [p for p in phrases if p.moras]


_TAILS = {("a", "a"), ("a", "i"), ("i", "i"), ("u", "i"), ("e", "i"), ("o", "i"),
          ("u", "u"), ("o", "u"), ("e", "e"), ("o", "o")}


def special_romaji(kana: list[str]) -> list[bool]:
    """kana.special_moras for jsut-label phoneme moras (no word boundaries
    in the labels, so a phrase-final particle o after o is kept separate)."""
    out = []
    for i, m in enumerate(kana):
        if i == 0:
            out.append(False)
        elif m in ("N", "cl"):
            out.append(True)
        elif i == len(kana) - 1 and m == "o":
            out.append(False)
        else:
            out.append(len(m) == 1 and (kana[i - 1][-1], m) in _TAILS)
    return out


_KATAKANA_MORAS = (
    "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン"
    "ガギグゲゴザジズゼゾダヂヅデドバビブベボパピプペポヴ"
)
_YOON = ["キャ", "キュ", "キョ", "ギャ", "ギュ", "ギョ", "シャ", "シュ", "シェ", "ショ", "ジャ", "ジュ",
         "ジェ", "ジョ", "チャ", "チュ", "チェ", "チョ", "ニャ", "ニュ", "ニョ", "ヒャ", "ヒュ", "ヒョ",
         "ビャ", "ビュ", "ビョ", "ピャ", "ピュ", "ピョ", "ミャ", "ミュ", "ミョ", "リャ", "リュ", "リョ",
         "ファ", "フィ", "フェ", "フォ", "ティ", "ディ", "トゥ", "ドゥ", "ツァ", "ツェ", "ツォ", "ウィ",
         "ウェ", "ウォ", "イェ", "デュ", "テュ", "フュ", "ヴァ", "ヴィ", "ヴェ", "ヴォ"]


def romaji_to_kana() -> dict[str, str]:
    """jsut-label phoneme moras ('kya', 'N', 'cl') → katakana, derived from
    OpenJTalk's own kana → phoneme conversion."""
    import pyopenjtalk

    table = {"N": "ン", "cl": "ッ"}
    for kana in list(_KATAKANA_MORAS) + _YOON:
        ph = pyopenjtalk.g2p(kana).replace(" ", "")
        table.setdefault(ph, kana)
        table.setdefault(ph.lower(), kana)  # devoiced vowels come out upper-case
    return table
