// Detail panel for one phrase: verdict, expected vs heard, pitch chart,
// words and where their accents came from.

import { speakPhrase } from "./api";
import type { AnalyzedPhrase, Phrase, Word } from "./api";
import { reason, tr } from "./i18n";
import { btn, confidenceLabel, el, notationNode, pattern, statusLabel } from "./render";
import { tutorButton } from "./tutor";

const SVG = "http://www.w3.org/2000/svg";

function svg<K extends keyof SVGElementTagNameMap>(tag: K, attrs: Record<string, string | number>): SVGElementTagNameMap[K] {
  const node = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  return node;
}

function verdict(p: AnalyzedPhrase): string {
  const d = tr();
  const pct = p.p_expected === null ? "" : d.likely(Math.round(p.p_expected * 100));
  switch (p.status) {
    case "correct":
      return p.said_as_one ? d.vSaidAsOne : d.vMatches(pct);
    case "error":
      return d.vError(pct);
    case "unverified":
      if (p.unclear_reason === "native-variant") return d.vNativeVariant;
      return d.vUnconfirmed(pct);
    case "uncertain":
      if (p.unclear_reason === "alignment") return d.vAlignment;
      if (p.unclear_reason === "unclear") return d.vUnclear(pct);
      return d.vNoPitch;
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

  const tx = tr();
  const root = el("figure", { class: "chart" });
  const legend = el("div", { class: "legend" },
    el("span", { class: "key measured" }, tx.keyMeasured),
    el("span", { class: "key expected" }, tx.keyExpected),
    ...(p.expected_contour ? [el("span", { class: "key native" }, tx.keyNative)] : []));
  const box = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": tx.pitchOf(p.text) });

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
      tip.textContent = tx.tooltip(p.moras[i], v === null ? tx.unvoiced : `${v > 0 ? "+" : ""}${v.toFixed(1)} st`,
        exp[i] ? tx.high : tx.low);
      tip.hidden = false;
      tip.style.left = `${(x((s + e) / 2) / W) * 100}%`;
    });
    hit.addEventListener("mouseleave", () => (tip.hidden = true));
    box.append(hit);
  });

  root.append(legend, el("div", { class: "plot" }, box, tip));

  // table view of the same data
  const table = el("table", {},
    el("thead", {}, el("tr", {}, el("th", {}, tx.mora), el("th", {}, tx.dictionary), el("th", {}, tx.yourPitch))));
  const body = el("tbody");
  p.moras.forEach((m, i) => {
    const v = p.mora_pitch[i];
    body.append(el("tr", {}, el("td", {}, m), el("td", {}, exp[i] ? tx.high : tx.low),
      el("td", {}, v === null || v === undefined ? "—" : v.toFixed(1))));
  });
  table.append(body);
  root.append(el("details", { class: "disclosure" }, el("summary", {}, tx.showTable), table));
  return root;
}

