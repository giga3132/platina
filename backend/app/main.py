"""Platina API.

Run from backend/:  ../.venv/bin/uvicorn app.main:app --reload
"""

from __future__ import annotations

import threading
from collections import Counter
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

import json

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .accent.engine import analyze_text, notation
from .accent.overrides import OverrideStore
from .accent.variants import VariantStore
from .labels import DATA, LabelStore
from .lessons import LessonJobs, LessonStore


@asynccontextmanager
async def lifespan(_app):
    jobs.resume()  # lessons a restart interrupted
    yield


app = FastAPI(title="Platina", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

overrides = OverrideStore()
labels = LabelStore()
variants = VariantStore()
lessons = LessonStore()
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
    context: str = Field("", description="use this accent applies to: '' (any), modified, "
                                         "unmodified, noun or adverb")


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
    try:
        overrides.put(body.lemma, body.reading, body.accents, body.note, body.context)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"ok": True}


@app.delete("/overrides")
def delete_override(lemma: str, reading: str, context: str | None = None):
    overrides.delete(lemma, reading, context)
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
    lesson: str | None = Field(None, description="cut the clip from this lesson's audio instead of an upload")
    text: str
    phrase_index: int = Field(description="index into analyze_text(text)'s phrases")
    said: int | None = Field(None, description="accent really said (0 = flat); null = not sure")
    start: float = 0.0  # utterance within the uploaded recording
    end: float | None = None
    verdict: str | None = None
    session: str = ""


@app.post("/labels")
def add_label(audio: UploadFile | None = File(None), meta: str = Form(...)):
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
    if m.lesson:
        if _lesson(m.lesson)["status"] != "done":
            raise HTTPException(409, "the lesson isn't analyzed yet")
        clip = labels.save_clip(load_audio(lessons.audio(m.lesson), start=m.start, end=m.end))
    elif audio is not None:
        wav = load_audio(audio.file.read())
        end = len(wav) if m.end is None else int(m.end * SAMPLE_RATE)
        clip = labels.save_clip(wav[int(m.start * SAMPLE_RATE):end])
    else:
        raise HTTPException(422, "send the audio or a lesson id")
    labels.add(source=m.source, clip=clip, text=m.text, phrase_index=m.phrase_index, moras=p.moras,
               expected=p.alternatives, said=m.said, verdict=m.verdict, session=m.session or m.lesson or "")
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


# --- lessons: a whole class recorded, analyzed afterwards ------------------------

def analysis_version() -> str:
    """Names what a verdict depends on (accent model, NHK overrides, native
    variants), so lessons analyzed under an older one can be redone."""
    import hashlib

    from .accent import model as learned

    h = hashlib.sha1()
    if learned.MODEL.exists():
        st = learned.MODEL.stat()
        h.update(f"{st.st_size}:{st.st_mtime_ns}".encode())
    h.update(json.dumps(overrides.all(), sort_keys=True, ensure_ascii=False).encode())
    h.update(json.dumps(overrides.all_forms(), sort_keys=True, ensure_ascii=False).encode())
    h.update(json.dumps(sorted((v["key"], v["accent"], v["status"]) for v in variants.all()),
                        ensure_ascii=False).encode())
    return h.hexdigest()[:12]


def _segment(wav):
    from .audio.asr import segment

    return [(u.start, u.end) for u in segment(wav)]


def _transcribe(wav):
    from .audio.asr import transcribe

    return transcribe(wav)


def _analyze(wav, text, offset):
    from .analyze import analyze_audio

    return analyze_audio(wav, text, overrides, offset=offset, variants=variants)


jobs = LessonJobs(lessons, segment=_segment, transcribe=_transcribe, analyze=_analyze,
                  version=analysis_version, gpu=_gpu)


def _lesson(lid: str) -> dict:
    try:
        lesson = lessons.get(lid)
    except KeyError:
        lesson = None
    if lesson is None:
        raise HTTPException(404, "no such lesson")
    return lesson


def _brief(lesson: dict, version: str) -> dict:
    out = {k: lesson[k] for k in ("id", "created_at", "title", "status", "done", "total", "duration", "error")}
    out["summary"] = lesson["summary"]
    out["outdated"] = lesson["status"] == "done" and lesson["version"] != version
    return out


class LessonIn(BaseModel):
    title: str = ""


