// Detail panel for one phrase: verdict, expected vs heard, pitch chart,
// words and where their accents came from.

import type { AnalyzedPhrase, Phrase, Word } from "./api";
import { CONFIDENCE_LABEL, STATUS_LABEL, el, notationNode, pattern } from "./render";

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
      return `matches the dictionary${pct}.`;
    case "error":
      return `your accent sounds different from the dictionary${pct}.`;
    case "unverified":
      return `sounds different, but the dictionary accent itself isn't confirmed — check it in NHK${pct}.`;
    case "uncertain":
      return p.observed === null
        ? "couldn't measure the pitch here (devoiced vowels, noise, or the words didn't line up with the audio)."
        : `not clear enough to judge${pct}.`;
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
    el("span", { class: "key expected" }, "dictionary high/low"));
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
    const fix = el("button", { type: "button", class: "link" }, "Set from NHK");
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
  opts: { onFix: (w: Word) => void; onPlay?: (start: number, end: number) => void },
): void {
  host.replaceChildren();
  host.hidden = false;
  const head = el("header", {}, el("h3", {}, p.text));
  if ("status" in p && opts.onPlay && p.mora_times.length) {
    const play = el("button", { type: "button", class: "secondary" }, "▶ Play");
    const [s] = p.mora_times[0], [, e] = p.mora_times[p.mora_times.length - 1];
    play.addEventListener("click", () => opts.onPlay!(s, e));
    head.append(play);
  }
  host.append(head);

  const rows = el("dl", { class: "compare" });
  rows.append(el("dt", {}, "Expected"), el("dd", {}, notationNode(p, p.accent)));
  if (p.alternatives.length > 1) {
    const alts = el("dd", { class: "alts" });
    p.alternatives.slice(1).forEach((a) => alts.append(notationNode(p, a), " "));
    rows.append(el("dt", {}, "Also OK"), alts);
  }
  if ("status" in p) {
    if (p.observed !== null) rows.append(el("dt", {}, "You said"), el("dd", {}, notationNode(p, p.observed, p.accent)));
    host.append(el("p", { class: `verdict s-${p.status}` }, `${STATUS_LABEL[p.status]}: ${verdict(p)}`));
  }
  host.append(rows);
  host.append(el("p", { class: "muted" }, `Expected accent: ${CONFIDENCE_LABEL[p.confidence]}`));
  if (p.reasons.length) host.append(el("ul", { class: "reasons" }, ...p.reasons.map((r) => el("li", {}, r))));
  if ("status" in p && p.mora_times.length) host.append(pitchChart(p));
  host.append(wordsTable(p.words, opts.onFix));
}
