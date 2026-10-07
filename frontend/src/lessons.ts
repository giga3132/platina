// Lessons: record a whole class (uploaded in pieces as it is recorded), then
// review it once Platina has analyzed it — the clearest mistakes, the ones
// you repeat, and the full transcript.

import * as api from "./api";
import type { AnalyzedPhrase, Lesson, LessonDetail, LessonUtterance, Status, Word } from "./api";
import { renderDetail } from "./detail";
import { Clip, Recorder } from "./recorder";
import { el, notationNode, phraseRow } from "./render";
import { tutorButton } from "./tutor";

const PIECE_MS = 15_000; // a crash loses at most this much
const POLL_MS = 3_000;

type Filter = "all" | "error" | "uncertain";

let ctx: { detail: HTMLElement; onFix: (w: Word) => void };
const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;
const recorder = new Recorder();
let recording: { id: string; uploader: PieceUploader; tick: number; stopMeter: () => void } | undefined;
let view: { lesson: LessonDetail; clip: Clip; filter: Filter } | undefined;
let listTimer: number | undefined;
let viewTimer: number | undefined;

// --- formatting ----------------------------------------------------------------

export function clock(s: number): string {
  const t = Math.max(0, Math.floor(s));
  const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), sec = t % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}` : `${m}:${String(sec).padStart(2, "0")}`;
}

export function minutes(s: number): string {
  const m = Math.round(s / 60);
  if (m < 1) return s > 0 ? "under 1 min" : "0 min";
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")} min`;
}

export function dateOf(ts: number): string {
  return new Date(ts * 1000).toLocaleString(undefined, {
    weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
  });
}

const sleep = (ms: number) => new Promise((r) => window.setTimeout(r, ms));

// --- recording ---------------------------------------------------------------------

/** Sends recorded pieces in order, retrying until the server has each one. */
class PieceUploader {
  private queue: Blob[] = [];
  private seq = 0;
  private sending = false;
  private idle: (() => void)[] = [];

  constructor(private id: string, private onSaved: (pieces: number) => void,
              private onTrouble: (message: string | null) => void) {}

  add(piece: Blob): void {
    this.queue.push(piece);
    void this.pump();
  }

  private async pump(): Promise<void> {
    if (this.sending) return;
    this.sending = true;
    let delay = 1000;
    while (this.queue.length) {
      try {
        const saved = await api.sendLessonChunk(this.id, this.seq, this.queue[0]);
        this.queue.shift();
        this.seq++;
        delay = 1000;
        this.onTrouble(null);
        this.onSaved(saved);
      } catch {
        this.onTrouble(`Can't reach Platina — retrying (${this.queue.length} piece${this.queue.length > 1 ? "s" : ""} waiting). Keep this page open.`);
        await sleep(delay);
        delay = Math.min(delay * 2, 30_000);
      }
    }
    this.sending = false;
    this.idle.splice(0).forEach((r) => r());
  }

  flush(): Promise<void> {
    if (!this.queue.length && !this.sending) return Promise.resolve();
    return new Promise((r) => this.idle.push(r));
  }
}

function meter(stream: MediaStream): () => void {
  const node = $<HTMLMeterElement>("lesson-meter");
  const ac = new AudioContext();
  void ac.resume(); // may start suspended when created after an await
  const analyser = ac.createAnalyser();
  analyser.fftSize = 2048;
  ac.createMediaStreamSource(stream).connect(analyser);
  const buf = new Float32Array(analyser.fftSize);
  const timer = window.setInterval(() => {
    analyser.getFloatTimeDomainData(buf);
    let sum = 0;
    for (const v of buf) sum += v * v;
    const db = 20 * Math.log10(Math.sqrt(sum / buf.length) + 1e-9);
    node.value = Math.min(1, Math.max(0, (db + 60) / 50)); // -60 dBFS (silence) … -10 dBFS (loud)
  }, 100);
  return () => {
    window.clearInterval(timer);
    void ac.close();
    node.value = 0;
  };
}

