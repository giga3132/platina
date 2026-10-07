"""Platina API.

Run from backend/:  ../.venv/bin/uvicorn app.main:app --reload
"""

from __future__ import annotations

import threading
from collections import Counter
from pathlib import Path
from urllib.parse import quote

import json

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .accent.engine import analyze_text, notation
from .accent.overrides import OverrideStore
from .accent.variants import VariantStore
from .labels import DATA, LabelStore

app = FastAPI(title="Platina")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

overrides = OverrideStore()
labels = LabelStore()
variants = VariantStore()
REVIEW = DATA / "review.json"  # written by tools/review_queue.py
_gpu = threading.Lock()  # one analysis at a time: the models share a 4 GB GPU


class TextIn(BaseModel):
    text: str


GOLD = Path(__file__).resolve().parents[1] / "tests" / "gold" / "sentences.yaml"


class GoldIn(BaseModel):
    text: str
    expected: str = Field(description="notation checked in NHK, e.g. オト＼オ キイタ━")
    note: str = ""


class SpeakIn(BaseModel):
    text: str
    speed: float = Field(1.0, ge=0.5, le=2.0)
    accents: dict[int, int] | None = Field(
        None, description="phrase index (among phrases with a reading) → accent to say instead")


class SpeakPhraseIn(BaseModel):
    moras: list[str]
    accent: int = Field(description="0 = heiban, n = drop after mora n")
    speed: float = Field(1.0, ge=0.5, le=2.0)


class OverrideIn(BaseModel):
    lemma: str = Field(description="dictionary form, e.g. 聞く")
    reading: str = Field(description="reading in kana, e.g. きく")
    accents: list[int] = Field(description="NHK accent numbers, preferred first, e.g. [0]")
    note: str = ""


@app.post("/expected")
def expected(body: TextIn):
    phrases = analyze_text(body.text, overrides, variants)
    return {
        "text": body.text,
        "notation": notation(phrases),
        "phrases": [p.to_dict() for p in phrases],
    }


@app.post("/gold")
def add_gold(body: GoldIn):
    """Append an NHK-checked sentence to the engine's regression tests."""
    import yaml

    entry = {"text": body.text.strip(), "expected": " ".join(body.expected.split()),
             "verified": True}
    if body.note:
        entry["note"] = body.note
    text = GOLD.read_text()
    with GOLD.open("a") as fh:
        if text and not text.endswith("\n"):
            fh.write("\n")
        fh.write("- " + yaml.safe_dump(entry, allow_unicode=True, default_flow_style=True,
                                       sort_keys=False, width=1000))
    return {"ok": True}


@app.get("/overrides")
def list_overrides():
    return overrides.all()


@app.put("/overrides")
def put_override(body: OverrideIn):
    overrides.put(body.lemma, body.reading, body.accents, body.note)
    return {"ok": True}


@app.delete("/overrides")
def delete_override(lemma: str, reading: str):
    overrides.delete(lemma, reading)
    return {"ok": True}


def _speak(kana: str, speed: float) -> Response:
    from . import tutor

    try:
        wav = tutor.synthesize(kana, speed)
    except tutor.TutorUnavailable as e:
        raise HTTPException(503, str(e)) from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return Response(wav, media_type="audio/wav", headers={"X-Platina-Kana": quote(kana)})


@app.post("/speak")
def speak(body: SpeakIn):
    """The tutor says `text` with the expected accent shown on screen."""
    from .tutor import to_kana

    try:
        kana = to_kana(analyze_text(body.text, overrides, variants), body.text, body.accents)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return _speak(kana, body.speed)


@app.post("/speak/phrase")
def speak_phrase(body: SpeakPhraseIn):
    """One accent phrase with a given accent (an alternative, or what the user said)."""
    from .tutor import phrase_kana

    try:
        kana = phrase_kana(body.moras, body.accent)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return _speak(kana, body.speed)


@app.get("/speak/credit")
def speak_credit():
    """VOICEVOX's terms require crediting the character: "VOICEVOX:<name>"."""
    from . import tutor

    try:
        return {"credit": f"VOICEVOX:{tutor.speaker_name()}"}
    except tutor.TutorUnavailable as e:
        raise HTTPException(503, str(e)) from e


@app.post("/analyze")
def analyze(audio: UploadFile = File(...), text: str | None = Form(None)):
    """Recording → transcript (or the given text) → per-phrase accent verdicts.
    With `text`, the whole recording is taken to be that text."""
    from .analyze import analyze_audio
    from .audio.asr import Utterance, recognize
    from .audio.pitch import SAMPLE_RATE, load_audio

    wav = load_audio(audio.file.read())
    with _gpu:
        if text and text.strip():
            utterances = [Utterance(0.0, len(wav) / SAMPLE_RATE, wav, text.strip())]
        else:
            utterances = recognize(wav)
        results = []
        for u in utterances:
            r = analyze_audio(u.wav, u.text, overrides, offset=u.start, variants=variants)
            results.append({"start": round(u.start, 3), "end": round(u.end, 3), **r})

    counts = Counter(p["status"] for r in results for p in r["phrases"])
    return {"duration": round(len(wav) / SAMPLE_RATE, 3), "utterances": results,
            "summary": dict(counts)}


