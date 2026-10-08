import "./style.css";

import * as api from "./api";
import type { AnalyzeResult, Word } from "./api";
import { renderDetail } from "./detail";
import { applyStatic, lang, setLang, tr } from "./i18n";
import { Clip, Recorder } from "./recorder";
import { btn, el, legend, notationNode, phraseRow, segments, statusLabel } from "./render";
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

// --- two spaces: My lessons (Lessons, Progress) and the Workshop ------------
// Every tab has its own address (#lessons, #progress, #quick-check, ...), so
// either space can be bookmarked; #lessons/<id> opens one lesson. The space
// sets the colours (<html data-space>); switching space plays a short wipe.

const SPACE_OF = {
  lessons: "lessons", progress: "lessons",
  "quick-check": "workshop", type: "workshop", nhk: "workshop", practice: "workshop",
} as const;
type Tab = keyof typeof SPACE_OF;
type Space = (typeof SPACE_OF)[Tab];
const isTab = (t: string): t is Tab => Object.hasOwn(SPACE_OF, t);
const nhkBack = $<HTMLButtonElement>("nhk-back");
let space: Space | undefined;
/** Where each space was left this session (an open lesson, too). */
const lastHash: Partial<Record<Space, string>> = {};

function rememberedTab(s?: Space): Tab {
  try {
    const t = localStorage.getItem(s ? `platina-tab-${s}` : "platina-tab");
    if (t && isTab(t) && (!s || SPACE_OF[t] === s)) return t;
  } catch { /* storage blocked: default */ }
  return s === "workshop" ? "quick-check" : "lessons";
}

function route(): void {
  const [head, ...rest] = location.hash.replace(/^#/, "").split("/").map(decodeURIComponent);
  if (!isTab(head)) {
    history.replaceState(null, "", `#${rememberedTab()}`);
    return route();
  }
  if (space && SPACE_OF[head] !== space) wipe(() => showTab(head, rest));
  else showTab(head, rest);
}

type TransitionDocument = Document & {
  startViewTransition?: (update: () => void) => { ready: Promise<void>; finished: Promise<void> };
};

/** Persona-style colour wipe into the other space: the new page is revealed
 * behind a slanted edge carrying the new space's colour (style.css). */
function wipe(update: () => void): void {
  const doc = document as TransitionDocument;
  if (!doc.startViewTransition || matchMedia("(prefers-reduced-motion: reduce)").matches) return update();
  const root = document.documentElement;
  const t = doc.startViewTransition(() => {
    update();
    root.classList.add("space-wipe");
  });
  t.ready.catch(() => {}); // skipped (another switch came first): the page still updates, just without the wipe
  void t.finished.finally(() => root.classList.remove("space-wipe"));
}

function showTab(name: Tab, rest: string[] = []): void {
  space = SPACE_OF[name];
  document.documentElement.dataset.space = space;
  lastHash[space] = [name, ...rest.slice(0, name === "lessons" ? 1 : 0)].map(encodeURIComponent).join("/");
  document.querySelectorAll<HTMLElement>(".space-switch button").forEach((b) =>
    b.setAttribute("aria-pressed", String(b.dataset.space === space)));
  document.querySelectorAll<HTMLElement>(".subnav ul").forEach((u) => (u.hidden = u.dataset.space !== space));
  document.querySelectorAll<HTMLElement>("nav a[data-tab]").forEach((a) =>
    a.dataset.tab === name ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"));
  document.querySelectorAll<HTMLElement>(".tab").forEach((s) => (s.hidden = s.id !== `tab-${name}`));
  detail.hidden = true;
  try {
    localStorage.setItem("platina-tab", name);
    localStorage.setItem(`platina-tab-${space}`, name);
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
    summary.append(el("p", { class: "empty" }, d.noSpeech));
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
  const saved = el("span", { class: "status", "aria-live": "polite" });
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
    el("details", { class: "gold disclosure" },
      el("summary", {}, d.goldSummary),
      el("p", {}, d.goldHelp),
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

// three lists, one at a time: words to check, saved, native accents
type NhkView = "check" | "saved" | "variants";
let nhkView: NhkView | undefined; // until picked: "check" when there is something to check
const showNhkView = segments($("nhk-views"), $("tab-nhk"), (v) => (nhkView = v as NhkView));
const countBadge = (id: string, n: number) => ($(id).textContent = n ? String(n) : "");

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
  countBadge("count-saved", saved.length);
  $("nhk-search").hidden = saved.length <= SAVED_SHOWN;

  const table = $("nhk-list");
  table.replaceChildren(el("thead", {}, el("tr", {},
    el("th", {}, d.lemma), el("th", {}, d.reading), el("th", {}, d.accent), el("th", {}, d.note), el("th", {}))));
  const body = el("tbody");
  for (const o of shown) {
    const del = btn("", { quiet: true, danger: true, icon: "trash", title: d.deleteNamed(o.lemma) });
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
  if (q && !matches.length) more.append(el("span", { class: "empty" }, d.noSavedMatch));
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
  if (!toCheck.size) ul.append(el("li", { class: "empty" }, d.nothingYetRecord));
  countBadge("count-check", toCheck.size);
  showNhkView(nhkView ?? (toCheck.size ? "check" : "saved"));
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
  if (!list.length) body.append(el("tr", {}, el("td", { class: "empty" }, d.noVariants)));
  table.append(body);
  countBadge("count-variants", list.length);
}

// --- help panels (ⓘ) and the notation key in them ----------------------------

document.addEventListener("click", (e) => {
  const b = (e.target as HTMLElement).closest<HTMLButtonElement>(".help-btn");
  const panel = b && document.getElementById(b.getAttribute("aria-controls") ?? "");
  if (!b || !panel) return;
  panel.hidden = !panel.hidden;
  b.setAttribute("aria-expanded", String(!panel.hidden));
});

const fillLegends = () => document.querySelectorAll(".legend-slot").forEach((s) => s.replaceChildren(legend()));

// --- space switch -----------------------------------------------------------------

document.querySelectorAll<HTMLButtonElement>(".space-switch button").forEach((b) =>
  b.addEventListener("click", () => {
    const s = b.dataset.space as Space;
    if (s !== space) location.hash = `#${lastHash[s] ?? rememberedTab(s)}`;
  }));

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
  fillLegends();
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
fillLegends();
langToggle.lang = lang() === "en" ? "ja" : "en";
initLessons({ detail, onFix: (w) => fixWord(w, location.hash) });
window.addEventListener("hashchange", route);
route();