async function startRecording(): Promise<void> {
  const button = $<HTMLButtonElement>("lesson-record");
  const status = $("lesson-status");
  button.disabled = true;
  let id: string;
  try {
    id = await api.createLesson();
  } catch {
    status.textContent = "Can't reach Platina. Is it running? Start it with ./start.sh.";
    button.disabled = false;
    return;
  }
  const saved = $("lesson-saved");
  const uploader = new PieceUploader(id,
    (pieces) => (saved.textContent = `Saved up to ${clock((pieces * PIECE_MS) / 1000)}`),
    (trouble) => (status.textContent = trouble ?? "Recording. You can leave this tab in the background during class."));
  try {
    await recorder.start((piece) => uploader.add(piece), PIECE_MS);
  } catch (e) {
    await api.deleteLesson(id).catch(() => {});
    status.textContent = `Microphone unavailable: ${(e as Error).message}. Allow microphone access for this page and try again.`;
    button.disabled = false;
    return;
  }
  const tick = window.setInterval(() => {
    $("lesson-timer").textContent = clock((performance.now() - recorder.startedAt) / 1000);
  }, 500);
  recording = { id, uploader, tick, stopMeter: meter(recorder.stream!) };
  $("lesson-live").hidden = false;
  $("lesson-timer").textContent = "0:00";
  saved.textContent = "Nothing saved yet (the first piece arrives after 15 seconds)";
  button.textContent = "■ Stop and analyze";
  button.classList.add("on");
  button.disabled = false;
  status.textContent = "Recording. You can leave this tab in the background during class.";
  void refreshList();
}

async function stopRecording(): Promise<void> {
  const rec = recording;
  if (!rec) return;
  const button = $<HTMLButtonElement>("lesson-record");
  const status = $("lesson-status");
  button.disabled = true;
  status.textContent = "Saving the last piece…";
  await recorder.stop();
  window.clearInterval(rec.tick);
  rec.stopMeter();
  await rec.uploader.flush();
  recording = undefined;
  $("lesson-live").hidden = true;
  button.textContent = "● Start lesson recording";
  button.classList.remove("on");
  button.disabled = false;
  try {
    await api.finishLesson(rec.id);
    status.textContent = "Saved. Platina is analyzing your lesson; the progress bar below shows how far it is. " +
      "You can close this page meanwhile.";
  } catch (e) {
    status.textContent = `Couldn't finish the recording: ${(e as Error).message}`;
  }
  void refreshList();
}

// --- lesson list -----------------------------------------------------------------------

function statusLine(ls: Lesson): HTMLElement {
  const box = el("div", { class: "lesson-state" });
  switch (ls.status) {
    case "recording":
      if (recording?.id === ls.id) {
        box.append(el("span", { class: "tag live" }, "Recording now"));
      } else {
        const go = el("button", { type: "button", class: "secondary" }, "Analyze what was saved");
        go.addEventListener("click", async () => {
          go.disabled = true;
          await api.finishLesson(ls.id).catch((e) => alert(`Couldn't: ${(e as Error).message}`));
          void refreshList();
        });
        box.append(el("span", {}, "The recording was interrupted. "), go);
      }
      break;
    case "queued":
      box.append(el("span", {}, "Waiting to be analyzed…"));
      break;
    case "processing": {
      const label = ls.total ? `Analyzing: line ${ls.done} of ${ls.total}` : "Finding where you spoke…";
      box.append(el("progress", { max: String(ls.total || 1), value: String(ls.done), "aria-label": label }),
        el("span", {}, ` ${label}`));
      break;
    }
    case "failed": {
      const retry = el("button", { type: "button", class: "secondary" }, "Try again");
      retry.addEventListener("click", async () => {
        retry.disabled = true;
        await api.retryLesson(ls.id).catch((e) => alert(`Couldn't: ${(e as Error).message}`));
        void refreshList();
      });
      box.append(el("span", { class: "s-error-text" }, `Something went wrong: ${(ls.error ?? "").split("\n").filter(Boolean).pop() ?? ""} `), retry);
      break;
    }
    case "done": {
      const s = ls.summary!;
      box.append(el("span", { class: "level-badge" }, `Level ${Math.round(s.level)}`),
        el("span", {}, ` · ${s.mistakes} mistake${s.mistakes === 1 ? "" : "s"} in ${s.judged} judged phrases`));
      if (!s.reliable) box.append(el("span", { class: "tag" }, "too short to count"));
      if (ls.outdated) box.append(el("span", { class: "tag" }, "older analysis"));
    }
  }
  return box;
}

