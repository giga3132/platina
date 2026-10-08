"""Import NHK accents written down in an Anki deck into the overrides store.

The deck is a plain-text Anki export (Notes in Plain Text, HTML kept): front =
headword (先生, せんせい【先生】, よそう《×装う》, 辺（ヘン）, ...), back = one
pronunciation per line in katakana or hiragana, with ↘ / ＼ after the accent
nucleus and ＝ / ━ at the end of a heiban word. The first lines that read as
the headword are its accents (first = preferred); later lines (inflections,
"毛を ケオ━", notes) are ignored.

Cards for one use of a word (（「優しい〜に」など修飾語を伴って）, ［副詞］) are
stored with that context (see app/accent/overrides.py); a word with only
per-use cards also gets a plain row with all its accents, noun use first.

The other lines of a plain card that spell a form of the word (高い:
タ＼カク, タカ＼カッタ; 学ぶ: マナバナイ━, マナビマ＼ス; 駅: エ＼キオ) are
stored as NHK forms, which the engine uses for a phrase that is exactly
that form.

Single words go into data/overrides.sqlite (note "anki: <headword>"), so the
engine marks phrases made of them as NHK-checked. Re-running replaces earlier
anki imports but never overwrites an override entered in the app (unless
--force). Compounds the tagger splits (美術館, 土曜日) can't be stored per
lexeme; --check prints where the engine's compound accent differs from the
deck, which is where rules.py needs work.

Usage (from backend/):
  ../.venv/bin/python -m tools.import_anki ../単語の発音.txt [--dry-run] [--check] [--force]
"""

from __future__ import annotations

import argparse
import csv
import html
import re
from collections import defaultdict
from pathlib import Path

from app.accent.engine import analyze_text
from app.accent.kana import split_moras, to_katakana
from app.accent.overrides import OverrideStore
from app.accent.sources import unidic_morphs

DOWN = "↘＼\\"
FLAT = "＝━"
_PRON = re.compile(r"[ァ-ヴー゚↘＼\\＝━]+")


def _lines(field: str) -> list[str]:
    field = re.sub(r"<[^>]+>", "\n", field)
    return [x.strip() for x in html.unescape(field).replace("\xa0", " ").split("\n") if x.strip()]


def parse_pron(line: str) -> tuple[str, int] | None:
    """"センセ↘イ" → ("センセイ", 3); "アンキ＝" → ("アンキ", 0); else None."""
    word = to_katakana(re.split(r"[\s（(←]", line)[0])
    # nasal ガ行 is written カ゚ (カ + U+309A)
    word = re.sub("([カキクケコ])゚", lambda m: chr(ord(m.group(1)) + 1), word)
    if not _PRON.fullmatch(word):
        return None
    down = [i for i, c in enumerate(word) if c in DOWN]
    kana = re.sub(r"[↘＼\\＝━]", "", word)
    if down:
        return kana, len(split_moras(word[:down[0]]))
    if word[-1] in FLAT:
        return kana, 0
    return None


def same_word(nhk: str, reading: str) -> bool:
    """NHK writes long vowels as ー (セーキョー) where readings spell them
    out (セイキョウ); otherwise the moras must match."""
    a, b = split_moras(nhk), split_moras(to_katakana(reading))
    return len(a) == len(b) and all(x == y or x == "ー" or {x, y} <= {"ヲ", "オ"}
                                    for x, y in zip(a, b))


_POS_CONTEXT = {"名詞": "noun", "副詞": "adverb"}
# 「彼の〜に行く」など，修飾語を伴った場合は「…ウチ＼（ニ）…」
_MODIFIED_NOTE = re.compile(r"修飾語を伴った場合は「…?([ァ-ヴー゚↘＼\\＝━]+)")


def head_context(field: str) -> str:
    """The use a card is restricted to: modified / unmodified (by a 連体修飾語),
    noun / adverb (［名詞］ / ［副詞］), or '' for any use."""
    text = " ".join(_lines(field))
    if "修飾語を伴わない" in text:
        return "unmodified"
    if "修飾語を伴って" in text or "修飾語を伴った" in text:
        return "modified"
    m = re.search(r"［(.+?)］", _lines(field)[0])
    return _POS_CONTEXT.get(m.group(1), "") if m else ""


def modified_note(back: str) -> tuple[str, int] | None:
    """Accent a card gives only in a note for the modified use (うち)."""
    for line in _lines(back):
        if (m := _MODIFIED_NOTE.search(line)):
            return parse_pron(m.group(1))
    return None


