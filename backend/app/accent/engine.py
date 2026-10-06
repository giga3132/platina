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

from .notation import phrase_notation, pitch_pattern
from .overrides import OverrideStore
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


def analyze_text(text: str, overrides: OverrideStore | None = None) -> list[Phrase]:
    morphs = unidic_morphs(text)
    oj = _openjtalk_index(text)
    out: list[Phrase] = []

    for ph in group_phrases(morphs):
        words, lex = [], []
        for m in ph:
            ov = overrides.lookup(m) if overrides else None
            accs = ov if ov is not None else m.accents
            lex.append(accs)
            words.append(Word(m.surface, m.lemma, m.lemma_reading, m.pos, accs,
                              "override" if ov is not None else ("unidic" if accs else "none"),
                              len(m.moras)))

        moras = _moras(ph)
        accents, known = phrase_accents(ph, lex)
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

        out.append(Phrase(
            start=ph[0].start, end=ph[-1].end,
            text=text[ph[0].start:ph[-1].end],
            moras=moras, accent=accents[0], alternatives=accents,
            confidence=confidence,
            notation=phrase_notation(moras, accents[0]),
            pitch=pitch_pattern(len(moras), accents[0]),
            words=words, reasons=reasons,
        ))
    return out


def notation(phrases: list[Phrase]) -> str:
    return " ".join(p.notation for p in phrases)