export async function refreshList(): Promise<void> {
  window.clearTimeout(listTimer);
  const ul = $("lesson-list");
  let list: Lesson[];
  try {
    list = await api.listLessons();
  } catch {
    ul.replaceChildren(el("li", { class: "muted" }, "Can't reach Platina. Is it running? Start it with ./start.sh."));
    return;
  }
  ul.replaceChildren();
  if (!list.length) {
    ul.append(el("li", { class: "muted" },
      "No lessons yet. Press “Start lesson recording” before your next class, or upload a recording."));
  }
  for (const ls of list) {
    const title = ls.status === "done"
      ? el("a", { href: `#lessons/${ls.id}`, class: "lesson-title" }, ls.title)
      : el("span", { class: "lesson-title" }, ls.title);
    const meta = [dateOf(ls.created_at)];
    if (ls.duration) meta.push(`${minutes(ls.duration)} recorded`);
    if (ls.summary) meta.push(`you spoke ${minutes(ls.summary.speaking_s)}`);
    const del = el("button", { type: "button", class: "link danger" }, "Delete");
    del.setAttribute("aria-label", `Delete ${ls.title}`);
    del.addEventListener("click", async () => {
      if (!confirm(`Delete “${ls.title}”? Its recording and review are removed for good.`)) return;
      await api.deleteLesson(ls.id);
      void refreshList();
    });
    ul.append(el("li", { class: "lesson-item" },
      el("div", { class: "lesson-head" }, title, del),
      el("div", { class: "muted" }, meta.join(" · ")),
      statusLine(ls)));
  }
  const busy = list.some((ls) => ls.status === "queued" || ls.status === "processing");
  if (busy) listTimer = window.setTimeout(() => {
    if (!$("lessons-home").hidden && !$("tab-lessons").hidden) void refreshList();
  }, POLL_MS);
}

// --- one lesson -----------------------------------------------------------------------------

function statusesOf(u: LessonUtterance): Set<Status> {
  return new Set((u.result?.phrases ?? []).filter((p) => p.moras.length).map((p) => p.status));
}

function summaryBlock(lesson: LessonDetail): HTMLElement {
  const s = lesson.summary!;
  const box = el("section", { class: "lesson-summary", "aria-label": "Summary" });
  const card = (value: string, label: string, cls = "") =>
    el("div", { class: `stat ${cls}` }, el("span", { class: "stat-value" }, value), el("span", { class: "stat-label" }, label));
  box.append(el("div", { class: "stats" },
    card(String(Math.round(s.level)), `Level (range ${Math.round(s.level_range[0])}–${Math.round(s.level_range[1])})`, "level"),
    card(String(s.counts.correct ?? 0), "Correct"),
    card(String(s.counts.error ?? 0), "Mistakes", "s-error"),
    card(String(s.counts.uncertain ?? 0), "Unclear (not counted)"),
    card(minutes(s.speaking_s), "You spoke")));
  if (!s.reliable) {
    box.append(el("p", { class: "note" },
      "A short lesson: it is shown here but doesn't count in your progress, because a few phrases can't show your level reliably."));
  }
  box.append(el("details", { class: "explain" }, el("summary", {}, "How is the level worked out?"),
    el("p", {}, `Of the ${s.judged} phrases Platina could judge, you said ${s.correct} with the expected accent` +
      (s.accuracy === null ? "." : ` (${Math.round(s.accuracy * 100)} %).`) +
      " The level is the lowest value that share is likely to be, so it grows with how much you said: two correct" +
      " phrases give about 42, 19 of 20 about 80, 285 of 300 about 92. Unclear phrases and words whose dictionary" +
      " accent is unsure don't count either way.")));
  return box;
}

