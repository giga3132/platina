"""Accent rules: inflection (aModType), accent-phrase grouping and accent
combination (aConType).

Phrase grouping is a port of OpenJTalk's njd_set_accent_phrase.c, and the
combination rules port njd_set_accent_type.c, extended with the rules the
UniDic manual (表9–12) defines that OpenJTalk lacks (M1/M2/M4, F6, P4, P13).
Corrections to rules found to disagree with NHK live in RULE_CORRECTIONS.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .sources import Morph

# Rule corrections, each backed by an NHK-checked gold sentence.
# (pattern in aConType/chain_rule, replacement, reason)
RULE_CORRECTIONS: list[tuple[re.Pattern, str, str]] = [
    # Both UniDic 3.1 and OpenJTalk give た/だ "動詞%F2@1", which turns a heiban
    # verb + た into odaka (キイタ＼). NHK: 聞く[0] → キイタ (heiban). The UniDic
    # manual itself lists た as F1 (表12).
    (re.compile(r"(?<!助)動詞%F2@1"), "動詞%F1", "た after a verb keeps the verb's accent"),
]


def corrected_con_type(m: Morph) -> str:
    con = m.con_type
    if m.pos == "助動詞" and m.ctype in ("助動詞-タ", "特殊・タ"):
        for pattern, repl, _reason in RULE_CORRECTIONS:
            con = pattern.sub(repl, con)
    return con


# --- inflection ------------------------------------------------------------

def apply_mod_type(base: int, mod_type: str, n_moras: int) -> tuple[int, bool]:
    """Accent of an inflected form from the lexeme's base accent (UniDic 表9).
    Returns (accent, known_rule)."""
    if not mod_type or mod_type == "*":
        return base, True
    m = re.fullmatch(r"M(\d+)@(-?\d+)", mod_type)
    if not m:
        return base, False
    kind, val = int(m.group(1)), int(m.group(2))
    if kind == 1:
        acc = n_moras - val
    elif kind == 2:
        acc = n_moras - val if base == 0 else base
    elif kind == 4:
        acc = base if base in (0, 1) else base - val
    else:
        return base, False
    return max(0, min(acc, n_moras)), True


# --- phrase grouping (njd_set_accent_phrase.c) ------------------------------

def _chain_flag(prev: Morph, node: Morph) -> bool:
    p, n = prev, node
    flag = True  # Rule 01
    if p.pos == "名詞" and n.pos == "名詞":  # Rule 02
        flag = True
    if p.pos == "形容詞" and n.pos == "名詞":  # Rule 03
        flag = False
    if p.pos == "名詞" and p.pos_group1 == "形容動詞語幹" and n.pos == "名詞":  # Rule 04
        flag = False
    if p.pos == "動詞" and n.pos in ("形容詞", "名詞"):  # Rule 05
        flag = False
    if {p.pos, n.pos} & {"副詞", "接続詞", "連体詞"}:  # Rule 06
        flag = False
    if (p.pos == "名詞" and p.pos_group1 == "副詞可能") or \
       (n.pos == "名詞" and n.pos_group1 == "副詞可能"):  # Rule 07
        flag = False
    if n.pos in ("助動詞", "助詞"):  # Rule 08
        flag = True
    if p.pos in ("助動詞", "助詞") and n.pos not in ("助動詞", "助詞"):  # Rule 09
        flag = False
    if p.pos_group1 == "接尾" and n.pos == "名詞":  # Rule 10
        flag = False
    if n.pos == "形容詞" and n.pos_group1 == "非自立":  # Rule 11
        if p.pos in ("動詞", "形容詞") and p.cform.startswith("連用"):
            flag = True
        elif p.pos == "助詞" and p.pos_group1 == "接続助詞" and p.surface in ("て", "で"):
            flag = True
    if n.pos == "動詞" and n.pos_group1 == "非自立":  # Rule 12
        if p.pos == "動詞" and p.cform.startswith("連用"):
            flag = True
        elif p.pos == "名詞" and p.pos_group1 == "サ変接続":
            flag = True
    if p.pos == "名詞" and (n.pos in ("動詞", "形容詞") or
                           n.pos_group1 == "形容動詞語幹"):  # Rule 13
        flag = False
    if n.pos == "記号" or p.pos == "記号":  # Rule 14
        flag = False
    if n.pos == "接頭詞":  # Rule 15
        flag = False
    if p.pos_group3 == "姓" and n.pos == "名詞":  # Rule 16
        flag = False
    if p.pos == "名詞" and n.pos_group3 == "名":  # Rule 17
        flag = False
    if n.pos_group1 == "接尾":  # Rule 18
        flag = True
    if n.pos == "感動詞" or p.pos == "感動詞":  # not in OpenJTalk: interjections stand alone
        flag = False
    return flag


def group_phrases(morphs: list[Morph]) -> list[list[Morph]]:
    """Split into accent phrases. Symbols end a phrase and are dropped."""
    phrases: list[list[Morph]] = []
    current: list[Morph] = []
    prev = None
    for m in morphs:
        if m.is_symbol:
            if current:
                phrases.append(current)
            current, prev = [], m
            continue
        if current and prev is not None and not _chain_flag(prev, m):
            phrases.append(current)
            current = []
        current.append(m)
        prev = m
    if current:
        phrases.append(current)
    return phrases


# --- accent combination (njd_set_accent_type.c + UniDic 表10–12) ------------

def _get_rule(con: str, prev_pos: str) -> tuple[str, list[int]]:
    """Pick the rule for this previous POS. Like OpenJTalk, the POS match is a
    substring match (so 動詞 also matches 助動詞) and the first match wins."""
    if not con or con == "*":
        return "*", []
    for entry in re.split(r"[,/]", con):
        entry = entry.strip()
        if "%" in entry:
            pos, rule = entry.split("%", 1)
            if pos not in prev_pos:
                continue
        else:
            rule = entry
        name, *args = rule.split("@")
        return name, [int(a) for a in args if a.lstrip("-").isdigit()]
    return "*", []


@dataclass
class PhraseAccent:
    accent: int
    known: bool  # False if a word's base accent or a rule was unknown


def combine(phrase: list[Morph], base: list[int | None]) -> PhraseAccent:
    """Accent of one phrase. ``base`` holds each morph's (inflected) accent,
    None where unknown."""
    known = True
    top = base[0] if base[0] is not None else 0
    if base[0] is None and not phrase[0].is_function_word:
        known = False
    n1 = len(phrase[0].moras)
    for i in range(1, len(phrase)):
        node, prev = phrase[i], phrase[i - 1]
        m2 = base[i]
        if m2 is None:
            if not node.is_function_word:
                known = False
            m2 = 0
        n2 = len(node.moras)

        if prev.pos == "接頭詞" and prev.con_type.startswith("P"):
            # UniDic puts the prefix rule on the prefix itself (表11).
            rule, args = _get_rule(prev.con_type, "")
        else:
            rule, args = _get_rule(corrected_con_type(node), prev.pos)
        a = args[0] if rule.startswith("F") and args else 0
        if rule.startswith("F") and node.is_function_word and node.mod_type.startswith("M1@"):
            # Volitional auxiliaries (ましょう, でしょう) carry M1@m: their own
            # accent sits m moras before their end, shifting the attachment
            # point: アイマショ＼ウ, アメデショ＼ウ.
            a = n2 - int(node.mod_type.split("@")[1])
        flat_or_last = m2 in (0, n2)

        match rule:
            case "*" | "F1" | "C5" | "P13":
                pass
            case "F2":
                if top == 0:
                    top = n1 + a
            case "F3":
                if top != 0:
                    top = n1 + a
            case "F4":
                top = n1 + a
            case "F5" | "C4" | "P6":
                top = 0
            case "F6":
                b = args[1] if len(args) > 1 else a
                top = n1 + (a if top == 0 else b)
            case "C1":
                top = n1 + m2
            case "C2":
                top = n1 + 1
            case "C3":
                top = n1
            case "P1":
                top = 0 if flat_or_last else n1 + m2
            case "P2":
                top = n1 + 1 if flat_or_last else n1 + m2
            case "P4":
                top = n1 + 1 if flat_or_last else top
            case "P14":
                top = top if flat_or_last else n1 + m2
            case _:
                known = False
        if top == 0 and _is_nai_stem_form(node):
            # Not in UniDic/OpenJTalk: after a heiban verb, ない is flat only in
            # its plain form; なく(て) / なけれ(ば) / なかっ(た) fall after な:
            # イカナイ but イカナ＼クテ, イカナ＼ケレバ, イカナ＼カッタ.
            top = n1 + 1
        n1 += n2
    return PhraseAccent(max(0, min(top, n1)), known)


def _is_nai_stem_form(m: Morph) -> bool:
    return (m.pos == "助動詞" and m.ctype in ("助動詞-ナイ", "特殊・ナイ")
            and m.cform.startswith(("連用", "仮定")))


def base_accents(m: Morph, accents: list[int]) -> tuple[list[int | None], bool]:
    """All inflected accents for a morph given its lexeme accents."""
    if not accents:
        return [None], True
    out, known = [], True
    for a in accents:
        acc, ok = apply_mod_type(a, m.mod_type, len(m.moras))
        known &= ok
        if acc not in out:
            out.append(acc)
    return out, known


def phrase_accents(phrase: list[Morph], lexeme_accents: list[list[int]]) -> tuple[list[int], bool]:
    """Every accent the phrase can take (preferred first), and whether every
    base accent and rule involved was known."""
    options, known = [], True
    for m, accs in zip(phrase, lexeme_accents):
        o, ok = base_accents(m, accs)
        options.append(o)
        known &= ok
    # Preferred reading of every word, then each word's alternatives one at a
    # time (a full cartesian product explodes on long phrases).
    primary = [o[0] for o in options]
    combos = [primary] + [
        primary[:i] + [alt] + primary[i + 1:]
        for i, o in enumerate(options) for alt in o[1:]
    ]
    results: list[int] = []
    for combo in combos:
        r = combine(phrase, combo)
        known &= r.known
        if r.accent not in results:
            results.append(r.accent)
    return results, known
