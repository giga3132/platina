// Detail panel for one phrase: verdict, expected vs heard, pitch chart,
// words and where their accents came from.

import { speakPhrase } from "./api";
import type { AnalyzedPhrase, Phrase, Word } from "./api";
import { CONFIDENCE_LABEL, STATUS_LABEL, btn, el, notationNode, pattern } from "./render";
import { tutorButton } from "./tutor";

const SVG = "http://www.w3.org/2000/svg";

function svg<K extends keyof SVGElementTagNameMap>(tag: K, attrs: Record<string, string | number>): SVGElementTagNameMap[K] {
  const node = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  return node;
}

function verdict(p: AnalyzedPhrase): string {
  const pct = p.p_expected === null ? "" : ` (${Math.round(p.p_expected * 100)}% likely you said the expected accent)`;
  switch (p.status) {
    case "correct":
      return p.said_as_one
        ? "matches, said in one breath with the neighbouring phrase (natives often do)."
        : `matches the dictionary${pct}.`;
    case "error":
      return `your accent sounds different from the dictionary${pct}.`;
    case "unverified":
      if (p.unclear_reason === "native-variant")
        return "differs from the dictionary, but many native speakers say it this way too.";
      return `sounds different, but the dictionary accent itself isn't confirmed — check it in NHK${pct}.`;
    case "uncertain":
      if (p.unclear_reason === "alignment")
        return "the moras that decide this didn't line up well with the audio, so it isn't judged.";
      if (p.unclear_reason === "unclear")
        return `no accent was heard clearly enough to call it a mistake${pct}.`;
      return "couldn't measure the pitch here (devoiced vowels, noise, or the words didn't line up with the audio).";
  }
}

