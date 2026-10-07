// Lessons: record a whole class (uploaded in pieces as it is recorded), then
// review it once Platina has analyzed it — the clearest mistakes, the ones
// you repeat, and the full transcript.

import * as api from "./api";
import type { AnalyzedPhrase, Lesson, LessonDetail, LessonUtterance, Status, Word } from "./api";
import { renderDetail } from "./detail";
import { locale, tr } from "./i18n";
import { Clip, Recorder } from "./recorder";
import { btn, el, notationNode, phraseRow } from "./render";
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
  if (m < 1) return s > 0 ? tr().underMinute : tr().zeroMinutes;
  return tr().minutes(m);
}

export function dateOf(ts: number): string {
  return new Date(ts * 1000).toLocaleString(locale(), {
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
        this.onTrouble(tr().retrying(this.queue.length));
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
  const d = tr();
  button.disabled = true;
  let id: string;
  try {
    id = await api.createLesson(d.defaultLessonTitle(new Date()));
  } catch {
    status.textContent = d.cantReach;
    button.disabled = false;
    return;
  }
  const saved = $("lesson-saved");
  const uploader = new PieceUploader(id,
    (pieces) => (saved.textContent = tr().savedUpTo(clock((pieces * PIECE_MS) / 1000))),
    (trouble) => (status.textContent = trouble ?? tr().recordingBackground));
  try {
    await recorder.start((piece) => uploader.add(piece), PIECE_MS);
  } catch (e) {
    await api.deleteLesson(id).catch(() => {});
    status.textContent = d.micUnavailableLesson((e as Error).message);
    button.disabled = false;
    return;
  }
  const tick = window.setInterval(() => {
    $("lesson-timer").textContent = clock((performance.now() - recorder.startedAt) / 1000);
  }, 500);
  recording = { id, uploader, tick, stopMeter: meter(recorder.stream!) };
  $("lesson-live").hidden = false;
  $("lesson-timer").textContent = "0:00";
  saved.textContent = d.nothingSavedYet;
  button.textContent = d.lessonStop;
  button.classList.add("on");
  button.disabled = false;
  status.textContent = d.recordingBackground;
  void refreshList();
}

async function stopRecording(): Promise<void> {
  const rec = recording;
  if (!rec) return;
  const button = $<HTMLButtonElement>("lesson-record");
  const status = $("lesson-status");
  button.disabled = true;
  const d = tr();
  status.textContent = d.savingLastPiece;
  await recorder.stop();
  window.clearInterval(rec.tick);
  rec.stopMeter();
  await rec.uploader.flush();
  recording = undefined;
  $("lesson-live").hidden = true;
  button.textContent = tr().lessonRecord;
  button.classList.remove("on");
  button.disabled = false;
  try {
    await api.finishLesson(rec.id);
    status.textContent = tr().lessonSavedAnalyzing;
  } catch (e) {
    status.textContent = tr().couldntFinish((e as Error).message);
  }
  void refreshList();
}

// --- lesson list -----------------------------------------------------------------------

function statusLine(ls: Lesson): HTMLElement {
  const d = tr();
  const box = el("div", { class: "lesson-state" });
  switch (ls.status) {
    case "recording":
      if (recording?.id === ls.id) {
        box.append(el("span", { class: "tag live" }, d.recordingNow));
      } else {
        const go = btn(d.analyzeSaved);
        go.addEventListener("click", async () => {
          go.disabled = true;
          await api.finishLesson(ls.id).catch((e) => alert(d.couldnt((e as Error).message)));
          void refreshList();
        });
        box.append(el("span", {}, d.interrupted), go);
      }
      break;
    case "queued":
      box.append(el("span", {}, d.waitingAnalysis));
      break;
    case "processing": {
      const label = ls.total ? d.analyzingLine(ls.done, ls.total) : d.findingSpeech;
      box.append(el("progress", { max: String(ls.total || 1), value: String(ls.done), "aria-label": label }),
        el("span", {}, ` ${label}`));
      break;
    }
    case "failed": {
      const retry = btn(d.tryAgain);
      retry.addEventListener("click", async () => {
        retry.disabled = true;
        await api.retryLesson(ls.id).catch((e) => alert(d.couldnt((e as Error).message)));
        void refreshList();
      });
      box.append(el("span", { class: "s-error-text" }, d.somethingWrong((ls.error ?? "").split("\n").filter(Boolean).pop() ?? "")), retry);
      break;
    }
    case "done": {
      const s = ls.summary!;
      box.append(el("span", { class: "level-badge" }, d.levelBadge(Math.round(s.level))),
        el("span", {}, d.mistakesIn(s.mistakes, s.judged)));
      if (!s.reliable) box.append(el("span", { class: "tag" }, d.tooShort));
      if (ls.outdated) box.append(el("span", { class: "tag" }, d.olderAnalysis));
    }
  }
  return box;
}

export async function refreshList(): Promise<void> {
  window.clearTimeout(listTimer);
  const d = tr();
  const ul = $("lesson-list");
  let list: Lesson[];
  try {
    list = await api.listLessons();
  } catch {
    ul.replaceChildren(el("li", { class: "muted" }, d.cantReach));
    return;
  }
  ul.replaceChildren();
  if (!list.length) {
    ul.append(el("li", { class: "muted" }, d.noLessons));
  }
  for (const ls of list) {
    const title = ls.status === "done"
      ? el("a", { href: `#lessons/${ls.id}`, class: "lesson-title" }, ls.title)
      : el("span", { class: "lesson-title" }, ls.title);
    const meta = [dateOf(ls.created_at)];
    if (ls.duration) meta.push(d.recorded(minutes(ls.duration)));
    if (ls.summary) meta.push(d.youSpokeFor(minutes(ls.summary.speaking_s)));
    const del = btn(d.delete, { quiet: true, danger: true });
    del.setAttribute("aria-label", d.deleteNamed(ls.title));
    del.addEventListener("click", async () => {
      if (!confirm(d.confirmDelete(ls.title))) return;
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
  const d = tr();
  const s = lesson.summary!;
  const box = el("section", { class: "lesson-summary", "aria-label": d.summary });
  const card = (value: string, label: string, cls = "") =>
    el("div", { class: `stat ${cls}` }, el("span", { class: "stat-value" }, value), el("span", { class: "stat-label" }, label));
  box.append(el("div", { class: "stats" },
    card(String(Math.round(s.level)), d.levelRange(Math.round(s.level_range[0]), Math.round(s.level_range[1])), "level"),
    card(String(s.counts.correct ?? 0), d.status_correct),
    card(String(s.counts.error ?? 0), d.mistakes, "s-error"),
    card(String(s.counts.uncertain ?? 0), d.unclearNotCounted),
    card(minutes(s.speaking_s), d.youSpoke)));
  if (!s.reliable) {
    box.append(el("p", { class: "note" }, d.shortLessonNote));
  }
  box.append(el("details", { class: "explain" }, el("summary", {}, d.howLevel),
    el("p", {}, d.lessonLevelExplain(s.judged, s.correct, s.accuracy === null ? null : Math.round(s.accuracy * 100)))));
  return box;
}

/** "長島市業に  expected ナガシマシ＼ギョウニ  you said ナガシマシギョウニ━". */
function mistakeRow(text: string, moras: string[], accent: number, said: number, count?: number): HTMLElement {
  const phrase = { moras };
  const row = el("div", { class: "mistake" },
    el("span", { class: "mistake-text", lang: "ja" }, text),
    el("span", { class: "pair" }, el("span", { class: "label" }, tr().expected), notationNode(phrase, accent)),
    el("span", { class: "pair said" }, el("span", { class: "label" }, tr().youSaid), notationNode(phrase, said, accent)));
  if (count) row.append(el("span", { class: "count-badge" }, `${count}×`));
  return row;
}

function obviousBlock(lesson: LessonDetail): HTMLElement {
  const d = tr();
  const s = lesson.summary!;
  const box = el("section", {}, el("h3", {}, d.mostObvious));
  if (!s.obvious.length) {
    box.append(el("p", { class: "muted" }, d.noClearMistakes));
    return box;
  }
  box.append(el("p", { class: "muted" }, d.obviousIntro));
  const ol = el("ol", { class: "mistakes" });
  for (const m of s.obvious) {
    const play = btn(d.you, { play: true, title: d.hearYourselfSayIt });
    play.addEventListener("click", () => view?.clip.play(m.start, m.end));
    const go = btn(d.goTo(clock(m.start)), { quiet: true, title: d.showLine });
    go.addEventListener("click", () => focusPhrase(m.utterance, m.phrase));
    ol.append(el("li", {}, mistakeRow(m.text, m.moras, m.accent, m.said),
      el("div", { class: "actions" }, play,
        tutorButton(d.expectedBtn, () => api.speakPhrase(m.moras, m.accent), d.hearExpected), go)));
  }
  box.append(ol);
  return box;
}

function repeatedBlock(lesson: LessonDetail): HTMLElement {
  const d = tr();
  const s = lesson.summary!;
  const box = el("section", {}, el("h3", {}, d.repeated));
  if (!s.repeated.length) {
    box.append(el("p", { class: "muted" }, d.noRepeated));
    return box;
  }
  const ul = el("ul", { class: "mistakes" });
  for (const r of s.repeated) {
    const each = el("div", { class: "occurrences" });
    for (const o of r.occurrences) {
      const play = btn(clock(o.start), { play: true, title: d.hearYourselfAt(clock(o.start)) });
      play.addEventListener("click", () => view?.clip.play(o.start, o.end));
      const go = btn(d.goToLine, { quiet: true });
      go.addEventListener("click", () => focusPhrase(o.utterance, o.phrase));
      each.append(el("span", { class: "occurrence" }, play, go));
    }
    ul.append(el("li", {}, mistakeRow(r.text, r.moras, r.accent, r.said, r.count),
      el("div", { class: "actions" },
        tutorButton(d.expectedBtn, () => api.speakPhrase(r.moras, r.accent), d.hearExpected)),
      el("details", { class: "each" }, el("summary", {}, d.hearEachTime), each)));
  }
  box.append(ul);
  return box;
}

function utteranceBlock(lesson: LessonDetail, u: LessonUtterance): HTMLElement {
  const d = tr();
  const block = el("div", { class: "utterance", "data-idx": String(u.idx) });
  const play = btn(clock(u.start), { play: true, quiet: true, title: d.hearThisLine(clock(u.start)) });
  play.classList.add("time");
  play.addEventListener("click", () => view?.clip.play(u.start, u.end, 0.1, 0.3));
  const line = el("div", { class: "transcript" }, play, el("span", { class: "line-text", lang: "ja" }, u.text || "…"));
  if (u.skipped) {
    line.append(el("span", { class: "tag" }, d.skipped(u.skipped)));
  }
  if (u.edited) line.append(el("span", { class: "tag" }, d.textFixed));
  const fix = btn(d.editText, { quiet: true, title: d.editTextTitle });
  fix.addEventListener("click", () => editLine(line, u));
  const actions = el("span", { class: "actions" }, fix);
  if (u.result) actions.append(tutorButton(d.tutor, () => api.speak(u.text), d.hearLineExpected));
  line.append(actions);
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
          return tr().reportSaved(stats.your_phrases);
        },
      })));
  }
  return block;
}