# --- labelled recordings (Practice tab, "Wrong verdict?", native review) -------

class LabelMeta(BaseModel):
    source: str = Field(pattern="^(practice|report)$")
    text: str
    phrase_index: int = Field(description="index into analyze_text(text)'s phrases")
    said: int | None = Field(None, description="accent really said (0 = flat); null = not sure")
    start: float = 0.0  # utterance within the uploaded recording
    end: float | None = None
    verdict: str | None = None
    session: str = ""


@app.post("/labels")
def add_label(audio: UploadFile = File(...), meta: str = Form(...)):
    """Store one utterance of the user's voice with the accent really said
    in one of its phrases."""
    from .audio.pitch import SAMPLE_RATE, load_audio

    m = LabelMeta(**json.loads(meta))
    phrases = analyze_text(m.text, overrides)
    if not 0 <= m.phrase_index < len(phrases) or not phrases[m.phrase_index].moras:
        raise HTTPException(422, "no such phrase")
    p = phrases[m.phrase_index]
    if m.said is not None and not 0 <= m.said <= len(p.moras):
        raise HTTPException(422, "accent out of range")
    wav = load_audio(audio.file.read())
    end = len(wav) if m.end is None else int(m.end * SAMPLE_RATE)
    clip = labels.save_clip(wav[int(m.start * SAMPLE_RATE):end])
    labels.add(source=m.source, clip=clip, text=m.text, phrase_index=m.phrase_index, moras=p.moras,
               expected=p.alternatives, said=m.said, verdict=m.verdict, session=m.session)
    return {"ok": True, "stats": labels.stats()}


@app.get("/labels/stats")
def label_stats():
    return labels.stats()


def _review_items() -> list[dict]:
    return json.loads(REVIEW.read_text()) if REVIEW.exists() else []


@app.get("/review/next")
def review_next():
    """Next native corpus phrase the detector flagged, for the user to judge."""
    done = {r["note"] for r in labels.all() if r["source"] == "review"}
    items = _review_items()
    for it in items:
        if it["id"] not in done:
            return {**it, "remaining": sum(i["id"] not in done for i in items)}
    return {"remaining": 0}


@app.get("/review/audio/{item_id:path}")
def review_audio(item_id: str):
    for it in _review_items():
        if it["id"] == item_id:
            return FileResponse(it["path"])
    raise HTTPException(404)


class ReviewIn(BaseModel):
    id: str
    answer: str = Field(pattern="^(variant|misheard|dictionary|unsure)$")


@app.post("/review")
def review_answer(body: ReviewIn):
    for it in _review_items():
        if it["id"] == body.id:
            labels.add(source="review", clip=it["path"], text=it["text"], phrase_index=it["phrase"],
                       moras=it["moras"], expected=it["expected"], said=None, verdict=it["heard_notation"],
                       answer=body.answer, speaker=it["spk"], note=it["id"])
            return {"ok": True}
    raise HTTPException(404)


@app.get("/practice/next")
def practice_next(text: str | None = None):
    """A sentence, one of its phrases and a target accent to imitate: the
    expected accent, or (about half the time) a typical learner mistake."""
    import random

    import yaml

    from .accent.features import possible
    from .accent.kana import special_moras

    if not text:
        text = random.choice([e["text"] for e in yaml.safe_load(GOLD.read_text())])
    phrases = analyze_text(text, overrides)
    voiced = [i for i, p in enumerate(phrases) if len(p.moras) >= 2]
    if not voiced:
        raise HTTPException(422, "no phrase to practise")
    idx = random.choice(voiced)
    p = phrases[idx]
    n = len(p.moras)
    ok = possible(n, special_moras(p.moras))
    accented = [a for a in range(1, n) if ok[a - 1]]
    target, kind = p.accent, "expected"
    if random.random() < 0.5:
        flat = p.accent in (0, n)
        options = ([("added a drop", a) for a in accented] if flat else
                   [("said flat", 0)] + [("1 mora off" if abs(a - p.accent) == 1 else "2+ moras off", a)
                                         for a in accented if a != p.accent])
        if options:
            kind, target = random.choice(options)
    with_moras = [i for i, q in enumerate(phrases) if q.moras]
    return {"text": text, "phrases": [q.to_dict() for q in phrases], "phrase_index": idx,
            "speak_index": with_moras.index(idx), "target": target, "kind": kind}


# --- native variants (tools/mine_variants.py) ----------------------------------

@app.get("/variants")
def list_variants():
    return variants.all()


class VariantStatusIn(BaseModel):
    key: str
    accent: int
    status: str = Field(pattern="^(approved|rejected|proposed)$")


@app.put("/variants")
def set_variant(body: VariantStatusIn):
    variants.set_status(body.key, body.accent, body.status)
    return {"ok": True}
