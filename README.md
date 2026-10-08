English | [日本語](README.ja.md)

# platina
App for practicing Japanese pitch accent.

> **Using Platina for your lessons? Start here: [LESSONS.md](LESSONS.md)**. It's a step-by-step guide to
> recording your classes, reviewing your mistakes and following your progress, with no programming needed.

Speak (read a book aloud or just talk). Platina transcribes the speech, works out the
expected accent of every accent phrase, including how accents change when words join,
measures the accent you actually produced, and marks the differences:

```
音を聞いた。  →  オト＼オ キイタ━
```

`＼` = the pitch drops after this mora, `━` = it stays high to the end (flat / 平板).
Phrases you said differently are red, and show what you said (`you: オ＼トオ`).

The interface is in English or Japanese: the button at the top right switches (日本語 / English). The choice is
remembered in the browser; the first visit follows the browser's language. All UI text is in `frontend/src/i18n.ts`
(`en`, and `ja` with the same type, so a missing translation is a compile error).

The app has two areas:

- **My lessons** (*Lessons*, *Progress*). Record a whole class, review it afterwards (most obvious mistakes,
  repeated mistakes, the full transcript), and follow your level across lessons. See [LESSONS.md](LESSONS.md).
  Code: `backend/app/{lessons,progress}.py`, `frontend/src/{lessons,progress}.ts`.
- **Workshop** (*Quick check*, *Type*, *My NHK accents*, *Practice*). One-off recordings, typed text, your NHK
  accents, and labelled takes for training. Nothing here changes your lessons or progress.

## How it works

| Step | What | Where |
|---|---|---|
| Expected accent | UniDic 3.1 accents (`aType` / `aConType` / `aModType`), combined with a Python port of OpenJTalk's accent-phrase and accent-combination rules. OpenJTalk's own lexicon goes through the same rules as an independent cross-check. **Your NHK-checked overrides win over both.** | `backend/app/accent/{sources,rules,engine}.py` |
| Rule corrections | Places where the dictionaries' rules disagree with standard Tokyo accent: た after verbs, なく/なけれ/なかっ after heiban verbs, volitional ましょう/でしょう. Each one is backed by gold sentences. | `rules.py` |
| Speech → text | silero-vad splits recordings at pauses; kotoba-whisper v2.0 transcribes each utterance | `backend/app/audio/asr.py` |
| Timing | Mora-level CTC forced alignment (wav2vec2, hiragana) | `backend/app/audio/align.py` |
| Pitch | FCPE (torchfcpe) for the accent model, Praat (parselmouth) as fallback; semitones relative to your median | `backend/app/audio/pitch.py` |
| Speech features | A self-supervised Japanese HuBERT (ReazonSpeech `japanese-hubert-base-k2`): each mora's frames from 4 layers, averaged and compressed (PCA). They show how each mora was said (voicing, devoicing, clarity) beyond the pitch track. | `backend/app/audio/ssl.py` |
| Your accent | A small neural network (bidirectional GRU) reads every mora of the utterance (pitch shape in your own range, voicing, duration, energy, sound class, HuBERT features) and gives each phrase a probability for every accent it could have. Accents the audio can't tell apart (devoiced moras, misaligned moras, a final question rise) are merged, so they never decide a verdict. Trained on 101 native speakers (JSUT + JVS) plus re-pitched copies of their speech with deliberate mistakes. The older gradient-boosted model is the fallback when `accent_model.pt` is missing. | `backend/app/accent/{model,detect}.py` |
| Verdict | correct / **mistake** (red) / unclear / check-the-dictionary (grey). A mistake needs the expected accent to be unlikely **and** another accent to be heard clearly. | `backend/app/analyze.py` |
| Natives | Accents many natives use that dictionaries don't list (mined from 100 JVS speakers) are accepted or shown grey, never red; phrases said in one breath (読んで\|います) are accepted; the pitch chart shows a typical native contour, not just a high/low step. | `accent/{variants,contour}.py`, `engine.py` |

Each expected accent records where it came from:
- **NHK**: all content words in the phrase have one of your overrides.
- **agree**: UniDic and OpenJTalk agree.
- **uncertain**: they don't. Uncertain phrases are never counted as your mistake.

### Accuracy (held-out speakers and sentences, never seen in training)

Every corpus phrase was said correctly by a native, so "false alarm" = a correct accent flagged as a
mistake; "caught" = pretending the dictionary expected each other possible accent, how often that
mistake is flagged. Old = the JSUT-only gradient-boosted detector with the old verdict rule.