function editLine(line: HTMLElement, u: LessonUtterance): void {
  const d = tr();
  const input = el("input", { lang: "ja", value: u.text, "aria-label": d.correctedText });
  const save = el("button", { type: "submit" }, d.saveRecheck);
  const cancel = el("button", { type: "button", class: "secondary" }, d.cancel);
  save.classList.add("small");
  cancel.classList.add("small");
  const status = el("span", { class: "muted", "aria-live": "polite" });
  const form = el("form", { class: "fix-line" }, input, save, cancel, status);
  cancel.addEventListener("click", () => form.replaceWith(line));
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!view) return;
    save.disabled = true;
    status.textContent = d.checkingLine;
    try {
      const r = await api.fixLessonLine(view.lesson.id, u.idx, input.value);
      const i = view.lesson.utterances.findIndex((x) => x.idx === u.idx);
      view.lesson.utterances[i] = r.utterance;
      view.lesson.summary = r.summary;
      renderLesson();
      focusLine(u.idx);
    } catch (err) {
      status.textContent = d.couldnt((err as Error).message);
      save.disabled = false;
    }
  });
  line.replaceWith(form);
  input.focus();
}

function transcriptBlock(lesson: LessonDetail): HTMLElement {
  const d = tr();
  const box = el("section", { class: "lesson-transcript" }, el("h3", {}, d.everything));
  const filters = el("div", { class: "filters", role: "group", "aria-label": d.show });
  const options: [Filter, string][] = [["all", d.allLines], ["error", d.linesMistakes], ["uncertain", d.linesUnclear]];
  for (const [f, label] of options) {
    const b = el("button", { type: "button", class: "filter", "aria-pressed": String(view!.filter === f) }, label);
    b.addEventListener("click", () => {
      view!.filter = f;
      filters.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      applyFilter();
    });
    filters.append(b);
  }
  box.append(filters, el("p", { class: "muted keys" },
    d.keysHelp[0], el("kbd", {}, "j"), d.keysHelp[1], el("kbd", {}, "k"), d.keysHelp[2]));
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
  const d = tr();
  const host = $("lesson-view");
  const title = el("input", { class: "title-input", value: lesson.title, "aria-label": d.lessonTitle });
  title.addEventListener("change", () => void api.renameLesson(lesson.id, title.value));
  const meta = [dateOf(lesson.created_at)];
  if (lesson.duration) meta.push(d.recorded(minutes(lesson.duration)));
  host.replaceChildren(
    el("p", {}, el("a", { href: "#lessons", class: "back-link" }, d.allLessons)),
    el("h2", { class: "lesson-h" }, title),
    el("p", { class: "muted" }, meta.join(" · ")));

  if (lesson.status !== "done") {
    host.append(statusLine(lesson), el("p", { class: "muted" }, d.reviewAppears));
    viewTimer = window.setTimeout(() => {
      if (view?.lesson.id === lesson.id && !host.hidden) void openLesson(lesson.id);
    }, POLL_MS);
    return;
  }
  if (lesson.outdated) {
    const again = btn(d.recheckCurrent);
    again.addEventListener("click", async () => {
      again.disabled = true;
      await api.reanalyzeLessons();
      void openLesson(lesson.id);
    });
    host.append(el("p", { class: "note" }, d.outdatedLesson, again));
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
    host.replaceChildren(el("p", {}, el("a", { href: "#lessons", class: "back-link" }, tr().allLessons)),
      el("p", {}, tr().couldntOpen((e as Error).message)));
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

export const lessonRecording = (): boolean => recording !== undefined;

export function initLessons(c: typeof ctx): void {
  ctx = c;
  $("lesson-record").addEventListener("click", () => void (recording ? stopRecording() : startRecording()));
  $<HTMLInputElement>("lesson-upload").addEventListener("change", async (e) => {
    const input = e.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    const status = $("lesson-status");
    status.textContent = tr().uploading(file.name);
    try {
      await api.uploadLesson(file);
      status.textContent = tr().uploaded;
    } catch (err) {
      status.textContent = tr().couldntUseFile((err as Error).message);
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

