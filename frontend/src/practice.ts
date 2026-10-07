// Practice tab: imitate a target accent (the right one, or a deliberate
// mistake) and keep the takes that sound like the target. Each kept take is
// a labelled recording of your voice, which is how Platina measures — and
// learns — how often it misjudges you. Also: review native phrases the
// detector flagged.

import * as api from "./api";
import type { PracticeItem, ReviewItem } from "./api";
import { Clip, Recorder } from "./recorder";
import { btn, el, notationNode } from "./render";
import { tutorButton } from "./tutor";

const $ = (id: string) => document.getElementById(id)!;
const recorder = new Recorder();
let item: PracticeItem | undefined;
let take: Blob | undefined;
let clip: Clip | undefined;
let started = false;

export async function initPractice(): Promise<void> {
  if (started) return;
  started = true;
  $("practice-next").addEventListener("click", () => void next());
  $("practice-own").addEventListener("submit", (e) => {
    e.preventDefault();
    const text = ($("practice-text") as HTMLInputElement).value.trim();
    if (text) void next(text);
  });
  $("review-next").addEventListener("click", () => void review());
  await Promise.all([next(), refreshStats()]);
}

async function refreshStats(): Promise<void> {
  try {
    const s = await api.labelStats();
    $("practice-stats").textContent =
      `${s.your_phrases} labelled phrases of your voice (${s.your_correct} correct, ${s.your_mistakes} deliberate mistakes) ` +
      `over ${s.sessions} session${s.sessions === 1 ? "" : "s"}. Aim: ~300 of each.`;
  } catch {
    $("practice-stats").textContent = "";
  }
}

async function next(text?: string): Promise<void> {
  const host = $("practice-item");
  take = undefined;
  try {
    item = await api.practiceNext(text);
  } catch (e) {
    host.replaceChildren(el("p", { class: "muted" }, `Couldn't load a sentence: ${(e as Error).message}`));
    return;
  }
  const it = item;
  const target = it.phrases[it.phrase_index];
  const line = el("p", { class: "notation-line", lang: "ja" });
  it.phrases.forEach((p, i) => {
    if (!p.moras.length) return;
    const span = el("span", { class: i === it.phrase_index ? "target" : "muted" }, notationNode(p, i === it.phrase_index ? it.target : p.accent));
    line.append(span, " ");
  });
  const isMistake = it.kind !== "expected";
  const say = el("p", {},
    "Say ", el("strong", { lang: "ja" }, target.text), " as ", notationNode(target, it.target),
    isMistake ? el("span", { class: "s-error sample" }, ` — a deliberate mistake (${it.kind})`) : " — the expected accent");
  const hear = tutorButton("▶ Hear the target", () => api.speak(it.text, 1, { [it.speak_index]: it.target }),
    "The tutor says the sentence with this accent");
  const rec = el("button", { type: "button", class: "record" }, "● Record");
  const status = el("p", { class: "muted", "aria-live": "polite" });
  const keep = el("div", { class: "controls", hidden: "" });
  rec.addEventListener("click", async () => {
    if (!recorder.recording) {
      await recorder.start();
      rec.textContent = "■ Stop";
      rec.classList.add("on");
      status.textContent = "Recording… say the whole sentence.";
      return;
    }
    rec.textContent = "● Record again";
    rec.classList.remove("on");
    take = await recorder.stop();
    clip?.dispose();
    clip = new Clip(take);
    status.textContent = "Listen back. Keep it only if it sounds like the target.";
    keep.hidden = false;
  });
  const play = btn("My take", { play: true });
  play.addEventListener("click", () => clip?.play(0, 60));
  const save = el("button", { type: "button" }, "Keep — I said it like the target");
  save.addEventListener("click", async () => {
    if (!take) return;
    status.textContent = "Saving…";
    try {
      await api.addLabel(take, { source: "practice", text: it.text, phrase_index: it.phrase_index, said: it.target });
      status.textContent = "Saved.";
      await refreshStats();
      await next();
    } catch (e) {
      status.textContent = `Couldn't save: ${(e as Error).message}`;
    }
  });
  const skip = btn("Skip", { quiet: true });
  skip.addEventListener("click", () => void next());
  keep.append(play, save, skip);
  host.replaceChildren(line, say, el("div", { class: "controls" }, hear, rec), keep, status);
}

async function review(): Promise<void> {
  const host = $("review-item");
  const it = await api.reviewNext();
  if (!("id" in it)) {
    host.replaceChildren(el("p", { class: "muted" },
      "Nothing to review. Build a queue with tools/review_queue.py (needs a corpus cache)."));
    return;
  }
  const r = it as ReviewItem;
  const phrase = { moras: r.moras };
  const audio = new Audio(`/api/review/audio/${r.id.split("/").map(encodeURIComponent).join("/")}`);
  const play = btn("Phrase", { play: true });
  play.addEventListener("click", () => {
    audio.currentTime = Math.max(0, r.start - 0.1);
    void audio.play();
    window.setTimeout(() => audio.pause(), (r.end - r.start + 0.3) * 1000);
  });
  const whole = btn("Whole sentence", { play: true });
  whole.addEventListener("click", () => {
    audio.currentTime = 0;
    void audio.play();
  });
  const answers = el("div", { class: "controls" });
  const choices: [string, "variant" | "misheard" | "dictionary" | "unsure"][] = [
    ["Native said another accent", "variant"], ["Platina misheard", "misheard"],
    ["Dictionary is wrong", "dictionary"], ["Can't tell", "unsure"]];
  for (const [label, answer] of choices) {
    const b = el("button", { type: "button", class: "secondary" }, label);
    b.addEventListener("click", async () => {
      await api.reviewAnswer(r.id, answer);
      await review();
    });
    answers.append(b);
  }
  host.replaceChildren(
    el("p", { lang: "ja" }, r.text),
    el("p", {}, "Expected ", notationNode(phrase, r.expected[0]), " · Platina heard ", notationNode(phrase, r.heard, r.expected[0])),
    el("div", { class: "controls" }, play, whole), answers,
    el("p", { class: "muted" }, `${r.remaining} left`));
}
