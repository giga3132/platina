"""Lexical sources: tokenize text into Morphs carrying base accent information.

Two independent lexicons are read through MeCab (fugashi):

* UniDic 3.1 — primary. Accent fields aType / aConType / aModType.
* OpenJTalk's naist-jdic — cross-check. Read raw, i.e. *before* OpenJTalk's
  own accent rules run, so both lexicons go through the same rule engine
  (``rules.py``) and any disagreement is a genuine lexical disagreement.

POS tags are normalized to the IPA-style names OpenJTalk's rules use
(名詞 / 動詞 / 助詞 / 接頭詞 / 記号 …) so one rule set serves both sources.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

import fugashi
import pyopenjtalk
import unidic

from .kana import PARTICLE_PRON, is_kana, split_moras, to_katakana


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


def unidic_morphs(text: str) -> list[Morph]:
    words = list(_unidic_tagger()(text))
    spans = _offsets(text, [w.surface for w in words])
    out = []
    for w, (s, e) in zip(words, spans):
        f = w.feature
        pos, g1, g3 = _unidic_pos(f)
        kana = getattr(f, "kana", None)
        if pos == "助詞":
            kana = getattr(f, "pron", None) or kana
        out.append(Morph(
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
        ))
    return out


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
        pos, g1, g2, g3, ctype, cform, orig, read, _pron, accmora, chain = f[:11]
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
        ))
    return out