| test set | false alarms (old → now) | caught (old → now) | unclear (old → now) | 1 mora off caught |
|---|---|---|---|---|
| JSUT (1 speaker, exact labels) | 2.5 % → **0.8 %** | 58 % → **72 %** | 31 % → 9 % | 37 % → 52 % |
| JVS nonpara30 (other speakers, JSUT labels) | 6.1 % → **4.2 %** | 55 % → **68 %** | 33 % → 11 % | 42 % → 58 % |
| JVS parallel100 (dictionary labels) | 10.8 % → **6.0 %** | 55 % → **68 %** | 28 % → 18 % | 42 % → 59 % |
| native voices re-pitched to a wrong accent | 2.4–3.5 % → **0.3–1.3 %** | 54–60 % → **66–77 %** | 34–42 % → 9–13 % | 40–46 % → 58–73 % |

Notes: JVS false alarms include natives who really used another accent and dictionary errors
(parallel100 is labelled by the engine, not by hand) — the review queue in the Practice tab splits
them by cause. Accuracy on *your* voice is unknown until you've labelled recordings in the Practice
tab (`tools/evaluate.py user.pkl`).

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
./start.sh            # API + frontend (+ VOICEVOX if installed), opens http://localhost:5173/#lessons
```

or by hand:

```sh
cd backend && ../.venv/bin/uvicorn app.main:app --port 8000     # API
cd frontend && npm run dev                                       # http://localhost:5173
```

`PLATINA_API_PORT` / `PLATINA_WEB_PORT` change the ports. Lessons are stored in `backend/data/lessons.sqlite` and
`backend/data/lessons/` (`PLATINA_LESSONS_DB` / `PLATINA_LESSONS_DIR`), both gitignored.

The first analysis downloads the speech models (~2.5 GB) and loads them onto the GPU (about 2.3 GB used).

## Practice tab: teach Platina your voice

Accuracy on *your* voice is only known once there are labelled recordings of it:

- **Practice**: Platina picks a phrase and a target accent — the right one, or a deliberate mistake
  (said flat, a drop added, 1 or 2 moras off). Hear it from the tutor, say the sentence, and keep the
  take only if it sounds like the target. Aim for ~300 correct and ~300 deliberate mistakes over
  several sessions.
- **Wrong verdict?** (phrase details): tell Platina which accent you really said.
- **Review native recordings**: phrases from native speakers that Platina would have flagged —
  was it the speaker, Platina, or the dictionary?

Clips go to `backend/data/recordings/`, labels to `backend/data/labels.sqlite` (both gitignored).
`tools/build_cache.py user` turns them into an evaluation set (held out by session) and training data.

## Making it match NHK (optional)

Platina works without NHK: expected accents come from UniDic and OpenJTalk. Where you know the NHK
日本語発音アクセント新辞典 accent of a word, you can enter it, and it then **replaces the dictionary
accent for that word everywhere**: in conjugated forms, in phrases, and in lessons you re-analyze. Grey
"check the dictionary" words become normal words that can be marked right or wrong. Phrases made only of
such words are labelled **NHK**. If you list several accents, all of them count as correct, and the
first one is the one Platina plays and shows.

The dictionary can't be bundled, so these accents stay on your machine (`backend/data/overrides.sqlite`,
ignored by git). There are two ways to add them:

- **My NHK accents** tab: look up a grey word, or one under *Words to check*, and enter its accent
  number(s) (0 = heiban, n = drop after mora n).
- **From an Anki deck**: export a deck of NHK accents as *Notes in Plain Text* (front `せんせい【先生】`,
  back `センセ↘イ`, `アンキ＝` or `ヨソー━`, one per line) and run
  `cd backend && ../.venv/bin/python -m tools.import_anki deck.txt`. Re-run it after adding cards.
  Accents entered in the app are kept. `--check` lists compounds (美術館, 冷蔵庫) where the rules
  disagree with your cards.
  Cards for one use of a word are kept apart and applied only to that use. One kind says it's
  modified, like `ひと【人】（「優しい〜に」など修飾語を伴って）`: then 優しい人に gets ヒト＼ニ and
  人を呼ぶ stays ヒトオ━. The other kind marks part of speech, like `きのう［名詞］` / `きのう［副詞］`:
  then 昨日まで gets キノ＼ーマデ and 昨日会った gets キノー━.
  Extra lines on a card that spell a form of the word are used as written, in the card's order.
  Examples are conjugations (高い: `タ＼カク`, `タカ＼カッタ`; 学ぶ: `マナビマ＼ス`) and particle forms
  (駅: `エ＼キオ`). Words without such lines fall back to the rules.

For development: **Type** tab → *Save as NHK-checked test case* adds a sentence to
`backend/tests/gold/sentences.yaml`. Entries marked `verified: false` still need checking against NHK.

## Tutor voice

Press ▶ (Type tab, next to each recording, and in the phrase details) to hear a sentence or
phrase said with the accent shown on screen. That includes your NHK overrides and
alternative accents, and you can hear the accent *you* used in the same voice.

The accent always comes from Platina, never from the speech synthesizer. Each phrase becomes
VOICEVOX kana (`音を聞いた。` → `オト'オ/キイタ'`), and Platina then sets every mora's pitch
from the phrase's high/low pattern, because VOICEVOX's own contour is often too faint to
learn from (`backend/app/tutor.py`).

Run the [VOICEVOX engine](https://github.com/VOICEVOX/voicevox_engine/releases) locally
(Linux CPU build, ~1.8 GB download):

```sh
~/.local/share/voicevox/linux-cpu-x64/run          # http://127.0.0.1:50021
```

| env var | default | |
|---|---|---|
| `PLATINA_VOICEVOX_URL` | `http://127.0.0.1:50021` | |
| `PLATINA_VOICEVOX_SPEAKER` | `30` (No.7 アナウンス) | style id from `/speakers`; `11` (玄野武宏) is a good male voice |

