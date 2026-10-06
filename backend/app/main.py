"""Platina API.

Run from backend/:  ../.venv/bin/uvicorn app.main:app --reload
"""

from __future__ import annotations

import threading
from collections import Counter
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .accent.engine import analyze_text, notation
from .accent.overrides import OverrideStore

app = FastAPI(title="Platina")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

overrides = OverrideStore()
_gpu = threading.Lock()  # one analysis at a time: the models share a 4 GB GPU


class TextIn(BaseModel):
    text: str


GOLD = Path(__file__).resolve().parents[1] / "tests" / "gold" / "sentences.yaml"


class GoldIn(BaseModel):
    text: str
    expected: str = Field(description="notation checked in NHK, e.g. オト＼オ キイタ━")
    note: str = ""


class OverrideIn(BaseModel):
    lemma: str = Field(description="dictionary form, e.g. 聞く")
    reading: str = Field(description="reading in kana, e.g. きく")
    accents: list[int] = Field(description="NHK accent numbers, preferred first, e.g. [0]")
    note: str = ""


@app.post("/expected")
def expected(body: TextIn):
    phrases = analyze_text(body.text, overrides)
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
            r = analyze_audio(u.wav, u.text, overrides, offset=u.start)
            results.append({"start": round(u.start, 3), "end": round(u.end, 3), **r})

    counts = Counter(p["status"] for r in results for p in r["phrases"])
    return {"duration": round(len(wav) / SAMPLE_RATE, 3), "utterances": results,
            "summary": dict(counts)}
