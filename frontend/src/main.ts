import "./style.css";

import * as api from "./api";
import type { AnalyzeResult, Word } from "./api";
import { renderDetail } from "./detail";
import { Clip, Recorder } from "./recorder";
import { STATUS_LABEL, el, notationNode, phraseRow } from "./render";
import { initPractice } from "./practice";
import { tutorButton } from "./tutor";

const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;

const detail = $("detail");
const recorder = new Recorder();
let clip: Clip | undefined;
let last: { audio: Blob; text: string } | undefined;
const toCheck = new Map<string, Word>();

// --- tabs -------------------------------------------------------------------

function showTab(name: string): void {
  document.querySelectorAll<HTMLElement>("[role=tab]").forEach((b) =>
    b.setAttribute("aria-selected", String(b.dataset.tab === name)));
  document.querySelectorAll<HTMLElement>(".tab").forEach((s) => (s.hidden = s.id !== `tab-${name}`));
  detail.hidden = true;
  if (name === "nhk") void refreshOverrides();
  if (name === "practice") void initPractice();
}
document.querySelectorAll<HTMLElement>("[role=tab]").forEach((b) =>
  b.addEventListener("click", () => showTab(b.dataset.tab!)));

function fixWord(w: Word): void {
  showTab("nhk");
  const form = $<HTMLFormElement>("nhk-form");
  (form.elements.namedItem("lemma") as HTMLInputElement).value = w.lemma;
  (form.elements.namedItem("reading") as HTMLInputElement).value = w.reading;
  const acc = form.elements.namedItem("accents") as HTMLInputElement;
  acc.value = "";
  acc.placeholder = w.accents.length ? `UniDic says ${w.accents.join(",")}` : "0  or  0,2";
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
      status.textContent = `Microphone unavailable: ${(e as Error).message}`;
      return;
    }
    recordBtn.textContent = "■ Stop";
    recordBtn.classList.add("on");
    status.textContent = "Recording… read aloud or just talk.";
    tick = window.setInterval(() => {
      const s = Math.floor((performance.now() - recorder.startedAt) / 1000);
      $("timer").textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    }, 250);
  } else {
    window.clearInterval(tick);
    recordBtn.textContent = "● Record";
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
  status.textContent = "Analyzing… (the first run loads the speech models, ~30 s)";
  recordBtn.disabled = true;
  try {
    showResults(await api.analyze(audio, text));
    status.textContent = "";
  } catch (e) {
    status.textContent = `Analysis failed: ${(e as Error).message}`;
  } finally {
    recordBtn.disabled = false;
  }
}

function showResults(res: AnalyzeResult): void {
  const host = $("results");
  host.replaceChildren();
  detail.hidden = true;
  const total = Object.values(res.summary).reduce((a, b) => a + (b ?? 0), 0);
  const summary = $("summary");
  summary.replaceChildren();
  if (!total) {
    summary.append(el("p", { class: "muted" }, "No speech recognized."));
    return;
  }
  for (const s of ["correct", "error", "unverified", "uncertain"] as const) {
    if (res.summary[s]) summary.append(el("span", { class: `count s-${s}` }, `${res.summary[s]} ${STATUS_LABEL[s].toLowerCase()}`));
  }

  for (const u of res.utterances) {
    const block = el("div", { class: "utterance" });
    const replay = el("button", { type: "button", class: "link" }, "▶");
    replay.addEventListener("click", () => clip?.play(u.start, u.end));
    const tutor = tutorButton("▶ Tutor", () => api.speak(u.text), "Hear this sentence with the expected accent");
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
          return `Saved — thanks. ${stats.your_phrases} labelled phrases of your voice so far.`;
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
    const again = el("button", { type: "button", class: "secondary" }, "Re-check this recording");
    again.addEventListener("click", () => last && void run(last.audio));
    host.append(again);
  }
}

// --- type -------------------------------------------------------------------