function obviousBlock(lesson: LessonDetail): HTMLElement {
  const s = lesson.summary!;
  const box = el("section", {}, el("h3", {}, "Most obvious mistakes"));
  if (!s.obvious.length) {
    box.append(el("p", { class: "muted" }, "No clear mistakes in this lesson."));
    return box;
  }
  box.append(el("p", { class: "muted" }, "The phrases Platina is surest you said with a different accent."));
  const ol = el("ol", { class: "mistakes" });
  for (const m of s.obvious) {
    const phrase = { moras: m.moras };
    const play = el("button", { type: "button", class: "secondary" }, "▶ You");
    play.addEventListener("click", () => view?.clip.play(m.start, m.end));
    const go = el("button", { type: "button", class: "link" }, `Go to ${clock(m.start)}`);
    go.addEventListener("click", () => focusPhrase(m.utterance, m.phrase));
    ol.append(el("li", {},
      el("span", { class: "mistake-text", lang: "ja" }, m.text), " ",
      el("span", { class: "label" }, "expected "), notationNode(phrase, m.accent), " ",
      el("span", { class: "label" }, "you said "), notationNode(phrase, m.said, m.accent), " ",
      play, " ", tutorButton("▶ Expected", () => api.speakPhrase(m.moras, m.accent), "Hear the expected accent"), " ", go));
  }
  box.append(ol);
  return box;
}

function repeatedBlock(lesson: LessonDetail): HTMLElement {
  const s = lesson.summary!;
  const box = el("section", {}, el("h3", {}, "Repeated mistakes"));
  if (!s.repeated.length) {
    box.append(el("p", { class: "muted" }, "No mistake came up more than once."));
    return box;
  }
  const ul = el("ul", { class: "mistakes" });
  for (const r of s.repeated) {
    const phrase = { moras: r.moras };
    const each = el("ul", { class: "occurrences" });
    for (const o of r.occurrences) {
      const play = el("button", { type: "button", class: "secondary" }, `▶ ${clock(o.start)}`);
      play.setAttribute("aria-label", `Play at ${clock(o.start)}`);
      play.addEventListener("click", () => view?.clip.play(o.start, o.end));
      const go = el("button", { type: "button", class: "link" }, "Go to line");
      go.addEventListener("click", () => focusPhrase(o.utterance, o.phrase));
      each.append(el("li", {}, play, " ", go));
    }
    ul.append(el("li", {},
      el("span", { class: "mistake-text", lang: "ja" }, r.text), " · ",
      el("span", { class: "label" }, "you said "), notationNode(phrase, r.said, r.accent), " ",
      el("span", { class: "label" }, "expected "), notationNode(phrase, r.accent), " · ",
      el("strong", {}, `${r.count} times`), " ",
      tutorButton("▶ Expected", () => api.speakPhrase(r.moras, r.accent), "Hear the expected accent"),
      el("details", {}, el("summary", {}, "Show each time"), each)));
  }
  box.append(ul);
  return box;
}

function utteranceBlock(lesson: LessonDetail, u: LessonUtterance): HTMLElement {
  const block = el("div", { class: "utterance", "data-idx": String(u.idx) });
  const play = el("button", { type: "button", class: "link time" }, `▶ ${clock(u.start)}`);
  play.setAttribute("aria-label", `Play from ${clock(u.start)}`);
  play.addEventListener("click", () => view?.clip.play(u.start, u.end));
  const text = el("span", { lang: "ja" }, u.text || "…");
  const line = el("p", { class: "transcript" }, play, " ", text);
  if (u.skipped) {
    line.append(" ", el("span", { class: "muted" }, `(${u.skipped === "not Japanese" ? "not Japanese" : "no speech"} — not judged)`));
  }
  const fix = el("button", { type: "button", class: "link" }, "✎ Fix text");
  fix.setAttribute("aria-label", `Fix the text of the line at ${clock(u.start)}`);
  fix.addEventListener("click", () => editLine(line, u));
  line.append(" ", fix);
  if (u.result) line.append(" ", tutorButton("▶ Tutor", () => api.speak(u.text), "Hear this line with the expected accent"));
  if (u.edited) line.append(" ", el("span", { class: "tag" }, "text fixed by you"));
  block.append(line);
  if (u.result) {
    block.append(phraseRow(u.result.phrases, (p: AnalyzedPhrase) =>
      renderDetail(ctx.detail, p, {
        onFix: ctx.onFix,
        onPlay: (s, e) => view?.clip.play(s, e),
        onReport: async (said) => {
          const stats = await api.addLabel(null, {
            source: "report", lesson: lesson.id, text: u.text, phrase_index: u.result!.phrases.indexOf(p), said,
            start: u.start, end: u.end, verdict: p.status,
          });
          return `Saved — thanks. ${stats.your_phrases} labelled phrases of your voice so far.`;
        },
      })));
  }
  return block;
}

