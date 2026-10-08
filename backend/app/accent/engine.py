"""Expected-accent engine: text → accent phrases with expected accent,
acceptable alternatives and a confidence level.

Confidence:
  nhk        every content word in the phrase has a user (NHK-checked) override,
             and no compound rule built the accent (日本+語 needs 日本語 itself)
  agree      UniDic and OpenJTalk's lexicon, run through the same rules, agree
  uncertain  they disagree, a word/rule is unknown, or phrasing differs.
             The UI shows these grey and never counts them as the user's error.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace

from .kana import same_moras, split_moras, strip_reading_hints, to_hiragana, with_reading_hint
from .notation import phrase_notation, pitch_pattern
from .overrides import OverrideStore
from .variants import VariantStore, phrase_key
from .rules import compound_rule, group_phrases, phrase_accents
from .sources import Morph, kanji_part, openjtalk_morphs, reads_as, unidic_morphs


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
    # other readings of its kanji: {start, end, surface, reading (hiragana),
    # text: the input text with that reading as a hint}
    reading_alternatives: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _span(phrase: list[Morph]) -> tuple[int, int]:
    return phrase[0].start, phrase[-1].end


def _moras(phrase: list[Morph]) -> list[str]:
    return [mo for m in phrase for mo in m.moras]


def _openjtalk_index(morphs: list[Morph]) -> dict[tuple[int, int], tuple[list[int], bool, list[str], list[str]]]:
    """OpenJTalk's phrases by span: accents, known, moras and pronunciation
    (実は: ジツハ, ジツワ)."""
    index = {}
    for ph in group_phrases(morphs):
        accs, known = phrase_accents(ph, [m.accents for m in ph])
        pron = [mo for m in ph for mo in (split_moras(m.pron) if m.pron else m.moras)]
        index[_span(ph)] = (accs, known, _moras(ph), pron)
    return index


MAX_COMPOUND = 5  # words in a run tried as one stored compound


def compounds(morphs: list[Morph], overrides: OverrideStore) -> list[Morph]:
    """The morphs with each run the user stored whole (日本語, 土曜日, which
    UniDic splits 日本 + 語, 土曜 + 日) merged into one word carrying the
    stored accent. Runs start at a content word, hold no particle or
    auxiliary, and end uninflected (stored by dictionary form). Merging comes
    before phrase grouping, which would otherwise split 土曜 | 日."""
    out, i = [], 0
    while i < len(morphs):
        m, merged = morphs[i], None
        if not (m.is_function_word or m.is_symbol):
            j = i
            while j + 1 < min(len(morphs), i + MAX_COMPOUND) and \
                    morphs[j + 1].pos not in ("助詞", "助動詞") and not morphs[j + 1].is_symbol:
                j += 1
            for k in range(j, i, -1):
                run = morphs[i:k + 1]
                if run[-1].ctype != "*":
                    continue
                surface, moras = "".join(x.surface for x in run), [mo for x in run for mo in x.moras]
                accs = overrides.lookup_compound(surface, "".join(moras))
                if accs is not None:
                    last = run[-1]
                    merged = replace(
                        m, surface=surface, end=last.end, moras=moras, lemma=surface,
                        lemma_reading="".join(moras), accents=accs, pos=last.pos,
                        pos_group1="一般" if last.pos_group1 == "接尾" else last.pos_group1,
                        cform=last.cform, ctype=last.ctype, mod_type="*",
                        con_type="*" if m.pos == "接頭詞" else m.con_type,
                        source="override", alt_readings=[])
                    i = k + 1
                    break
        if merged is None:
            merged = m
            i += 1
        out.append(merged)
    return out


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
        if len(fm) == len(moras) and same_moras(fm, moras):
            return accents
        if (len(fm) < len(moras) and len(fm) in ends and all(accents)
                and same_moras(fm, moras[:len(fm)]) and (best is None or len(fm) > best[0])):
            best = (len(fm), accents)
    return best[1] if best else None


def nhk_support(overrides: OverrideStore):
    """Counts a path's words, and runs stored whole (日本人 ニホンジン), that
    the user has NHK accents for: evidence for the path's readings."""
    def count(path: list[Morph]) -> int:
        n = sum(map(overrides.has_reading, path))
        for i in range(len(path) - 1):
            run = []
            for m in path[i:i + 4]:
                if m.pos in ("助詞", "助動詞") or m.is_symbol:
                    break
                run.append(m)
                if len(run) > 1 and overrides.lookup_compound(
                        "".join(x.surface for x in run), "".join(mo for x in run for mo in x.moras)):
                    n += 1
        return n
    return count


