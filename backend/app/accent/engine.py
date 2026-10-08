"""Expected-accent engine: text → accent phrases with expected accent,
acceptable alternatives and a confidence level.

Confidence:
  nhk        every content word in the phrase has a user (NHK-checked) override
  agree      UniDic and OpenJTalk's lexicon, run through the same rules, agree
  uncertain  they disagree, a word/rule is unknown, or phrasing differs.
             The UI shows these grey and never counts them as the user's error.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .kana import split_moras
from .notation import phrase_notation, pitch_pattern
from .overrides import OverrideStore
from .variants import VariantStore, phrase_key
from .rules import group_phrases, phrase_accents
from .sources import Morph, openjtalk_morphs, unidic_morphs


@dataclass
class Word:
    surface: str
    lemma: str
    reading: str
    pos: str
    accents: list[int]
    source: str  # "override" | "unidic" | "none"
    n_moras: int


@dataclass
class Phrase:
    start: int
    end: int
    text: str
    moras: list[str]
    accent: int
    alternatives: list[int]  # every acceptable accent, preferred first
    confidence: str  # "nhk" | "agree" | "uncertain"
    notation: str
    pitch: list[bool]
    words: list[Word] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    merge_accents: list[int] = field(default_factory=list)  # accents if said as one phrase with the next
    native_variants: list[int] = field(default_factory=list)  # approved, also in alternatives
    proposed_variants: list[int] = field(default_factory=list)  # mined, not yet reviewed

    def to_dict(self) -> dict:
        return asdict(self)


def _span(phrase: list[Morph]) -> tuple[int, int]:
    return phrase[0].start, phrase[-1].end


def _moras(phrase: list[Morph]) -> list[str]:
    return [mo for m in phrase for mo in m.moras]


def _openjtalk_index(text: str) -> dict[tuple[int, int], tuple[list[int], bool, int]]:
    index = {}
    for ph in group_phrases(openjtalk_morphs(text)):
        accs, known = phrase_accents(ph, [m.accents for m in ph])
        index[_span(ph)] = (accs, known, len(_moras(ph)))
    return index


# Auxiliary verbs natives often say in one phrase with a preceding て-form,
# where OpenJTalk's grouping starts a new phrase (食べて|います).
_AUX_AFTER_TE = {"居る", "いる", "有る", "ある", "置く", "おく", "仕舞う", "しまう", "行く", "いく",
                 "来る", "くる", "見る", "みる"}


def joinable(prev: list[Morph], nxt: list[Morph]) -> bool:
    """Adjacent phrases natives often say as one accent phrase."""
    last, first = prev[-1], nxt[0]
    if last.surface in ("て", "で") and last.pos == "助詞" and first.pos == "動詞" \
            and first.lemma in _AUX_AFTER_TE:
        return True
    # noun + の + noun (日本の首都)
    return last.surface == "の" and last.pos == "助詞" and first.pos == "名詞" and len(prev) >= 2


def usage(morphs: list[Morph], i: int) -> tuple[str, ...]:
    """How a noun or adverb is used, for words whose NHK accent depends on it
    (see overrides.py): modified / unmodified by a 連体修飾語 (優しい人, あの人,
    話題の人, 静かな人) and noun / adverb (昨日は vs 昨日会った)."""
    m = morphs[i]
    if m.pos == "副詞":
        return ("adverb",)
    if m.pos != "名詞" or m.is_function_word:
        return ()
    prev = morphs[i - 1] if i > 0 else None
    nxt = morphs[i + 1] if i + 1 < len(morphs) else None
    modified = prev is not None and (
        prev.pos == "連体詞"
        or (prev.pos == "助詞" and prev.surface == "の")
        or (prev.pos in ("動詞", "形容詞", "助動詞") and prev.cform.startswith(("連体形", "終止形"))))
    uses = ["modified" if modified else "unmodified"]
    # bare before a predicate (昨日会った, 昨日、会った) is adverbial; a particle,
    # だ/です or the end of the sentence (それは昨日。) makes it a noun
    adverbial = m.pos_group1 in ("副詞可能", "数") and nxt is not None and (
        nxt.surface == "、" or not (nxt.is_function_word or nxt.is_symbol))
    uses.append("adverb" if adverbial else "noun")
    return tuple(uses)


def _same_moras(a: list[str], b: list[str]) -> bool:
    """NHK writes long vowels as ー (イーマス) where readings spell them out."""
    return len(a) == len(b) and all(x == y or "ー" in (x, y) or {x, y} <= {"ヲ", "オ"}
                                    for x, y in zip(a, b))


def nhk_form(phrase: list[Morph], moras: list[str], forms: list[tuple[str, list[int]]]) -> list[int] | None:
    """Accents NHK lists for this phrase as a form of its first word: the
    phrase is that form (タ＼カク), or starts with it at a word boundary and
    the form already has its drop (タ＼カカッタ + です)."""
    ends, n = set(), 0
    for m in phrase:
        n += len(m.moras)
        ends.add(n)
    best: tuple[int, list[int]] | None = None
    for form, accents in forms:
        fm = split_moras(form)
        if len(fm) == len(moras) and _same_moras(fm, moras):
            return accents
        if (len(fm) < len(moras) and len(fm) in ends and all(accents)
                and _same_moras(fm, moras[:len(fm)]) and (best is None or len(fm) > best[0])):
            best = (len(fm), accents)
    return best[1] if best else None


def analyze_text(text: str, overrides: OverrideStore | None = None,
                 variants: VariantStore | None = None) -> list[Phrase]:
    morphs = unidic_morphs(text)
    oj = _openjtalk_index(text)
    out: list[Phrase] = []
    groups = group_phrases(morphs)

    uses = {id(m): usage(morphs, i) for i, m in enumerate(morphs)}

    def lookup(m) -> tuple[list[int], str] | None:
        return overrides.lookup_use(m, uses[id(m)]) if overrides else None

    def lexeme(m):
        hit = lookup(m)
        return hit[0] if hit else m.accents

    for gi, ph in enumerate(groups):
        words, lex, use_notes = [], [], []
        for m in ph:
            hit = lookup(m)
            accs = hit[0] if hit else m.accents
            if hit and hit[1]:
                use_notes.append(f"NHK {hit[1]} use of {m.surface}")
            lex.append(accs)
            words.append(Word(m.surface, m.lemma, m.lemma_reading, m.pos, accs,
                              "override" if hit else ("unidic" if accs else "none"),
                              len(m.moras)))

        moras = _moras(ph)
        accents, known = phrase_accents(ph, lex)
        if overrides and not ph[0].is_function_word:
            listed = nhk_form(ph, moras, overrides.forms(ph[0]))
            if listed is not None:
                accents = list(listed)
                use_notes.append(f"NHK form of {ph[0].lemma}")
        content = [w for w, m in zip(words, ph) if not m.is_function_word]
        reasons: list[str] = []

        if content and all(w.source == "override" for w in content):
            confidence = "nhk"
        else:
            confidence = "agree"
            if not known:
                unknown = [w.surface for w, m in zip(words, ph)
                           if not m.is_function_word and not w.accents]
                reasons.append("no accent data for " + "・".join(unknown) if unknown
                               else "unknown accent rule")
            if not moras:
                reasons.append("no reading")
            match = oj.get(_span(ph))
            if match is None:
                reasons.append("dictionaries split this phrase differently")
            else:
                oj_accs, oj_known, oj_n = match
                if oj_n != len(moras):
                    reasons.append("dictionaries disagree on the reading")
                elif oj_accs[0] != accents[0]:
                    reasons.append(
                        f"dictionaries disagree: UniDic "
                        f"{phrase_notation(moras, accents[0])}, OpenJTalk "
                        f"{phrase_notation(moras, oj_accs[0])}")
                    accents += [a for a in oj_accs if a not in accents]
            if reasons:
                confidence = "uncertain"
        reasons += use_notes

        native, proposed = [], []
        if variants is not None and moras:
            found = variants.lookup(phrase_key([m.lemma for m in ph], moras))
            native = [a for a in found["approved"] if a not in accents]
            proposed = [a for a in found["proposed"] if a not in accents]
            accents = accents + native

        merge: list[int] = []
        nxt = groups[gi + 1] if gi + 1 < len(groups) else None
        if nxt and nxt[0].start == ph[-1].end and joinable(ph, nxt):
            # Said in one breath, a phrase keeps only its first drop: the
            # first part's drop if it has one, else the second part's.
            n1 = len(moras)
            second, _ = phrase_accents(nxt, [lexeme(m) for m in nxt])
            n2 = len(_moras(nxt))
            for a1 in accents:
                for a2 in second:
                    m = a1 if 0 < a1 < n1 else (n1 + a2 if 0 < a2 < n2 else 0)
                    if m not in merge:
                        merge.append(m)

        out.append(Phrase(
            start=ph[0].start, end=ph[-1].end,
            text=text[ph[0].start:ph[-1].end],
            moras=moras, accent=accents[0], alternatives=accents,
            confidence=confidence,
            notation=phrase_notation(moras, accents[0]),
            pitch=pitch_pattern(len(moras), accents[0]),
            words=words, reasons=reasons,
            merge_accents=merge,
            native_variants=native, proposed_variants=proposed,
        ))
    return out


def notation(phrases: list[Phrase]) -> str:
    return " ".join(p.notation for p in phrases)
