# Using Platina for your lessons

Welcome! This guide is for you if you take Japanese classes (on Zoom, for example) and want to know how your
**pitch accent** is doing: which words you say with the wrong rise and fall, which mistakes you keep repeating, and
whether you're improving over time.

You don't need to know anything about programming. Each step tells you what to type and what you should see.

## Contents

1. [What Platina does in a lesson](#1-what-platina-does-in-a-lesson)
2. [What you need](#2-what-you-need)
3. [One-time setup](#3-one-time-setup)
4. [Before class](#4-before-class)
5. [During class](#5-during-class)
6. [After class: your review](#6-after-class-your-review)
7. [Recorded somewhere else? Upload it](#7-recorded-somewhere-else-upload-it)
8. [Your progress](#8-your-progress)
9. [Tips](#9-tips)
10. [Privacy](#10-privacy)
11. [Troubleshooting](#11-troubleshooting)

## 1. What Platina does in a lesson

You press **Start lesson recording** before class and **Stop and analyze** after it. A few minutes later Platina shows
you, for everything you said in Japanese:

- **Most obvious mistakes**: the phrases where Platina is surest your accent was different. For example
  橋 said like 箸: *expected* ハシ＼ (high, then low), *you said* ハ＼シ (it dropped right after ハ).
- **Repeated mistakes**: the same word said the same wrong way several times.
- **Everything you said**: the whole lesson as text, so you can go through it line by line and listen to yourself.

Every lesson is saved, and the **Progress** page shows how your level changes from lesson to lesson.

How to read the accent marks:

| Mark | Meaning |
|---|---|
| A line over a sound (オ̄) | that part is said high |
| ＼ | the pitch drops after this sound |
| ━ | the word stays high to the end (flat, 平板) |

Next to every phrase, Platina also writes its verdict in words: *Correct*, *Mistake*, *Unclear* (it couldn't hear it
well enough to judge, so it doesn't count) or *Check the dictionary* (the dictionaries disagree, so it doesn't count either).

## 2. What you need

- **A computer running Linux** (macOS should work too).
- **About 12 GB of free disk space** for Platina and its speech models.
- **Headphones or earbuds during class.** Platina records your microphone exactly as it is (that keeps your pitch
  accurate). If your teacher's voice comes out of the laptop speakers, the microphone picks it up too, and their
  Japanese would be judged as yours.
- **Chrome, Firefox, or another modern browser.**
- **Ideally an NVIDIA graphics card** with at least 4 GB of memory. Without one Platina still works, it just takes
  longer to analyze a lesson: about 5 minutes for every minute you spoke.

## 3. One-time setup

You do this once. Open a terminal in the Platina folder and copy-paste these lines.

**1. Check you have the basic tools.** Each command should print a version number:

```sh
python3.12 --version
node --version
ffmpeg -version
```

If one says "command not found", install it first: Python 3.12, Node.js (version 18 or newer) and ffmpeg are
available from your system's package manager or software centre.

**2. Install Platina** (takes a while: it downloads about 7 GB):

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
.venv/bin/python -m unidic download
cd frontend && npm install && cd ..
```

You should see each command finish without a red "error" line at the end.

**3. Start it for the first time:**

```sh
./start.sh
```

You should see `Platina is running: http://localhost:5173/#lessons`, and your browser opens on the **Lessons** page.
The first lesson you analyze also downloads the speech models (about 3 GB), so that one takes longer.

**Optional: the tutor voice.** The ▶ *Expected* and ▶ *Tutor* buttons let a Japanese voice say a phrase with the
right accent. They need the free [VOICEVOX engine](https://github.com/VOICEVOX/voicevox_engine/releases): download the
Linux CPU version and unpack it to `~/.local/share/voicevox/`. `./start.sh` starts it for you from then on. Without
it, those buttons are greyed out and everything else works.

## 4. Before class

1. Open a terminal in the Platina folder and run `./start.sh`. Leave that terminal open.
   The browser opens on **Lessons**. (Already open? Go to <http://localhost:5173/#lessons>.)
2. **Put your headphones on.**
3. Press **● Start lesson recording**. The first time, the browser asks to use your microphone. Choose **Allow**.
4. Check that it's working:
   - the **timer** counts up;
   - the **Microphone** bar moves when you speak;
   - after about 15 seconds, **"Saved up to 0:15"** appears, and it keeps going up.

Now join your class as usual.

## 5. During class

- Keep the Platina tab open. It can sit in the background behind Zoom.
- Every 15 seconds the recording so far is saved on your computer. If the browser or computer crashes, you lose at
  most 15 seconds. The lesson then shows **"The recording was interrupted"**, with a button to analyze what was saved.
- If you see **"Can't reach Platina — retrying"**, the terminal running `./start.sh` was probably closed. Start it
  again. The recording keeps the pieces that haven't been sent and sends them as soon as Platina is back.

## 6. After class: your review

1. Press **■ Stop and analyze**.
2. Your lesson appears under **Your lessons** with a progress bar: *Analyzing: line 120 of 640*. With a graphics
   card this takes a few minutes; without one, about 5 minutes for every minute you spoke. You can close the page
   meanwhile; Platina keeps working as long as `./start.sh` is running.
3. When it's done, click the lesson's title. You see:
   - **The summary**: your level for this lesson (see [Your progress](#8-your-progress)), and how many phrases were
     correct, mistakes or unclear.
   - **Most obvious mistakes**, with **▶ You** (hear yourself), **▶ Expected** (hear the right accent) and
     **Go to …** (jump to that line).
   - **Repeated mistakes**, with **Show each time** to hear every occurrence.
   - **Everything you said**: the full transcript.

In the transcript:

- **Click a phrase** to see its details on the side: the expected accent, what you said, a chart of your pitch, and
  buttons to listen.
- **Show:** *All lines*, *Lines with mistakes* or *Lines with unclear phrases*.
- **Keyboard:** press <kbd>j</kbd> for the next mistake and <kbd>k</kbd> for the previous one. <kbd>Tab</kbd> and
  <kbd>Enter</kbd> work everywhere.
- **The text is wrong?** Speech recognition sometimes mishears. Click **✎ Fix text**, type what you really said, and
  press **Save and re-check**. Only that line is checked again.
- **Platina judged you wrong?** In the phrase details, open **Wrong verdict? Tell Platina what you said** and pick the
  accent you used. This saves the clip, which helps Platina learn your voice.

## 7. Recorded somewhere else? Upload it

If you recorded the class with your phone or with Zoom, press **Upload a recording** on the Lessons page and pick the
file (m4a, mp3, wav, webm, mp4 and most other formats work). It's analyzed like any other lesson.

Make sure **only your voice** is in it: a recording of the whole Zoom meeting includes your teacher. Zoom can save
each person separately: *Settings → Recording → Record a separate audio file for each participant*. Upload your own file.

## 8. Your progress

Open **Progress** at the top. You see:

- **Your level**: the average of your last three lessons that count.
- **Change**: how much your level moved since your first lessons (shown once four lessons count).
- **You've spoken**: how long you've spoken Japanese in all your lessons together.
- A **chart** of your level in each lesson, and how many minutes you spoke. Click a point to open that lesson, or use
  **Show as table** to see the same numbers as a table.
- **Words to work on**: words you got wrong in two or more lessons, or three or more times.
- **Fixed**: words you used to get wrong and have since said right three times in a row.

**What the level means.** It comes from the share of your phrases with the right accent, but it also takes into
account *how much* you said. Two correct phrases don't prove much, so they give a level of about 42. 19 correct out of
20 give about 80, and 285 out of 300 about 92. Staying quiet can't give a high level, and speaking a lot only helps
when the accents are right.

**Why some lessons don't count.** A lesson counts in your progress once Platina could judge at least 60 of your
phrases and you spoke for at least 3 minutes. Shorter lessons are still saved and reviewable, and they appear on the
chart as **hollow grey points**, labelled *too short to count*.

**"Analyzed with an older model or older NHK accents."** If you add NHK accents (see [Tips](#9-tips)) or Platina
gets better, older lessons were judged differently. Press **Re-check them** to make all lessons comparable again.

## 9. Tips

- **Speak in full sentences** when you can. Platina judges each word in context, and short answers like 「はい」 say
  little about your accent.
- **Aim for a few minutes of your own speaking** per lesson, so the lesson counts.
- **Grey words** (*Check the dictionary*) are words whose accent the dictionaries disagree on. If you have the NHK
  accent dictionary, look the word up and enter it under **Workshop → My NHK accents**. From then on Platina uses your
  entry. Press **← Back to lesson** to return.
- The **Workshop** (Quick check, Type, My NHK accents, Practice) is for one-off checks and experiments. Nothing there
  changes your lessons or progress.

## 10. Privacy

Everything stays on your computer. Nothing is uploaded to the internet.

- Lesson recordings are in `backend/data/lessons/` (one folder per lesson), the reviews in
  `backend/data/lessons.sqlite`.
- **Delete one lesson:** the **Delete** link next to it on the Lessons page removes its recording and review for good.
- **Delete all lessons:** stop Platina (<kbd>Ctrl</kbd>+<kbd>C</kbd> in its terminal), then delete the folder
  `backend/data/lessons/` and the file `backend/data/lessons.sqlite`.

## 11. Troubleshooting

**"Platina isn't installed yet"** when running `./start.sh`: do the [one-time setup](#3-one-time-setup) first.

**"Platina already seems to be running"**: it's already open in another terminal. Use that one, or press
<kbd>Ctrl</kbd>+<kbd>C</kbd> there first.

**"Microphone unavailable"**: the browser blocked the microphone. Click the microphone or lock icon next to the
address bar, allow the microphone for this page, and press Start again. Also check your system's sound settings use
the right microphone.

**The Microphone bar doesn't move**: the wrong microphone is selected, or it's muted. Check your system's sound
settings.

**"No speech recognized" or an empty review**: check the recording has your voice in it (▶ in the transcript). Very
quiet recordings or recordings with only English don't give anything to judge. English lines show *not Japanese — not
judged*.

**The analysis seems stuck**: the first lesson downloads the speech models (about 3 GB), which can take a while. The
terminal running `./start.sh` must stay open. If it still doesn't move, stop Platina with <kbd>Ctrl</kbd>+<kbd>C</kbd>
and start it again: the analysis continues where it stopped.

**"Something went wrong" with "out of memory"**: another program is using the graphics card (games, video editing,
another Platina). Close it and press **Try again**.

**The ▶ Expected and ▶ Tutor buttons are greyed out**: the tutor voice (VOICEVOX) isn't installed or running. See the
optional step in [One-time setup](#3-one-time-setup). Everything else works without it.

**Where are the logs?** In `~/.local/state/platina/` (`api.log`, `web.log`). They help if you ask someone for help.
