// Practice tab: imitate a target accent (the right one, or a deliberate
// mistake) and keep the takes that sound like the target. Each kept take is
// a labelled recording of your voice, which is how Platina measures — and
// learns — how often it misjudges you. Also: review native phrases the
// detector flagged.

import * as api from "./api";
import type { PracticeItem, ReviewItem } from "./api";
import { kindLabel, tr } from "./i18n";
import { Clip, Recorder } from "./recorder";
import { btn, el, notationNode, segments } from "./render";
import { tutorButton } from "./tutor";

const $ = (id: string) => document.getElementById(id)!;
const recorder = new Recorder();
let item: PracticeItem | undefined;
let take: Blob | undefined;
let clip: Clip | undefined;
let started = false;

export const practiceRecording = (): boolean => recorder.recording;

/** Draws the current sentence and stats again (after a language switch). */
export function redrawPractice(): void {
  if (!started || recorder.recording) return;
  if (item) render(item);
  void refreshStats();
}

export async function initPractice(): Promise<void> {
  if (started) return;
  started = true;
  $("practice-next").addEventListener("click", () => void next());
  $("practice-own").addEventListener("submit", (e) => {
    e.preventDefault();
    const text = ($("practice-text") as HTMLInputElement).value.trim();
    if (text) void next(text);
  });
  // the review loads its next phrase whenever it's opened
  const show = segments($("practice-views"), $("tab-practice"), (v) => v === "review" && void review());
  show("takes");
  await Promise.all([next(), refreshStats()]);
}

async function refreshStats(): Promise<void> {
  try {
    const s = await api.labelStats();
    $("practice-stats").textContent = tr().practiceStats(s.your_phrases, s.your_correct, s.your_mistakes, s.sessions);
  } catch {
    $("practice-stats").textContent = "";
  }
}

async function next(text?: string): Promise<void> {
  take = undefined;
  try {
    item = await api.practiceNext(text);
  } catch (e) {
    $("practice-item").replaceChildren(el("p", { class: "empty" }, tr().couldntLoad((e as Error).message)));
    return;
  }
  render(item);
}

function render(it: PracticeItem): void {
  const d = tr();
  const host = $("practice-item");
  take = undefined;
  const target = it.phrases[it.phrase_index];
  const line = el("p", { class: "notation-line", lang: "ja" });
  it.phrases.forEach((p, i) => {
    if (!p.moras.length) return;
    const span = el("span", { class: i === it.phrase_index ? "target" : "muted" }, notationNode(p, i === it.phrase_index ? it.target : p.accent));
    line.append(span, " ");
  });
  const isMistake = it.kind !== "expected";
  const say = el("p", {},
    d.sayAs[0], el("strong", { lang: "ja" }, target.text), d.sayAs[1], notationNode(target, it.target),
    isMistake ? el("span", { class: "s-error sample" }, d.deliberate(kindLabel(it.kind))) : d.theExpected);
  const hear = tutorButton(d.hearTarget, () => api.speak(it.text, 1, { [it.speak_index]: it.target }),
    d.hearTargetTitle);
  const rec = el("button", { type: "button", class: "record" }, d.record);
  const status = el("p", { class: "status", "aria-live": "polite" });
  const keep = el("div", { class: "controls", hidden: "" });
  rec.addEventListener("click", async () => {
    if (!recorder.recording) {
      await recorder.start();
      rec.textContent = d.stop;
      rec.classList.add("on");
      status.textContent = d.recordingSentence;
      return;
    }
    rec.textContent = d.recordAgain;
    rec.classList.remove("on");
    take = await recorder.stop();
    clip?.dispose();
    clip = new Clip(take);
    status.textContent = d.listenBack;
    keep.hidden = false;
  });
  const play = btn(d.myTake, { play: true });
  play.addEventListener("click", () => clip?.play(0, 60));
  const save = el("button", { type: "button" }, d.keep);
  save.addEventListener("click", async () => {
    if (!take) return;
    status.textContent = d.saving;
    try {
      await api.addLabel(take, { source: "practice", text: it.text, phrase_index: it.phrase_index, said: it.target });
      status.textContent = d.saved;
      await refreshStats();
      await next();
    } catch (e) {
      status.textContent = d.couldntSave((e as Error).message);
    }
  });
  const skip = btn(d.skip, { quiet: true });
  skip.addEventListener("click", () => void next());
  keep.append(play, save, skip);
  host.replaceChildren(line, say, el("div", { class: "controls" }, hear, rec), keep, status);
}

async function review(): Promise<void> {
  const d = tr();
  const host = $("review-item");
  const it = await api.reviewNext();
  if (!("id" in it)) {
    host.replaceChildren(el("p", { class: "empty" }, d.nothingToReview));
    return;
  }
  const r = it as ReviewItem;
  const phrase = { moras: r.moras };
  const audio = new Audio(`/api/review/audio/${r.id.split("/").map(encodeURIComponent).join("/")}`);
  const play = btn(d.phraseBtn, { play: true });
  play.addEventListener("click", () => {
    audio.currentTime = Math.max(0, r.start - 0.1);
    void audio.play();
    window.setTimeout(() => audio.pause(), (r.end - r.start + 0.3) * 1000);
  });
  const whole = btn(d.wholeSentence, { play: true });
  whole.addEventListener("click", () => {
    audio.currentTime = 0;
    void audio.play();
  });
  const answers = el("div", { class: "controls answers" });
  for (const answer of ["variant", "misheard", "dictionary", "unsure"] as const) {
    const b = el("button", { type: "button", class: "secondary small" }, d.reviewChoices[answer]);
    b.addEventListener("click", async () => {
      await api.reviewAnswer(r.id, answer);
      await review();
    });
    answers.append(b);
  }
  host.replaceChildren(
    el("p", { lang: "ja" }, r.text),
    el("p", {}, d.expectedHeard[0], notationNode(phrase, r.expected[0]), d.expectedHeard[1],
      notationNode(phrase, r.heard, r.expected[0])),
    el("div", { class: "controls" }, play, whole), answers,
    el("p", { class: "muted" }, d.left(r.remaining)));
}
