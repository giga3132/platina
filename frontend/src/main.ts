import "./style.css";

import * as api from "./api";
import type { AnalyzeResult, Word } from "./api";
import { renderDetail } from "./detail";
import { applyStatic, lang, setLang, tr } from "./i18n";
import { Clip, Recorder } from "./recorder";
import { btn, el, notationNode, phraseRow, statusLabel } from "./render";
import { initLessons, lessonRecording, showLessons } from "./lessons";
import { initPractice, practiceRecording, redrawPractice } from "./practice";
import { showProgress } from "./progress";
import { tutorButton } from "./tutor";

const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;

const detail = $("detail");
const recorder = new Recorder();
let clip: Clip | undefined;
let last: { audio: Blob; text: string } | undefined;
let lastResult: AnalyzeResult | undefined;
let typed: string | undefined;
const toCheck = new Map<string, Word>();

// --- tabs: "My lessons" (Lessons, Progress) and the Workshop ------------------
// Every tab has its own address (#lessons, #progress, #quick-check, ...), so
// either area can be bookmarked; #lessons/<id> opens one lesson.

const TABS = ["lessons", "progress", "quick-check", "type", "nhk", "practice"] as const;
type Tab = (typeof TABS)[number];
const isTab = (t: string): t is Tab => (TABS as readonly string[]).includes(t);
const nhkBack = $<HTMLButtonElement>("nhk-back");

function rememberedTab(): Tab {
  try {
    const t = localStorage.getItem("platina-tab");
    if (t && isTab(t)) return t;
  } catch { /* storage blocked: default */ }
  return "lessons";
}