/** Measured pitch per mora against the expected high/low pattern. */
function pitchChart(p: AnalyzedPhrase): HTMLElement {
  const W = 520, H = 200, L = 40, R = 16, T = 16, B = 34;
  const n = p.moras.length;
  const spans = p.mora_times.length === n ? p.mora_times : p.moras.map((_, i) => [i, i + 1] as [number, number]);
  const t0 = spans[0][0], t1 = spans[n - 1][1];
  const x = (t: number) => L + ((t - t0) / Math.max(t1 - t0, 1e-6)) * (W - L - R);

  const vals = p.mora_pitch.filter((v): v is number => v !== null);
  const lo = vals.length ? Math.min(...vals) : 0;
  const hi = vals.length ? Math.max(...vals) : 5;
  const pad = Math.max(1, (hi - lo) * 0.15);
  const yMin = lo - pad, yMax = hi + pad;
  const y = (v: number) => T + (1 - (v - yMin) / (yMax - yMin)) * (H - T - B);

  const root = el("figure", { class: "chart" });
  const legend = el("div", { class: "legend" },
    el("span", { class: "key measured" }, "your pitch (semitones)"),
    el("span", { class: "key expected" }, "dictionary high/low"),
    ...(p.expected_contour ? [el("span", { class: "key native" }, "typical native pitch")] : []));
  const box = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `pitch of ${p.text}` });

  // recessive grid: semitone lines every 2 st
  for (let v = Math.ceil(yMin / 2) * 2; v <= yMax; v += 2) {
    box.append(svg("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), class: "grid" }));
    const label = svg("text", { x: L - 6, y: y(v) + 4, class: "tick", "text-anchor": "end" });
    label.textContent = `${v > 0 ? "+" : ""}${v}`;
    box.append(label);
  }

  // expected H/L step, scaled to the measured range
  const exp = pattern(n, p.accent);
  const eLo = vals.length ? lo + (hi - lo) * 0.1 : 0, eHi = vals.length ? hi - (hi - lo) * 0.1 : 5;
  let d = "";
  spans.forEach(([s, e], i) => {
    const yy = y(exp[i] ? eHi : eLo);
    d += `${i ? "L" : "M"}${x(s)},${yy} L${x(e)},${yy} `;
  });
  box.append(svg("path", { d, class: "expected-line" }));

  // how natives typically move their pitch for this accent (contour model)
  if (p.expected_contour && p.expected_contour.length === n) {
    const flat = p.expected_contour.flat();
    const cLo = Math.min(...flat), cHi = Math.max(...flat);
    const scale = (v: number) => eLo + ((v - cLo) / Math.max(cHi - cLo, 1e-6)) * (eHi - eLo);
    const pts: string[] = [];
    spans.forEach(([s, e], i) => p.expected_contour![i].forEach((v, j, row) =>
      pts.push(`${x(s + ((j + 0.5) / row.length) * (e - s))},${y(scale(v))}`)));
    box.append(svg("polyline", { points: pts.join(" "), class: "native-line" }));
  }

  // measured pitch: line through voiced moras + markers
  const pts = spans
    .map(([s, e], i) => ({ cx: x((s + e) / 2), v: p.mora_pitch[i], i }))
    .filter((q): q is { cx: number; v: number; i: number } => q.v !== null && q.v !== undefined);
  if (pts.length > 1) {
    box.append(svg("polyline", { points: pts.map((q) => `${q.cx},${y(q.v)}`).join(" "), class: "measured-line" }));
  }
  for (const q of pts) box.append(svg("circle", { cx: q.cx, cy: y(q.v), r: 4.5, class: "measured-dot" }));

  // mora labels + hover columns
  const tip = el("div", { class: "tooltip", hidden: "" });
  spans.forEach(([s, e], i) => {
    const label = svg("text", { x: x((s + e) / 2), y: H - 12, class: "mora-label", "text-anchor": "middle" });
    label.textContent = p.moras[i];
    box.append(label);
    const hit = svg("rect", { x: x(s), y: T, width: Math.max(x(e) - x(s), 6), height: H - T - B + 20, class: "hit" });
    hit.addEventListener("mouseenter", () => {
      const v = p.mora_pitch[i];
      tip.textContent = `${p.moras[i]}  you: ${v === null ? "unvoiced" : `${v > 0 ? "+" : ""}${v.toFixed(1)} st`}  ·  dictionary: ${exp[i] ? "high" : "low"}`;
      tip.hidden = false;
      tip.style.left = `${(x((s + e) / 2) / W) * 100}%`;
    });
    hit.addEventListener("mouseleave", () => (tip.hidden = true));
    box.append(hit);
  });

  root.append(legend, el("div", { class: "plot" }, box, tip));

  // table view of the same data
  const table = el("table", {},
    el("thead", {}, el("tr", {}, el("th", {}, "Mora"), el("th", {}, "Dictionary"), el("th", {}, "Your pitch (semitones)"))));
  const body = el("tbody");
  p.moras.forEach((m, i) => {
    const v = p.mora_pitch[i];
    body.append(el("tr", {}, el("td", {}, m), el("td", {}, exp[i] ? "high" : "low"),
      el("td", {}, v === null || v === undefined ? "—" : v.toFixed(1))));
  });
  table.append(body);
  root.append(el("details", {}, el("summary", {}, "Show as table"), table));
  return root;
}

function wordsTable(words: Word[], onFix: (w: Word) => void): HTMLElement {
  const table = el("table", { class: "words" },
    el("thead", {}, el("tr", {}, el("th", {}, "Word"), el("th", {}, "Dictionary form"), el("th", {}, "Reading"),
      el("th", {}, "Accent"), el("th", {}, "Source"), el("th", {}))));
  const body = el("tbody");
  const SOURCE = { override: "NHK (checked by you)", unidic: "UniDic", none: "none" };
  for (const w of words) {
    const fix = btn("Set from NHK", { quiet: true });
    fix.addEventListener("click", () => onFix(w));
    const content = !["助詞", "助動詞", "記号"].includes(w.pos);
    body.append(el("tr", {},
      el("td", {}, w.surface), el("td", {}, w.lemma), el("td", {}, w.reading),
      el("td", {}, w.accents.length ? w.accents.map((a) => `[${a}]`).join("") : "—"),
      el("td", {}, SOURCE[w.source]), el("td", {}, content ? fix : "")));
  }
  table.append(body);
  return table;
}

export function renderDetail(
  host: HTMLElement,
  p: Phrase | AnalyzedPhrase,
  opts: {
    onFix: (w: Word) => void;
    onPlay?: (start: number, end: number) => void;
    onReport?: (said: number | null) => Promise<string>;
  },
): void {
  host.replaceChildren();
  host.hidden = false;
  const head = el("header", {}, el("h3", {}, p.text));
  if ("status" in p && opts.onPlay && p.mora_times.length) {
    const play = btn("Play", { play: true, title: "Hear yourself say this phrase" });
    const [s] = p.mora_times[0], [, e] = p.mora_times[p.mora_times.length - 1];
    play.addEventListener("click", () => opts.onPlay!(s, e));
    head.append(play);
  }
  host.append(head);

  const rows = el("dl", { class: "compare" });
  const hear = (accent: number, title: string) =>
    p.moras.length ? tutorButton("▶", () => speakPhrase(p.moras, accent), title) : "";
  rows.append(el("dt", {}, "Expected"),
    el("dd", {}, notationNode(p, p.accent), " ", hear(p.accent, "Hear the expected accent")));
  const dictAlts = p.alternatives.slice(1).filter((a) => !p.native_variants.includes(a));
  if (dictAlts.length) {
    const alts = el("dd", { class: "alts" });
    dictAlts.forEach((a) => alts.append(notationNode(p, a), " ", hear(a, "Hear this accent"), " "));
    rows.append(el("dt", {}, "Also OK"), alts);
  }
  if (p.native_variants.length) {
    const alts = el("dd", { class: "alts" });
    p.native_variants.forEach((a) => alts.append(notationNode(p, a), " ", hear(a, "Hear this accent"), " "));
    rows.append(el("dt", {}, "Natives also say"), alts);
  }
  if ("status" in p) {
    if (p.observed !== null) {
      rows.append(el("dt", {}, "You said"), el("dd", {}, notationNode(p, p.observed, p.accent), " ",
        hear(p.observed, "Hear the accent you used, in the tutor's voice")));
    }
    host.append(el("p", { class: `verdict s-${p.status}` }, `${STATUS_LABEL[p.status]}: ${verdict(p)}`));
  }
  host.append(rows);
  host.append(el("p", { class: "muted" }, `Expected accent: ${CONFIDENCE_LABEL[p.confidence]}`));
  if (p.reasons.length) host.append(el("ul", { class: "reasons" }, ...p.reasons.map((r) => el("li", {}, r))));
  if ("status" in p && p.mora_times.length) host.append(pitchChart(p));
  if ("status" in p && opts.onReport && p.moras.length >= 2) host.append(reportBox(p, opts.onReport));
  host.append(wordsTable(p.words, opts.onFix));
}

/** "Wrong verdict?": the user says which accent they really used. Saved
 * as a labelled clip of their voice for evaluating and training the detector. */
function reportBox(p: AnalyzedPhrase, onReport: (said: number | null) => Promise<string>): HTMLElement {
  const box = el("details", { class: "report" }, el("summary", {}, "Wrong verdict? Tell Platina what you said"));
  const row = el("div", { class: "controls" });
  const status = el("span", { class: "muted", "aria-live": "polite" });
  const send = async (said: number | null) => {
    status.textContent = "Saving…";
    try {
      status.textContent = await onReport(said);
      row.querySelectorAll("button").forEach((b) => (b.disabled = true));
    } catch (e) {
      status.textContent = `Couldn't save: ${(e as Error).message}`;
    }
  };
  for (let a = 0; a < p.moras.length; a++) {
    const b = el("button", { type: "button", class: "secondary", title: "I said this" }, notationNode(p, a));
    b.addEventListener("click", () => void send(a));
    row.append(b);
  }
  const unsure = btn("Not sure", { quiet: true });
  unsure.addEventListener("click", () => void send(null));
  row.append(unsure);
  box.append(el("p", { class: "muted" }, "I said:"), row, status);
  return box;
}