def reading_alternatives(raw: str, phrase: list[Morph]) -> list[dict]:
    """Other readings of the phrase's kanji, each with the input text that
    asks for it (日本{にっぽん}語)."""
    out = []
    for m in phrase:
        for alt in m.alt_readings:
            kp = kanji_part(m, split_moras(alt))
            if kp:
                k, hira = kp
                out.append({"start": m.start, "end": m.start + k, "surface": m.surface[:k],
                            "reading": hira, "text": with_reading_hint(raw, m.start, m.start + k, hira)})
    return out


def analyze_text(text: str, overrides: OverrideStore | None = None,
                 variants: VariantStore | None = None) -> list[Phrase]:
    """Accent phrases of ``text``. Kanji may carry a reading hint, 日本{にっぽん};
    phrase offsets and texts then refer to the text without hints."""
    raw = text
    text, hints = strip_reading_hints(raw)
    reference = openjtalk_morphs(text)
    morphs = unidic_morphs(text, reference=reference, hints=hints,
                           prefer=nhk_support(overrides) if overrides else None,
                           compounds=overrides.compounds_in(text) if overrides else None)
    oj = _openjtalk_index(reference)
    unmet = {span: r for span, r in hints.items() if not reads_as(morphs, *span, r)}
    alt_readings = reading_alternatives(raw, morphs)
    split = morphs
    if overrides:
        morphs = compounds(morphs, overrides)
    merged = {id(m) for m in morphs} - {id(m) for m in split}
    out: list[Phrase] = []
    groups = group_phrases(morphs)

    uses = {id(m): usage(morphs, i) for i, m in enumerate(morphs)}

    def lookup(m) -> tuple[list[int], str] | None:
        if not overrides:
            return None
        if id(m) in merged:  # stored whole, see compounds()
            return m.accents, ""
        return overrides.lookup_use(m, uses[id(m)])

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
        listed = None
        if overrides and not ph[0].is_function_word:
            listed = nhk_form(ph, moras, overrides.forms(ph[0]))
            if listed is not None:
                accents = list(listed)
                use_notes.append(f"NHK form of {ph[0].lemma}")
        content = [w for w, m in zip(words, ph) if not m.is_function_word]
        built = listed is None and any(compound_rule(a, b) for a, b in zip(ph, ph[1:]))
        reasons: list[str] = []
        alternatives = [a for a in alt_readings if ph[0].start <= a["start"] < ph[-1].end]
        for (s, e), r in unmet.items():
            if ph[0].start <= s < ph[-1].end:
                reasons.append(f"reading {to_hiragana(r)} not in dictionary for {text[s:e]}")

        if content and all(w.source == "override" for w in content) and not built and not reasons:
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
                oj_accs, oj_known, oj_moras, oj_pron = match
                if not (same_moras(oj_moras, moras) or same_moras(oj_pron, moras)):
                    reasons.append("dictionaries disagree on the reading")
                elif oj_accs[0] != accents[0]:
                    reasons.append(
                        f"dictionaries disagree: UniDic "
                        f"{phrase_notation(moras, accents[0])}, OpenJTalk "
                        f"{phrase_notation(moras, oj_accs[0])}")
                    accents += [a for a in oj_accs if a not in accents]
            if reasons:
                confidence = "uncertain"
                hinted = {s for s, _ in hints}
                reasons += [f"other reading possible: {a['surface']} {a['reading']}"
                            for a in alternatives if a["start"] not in hinted]
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
            reading_alternatives=alternatives,
        ))
    return out


def notation(phrases: list[Phrase]) -> str:
    return " ".join(p.notation for p in phrases)
