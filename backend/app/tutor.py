"""Tutor voice: says text with exactly the accent Platina expects.

The accent comes from the engine (NHK overrides > UniDic + rules), never from
the speech synthesizer. VOICEVOX only renders it: we hand it AquesTalk-style
kana, where ' marks the accent nucleus of each accent phrase.

    音を聞いた。 → オト'オ/キイタ'

Run the VOICEVOX engine locally (default http://127.0.0.1:50021).
"""

from __future__ import annotations

import os
from functools import lru_cache

import httpx

from .accent.engine import Phrase
from .accent.kana import strip_reading_hints, vowel_of

VOICEVOX_URL = os.environ.get("PLATINA_VOICEVOX_URL", "http://127.0.0.1:50021")
# No.7 アナウンス: announcer style, and it follows the requested pitch closely
# (some voices, e.g. 青山龍星, creak down on the last mora whatever we ask).
SPEAKER = int(os.environ.get("PLATINA_VOICEVOX_SPEAKER", "30"))

PAUSE_CHARS = set("、。，．,.！？!?…・「」『』（）()　 \n")
_VOWEL_KANA = {"a": "ア", "i": "イ", "u": "ウ", "e": "エ", "o": "オ"}


class TutorUnavailable(RuntimeError):
    pass


def _normalize(moras: list[str]) -> list[str]:
    """ー → the previous mora's vowel; VOICEVOX's kana parser has no ー."""
    out: list[str] = []
    for m in moras:
        if m == "ー" and out and vowel_of(out[-1]):
            m = _VOWEL_KANA[vowel_of(out[-1])]
        out.append(m)
    return out


def phrase_kana(moras: list[str], accent: int) -> str:
    """One accent phrase. Heiban puts ' after the last mora: inside a phrase
    (particles included) heiban and odaka sound the same."""
    if not moras:
        raise ValueError("phrase has no reading")
    if not 0 <= accent <= len(moras):
        raise ValueError(f"accent {accent} outside 0..{len(moras)}")
    moras = _normalize(moras)
    nucleus = accent or len(moras)
    return "".join(moras[:nucleus]) + "'" + "".join(moras[nucleus:])


def to_kana(phrases: list[Phrase], text: str, accents: dict[int, int] | None = None) -> str:
    """Accent phrases → VOICEVOX kana. Punctuation between phrases becomes a
    pause (、), otherwise phrases are joined in one breath (/). `accents`
    replaces the accent of some phrases (index among phrases with moras),
    e.g. to say a deliberate mistake in the Practice tab."""
    text = strip_reading_hints(text)[0]  # phrase offsets are into the text without hints
    phrases = [p for p in phrases if p.moras]
    if not phrases:
        raise ValueError("nothing to say")
    acc = [(accents or {}).get(i, p.accent) for i, p in enumerate(phrases)]
    out = phrase_kana(phrases[0].moras, acc[0])
    for i, (prev, p) in enumerate(zip(phrases, phrases[1:]), start=1):
        gap = text[prev.end:p.start]
        out += "、" if any(c in PAUSE_CHARS for c in gap) else "/"
        out += phrase_kana(p.moras, acc[i])
    if text.rstrip().endswith(("？", "?")):
        out += "？"
    return out


# Pitch shaping, in VOICEVOX's units (ln Hz; 0.058 ≈ 1 semitone).
STEP = 0.23            # high vs. low within a phrase, ≈ 4 st: clear, teacher-like
INITIAL_RISE = 0.16    # the phrase-initial low before a rise is shallower
DECLINATION = 0.03     # each later phrase in a breath group starts a bit lower
DOWNSTEP = 0.07        # extra lowering after a phrase with a drop (catathesis)
FLOOR = 0.25           # long breath groups don't sink further than this


# PLATINA_TUTOR_CONTOUR=1: shape each phrase like natives do (accent/contour.py)
# instead of a flat high/low step. Check with tools/check_tutor.py first.
USE_CONTOUR = os.environ.get("PLATINA_TUTOR_CONTOUR") == "1"


