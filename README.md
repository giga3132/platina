# platina
App for practicing Japanese pitch accent.

Speak (read a book aloud or just talk). Platina transcribes the speech, works out the
expected accent of every accent phrase, including how accents change when words join,
measures the accent you actually produced, and marks the differences:

```
音を聞いた。  →  オト＼オ キイタ━
```

`＼` = the pitch drops after this mora, `━` = it stays high to the end (flat / 平板).
Phrases you said differently are red, and show what you said (`you: オ＼トオ`).

## How it works

| Step | What | Where |
|---|---|---|
| Expected accent | UniDic 3.1 accents (`aType` / `aConType` / `aModType`), combined with a Python port of OpenJTalk's accent-phrase and accent-combination rules. OpenJTalk's own lexicon goes through the same rules as an independent cross-check. **Your NHK-checked overrides win over both.** | `backend/app/accent/{sources,rules,engine}.py` |
| Rule corrections | Places where the dictionaries' rules disagree with standard Tokyo accent: た after verbs, なく/なけれ/なかっ after heiban verbs, volitional ましょう/でしょう. Each one is backed by gold sentences. | `rules.py` |
| Speech → text | silero-vad splits recordings at pauses; kotoba-whisper v2.0 transcribes each utterance | `backend/app/audio/asr.py` |
| Timing | Mora-level CTC forced alignment (wav2vec2, hiragana) | `backend/app/audio/align.py` |
| Pitch | Praat F0 (parselmouth), in semitones relative to your median | `backend/app/audio/pitch.py` |
| Your accent | A gradient-boosted classifier scores "the pitch falls after mora *a*" for each mora. Together these give a probability for each accent the phrase could have. | `backend/app/accent/{features,detect}.py` |
| Verdict | correct / **mistake** (red) / unclear / check-the-dictionary (grey) | `backend/app/analyze.py` |

Each expected accent records where it came from:
- **NHK**: all content words in the phrase have one of your overrides.
- **agree**: UniDic and OpenJTalk agree.
- **uncertain**: they don't. Uncertain phrases are never counted as your mistake.

### Accuracy (native read speech, held-out JSUT sentences)

| | correct accent flagged (false alarm) | wrong accent caught |
|---|---|---|
| expected flat | 2.6 % | 75 % |
| expected a drop | 3.3 % | 71 % |

Caught by kind of mistake (threshold 0.05): accent 2+ moras off 94 %, accented word said
flat 81 %, accent 1 mora off 63 %. These numbers come from one native speaker, so expect
some differences on your own voice.

## Setup

```sh
# backend (Python 3.12)
python3.12 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
.venv/bin/python -m unidic download

# frontend
cd frontend && npm install
```

## Run

```sh
cd backend && ../.venv/bin/uvicorn app.main:app --port 8000     # API
cd frontend && npm run dev                                       # http://localhost:5173
```

The first analysis downloads the speech models (~2.5 GB) and loads them onto the GPU (about 2.3 GB used).

## Making it match NHK

The NHK 日本語発音アクセント新辞典 can't be bundled, so you supply it yourself:

- **My NHK accents** tab: for a word marked grey, or listed under *Words to check*, look it up
  in the NHK app and enter its accent number(s). The override is stored per dictionary form, so
  conjugated forms and phrases follow automatically. It is saved in `backend/data/overrides.sqlite`,
  which git ignores.
- **Type** tab → *Save as NHK-checked test case*: adds a sentence to
  `backend/tests/gold/sentences.yaml`. Entries with `verified: false` were filled in from general
  knowledge and still need checking against NHK.

## Tests and tools

```sh
cd backend
../.venv/bin/python -m pytest tests          # engine gold set, detector, API, end-to-end
../.venv/bin/python -m tools.train_detector WAV_DIR LABEL_DIR --save   # retrain + held-out report
```

`tools/train_detector.py` uses the [JSUT corpus](https://sites.google.com/site/shinnosuketakamichi/publication/jsut)
with [jsut-label](https://github.com/sarulab-speech/jsut-label). Neither is included here.
JSUT is licensed for non-commercial use, and the shipped `detector_model.joblib` is trained on
it, so keep the app non-commercial or retrain on data you are licensed to use.