def form_lines(parsed: list[tuple[str, int]], head: str, reading: str, inflects: bool) -> list[tuple[str, int]]:
    """Lines that spell a form of the word rather than the word itself: they
    start with its stem (the reading minus the ending for verbs/adjectives)."""
    stem = split_moras(to_katakana(reading))
    if inflects:
        stem = stem[:-1]
    out = []
    for kana, acc in parsed:
        moras = split_moras(kana)
        if same_word(kana, head) or len(moras) <= len(stem):
            continue
        if same_word("".join(moras[:len(stem)]), "".join(stem)) and (kana, acc) not in out:
            out.append((kana, acc))
    return out


def parse_head(field: str) -> tuple[list[str], str | None]:
    """Headword forms and the kana reading, if the card gives one."""
    head = re.sub(r"［.+?］", "", _lines(field)[0]).strip()
    m = re.match(r"^([ぁ-んァ-ヴー]+)[【《](.+?)[】》]", head)
    if m:
        # 【２つ，二つ】, 【犬《×狗》】 (the kanji NHK marks as non-standard)
        forms = [re.sub(r"《.*", "", f) for f in
                 re.split(r"[・，,]", re.sub(r"[×△▽〈〉]", "", m.group(2)))]
        return [f for f in forms if f] or [m.group(1)], m.group(1)
    m = re.match(r"^(.+?)\s*[（(]([ぁ-んァ-ヴー]+)[）)]", head)
    if m:
        return [m.group(1)], m.group(2)
    return [re.split(r"[\s（(]", head)[0]], None


def read_deck(path: Path):
    lines = [l for l in path.read_text(encoding="utf-8").splitlines(keepends=True)
             if not l.startswith("#")]
    for row in csv.reader(lines, delimiter="\t"):
        if len(row) >= 2:
            yield row[0], row[1]


def _affix(m) -> bool:
    return m.is_function_word or m.pos == "接頭詞"


