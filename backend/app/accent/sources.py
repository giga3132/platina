"""Lexical sources: tokenize text into Morphs carrying base accent information.

Two independent lexicons are read through MeCab (fugashi):

* UniDic 3.1 — primary. Accent fields aType / aConType / aModType.
  MeCab's single best path reads homographs without regard to context
  (日本語 → ニッポンゴ, 明日 → アス), so the reading is chosen from its
  n-best paths: the user's reading hints first, then agreement with
  OpenJTalk, then readings the user has NHK accents for (``unidic_morphs``).
* OpenJTalk's naist-jdic — cross-check. Read raw, i.e. *before* OpenJTalk's
  own accent rules run, so both lexicons go through the same rule engine
  (``rules.py``) and any disagreement is a genuine lexical disagreement.

POS tags are normalized to the IPA-style names OpenJTalk's rules use
(名詞 / 動詞 / 助詞 / 接頭詞 / 記号 …) so one rule set serves both sources.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache

import fugashi
import pyopenjtalk
import unidic

from .kana import PARTICLE_PRON, is_kana, same_moras, split_moras, to_hiragana, to_katakana


@dataclass
class Morph:
    surface: str
    start: int
    end: int
    pos: str  # IPA-style: 名詞, 動詞, 形容詞, 助詞, 助動詞, 接頭詞, 記号, ...
    pos_group1: str = "*"  # 接尾, 非自立, 形容動詞語幹, サ変接続, 副詞可能, 数, ...
    pos_group3: str = "*"  # 姓 / 名 for person names
    cform: str = "*"
    ctype: str = "*"
    lemma: str = ""
    lemma_reading: str = ""
    moras: list[str] = field(default_factory=list)
    accents: list[int] = field(default_factory=list)  # [] = unknown
    con_type: str = "*"
    mod_type: str = "*"
    source: str = ""
    alt_readings: list[str] = field(default_factory=list)  # other likely moras for this span (UniDic)
    pron: str = ""  # pronunciation, for OpenJTalk: 実は ジツワ where moras has ジツハ

    @property
    def is_function_word(self) -> bool:
        return self.pos in ("助詞", "助動詞") or self.pos_group1 == "接尾"

    @property
    def is_symbol(self) -> bool:
        return self.pos == "記号"


def _offsets(text: str, surfaces: list[str]) -> list[tuple[int, int]]:
    spans, cursor = [], 0
    for s in surfaces:
        i = text.find(s, cursor)
        if i < 0:
            i = cursor
        spans.append((i, i + len(s)))
        cursor = i + len(s)
    return spans


def _parse_accents(value: str | None) -> list[int]:
    if not value or value == "*":
        return []
    out = []
    for part in value.split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            out.append(int(part))
    return out


def _display_moras(kana: str | None, surface: str, pos: str) -> list[str]:
    if not kana or kana == "*":
        kana = to_katakana(surface) if is_kana(surface) else ""
    kana = to_katakana(kana)
    if pos == "助詞" and kana in PARTICLE_PRON:
        kana = PARTICLE_PRON[kana]
    return split_moras(kana)


# --- UniDic ---------------------------------------------------------------

def _strip_gloss(lemma: str) -> str:
    """UniDic tags loanword lemmas with their origin: マレーシア-Malaysia."""
    head, sep, tail = lemma.partition("-")
    return head if sep and tail.isascii() else lemma


@lru_cache(maxsize=1)
def _unidic_tagger() -> fugashi.Tagger:
    return fugashi.Tagger('-d "%s"' % unidic.DICDIR)


def _unidic_pos(f) -> tuple[str, str, str]:
    p1, p2, p3, p4 = f.pos1, f.pos2, f.pos3, f.pos4
    if p1 == "名詞":
        if p2 == "固有名詞":
            return "名詞", "固有名詞", p4 if p4 in ("姓", "名") else "*"
        if p2 == "数詞":
            return "名詞", "数", "*"
        group = {"サ変可能": "サ変接続", "形状詞可能": "形容動詞語幹",
                 "副詞可能": "副詞可能"}.get(p3, "一般")
        return "名詞", group, "*"
    if p1 == "代名詞":
        return "名詞", "代名詞", "*"
    if p1 == "形状詞":
        return "名詞", "形容動詞語幹", "*"
    if p1 == "接尾辞":
        base = {"形容詞的": "形容詞", "動詞的": "動詞"}.get(p2, "名詞")
        return base, "接尾", "*"
    if p1 == "接頭辞":
        return "接頭詞", "*", "*"
    if p1 in ("動詞", "形容詞"):
        return p1, "非自立" if p2 == "非自立可能" else "自立", "*"
    if p1 in ("補助記号", "記号", "空白"):
        return "記号", p2, "*"
    return p1, p2, "*"


def _unidic_morph(w, s: int, e: int) -> Morph:
    f = w.feature
    pos, g1, g3 = _unidic_pos(f)
    kana = getattr(f, "kana", None)
    if pos == "助詞":
        kana = getattr(f, "pron", None) or kana
    return Morph(
        surface=w.surface, start=s, end=e,
        pos=pos, pos_group1=g1, pos_group3=g3,
        cform=getattr(f, "cForm", None) or "*",
        ctype=getattr(f, "cType", None) or "*",
        lemma=_strip_gloss(getattr(f, "lemma", None) or w.surface),
        lemma_reading=to_katakana(getattr(f, "lForm", None) or ""),
        moras=[] if pos == "記号" else _display_moras(kana, w.surface, pos),
        accents=_parse_accents(getattr(f, "aType", None)),
        con_type=getattr(f, "aConType", None) or "*",
        mod_type=getattr(f, "aModType", None) or "*",
        source="unidic",
    )


def _path(text: str, words) -> list[Morph]:
    spans = _offsets(text, [w.surface for w in words])
    return [_unidic_morph(w, s, e) for w, (s, e) in zip(words, spans)]


N_BEST = 8  # 明日 アシタ is MeCab's 5th path
ALT_RANK = 4  # other readings offered from paths this good, or backed by OpenJTalk / NHK


def _moras_from(path: list[Morph], start: int, end: int) -> list[str] | None:
    """Moras of the morphs from the one starting at ``start`` through the one
    reaching ``end``; None if no morph starts there."""
    out, inside = [], False
    for m in path:
        if m.start == start:
            inside = True
        if inside:
            out += m.moras
            if m.end >= end:
                return out
    return None


def reads_as(path: list[Morph], start: int, end: int, reading: str) -> bool:
    """The path reads text[start:end] (plus any okurigana) as ``reading``."""
    want = split_moras(reading)
    got = _moras_from(path, start, end)
    return got is not None and same_moras(got[:len(want)], want)


def _disagreement(path: list[Morph], reference: list[Morph]) -> int:
    """Reference words the path reads differently over the same span. Only
    readings count: a path isn't better for splitting text like the
    reference does (ましょ + う vs ましょう)."""
    n = 0
    for r in reference:
        if r.is_symbol or not r.moras or not any(m.end == r.end for m in path):
            continue
        got = _moras_from(path, r.start, r.end)
        if got is not None and not same_moras(got, r.moras) \
                and not same_moras(got, split_moras(r.pron)):
            n += 1
    return n


def kanji_part(m: Morph, moras: list[str]) -> tuple[int, str] | None:
    """Length of a morph's leading kanji and their reading in hiragana, with
    trailing okurigana cut off the reading (行っ オコナッ → 1, おこな)."""
    k = len(m.surface)
    while k and is_kana(m.surface[k - 1]):
        k -= 1
    if not k or any(is_kana(c) for c in m.surface[:k]):
        return None
    tail = split_moras(to_katakana(m.surface[k:]))
    if tail and not same_moras(moras[-len(tail):], tail):
        return None
    return k, to_hiragana("".join(moras[:len(moras) - len(tail)]))


def unidic_morphs(text: str, reference: list[Morph] | None = None,
                  prefer: Callable[[list[Morph]], int] | None = None,
                  hints: dict[tuple[int, int], str] | None = None,
                  compounds: dict[tuple[int, int], str] | None = None) -> list[Morph]:
    """Morphs of MeCab's n-best UniDic path that best fits the reading
    ``hints`` (span → katakana), then ``compounds`` (span → katakana, the
    reading of an NHK word stored whole that the tagger splits), then the evidence for its readings: words
    the user has NHK accents for (``prefer`` counts them) minus words the ``reference``
    (OpenJTalk) reads differently. Neither source alone outvotes the other
    (OpenJTalk reads 今オランダ as コン, NHK lists 実 ミ); ties go to MeCab's
    order."""
    if not text:
        return []
    tagger = _unidic_tagger()
    squeezed = "".join(text.split())
    paths = [_path(text, p) for p in tagger.nbestToNodeList(text, N_BEST)]
    paths = [p for p in paths if "".join(m.surface for m in p) == squeezed] \
        or [_path(text, list(tagger(text)))]
    hints = hints or {}

    def split(p: list[Morph]) -> tuple:
        return tuple((m.start, m.end) for m in p)

    best_split = split(paths[0])
    # an NHK compound counts only where the tagger splits it (日本 + 人), so
    # a one-word entry (実 ミ) never forces its reading on the text
    compounds = {(s, e): r for (s, e), r in (compounds or {}).items()
                 if sum(s <= a and b <= e for a, b in best_split) > 1}

    # Only the reading is chosen: a path split differently from MeCab's best
    # wins only through a hint (何{なに}人) or an NHK compound, and of paths with the same
    # readings the first keeps its lemmas and POS.
    first: dict[tuple, int] = {}
    for i, p in enumerate(paths):
        first.setdefault((split(p), tuple("".join(m.moras) for m in p)), i)

    def score(i: int) -> tuple:
        p = paths[i]
        return (sum(reads_as(p, s, e, r) for (s, e), r in hints.items()),
                sum(reads_as(p, s, e, r) and any(m.end == e for m in p)
                    for (s, e), r in compounds.items()),
                split(p) == best_split,
                (prefer(p) if prefer else 0)
                - (_disagreement(p, reference) if reference else 0),
                -i)

    best = max(first.values(), key=score)
    chosen = paths[best]

    for k, m in enumerate(chosen):
        if not kanji_part(m, m.moras):
            continue
        # a "suffix" with no word before it (方が良い, parsed 方 カタ) is a word
        prev = chosen[k - 1] if k else None
        suffix = m.pos_group1 == "接尾" and prev is not None and not (
            prev.is_function_word or prev.is_symbol)
        alts: list[str] = []
        for i, p in enumerate(paths):
            for o in p:
                if (o.start, o.end) != (m.start, m.end) or same_moras(o.moras, m.moras) \
                        or any(same_moras(split_moras(a), o.moras) for a in alts):
                    continue
                # A rank among MeCab's best or an NHK entry backs only the same
                # kind of word (語 ゴ, not the suffix 語り カタリ); OpenJTalk
                # reading it so in this very text backs any.
                same_kind = (o.pos, o.pos_group1 == "接尾") == (m.pos, suffix)
                backed = ((same_kind and (i < ALT_RANK or (prefer and prefer([o]))))
                          or (reference and any((r.start, r.end) == (o.start, o.end)
                                                and same_moras(r.moras, o.moras) for r in reference)))
                # 一 イッ (一日中) is 一 イチ before a consonant, not another reading
                sokuon = o.moras[-1:] == ["ッ"] and not is_kana(o.surface[-1])
                if backed and not sokuon and kanji_part(o, o.moras):
                    alts.append("".join(o.moras))
        m.alt_readings = alts
    return chosen


# --- OpenJTalk (naist-jdic, raw lexicon) ----------------------------------

@lru_cache(maxsize=1)
def _openjtalk_tagger() -> fugashi.GenericTagger:
    pyopenjtalk.g2p("あ")  # makes pyopenjtalk download its dictionary if needed
    d = pyopenjtalk.OPEN_JTALK_DICT_DIR
    d = d.decode() if isinstance(d, bytes) else d
    dicrc = os.path.join(d, "dicrc")
    if not os.path.exists(dicrc):  # OpenJTalk ships the dict without one
        with open(dicrc, "w") as fh:
            fh.write("cost-factor = 800\n"
                     "bos-feature = BOS/EOS,*,*,*,*,*,*,*,*,*,*,*,*\n")
    rc = os.path.join(unidic.DICDIR, "mecabrc")  # any (dummy) rc file works
    return fugashi.GenericTagger('-r "%s" -d "%s"' % (rc, d))


def openjtalk_morphs(text: str) -> list[Morph]:
    words = list(_openjtalk_tagger()(text))
    spans = _offsets(text, [w.surface for w in words])
    out = []
    for w, (s, e) in zip(words, spans):
        f = list(w.feature) + ["*"] * 11
        pos, g1, g2, g3, ctype, cform, orig, read, pron, accmora, chain = f[:11]
        acc = accmora.split("/")[0] if accmora else "*"
        if pos == "フィラー":
            pos = "感動詞"
        out.append(Morph(
            surface=w.surface, start=s, end=e,
            pos=pos, pos_group1=g1, pos_group3=g3,
            cform=cform, ctype=ctype,
            lemma=orig if orig != "*" else w.surface,
            lemma_reading="",
            moras=[] if pos == "記号" else _display_moras(read, w.surface, pos),
            accents=_parse_accents(acc),
            con_type=chain or "*",
            source="openjtalk",
            pron=pron if pron != "*" else "",
        ))
    return out