function route(): void {
  const [head, ...rest] = location.hash.replace(/^#/, "").split("/").map(decodeURIComponent);
  if (!isTab(head)) {
    history.replaceState(null, "", `#${rememberedTab()}`);
    return route();
  }
  showTab(head, rest);
}

function showTab(name: Tab, rest: string[] = []): void {
  document.querySelectorAll<HTMLElement>("nav a[data-tab]").forEach((a) =>
    a.dataset.tab === name ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"));
  document.querySelectorAll<HTMLElement>(".tab").forEach((s) => (s.hidden = s.id !== `tab-${name}`));
  detail.hidden = true;
  try {
    localStorage.setItem("platina-tab", name);
  } catch { /* storage blocked: not remembered */ }
  if (name !== "nhk") nhkBack.hidden = true;
  if (name === "nhk") void refreshOverrides();
  if (name === "practice") void initPractice();
  if (name === "lessons") showLessons(rest);
  if (name === "progress") void showProgress();
}

/** Opens My NHK accents with the word filled in; from a lesson, with a way back. */
function fixWord(w: Word, returnTo?: string): void {
  location.hash = "#nhk";
  nhkBack.hidden = !returnTo;
  nhkBack.onclick = () => returnTo && (location.hash = returnTo);
  const form = $<HTMLFormElement>("nhk-form");
  (form.elements.namedItem("lemma") as HTMLInputElement).value = w.lemma;
  (form.elements.namedItem("reading") as HTMLInputElement).value = w.reading;
  const acc = form.elements.namedItem("accents") as HTMLInputElement;
  acc.value = "";
  acc.placeholder = w.accents.length ? tr().unidicSays(w.accents.join(",")) : tr().accentPlaceholder;
  acc.focus();
}

// --- speak ------------------------------------------------------------------

const recordBtn = $<HTMLButtonElement>("record");
const status = $("speak-status");
let tick: number | undefined;

recordBtn.addEventListener("click", async () => {
  if (!recorder.recording) {
    try {
      await recorder.start();
    } catch (e) {
      status.textContent = tr().micUnavailable((e as Error).message);
      return;
    }
    recordBtn.textContent = tr().stop;
    recordBtn.classList.add("on");
    status.textContent = tr().recordingTalk;
    tick = window.setInterval(() => {
      const s = Math.floor((performance.now() - recorder.startedAt) / 1000);
      $("timer").textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    }, 250);
  } else {
    window.clearInterval(tick);
    recordBtn.textContent = tr().record;
    recordBtn.classList.remove("on");
    await run(await recorder.stop());
  }
});

$<HTMLInputElement>("upload").addEventListener("change", (e) => {
  const file = (e.target as HTMLInputElement).files?.[0];
  if (file) void run(file);
});

async function run(audio: Blob): Promise<void> {
  const text = $<HTMLTextAreaElement>("reading").value;
  last = { audio, text };
  clip?.dispose();
  clip = new Clip(audio);
  status.textContent = tr().analyzing;
  recordBtn.disabled = true;
  try {
    showResults(await api.analyze(audio, text));
    status.textContent = "";
  } catch (e) {
    status.textContent = tr().analysisFailed((e as Error).message);
  } finally {
    recordBtn.disabled = false;
  }
}

function showResults(res: AnalyzeResult): void {
  const d = tr();
  lastResult = res;
  const host = $("results");
  host.replaceChildren();
  detail.hidden = true;
  const total = Object.values(res.summary).reduce((a, b) => a + (b ?? 0), 0);
  const summary = $("summary");
  summary.replaceChildren();
  if (!total) {
    summary.append(el("p", { class: "muted" }, d.noSpeech));
    return;
  }
  for (const s of ["correct", "error", "unverified", "uncertain"] as const) {
    if (res.summary[s]) summary.append(el("span", { class: `count s-${s}` }, d.summaryCount(res.summary[s]!, statusLabel(s))));
  }

  for (const u of res.utterances) {
    const block = el("div", { class: "utterance" });
    const replay = btn("", { play: true, title: d.hearSentenceYourself });
    replay.addEventListener("click", () => clip?.play(u.start, u.end));
    const tutor = tutorButton(d.tutor, () => api.speak(u.text), d.hearSentenceExpected);
    block.append(el("p", { class: "transcript", lang: "ja" }, replay, " ", u.text, " ", tutor));
    const audio = last?.audio;
    block.append(phraseRow(u.phrases, (p) =>
      renderDetail(detail, p, {
        onFix: fixWord,
        onPlay: (s, e) => clip?.play(s, e),
        onReport: audio && (async (said) => {
          const stats = await api.addLabel(audio, {
            source: "report", text: u.text, phrase_index: u.phrases.indexOf(p), said,
            start: u.start, end: u.end, verdict: p.status,
          });
          return tr().reportSaved(stats.your_phrases);
        }),
      })));
    host.append(block);
    for (const p of u.phrases) {
      if (p.confidence !== "uncertain") continue;
      for (const w of p.words) {
        if (w.source !== "override" && !["助詞", "助動詞", "記号"].includes(w.pos)) toCheck.set(`${w.lemma}|${w.reading}`, w);
      }
    }
  }
  if (last) {
    const again = el("button", { type: "button", class: "secondary" }, d.recheckRecording);
    again.addEventListener("click", () => last && void run(last.audio));
    host.append(again);
  }
}

// --- type -------------------------------------------------------------------

$<HTMLFormElement>("type-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = $<HTMLTextAreaElement>("type-input").value.trim();
  if (text) void showTyped(text);
});

async function showTyped(text: string): Promise<void> {
  const d = tr();
  typed = text;
  const res = await api.expected(text);
  const host = $("type-results");
  const gold = el("input", { lang: "ja", value: res.notation, "aria-label": d.nhkNotation });
  const save = el("button", { type: "button", class: "secondary" }, d.saveGold);
  const saved = el("span", { class: "muted", "aria-live": "polite" });
  save.addEventListener("click", async () => {
    await api.addGold(res.text, gold.value);
    saved.textContent = d.goldAdded;
  });
  host.replaceChildren(
    el("p", { class: "notation-line", lang: "ja" }, res.notation),
    el("div", { class: "controls" },
      tutorButton(d.listen, () => api.speak(res.text)),
      tutorButton(d.slow, () => api.speak(res.text, 0.75))),
    phraseRow(res.phrases, (p) => renderDetail(detail, p, {
      onFix: fixWord,
      onReading: (t) => {
        $<HTMLTextAreaElement>("type-input").value = t;
        void showTyped(t);
      },
    })),
    el("details", { class: "gold" },
      el("summary", {}, d.goldSummary),
      el("p", { class: "muted" }, d.goldHelp),
      gold, el("div", { class: "controls" }, save, saved)),
  );
}

// --- NHK overrides -------------------------------------------------------------

$<HTMLFormElement>("nhk-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target as HTMLFormElement;
  const data = new FormData(form);
  const accents = String(data.get("accents")).split(/[,\s、]+/).filter(Boolean).map(Number);
  if (!accents.length || accents.some((a) => !Number.isInteger(a) || a < 0)) {
    $("nhk-status").textContent = tr().accentsInvalid;
    return;
  }
  await api.putOverride({
    lemma: String(data.get("lemma")).trim(),
    reading: String(data.get("reading")).trim(),
    accents,
    note: String(data.get("note") ?? ""),
  });
  toCheck.delete(`${data.get("lemma")}|${data.get("reading")}`);
  form.reset();
  $("nhk-status").textContent = tr().nhkSaved;
  await refreshOverrides();
});

// the saved list runs to thousands (Anki import): show a few, search or expand for the rest
const SAVED_SHOWN = 10;
let saved: api.Override[] = [];
let savedExpanded = false;

$<HTMLInputElement>("nhk-search").addEventListener("input", () => renderSaved());

const toKatakana = (s: string) => s.replace(/[ぁ-ゖ]/g, (c) => String.fromCharCode(c.charCodeAt(0) + 0x60));