def resolve(forms: list[str], kana_hint: str | None, prons: list[tuple[str, int]]):
    """(lemma, reading, accents), or (None, reason, morphs) if the headword
    isn't a single content word."""
    kana = prons[0][0]
    accents = list(dict.fromkeys(a for _, a in prons))
    for form in forms:
        ms = unidic_morphs(form)
        # 安心な, 変な: the な-adjective's stem carries the accent
        if len(ms) == 2 and ms[1].surface in ("な", "だ") and form.endswith(ms[1].surface):
            stem = [(k[:-1], a) for k, a in prons if k.endswith(("ナ", "ダ"))]
            if stem and same_word(stem[0][0], ms[0].lemma_reading):
                return ms[0].lemma, ms[0].lemma_reading, list(dict.fromkeys(a for _, a in stem))
        # ー matches any vowel, so いい (イー, tagged as 言う's 連用形) would
        # pass as 言う (イウ): a token that isn't its dictionary form (いい,
        # 凄 of 凄い) has to spell the lemma's reading exactly
        m0 = ms[0] if len(ms) == 1 else None
        if m0 and same_word(kana, m0.lemma_reading) and (
                m0.ctype == "*" or "".join(m0.moras) == m0.lemma_reading
                or to_katakana(kana) == m0.lemma_reading):
            if _affix(m0):
                return None, "function word or affix", ms
            return m0.lemma, m0.lemma_reading, accents
    ms = unidic_morphs(forms[0])
    if len(ms) > 1:
        return None, "compound", ms
    if kana_hint or ("ー" not in kana and not _affix(ms[0])):
        # the tagger reads the bare headword differently (鼻 → ビ, 人 → ジン);
        # in a sentence it produces this lemma with the card's reading
        return forms[0], to_katakana(kana_hint or kana), accents
    return None, "reading", ms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("deck", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true", help="compare compounds with the engine")
    ap.add_argument("--force", action="store_true", help="also replace overrides entered in the app")
    args = ap.parse_args()

    # (lemma, reading, context) → accents
    entries: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    heads: dict[tuple[str, str, str], str] = {}
    # (lemma, reading, form) → accents, from the card's other lines
    form_entries: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    form_heads: dict[tuple[str, str, str], str] = {}
    skipped: dict[str, list[str]] = defaultdict(list)
    compounds: list[tuple[str, list[tuple[str, int]]]] = []
    for front, back in read_deck(args.deck):
        forms, hint = parse_head(front)
        context = head_context(front)
        parsed = [p for p in map(parse_pron, _lines(back)) if p and p[0]]
        # the word's own accents: lines spelling the headword (or, without a
        # kana headword, the same word as the first line)
        prons = [p for p in parsed if same_word(p[0], hint or parsed[0][0])]
        if not prons:
            skipped["no pronunciation of the headword itself"].append(forms[0])
            continue
        lemma, reading, accents = resolve(forms, hint, prons)
        if lemma is None:
            skipped[reading].append(forms[0])
            if reading == "compound":
                compounds.append((forms[0], prons))
            continue
        if not context:
            inflects = (m := unidic_morphs(lemma)) and m[0].pos in ("動詞", "形容詞")
            for kana, acc in form_lines(parsed, hint or prons[0][0], reading, bool(inflects)):
                key = (lemma, reading, to_katakana(kana))
                form_heads.setdefault(key, forms[0])
                if acc not in form_entries[key]:
                    form_entries[key].append(acc)
        uses = [(context, accents)]
        if (note := modified_note(back)) and same_word(note[0], reading):
            uses.append(("modified", [note[1]]))
        for use, accs in uses:
            key = (lemma, reading, use)
            heads.setdefault(key, forms[0])
            entries[key] += [a for a in accs if a not in entries[key]]

    # a word with only per-use cards (昨日［名詞］/［副詞］) gets a plain row with
    # every accent, so uses the engine can't tell apart still match
    by_word: dict[tuple[str, str], list[str]] = defaultdict(list)
    for lemma, reading, use in entries:
        by_word[(lemma, reading)].append(use)
    for (lemma, reading), uses in by_word.items():
        if "" not in uses:
            plain = (lemma, reading, "")
            for use in sorted(uses, key=["noun", "unmodified", "modified", "adverb"].index):
                heads.setdefault(plain, heads[(lemma, reading, use)])
                entries[plain] += [a for a in entries[(lemma, reading, use)] if a not in entries[plain]]
    per_use = sum(1 for _, _, use in entries if use)

    store = OverrideStore()
    manual = {(o["lemma"], o["reading"], o["context"]) for o in store.all()
              if not o["note"].startswith("anki")}
    kept = [k for k in entries if k in manual and not args.force]
    changed = sum(1 for (l, r, use), accs in entries.items()
                  if not use and (m := unidic_morphs(l)) and len(m) == 1 and m[0].accents[:1] != accs[:1])
    if not args.dry_run:
        stale = [(o["lemma"], o["reading"], o["context"]) for o in store.all()
                 if o["note"].startswith("anki") and (o["lemma"], o["reading"], o["context"]) not in entries]
        for key in stale:
            store.delete(*key)
        for (lemma, reading, use), accs in entries.items():
            if (lemma, reading, use) not in kept:
                label = {"modified": "（修飾語を伴って）", "unmodified": "（修飾語を伴わないで）",
                         "noun": "［名詞］", "adverb": "［副詞］"}.get(use, "")
                store.put(lemma, reading, accs, f"anki: {heads[(lemma, reading, use)]}{label}", use)
        store.delete_forms("anki")
        for (lemma, reading, form), accs in form_entries.items():
            store.put_form(lemma, reading, form, accs, f"anki: {form_heads[(lemma, reading, form)]}")

    print(f"{len(entries) - per_use} words {'would be ' if args.dry_run else ''}imported "
          f"({changed} with a different first accent than UniDic), "
          f"plus {per_use} accents for one use (modified / noun / adverb) "
          f"and {len(form_entries)} forms (タ＼カク, マナビマ＼ス, エ＼キオ)")
    if kept:
        print(f"{len(kept)} kept as entered in the app (--force to replace): "
              + "、".join(k[0] for k in kept))
    for reason, words in skipped.items():
        print(f"skipped, {reason} ({len(words)}): " + "、".join(words[:40])
              + (" …" if len(words) > 40 else ""))

    if args.check:
        bad = []
        for word, prons in compounds:
            phrases = analyze_text(word)
            if len(phrases) != 1 or len(phrases[0].moras) != len(split_moras(prons[0][0])):
                continue
            if phrases[0].accent not in [a for _, a in prons]:
                bad.append(f"  {word}: deck {[a for _, a in prons]}, engine {phrases[0].alternatives}")
        checked = len(compounds)
        print(f"\ncompounds where the engine disagrees with the deck ({len(bad)} of {checked}):")
        print("\n".join(bad))


if __name__ == "__main__":
    main()
