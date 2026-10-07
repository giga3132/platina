"""Import NHK accents written down in an Anki deck into the overrides store.

The deck is a plain-text Anki export (Notes in Plain Text, HTML kept): front =
headword (先生, せんせい【先生】, よそう《×装う》, 辺（ヘン）, ...), back = one
pronunciation per line in katakana or hiragana, with ↘ / ＼ after the accent
nucleus and ＝ / ━ at the end of a heiban word. The first lines that read as
the headword are its accents (first = preferred); later lines (inflections,
"毛を ケオ━", notes) are ignored.

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


def parse_head(field: str) -> tuple[list[str], str | None]:
    """Headword forms and the kana reading, if the card gives one."""
    head = _lines(field)[0]
    m = re.match(r"^([ぁ-んァ-ヴー]+)[【《](.+?)[】》]", head)
    if m:
        forms = re.sub(r"[×△▽〈〉]", "", m.group(2)).split("・")
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
        if len(ms) == 1 and same_word(kana, ms[0].lemma_reading):
            if _affix(ms[0]):
                return None, "function word or affix", ms
            return ms[0].lemma, ms[0].lemma_reading, accents
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

    entries: dict[tuple[str, str], list[int]] = defaultdict(list)
    heads: dict[tuple[str, str], str] = {}
    skipped: dict[str, list[str]] = defaultdict(list)
    compounds: list[tuple[str, list[tuple[str, int]]]] = []
    for front, back in read_deck(args.deck):
        forms, hint = parse_head(front)
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
        key = (lemma, reading)
        heads.setdefault(key, forms[0])
        entries[key] += [a for a in accents if a not in entries[key]]

    store = OverrideStore()
    manual = {(o["lemma"], o["reading"]) for o in store.all() if not o["note"].startswith("anki")}
    kept = [k for k in entries if k in manual and not args.force]
    changed = sum(1 for (l, r), accs in entries.items()
                  if (m := unidic_morphs(l)) and len(m) == 1 and m[0].accents[:1] != accs[:1])
    if not args.dry_run:
        stale = [(o["lemma"], o["reading"]) for o in store.all()
                 if o["note"].startswith("anki") and (o["lemma"], o["reading"]) not in entries]
        for key in stale:
            store.delete(*key)
        for (lemma, reading), accs in entries.items():
            if (lemma, reading) not in kept:
                store.put(lemma, reading, accs, f"anki: {heads[(lemma, reading)]}")

    print(f"{len(entries)} words {'would be ' if args.dry_run else ''}imported "
          f"({changed} with a different first accent than UniDic)")
    if kept:
        print(f"{len(kept)} kept as entered in the app (--force to replace): "
              + "、".join(l for l, _ in kept))
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