@app.post("/lessons")
def lesson_create(body: LessonIn | None = None):
    """Start recording a lesson; pieces follow with /lessons/{id}/chunk."""
    return {"id": lessons.create(body.title if body else "")}


@app.post("/lessons/upload")
def lesson_upload(audio: UploadFile = File(...), title: str = Form("")):
    """A whole recording made elsewhere (phone, Zoom), analyzed like a lesson."""
    lid = lessons.create(title or Path(audio.filename or "").stem)
    lessons.save_upload(lid, audio.file.read())
    try:
        lessons.finish(lid)
    except Exception as e:  # noqa: BLE001 - not audio ffmpeg can read
        lessons.delete(lid)
        raise HTTPException(422, f"couldn't read this file as audio: {e}") from e
    jobs.submit(lid)
    return {"id": lid}


@app.post("/lessons/{lid}/chunk")
async def lesson_chunk(lid: str, seq: int, request: Request):
    """Piece `seq` of a lesson being recorded (raw MediaRecorder data)."""
    _lesson(lid)
    try:
        saved = lessons.append_chunk(lid, seq, await request.body())
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    return {"saved": saved}


@app.post("/lessons/{lid}/finish")
def lesson_finish(lid: str):
    lesson = _lesson(lid)
    if lesson["status"] != "recording":
        raise HTTPException(409, "already finished")
    try:
        lessons.finish(lid)
    except ValueError as e:  # nothing recorded
        lessons.delete(lid)
        raise HTTPException(422, str(e)) from e
    except Exception as e:  # noqa: BLE001 - keep the raw pieces, show the error in the list
        lessons.update(lid, status="failed", error=f"couldn't convert the recording: {e}")
        raise HTTPException(422, f"couldn't convert the recording: {e}") from e
    jobs.submit(lid)
    return {"ok": True}


@app.post("/lessons/{lid}/retry")
def lesson_retry(lid: str):
    """Analyze again after a failure."""
    if _lesson(lid)["status"] != "failed":
        raise HTTPException(409, "only a failed lesson can be retried")
    if lessons.audio(lid).exists():
        jobs.submit(lid)
        return {"ok": True}
    lessons.update(lid, status="recording")  # the conversion failed: try it again
    return lesson_finish(lid)


@app.get("/lessons")
def lesson_list():
    version = analysis_version()
    return [_brief(ls, version) for ls in reversed(lessons.all())]


@app.get("/lessons/{lid}")
def lesson_get(lid: str):
    return {**_brief(_lesson(lid), analysis_version()), "utterances": lessons.utterances(lid)}


@app.get("/lessons/{lid}/audio")
def lesson_audio(lid: str):
    _lesson(lid)
    if not lessons.audio(lid).exists():
        raise HTTPException(404, "no audio yet")
    return FileResponse(lessons.audio(lid), media_type="audio/webm")


@app.patch("/lessons/{lid}")
def lesson_rename(lid: str, body: LessonIn):
    _lesson(lid)
    lessons.update(lid, title=body.title.strip() or "Lesson")
    return {"ok": True}


@app.delete("/lessons/{lid}")
def lesson_delete(lid: str):
    _lesson(lid)
    lessons.delete(lid)
    return {"ok": True}


@app.put("/lessons/{lid}/utterances/{idx}")
def lesson_fix_line(lid: str, idx: int, body: TextIn):
    """Corrected transcript for one line: only that line is judged again."""
    if _lesson(lid)["status"] != "done":
        raise HTTPException(409, "the lesson is still being analyzed")
    try:
        u = jobs.reanalyze_line(lid, idx, body.text.strip())
    except KeyError as e:
        raise HTTPException(404, "no such line") from e
    return {"utterance": u, "summary": lessons.get(lid)["summary"]}


@app.post("/lessons/reanalyze")
def lesson_reanalyze():
    """Judge lessons analyzed with an older model or older NHK accents again."""
    version = analysis_version()
    todo = [ls["id"] for ls in lessons.all() if ls["status"] == "done" and ls["version"] != version]
    for lid in todo:
        jobs.submit(lid)
    return {"queued": len(todo)}


@app.get("/progress")
def progress_overview():
    from .progress import overview

    version = analysis_version()
    return overview([_brief(ls, version) for ls in lessons.all()], lessons.utterances)