function editLine(line: HTMLElement, u: LessonUtterance): void {
  const input = el("input", { lang: "ja", value: u.text, "aria-label": "Corrected text of this line" });
  const save = el("button", { type: "submit" }, "Save and re-check");
  const cancel = el("button", { type: "button", class: "secondary" }, "Cancel");
  const status = el("span", { class: "muted", "aria-live": "polite" });
  const form = el("form", { class: "fix-line" }, input, save, cancel, status);
  cancel.addEventListener("click", () => form.replaceWith(line));
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!view) return;
    save.disabled = true;
    status.textContent = "Checking this line again…";
    try {
      const r = await api.fixLessonLine(view.lesson.id, u.idx, input.value);
      const i = view.lesson.utterances.findIndex((x) => x.idx === u.idx);
      view.lesson.utterances[i] = r.utterance;
      view.lesson.summary = r.summary;
      renderLesson();
      focusLine(u.idx);
    } catch (err) {
      status.textContent = `Couldn't: ${(err as Error).message}`;
      save.disabled = false;
    }
  });
  line.replaceWith(form);
  input.focus();
}

function transcriptBlock(lesson: LessonDetail): HTMLElement {
  const box = el("section", { class: "lesson-transcript" }, el("h3", {}, "Everything you said"));
  const filters = el("div", { class: "filters", role: "group", "aria-label": "Show" });
  const options: [Filter, string][] = [["all", "All lines"], ["error", "Lines with mistakes"], ["uncertain", "Lines with unclear phrases"]];
  for (const [f, label] of options) {
    const b = el("button", { type: "button", class: "secondary filter", "aria-pressed": String(view!.filter === f) }, label);
    b.addEventListener("click", () => {
      view!.filter = f;
      filters.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      applyFilter();
    });
    filters.append(b);
  }
  box.append(filters, el("p", { class: "muted keys" },
    "Click a phrase for details. Keys: ", el("kbd", {}, "j"), " next mistake, ", el("kbd", {}, "k"), " previous."));
  const list = el("div", { class: "lines" });
  for (const u of lesson.utterances) list.append(utteranceBlock(lesson, u));
  box.append(list);
  return box;
}

function applyFilter(): void {
  if (!view) return;
  const f = view.filter;
  const byIdx = new Map(view.lesson.utterances.map((u) => [String(u.idx), u]));
  $("lesson-view").querySelectorAll<HTMLElement>(".utterance").forEach((block) => {
    const u = byIdx.get(block.dataset.idx!)!;
    block.hidden = f !== "all" && !statusesOf(u).has(f);
  });
}

function focusLine(idx: number): HTMLElement | null {
  const block = $("lesson-view").querySelector<HTMLElement>(`.utterance[data-idx="${idx}"]`);
  if (!block) return null;
  if (block.hidden && view) {
    view.filter = "all";
    $("lesson-view").querySelectorAll(".filter").forEach((b, i) => b.setAttribute("aria-pressed", String(i === 0)));
    applyFilter();
  }
  block.scrollIntoView({ block: "center" });
  return block;
}

function focusPhrase(idx: number, phrase: number): void {
  const block = focusLine(idx);
  const chip = block?.querySelectorAll<HTMLButtonElement>(".phrase")[phrase];
  if (chip) {
    chip.focus();
    chip.click();
  }
}

function step(dir: 1 | -1): void {
  const chips = [...$("lesson-view").querySelectorAll<HTMLButtonElement>(".utterance:not([hidden]) .phrase.s-error")];
  if (!chips.length) return;
  const at = chips.findIndex((c) => c === document.activeElement || c.classList.contains("selected"));
  const next = chips[at < 0 ? (dir > 0 ? 0 : chips.length - 1) : (at + dir + chips.length) % chips.length];
  next.scrollIntoView({ block: "center" });
  next.focus();
  next.click();
}

