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

from .kana import special_moras, vowel_of
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


# Contracted ている / ておく / てしまう / ていく (来て(る)ない, 見とく, 食べちゃう).
# UniDic tags them 助動詞, OpenJTalk 動詞-非自立.
_TE_CONTRACTIONS = {"てる", "でる", "とく", "どく", "ちゃう", "じゃう", "てく", "でく"}


def _is_te_contraction(node: Morph) -> bool:
    return node.lemma in _TE_CONTRACTIONS and (
        node.pos == "助動詞" or (node.pos == "動詞" and node.pos_group1 == "非自立"))


def _te_tail(node: Morph) -> bool:
    """What can follow a te-form inside its phrase without a drop of its own."""
    return (node.is_function_word or _is_te_contraction(node)
            or (node.pos == "形容詞" and node.pos_group1 == "非自立"))


def _is_te(prev: Morph, node: Morph) -> bool:
    """node is a te-form ending: て/で after a verb, or a contracted te-auxiliary."""
    if _is_te_contraction(node):
        return True
    if node.pos == "助動詞" and node.surface == "で" and prev.pos == "動詞":
        return True  # OpenJTalk tags the で of 読んで as だ
    return (node.pos == "助詞" and node.pos_group1 == "接続助詞" and node.surface in ("て", "で")
            and prev.pos in ("動詞", "助動詞"))


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
    starts, pos = set(), 0
    for m in phrase:
        starts.add(pos)
        pos += len(m.moras)
    special = special_moras([mo for m in phrase for mo in m.moras], starts)
    te_locked = False
    for i in range(1, len(phrase)):
        node, prev = phrase[i], phrase[i - 1]
        if _te_tail(node) and (te_locked or (top != 0 and _is_te(prev, node))):
            # Not in UniDic/OpenJTalk: a te-form that already has its drop keeps
            # it through what follows (キ＼テナイ, ヨ＼ンデナイ, ミ＼トク, タ＼ベテマセン).
            # The contracted て is tagged 助動詞, so ない/ます/とく's "動詞%F3/F4"
            # rules would otherwise match it and move the drop onto て; て + ない
            # parsed as 補助形容詞 gets C3, which does the same.
            te_locked = True
            n1 += len(node.moras)
            continue
        if top != 0 and _after_adjective_ku(prev, node):
            # an accented adjective keeps its drop before ない/なる:
            # タカ＼クナイ (not UniDic's C3 タカク＼ナイ), タカ＼クナル
            n1 += len(node.moras)
            continue
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
                # た after an adjective (形容詞%F4@-2) gives the かった form its
                # drop: アカ＼カッタ. An accented adjective already has its own,
                # which may be the earlier one (タ＼カカッタ), so keep it.
                if not (prev.pos == "形容詞" and top != 0 and node.ctype in ("助動詞-タ", "特殊・タ")):
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
                if _after_adjective_ku(prev, node):
                    # 赤い[0] + ない: ない keeps its own drop, アカクナ＼イ
                    # (UniDic's C3 gives the newer アカク＼ナイ, added in
                    # phrase_accents as an alternative)
                    top = n1 + m2
                else:
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
        if rule.startswith("C") and 0 < top <= len(special) and special[top - 1]:
            # A compound's nucleus never falls on ー/ン/ッ or a diphthong's
            # second half; it moves back one mora (NHK: レイゾ＼ーコ,
            # ヒコ＼ーキ, イデ＼ンシ, ブタ＼イゲキ).
            top -= 1
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
    if accents[0] == 0 and _is_adjective_ku_form(m):
        # NHK conjugates an adjective listed flat first (甘い アマイ━, アマ＼イ)
        # as flat only: アマク━, アマ＼クテ, アマ＼カッタ
        accents = [0]
    for a in accents:
        acc, ok = apply_mod_type(a, m.mod_type, len(m.moras))
        known &= ok
        for x in (acc, _adjective_shift(m, acc) if a else None):
            if x is not None and x not in out:
                out.append(x)
    return out, known


def _adjective_shift(m: Morph, acc: int) -> int | None:
    """Not in UniDic/OpenJTalk: an accented adjective's く/かった/ければ forms
    also take the drop one mora earlier, and NHK lists both (タカ＼ク and
    タ＼カク, タカ＼カッタ and タ＼カカッタ). A drop that would land on a
    long vowel's second half moves back once more (チ＼ーサク, オ＼ーキク);
    none lands on ッ/ン (NHK has only スッパ＼ク). Only for adjectives accented
    in the dictionary: 赤い[0]'s アカ＼カッタ has no second form."""
    if not (_is_adjective_ku_form(m) and acc >= 2):
        return None
    shifted = acc - 1
    mora = m.moras[shifted - 1]
    if mora in ("ッ", "ン"):
        return None
    if shifted >= 2 and (mora == "ー" or (vowel_of(m.moras[shifted - 2]), mora) in _LONG_VOWELS):
        # a diphthong's イ can carry it (オイ＼シク), a long vowel's tail can't
        shifted -= 1
    return shifted if shifted >= 1 else None


def _is_adjective_ku_form(m: Morph) -> bool:
    """高く, 高かっ(た), 高けれ(ば)."""
    return m.pos == "形容詞" and m.pos_group1 == "自立" and m.cform.startswith(("連用形", "仮定形"))


_LONG_VOWELS = {("a", "ア"), ("i", "イ"), ("u", "ウ"), ("e", "エ"), ("e", "イ"), ("o", "オ"), ("o", "ウ")}


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
    n = 0
    for i, m in enumerate(phrase[:-1]):
        n += len(m.moras)
        nxt = phrase[i + 1]
        if (_after_adjective_ku(m, nxt) and nxt.pos == "形容詞" and 0 in options[i]
                and n not in results):
            # flat adjective + ない also falls before ない: アカク＼ナイ
            results.append(n)
    if 0 in results and _ends_in_te_mo(phrase):
        # Not in UniDic/OpenJTalk: after a heiban verb, ～ても is flat
        # (イワレテモ) or, as most say it now, falls after て (イワレテ＼モ).
        drop = sum(len(m.moras) for m in phrase) - 1
        if drop not in results:
            results.append(drop)
    return results, known


def _after_adjective_ku(prev: Morph, node: Morph) -> bool:
    """ない / なる right after an adjective's く form (高くない, 高くなる)."""
    return (prev.pos == "形容詞" and prev.pos_group1 == "自立" and prev.cform.startswith("連用形")
            and node.pos in ("形容詞", "動詞") and node.pos_group1 == "非自立")


def _ends_in_te_mo(phrase: list[Morph]) -> bool:
    if len(phrase) < 3:
        return False
    verb, te, mo = phrase[-3:]
    return (mo.pos == "助詞" and mo.surface == "も" and te.pos_group1 == "接続助詞"
            and te.surface in ("て", "で") and verb.pos in ("動詞", "助動詞"))