def _contour_levels(n: int, accent: int, prev_drop: bool, final: bool) -> list[float] | None:
    """Per-mora offsets below the phrase's top (ln Hz), from the native contour model."""
    from .accent import contour

    if not (USE_CONTOUR and contour.available()):
        return None
    c = contour.predict(n, 0 if accent == n else accent, None, prev_drop, final).mean(axis=1)
    span = float(c.max() - c.min())
    if span < 1e-6:
        return [0.0] * n
    return [float((v - c.max()) / span * STEP) for v in c]


def shape_pitch(accent_phrases: list[dict]) -> None:
    """Replace VOICEVOX's predicted pitch with the H/L pattern of each phrase's
    accent. VOICEVOX conditions on the accent but renders it faintly (e.g.
    ヨミマ'ス comes out flat), too weak to teach from. Devoiced moras (pitch 0)
    stay devoiced; a pause resets the declination. A final ？ is still raised by
    VOICEVOX's own upspeak at synthesis."""
    voiced = [m["pitch"] for ap in accent_phrases for m in ap["moras"] if m["pitch"] > 0]
    if not voiced:
        return
    top = max(voiced)
    high = top
    prev_drop = False
    for k, ap in enumerate(accent_phrases):
        n = len(ap["moras"])
        accent = ap["accent"]  # 1-based nucleus; heiban arrives as n
        native = _contour_levels(n, accent, prev_drop, bool(ap.get("pause_mora")) or k == len(accent_phrases) - 1)
        prev_drop = accent < n and not ap.get("pause_mora")
        for i, m in enumerate(ap["moras"]):
            if m["pitch"] <= 0:
                continue
            if native is not None:
                m["pitch"] = high + native[i]
            elif 0 < i < accent:
                m["pitch"] = high
            elif i == 0:
                m["pitch"] = high if accent == 1 else high - INITIAL_RISE
            else:
                m["pitch"] = high - STEP
        if ap.get("pause_mora"):
            high = top
        else:
            high = max(high - DECLINATION - (DOWNSTEP if accent < n else 0), top - FLOOR)


def _client() -> httpx.Client:
    return httpx.Client(base_url=VOICEVOX_URL, timeout=60)


def _unavailable(e: Exception) -> TutorUnavailable:
    return TutorUnavailable(
        f"VOICEVOX engine not reachable at {VOICEVOX_URL} ({e}). "
        "Start it, e.g. ~/.local/share/voicevox/linux-cpu-x64/run")


def audio_query(kana: str, speed: float = 1.0, speaker: int = SPEAKER) -> dict:
    """Kana → VOICEVOX audio query with Platina's pitch pattern."""
    try:
        with _client() as c:
            phrases = c.post("/accent_phrases",
                             params={"text": kana, "speaker": speaker, "is_kana": True})
            if phrases.status_code == 400:
                raise ValueError(f"VOICEVOX rejected {kana!r}: {phrases.text}")
            phrases.raise_for_status()
            query = c.post("/audio_query", params={"text": "あ", "speaker": speaker})
            query.raise_for_status()
    except httpx.TransportError as e:
        raise _unavailable(e) from e
    q = query.json()
    q["accent_phrases"] = phrases.json()
    shape_pitch(q["accent_phrases"])
    q["speedScale"] = speed
    return q


def render(query: dict, speaker: int = SPEAKER) -> bytes:
    try:
        with _client() as c:
            wav = c.post("/synthesis", params={"speaker": speaker}, json=query)
            wav.raise_for_status()
            return wav.content
    except httpx.TransportError as e:
        raise _unavailable(e) from e


@lru_cache(maxsize=256)
def synthesize(kana: str, speed: float = 1.0, speaker: int = SPEAKER) -> bytes:
    """Kana → WAV bytes via the VOICEVOX engine."""
    return render(audio_query(kana, speed, speaker), speaker)


def speakers() -> list[dict]:
    try:
        return httpx.get(f"{VOICEVOX_URL}/speakers", timeout=10).json()
    except httpx.TransportError as e:
        raise TutorUnavailable(f"VOICEVOX engine not reachable at {VOICEVOX_URL}") from e


def speaker_name(speaker: int = SPEAKER) -> str:
    """Character name for the credit line VOICEVOX's terms require."""
    for s in speakers():
        if any(st["id"] == speaker for st in s["styles"]):
            return s["name"]
    return "unknown"