Some voices don't follow the pitch Platina asks for. 青山龍星, for example, creaks down on the
last mora of every sentence. Check a voice before switching to it:

```sh
cd backend && ../.venv/bin/python -m tools.check_tutor --speaker 30 11 --out /tmp/tutor
```

On the gold sentences, No.7 is within 0.6 semitones of the requested pitch on average, and
Platina's own detector judges 96 % of its confident phrases correct (玄野武宏: 100 %).
VOICEVOX's terms require a credit, `VOICEVOX:<character>`. The app shows it at the bottom of
the page.

## Tests and tools

```sh
cd backend
../.venv/bin/python -m pytest tests          # engine gold set, detector, model, labels, API, end-to-end
```

Training data (none of it is in the repo; JSUT and JVS are **non-commercial**, so the trained
models are too):

```sh
../.venv/bin/python -m tools.fetch_jsut ~/datasets/jsut16k                  # JSUT basic5000 via HTTP range requests
git clone https://github.com/sarulab-speech/jsut-label ~/datasets/jsut-label  # exact accent labels
../.venv/bin/python -m tools.jvs prepare jvs_ver1.zip ~/datasets/jvs16k      # JVS (download the zip yourself)

# align + pitch-track once (stop the app first: the GPU is small)
../.venv/bin/python -m tools.build_cache jsut ~/datasets/jsut16k ~/datasets/jsut-label/labels/basic5000 jsut.pkl
../.venv/bin/python -m tools.build_cache jvs  ~/datasets/jvs16k  ~/datasets/jsut-label/labels/basic5000 jvs.pkl
../.venv/bin/python -m tools.build_cache user - - user.pkl --f0 fcpe        # your labelled recordings

../.venv/bin/python -m tools.add_f0 jsut.pkl fcpe --out jsut_fcpe.pkl     # FCPE track (same for jvs)

# re-pitched mistakes (audio kept for HuBERT), per split: train, dev, test
PLATINA_F0=fcpe ../.venv/bin/python -m tools.repitch jsut.pkl jvs.pkl --out repitch_train.pkl --split train \
    --max 8000 --identity 0.3 --wav-dir ~/datasets/repitch_wav/train

# HuBERT features: PCA basis, then CACHE.ssl.pkl next to every cache
../.venv/bin/python -m tools.ssl_feats fit jsut_fcpe.pkl jvs_fcpe.pkl --pca ssl_pca.npz
../.venv/bin/python -m tools.ssl_feats extract jsut_fcpe.pkl jvs_fcpe.pkl repitch_*.pkl --pca ssl_pca.npz

# training, thresholds (stored in the checkpoint), evaluation
../.venv/bin/python -m tools.train_accent jsut_fcpe.pkl jvs_fcpe.pkl repitch_train.pkl [user.pkl] \
    --f0 fcpe --epochs 15 --ssl ssl_pca.npz --ssl-drop 0.6 --save
../.venv/bin/python -m tools.tune_thresholds jsut_fcpe.pkl jvs_fcpe.pkl repitch_dev.pkl --f0 fcpe --kinds exact,label,repitch
../.venv/bin/python -m tools.set_thresholds app/accent/accent_model.pt 0.05 0.05 0.5
../.venv/bin/python -m tools.evaluate jsut_fcpe.pkl jvs_fcpe.pkl [user.pkl] --f0 fcpe --split test --detector new

# natives: contour model, variants, review queue (Practice tab)
../.venv/bin/python -m tools.train_contour jsut.pkl jvs.pkl --save
../.venv/bin/python -m tools.mine_variants jvs.pkl
../.venv/bin/python -m tools.review_queue jsut.pkl jvs.pkl --split dev
```

`PLATINA_ACCENT_MODEL` points the app at another checkpoint; `PLATINA_F0=fcpe` switches the
pitch tracker (the checkpoint records which one it was trained with);
`PLATINA_TUTOR_CONTOUR=1` makes the tutor follow the native contour model.