function renderLesson(): void {
  if (!view) return;
  const lesson = view.lesson;
  const host = $("lesson-view");
  const title = el("input", { class: "title-input", value: lesson.title, "aria-label": "Lesson title" });
  title.addEventListener("change", () => void api.renameLesson(lesson.id, title.value));
  const meta = [dateOf(lesson.created_at)];
  if (lesson.duration) meta.push(`${minutes(lesson.duration)} recorded`);
  host.replaceChildren(
    el("p", {}, el("a", { href: "#lessons" }, "← All lessons")),
    el("h2", { class: "lesson-h" }, title),
    el("p", { class: "muted" }, meta.join(" · ")));

  if (lesson.status !== "done") {
    host.append(statusLine(lesson), el("p", { class: "muted" }, "The review appears here when the analysis is done."));
    viewTimer = window.setTimeout(() => {
      if (view?.lesson.id === lesson.id && !host.hidden) void openLesson(lesson.id);
    }, POLL_MS);
    return;
  }
  if (lesson.outdated) {
    const again = el("button", { type: "button", class: "secondary" }, "Re-check with the current settings");
    again.addEventListener("click", async () => {
      again.disabled = true;
      await api.reanalyzeLessons();
      void openLesson(lesson.id);
    });
    host.append(el("p", { class: "note" },
      "This lesson was analyzed before you changed NHK accents or Platina got a new model. ", again));
  }
  host.append(summaryBlock(lesson), obviousBlock(lesson), repeatedBlock(lesson), transcriptBlock(lesson));
  applyFilter();
}

async function openLesson(id: string, focus?: [number, number]): Promise<void> {
  window.clearTimeout(viewTimer);
  $("lessons-home").hidden = true;
  const host = $("lesson-view");
  host.hidden = false;
  let lesson: LessonDetail;
  try {
    lesson = await api.getLesson(id);
  } catch (e) {
    host.replaceChildren(el("p", {}, el("a", { href: "#lessons" }, "← All lessons")),
      el("p", {}, `Couldn't open this lesson: ${(e as Error).message}`));
    return;
  }
  if (view?.lesson.id !== id) {
    view?.clip.dispose();
    view = { lesson, clip: new Clip(api.lessonAudioUrl(id)), filter: "all" };
  } else {
    view.lesson = lesson;
  }
  renderLesson();
  if (focus) focusPhrase(focus[0], focus[1]);
}

// --- entry points -------------------------------------------------------------------------

/** #lessons → the list; #lessons/<id>[/<line>/<phrase>] → one lesson. */
export function showLessons(rest: string[]): void {
  const [id, line, phrase] = rest;
  if (id) {
    void openLesson(id, line !== undefined ? [Number(line), Number(phrase ?? 0)] : undefined);
    return;
  }
  window.clearTimeout(viewTimer);
  $("lesson-view").hidden = true;
  $("lessons-home").hidden = false;
  void refreshList();
}

export function initLessons(c: typeof ctx): void {
  ctx = c;
  $("lesson-record").addEventListener("click", () => void (recording ? stopRecording() : startRecording()));
  $<HTMLInputElement>("lesson-upload").addEventListener("change", async (e) => {
    const input = e.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    const status = $("lesson-status");
    status.textContent = `Uploading ${file.name}…`;
    try {
      await api.uploadLesson(file);
      status.textContent = "Uploaded. Platina is analyzing it; the progress bar below shows how far it is.";
    } catch (err) {
      status.textContent = `Couldn't use this file: ${(err as Error).message}`;
    }
    input.value = "";
    void refreshList();
  });
  window.addEventListener("beforeunload", (e) => {
    if (recording) e.preventDefault(); // the browser asks before closing a recording tab
  });
  document.addEventListener("keydown", (e) => {
    if ($("lesson-view").hidden || $("tab-lessons").hidden || e.ctrlKey || e.metaKey || e.altKey) return;
    const t = e.target as HTMLElement;
    if (t.closest("input, textarea, select, [contenteditable]")) return;
    if (e.key === "j") step(1);
    else if (e.key === "k") step(-1);
  });
}