function wordsTable(words: Word[], onFix: (w: Word) => void): HTMLElement {
  const d = tr();
  const table = el("table", { class: "words" },
    el("thead", {}, el("tr", {}, el("th", {}, d.word), el("th", {}, d.lemma), el("th", {}, d.reading),
      el("th", {}, d.accent), el("th", {}, d.source), el("th", {}))));
  const body = el("tbody");
  const SOURCE = { override: d.sourceOverride, unidic: "UniDic", none: d.sourceNone };
  for (const w of words) {
    const fix = btn(d.setFromNhk, { quiet: true });
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
    onReading?: (text: string) => void;
  },
): void {
  const d = tr();
  host.replaceChildren();
  host.hidden = false;
  const head = el("header", {}, el("h3", { lang: "ja" }, p.text));
  const tools = el("div", { class: "actions" });
  if ("status" in p && opts.onPlay && p.mora_times.length) {
    const play = btn(d.play, { play: true, title: d.hearPhraseYourself });
    const [s] = p.mora_times[0], [, e] = p.mora_times[p.mora_times.length - 1];
    play.addEventListener("click", () => opts.onPlay!(s, e));
    tools.append(play);
  }
  const close = btn("", { quiet: true, icon: "close", title: d.close });
  close.addEventListener("click", () => {
    host.hidden = true;
    document.querySelectorAll(".phrase.selected").forEach((n) => n.classList.remove("selected"));
  });
  tools.append(close);
  head.append(tools);
  host.append(head);

  const rows = el("dl", { class: "compare" });
  const hear = (accent: number, title: string) =>
    p.moras.length ? tutorButton("▶", () => speakPhrase(p.moras, accent), title) : "";
  rows.append(el("dt", {}, d.expectedRow),
    el("dd", {}, notationNode(p, p.accent), " ", hear(p.accent, d.hearExpected)));
  const dictAlts = p.alternatives.slice(1).filter((a) => !p.native_variants.includes(a));
  if (dictAlts.length) {
    const alts = el("dd", { class: "alts" });
    dictAlts.forEach((a) => alts.append(notationNode(p, a), " ", hear(a, d.hearThisAccent), " "));
    rows.append(el("dt", {}, d.alsoOk), alts);
  }
  if (p.native_variants.length) {
    const alts = el("dd", { class: "alts" });
    p.native_variants.forEach((a) => alts.append(notationNode(p, a), " ", hear(a, d.hearThisAccent), " "));
    rows.append(el("dt", {}, d.nativesAlso), alts);
  }
  if ("status" in p) {
    if (p.observed !== null) {
      rows.append(el("dt", {}, d.youSaidRow), el("dd", {}, notationNode(p, p.observed, p.accent), " ",
        hear(p.observed, d.hearYourAccent)));
    }
    host.append(el("p", { class: "verdict" }, el("span", { class: `pill s-${p.status}` }, statusLabel(p.status)), " ",
      verdict(p)));
  }
  if (opts.onReading && p.reading_alternatives.length) {
    const alts = el("dd", { class: "alts", lang: "ja" });
    for (const a of p.reading_alternatives) {
      const b = btn(`${a.surface}（${a.reading}）`, { quiet: true, title: d.readAsTitle(a.surface, a.reading) });
      b.addEventListener("click", () => opts.onReading!(a.text));
      alts.append(b, " ");
    }
    rows.append(el("dt", {}, d.readAs), alts);
  }
  host.append(rows);
  if ("status" in p && p.mora_times.length) host.append(pitchChart(p));

  // where the expected accent comes from: open when it's in doubt (that's
  // why the phrase is grey) and for typed text, where it's the point
  const sources = el("details", { class: "section disclosure" }, el("summary", {}, d.wordsAndSources),
    el("p", {}, d.expectedSource(confidenceLabel(p.confidence))));
  if (p.reasons.length) sources.append(el("ul", { class: "reasons" }, ...p.reasons.map((r) => el("li", {}, reason(r)))));
  sources.append(wordsTable(p.words, opts.onFix));
  sources.open = !("status" in p) || p.confidence === "uncertain" || p.status === "unverified";
  host.append(sources);
  if ("status" in p && opts.onReport && p.moras.length >= 2) host.append(reportBox(p, opts.onReport));
}

/** "Wrong verdict?": the user says which accent they really used. Saved
 * as a labelled clip of their voice for evaluating and training the detector. */
function reportBox(p: AnalyzedPhrase, onReport: (said: number | null) => Promise<string>): HTMLElement {
  const d = tr();
  const box = el("details", { class: "report section disclosure" }, el("summary", {}, d.wrongVerdict));
  const row = el("div", { class: "controls" });
  const status = el("span", { class: "status", "aria-live": "polite" });
  const send = async (said: number | null) => {
    status.textContent = d.saving;
    try {
      status.textContent = await onReport(said);
      row.querySelectorAll("button").forEach((b) => (b.disabled = true));
    } catch (e) {
      status.textContent = d.couldntSave((e as Error).message);
    }
  };
  for (let a = 0; a < p.moras.length; a++) {
    const b = el("button", { type: "button", class: "secondary", title: d.iSaidThis }, notationNode(p, a));
    b.addEventListener("click", () => void send(a));
    row.append(b);
  }
  const unsure = btn(d.notSure, { quiet: true });
  unsure.addEventListener("click", () => void send(null));
  row.append(unsure);
  box.append(el("p", {}, d.iSaid), row, status);
  return box;
}