function renderSaved(): void {
  const d = tr();
  const q = $<HTMLInputElement>("nhk-search").value.trim();
  const matches = q
    ? saved.filter((o) => o.lemma.includes(q) || o.reading.includes(toKatakana(q)) || o.note.includes(q))
    : saved;
  const shown = savedExpanded ? matches : matches.slice(0, SAVED_SHOWN);
  $("nhk-count").textContent = saved.length ? d.savedCount(saved.length) : "";
  $("nhk-search").hidden = saved.length <= SAVED_SHOWN;

  const table = $("nhk-list");
  table.replaceChildren(el("thead", {}, el("tr", {},
    el("th", {}, d.lemma), el("th", {}, d.reading), el("th", {}, d.accent), el("th", {}, d.note), el("th", {}))));
  const body = el("tbody");
  for (const o of shown) {
    const del = btn(d.delete, { quiet: true, danger: true });
    del.addEventListener("click", async () => {
      await api.deleteOverride(o.lemma, o.reading, o.context);
      await refreshOverrides();
    });
    body.append(el("tr", {}, el("td", { lang: "ja" }, o.lemma), el("td", { lang: "ja" }, o.reading),
      el("td", {}, o.accents.map((a) => `[${a}]`).join("")), el("td", {}, o.note), el("td", {}, del)));
  }
  table.append(body);
  table.hidden = !shown.length;

  const more = $("nhk-more");
  more.replaceChildren();
  if (q && !matches.length) more.append(el("span", { class: "muted" }, d.noSavedMatch));
  else if (matches.length > SAVED_SHOWN) {
    const toggle = btn(savedExpanded ? d.showFewer : d.showAllSaved(matches.length));
    toggle.addEventListener("click", () => {
      savedExpanded = !savedExpanded;
      renderSaved();
      if (!savedExpanded) $("nhk-search").scrollIntoView({ block: "nearest" });
    });
    more.append(toggle);
  }
}

async function refreshOverrides(): Promise<void> {
  const d = tr();
  saved = await api.listOverrides();
  renderSaved();

  const ul = $("to-check");
  ul.replaceChildren();
  for (const w of toCheck.values()) {
    const b = btn(`${w.lemma}（${w.reading}）`, { quiet: true });
    b.lang = "ja";
    b.addEventListener("click", () => fixWord(w));
    ul.append(el("li", {}, b, w.accents.length ? `  UniDic: ${w.accents.join(",")}` : ""));
  }
  if (!toCheck.size) ul.append(el("li", { class: "muted" }, d.nothingYetRecord));
  await refreshVariants();
}

async function refreshVariants(): Promise<void> {
  const d = tr();
  const table = $("variant-list");
  const list = await api.listVariants();
  table.replaceChildren(el("thead", {}, el("tr", {},
    el("th", {}, d.phrase), el("th", {}, d.nativesSay), el("th", {}, d.speakers), el("th", {}, d.status), el("th", {}))));
  const body = el("tbody");
  for (const v of list) {
    const [words, reading] = v.key.split("/");
    const moras = Array.from(reading.matchAll(/.[ャュョァィゥェォ]?/g), (m) => m[0]);
    const actions = el("td", {});
    for (const status of ["approved", "rejected"] as const) {
      if (v.status === status) continue;
      const b = btn(status === "approved" ? d.approve : d.reject, { quiet: true, danger: status === "rejected" });
      b.addEventListener("click", async () => {
        await api.setVariant(v.key, v.accent, status);
        await refreshVariants();
      });
      actions.append(b, " ");
    }
    body.append(el("tr", {}, el("td", { lang: "ja" }, words.replaceAll("|", "")),
      el("td", { lang: "ja" }, notationNode({ moras }, v.accent)), el("td", {}, `${v.speakers}/${v.total}`),
      el("td", {}, d.variantStatus[v.status] ?? v.status), actions));
  }
  if (!list.length) body.append(el("tr", {}, el("td", { class: "muted" }, d.noVariants)));
  table.append(body);
}

// --- tutor credit (required by VOICEVOX's terms) ------------------------------

let credit: string | undefined;
const showCredit = () => credit && ($("tutor-credit").textContent = tr().tutorCredit(credit));
api.tutorCredit().then((c) => {
  credit = c;
  showCredit();
}, () => {});

// --- language ------------------------------------------------------------------
// Switching redraws the current view in place; not while recording, so a
// redraw can't lose the recording's state.

const langToggle = $<HTMLButtonElement>("lang-toggle");
const recordingNow = () => recorder.recording || lessonRecording() || practiceRecording();

langToggle.addEventListener("click", () => {
  if (recordingNow()) return;
  setLang(lang() === "en" ? "ja" : "en");
  langToggle.lang = lang() === "en" ? "ja" : "en";
  showCredit();
  detail.hidden = true;
  if (lastResult) showResults(lastResult);
  if (typed) void showTyped(typed);
  redrawPractice();
  route();
});
// the toggle shows the other language's name; it is greyed out while recording
window.setInterval(() => (langToggle.disabled = recordingNow()), 500);

// --- start ---------------------------------------------------------------------

applyStatic();
langToggle.lang = lang() === "en" ? "ja" : "en";
initLessons({ detail, onFix: (w) => fixWord(w, location.hash) });
window.addEventListener("hashchange", route);
route();