$<HTMLFormElement>("type-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $<HTMLTextAreaElement>("type-input").value.trim();
  if (!text) return;
  const res = await api.expected(text);
  const host = $("type-results");
  const gold = el("input", { lang: "ja", value: res.notation, "aria-label": "NHK notation" });
  const save = el("button", { type: "button", class: "secondary" }, "Save as NHK-checked test sentence");
  const saved = el("span", { class: "muted", "aria-live": "polite" });
  save.addEventListener("click", async () => {
    await api.addGold(res.text, gold.value);
    saved.textContent = "Added to backend/tests/gold/sentences.yaml";
  });
  host.replaceChildren(
    el("p", { class: "notation-line", lang: "ja" }, res.notation),
    el("div", { class: "controls" },
      tutorButton("▶ Listen", () => api.speak(res.text)),
      tutorButton("▶ Slow", () => api.speak(res.text, 0.75))),
    phraseRow(res.phrases, (p) => renderDetail(detail, p, { onFix: fixWord })),
    el("details", { class: "gold" },
      el("summary", {}, "Checked this sentence in NHK? Save it as a test case"),
      el("p", { class: "muted" }, "Correct the notation below if NHK differs (＼ after the drop, ━ for flat, spaces between phrases)."),
      gold, el("div", { class: "controls" }, save, saved)),
  );
});

// --- NHK overrides -------------------------------------------------------------

$<HTMLFormElement>("nhk-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target as HTMLFormElement;
  const data = new FormData(form);
  const accents = String(data.get("accents")).split(/[,\s、]+/).filter(Boolean).map(Number);
  if (!accents.length || accents.some((a) => !Number.isInteger(a) || a < 0)) {
    $("nhk-status").textContent = "Accent numbers must be whole numbers like 0 or 0,2.";
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
  $("nhk-status").textContent = "Saved. Re-check a recording or text to see it applied.";
  await refreshOverrides();
});

async function refreshOverrides(): Promise<void> {
  const list = await api.listOverrides();
  const table = $("nhk-list");
  table.replaceChildren(el("thead", {}, el("tr", {},
    el("th", {}, "Dictionary form"), el("th", {}, "Reading"), el("th", {}, "Accent"), el("th", {}, "Note"), el("th", {}))));
  const body = el("tbody");
  for (const o of list) {
    const del = el("button", { type: "button", class: "link" }, "Delete");
    del.addEventListener("click", async () => {
      await api.deleteOverride(o.lemma, o.reading);
      await refreshOverrides();
    });
    body.append(el("tr", {}, el("td", { lang: "ja" }, o.lemma), el("td", { lang: "ja" }, o.reading),
      el("td", {}, o.accents.map((a) => `[${a}]`).join("")), el("td", {}, o.note), el("td", {}, del)));
  }
  table.append(body);

  const ul = $("to-check");
  ul.replaceChildren();
  for (const w of toCheck.values()) {
    const b = el("button", { type: "button", class: "link", lang: "ja" }, `${w.lemma}（${w.reading}）`);
    b.addEventListener("click", () => fixWord(w));
    ul.append(el("li", {}, b, w.accents.length ? `  UniDic: ${w.accents.join(",")}` : ""));
  }
  if (!toCheck.size) ul.append(el("li", { class: "muted" }, "Nothing yet — record something first."));
  await refreshVariants();
}

async function refreshVariants(): Promise<void> {
  const table = $("variant-list");
  const list = await api.listVariants();
  table.replaceChildren(el("thead", {}, el("tr", {},
    el("th", {}, "Phrase"), el("th", {}, "Natives say"), el("th", {}, "Speakers"), el("th", {}, "Status"), el("th", {}))));
  const body = el("tbody");
  for (const v of list) {
    const [words, reading] = v.key.split("/");
    const moras = Array.from(reading.matchAll(/.[ャュョァィゥェォ]?/g), (m) => m[0]);
    const actions = el("td", {});
    for (const status of ["approved", "rejected"] as const) {
      if (v.status === status) continue;
      const b = el("button", { type: "button", class: "link" }, status === "approved" ? "Approve" : "Reject");
      b.addEventListener("click", async () => {
        await api.setVariant(v.key, v.accent, status);
        await refreshVariants();
      });
      actions.append(b, " ");
    }
    body.append(el("tr", {}, el("td", { lang: "ja" }, words.replaceAll("|", "")),
      el("td", { lang: "ja" }, notationNode({ moras }, v.accent)), el("td", {}, `${v.speakers}/${v.total}`),
      el("td", {}, v.status), actions));
  }
  if (!list.length) body.append(el("tr", {}, el("td", { class: "muted" }, "None yet (tools/mine_variants.py).")));
  table.append(body);
}

// --- tutor credit (required by VOICEVOX's terms) ------------------------------

api.tutorCredit().then(
  (credit) => ($("tutor-credit").textContent = `Tutor voice: ${credit}`),
  () => {});
