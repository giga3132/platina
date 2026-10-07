// Progress across lessons: your level over time (only lessons long enough to
// be reliable count), how much you spoke, and words that keep going wrong —
// or that you've fixed.

import * as api from "./api";
import type { Progress, ProgressLesson, WordProgress } from "./api";
import { dateOf, minutes } from "./lessons";
import { el } from "./render";

const SVG = "http://www.w3.org/2000/svg";

function svg<K extends keyof SVGElementTagNameMap>(tag: K, attrs: Record<string, string | number>, text?: string): SVGElementTagNameMap[K] {
  const node = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  if (text !== undefined) node.textContent = text;
  return node;
}

function shortDate(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

function headline(p: Progress): HTMLElement {
  const card = (value: string, label: string, note: string) =>
    el("div", { class: "stat" }, el("span", { class: "stat-value" }, value), el("span", { class: "stat-label" }, label),
      el("span", { class: "stat-note" }, note));
  const minMin = Math.round(p.min_speaking_s / 60);
  return el("div", { class: "stats" },
    card(p.current_level === null ? "—" : String(Math.round(p.current_level)), "Your level",
      p.current_level === null
        ? `Appears after a lesson with at least ${p.min_judged} judged phrases and ${minMin} minutes of your speech.`
        : "Average of your last 3 counted lessons."),
    card(p.change === null ? "—" : `${p.change >= 0 ? "+" : "−"}${Math.abs(Math.round(p.change))}`, "Change",
      p.change === null ? "Shown once 4 lessons count." : "Since your first 3 counted lessons."),
    card(minutes(p.speaking_s), "You've spoken", `In ${p.lessons.length} lesson${p.lessons.length === 1 ? "" : "s"}.`));
}

/** Level per lesson with its likely range; short lessons hollow and grey. */
function chart(lessons: ProgressLesson[]): HTMLElement {
  const W = 720, H = 240, L = 40, R = 16, T = 14, B = 30;
  const n = lessons.length;
  const x = (i: number) => (n === 1 ? (L + W - R) / 2 : L + (i / (n - 1)) * (W - L - R));
  const low = Math.min(...lessons.map((s) => s.level_range[0]));
  const yMin = Math.max(0, Math.floor((low - 5) / 10) * 10);
  const y = (v: number) => T + (1 - (v - yMin) / (100 - yMin)) * (H - T - B);

  const box = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": "Your level in each lesson. The same numbers are in the table below." });
  for (let v = yMin; v <= 100; v += 10) {
    box.append(svg("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), class: "grid" }),
      svg("text", { x: L - 6, y: y(v) + 4, class: "tick", "text-anchor": "end" }, String(v)));
  }
  const counted = lessons.map((s, i) => ({ s, i })).filter(({ s }) => s.reliable);
  if (counted.length > 1) {
    box.append(svg("polyline", { points: counted.map(({ s, i }) => `${x(i)},${y(s.level)}`).join(" "), class: "level-line" }));
  }
  const every = Math.max(1, Math.ceil(n / 10));
  lessons.forEach((s, i) => {
    const g = svg("g", { class: s.reliable ? "point" : "point short" });
    g.append(svg("title", {}, `${dateOf(s.created_at)} · ${s.title} · level ${Math.round(s.level)}` +
      ` (likely ${Math.round(s.level_range[0])}–${Math.round(s.level_range[1])}) · ${s.judged} phrases judged` +
      (s.reliable ? "" : " · too short to count")));
    if (s.reliable) g.append(svg("line", { x1: x(i), x2: x(i), y1: y(s.level_range[0]), y2: y(s.level_range[1]), class: "whisker" }));
    g.append(svg("circle", { cx: x(i), cy: y(s.level), r: 5 }));
    g.addEventListener("click", () => (location.hash = `#lessons/${s.id}`));
    box.append(g);
    if (i % every === 0 || i === n - 1) {
      box.append(svg("text", { x: x(i), y: H - 10, class: "tick", "text-anchor": "middle" }, shortDate(s.created_at)));
    }
  });

  // how much you spoke, on the same lesson axis
  const SH = 70;
  const most = Math.max(...lessons.map((s) => s.speaking_s), 60);
  const bars = svg("svg", { viewBox: `0 0 ${W} ${SH}`, role: "img", "aria-label": "Minutes you spoke in each lesson." });
  const bw = Math.min(24, (W - L - R) / Math.max(n, 1) * 0.6);
  lessons.forEach((s, i) => {
    const h = (s.speaking_s / most) * (SH - 18);
    bars.append(svg("rect", { x: x(i) - bw / 2, y: SH - 4 - h, width: bw, height: Math.max(h, 1),
      class: s.reliable ? "bar" : "bar short" }));
  });
  bars.append(svg("text", { x: L - 6, y: 12, class: "tick", "text-anchor": "end" }, `${Math.round(most / 60)}m`));

  const legend = el("div", { class: "legend" },
    el("span", { class: "key counted" }, "counted lesson (line: likely range)"),
    el("span", { class: "key short" }, "too short to count"));
  return el("figure", { class: "chart progress-chart" }, legend, box,
    el("figcaption", { class: "muted" }, "Minutes you spoke in each lesson"), bars, table(lessons));
}

function pct(c: number, n: number): string {
  return n ? `${Math.round((100 * c) / n)} % (${c}/${n})` : "—";
}

function table(lessons: ProgressLesson[]): HTMLElement {
  const t = el("table", {},
    el("thead", {}, el("tr", {}, ...["Lesson", "Level", "Likely range", "Correct", "Judged phrases", "You spoke", "Counted"]
      .map((h) => el("th", {}, h)))));
  const body = el("tbody");
  for (const s of [...lessons].reverse()) {
    body.append(el("tr", {},
      el("td", {}, el("a", { href: `#lessons/${s.id}` }, `${shortDate(s.created_at)} · ${s.title}`)),
      el("td", {}, String(Math.round(s.level))),
      el("td", {}, `${Math.round(s.level_range[0])}–${Math.round(s.level_range[1])}`),
      el("td", {}, s.accuracy === null ? "—" : `${Math.round(s.accuracy * 100)} %`),
      el("td", {}, String(s.judged)),
      el("td", {}, minutes(s.speaking_s)),
      el("td", {}, s.reliable ? "yes" : "no, too short")));
  }
  t.append(body);
  return el("details", {}, el("summary", {}, "Show as table"), t);
}

function words(title: string, intro: string, empty: string, list: WordProgress[], fixed = false): HTMLElement {
  const box = el("section", { class: "word-list" }, el("h3", {}, title), el("p", { class: "muted" }, intro));
  if (!list.length) {
    box.append(el("p", { class: "muted" }, empty));
    return box;
  }
  const ul = el("ul");
  for (const w of list) {
    const o = w.last_wrong;
    const what = fixed
      ? `wrong ${w.wrong} time${w.wrong === 1 ? "" : "s"} before, right since`
      : `wrong ${w.wrong} of ${w.total} times, in ${w.lessons} lesson${w.lessons === 1 ? "" : "s"}`;
    ul.append(el("li", {},
      el("span", { lang: "ja", class: "word" }, `${w.lemma}（${w.reading}）`), ` — ${what} · `,
      el("a", { href: `#lessons/${o.lesson}/${o.utterance}/${o.phrase}` }, fixed ? "last mistake" : "latest mistake")));
  }
  box.append(ul);
  return box;
}

function kinds(lessons: ProgressLesson[]): HTMLElement {
  const KINDS = ["flat for accented", "accented for flat", "1 mora off", "2+ moras off"];
  const t = el("table", {},
    el("thead", {}, el("tr", {}, ...["Lesson", "Flat phrases right", "Accented phrases right", "Said flat instead of a drop",
      "Added a drop to a flat word", "Drop 1 mora off", "Drop 2+ moras off"].map((h) => el("th", {}, h)))));
  const body = el("tbody");
  for (const s of [...lessons].reverse()) {
    body.append(el("tr", {},
      el("td", {}, `${shortDate(s.created_at)} · ${s.title}`),
      el("td", {}, pct(s.by_type.flat.correct, s.by_type.flat.judged)),
      el("td", {}, pct(s.by_type.accented.correct, s.by_type.accented.judged)),
      ...KINDS.map((k) => el("td", {}, String(s.kinds[k] ?? 0)))));
  }
  t.append(body);
  return el("details", { class: "kinds" }, el("summary", {}, "By kind of mistake"),
    el("p", { class: "muted" }, "Which accents give you trouble: flat (平板) words or words with a drop, and what the mistake was."), t);
}

export async function showProgress(): Promise<void> {
  const host = document.getElementById("progress-view")!;
  let p: Progress;
  try {
    p = await api.progress();
  } catch {
    host.replaceChildren(el("p", { class: "muted" }, "Can't reach Platina. Is it running? Start it with ./start.sh."));
    return;
  }
  if (!p.lessons.length) {
    host.replaceChildren(el("p", {}, "No lessons yet. Record your first one in ", el("a", { href: "#lessons" }, "Lessons"), "."),
      el("p", { class: "muted" },
        `A lesson counts in your progress once Platina could judge at least ${p.min_judged} of your phrases ` +
        `and you spoke for ${Math.round(p.min_speaking_s / 60)} minutes or more.`));
    return;
  }
  host.replaceChildren(headline(p));
  if (p.outdated) {
    const again = el("button", { type: "button", class: "secondary" }, "Re-check them");
    again.addEventListener("click", async () => {
      again.disabled = true;
      const n = await api.reanalyzeLessons();
      again.replaceWith(el("span", {}, `${n} lesson${n === 1 ? "" : "s"} queued. Progress updates when they're done.`));
    });
    host.append(el("p", { class: "note" },
      `${p.outdated} lesson${p.outdated === 1 ? " was" : "s were"} analyzed with older NHK accents or an older model, ` +
      "so they aren't fully comparable. ", again));
  }
  host.append(
    el("h3", {}, "Level per lesson"),
    chart(p.lessons),
    el("div", { class: "word-columns" },
      words("Words to work on", "Wrong in two or more lessons, or three or more times.",
        "Nothing yet. Words you keep getting wrong show up here.", p.work_on),
      words("Fixed", "Words you used to get wrong and have said right three times in a row since.",
        "Nothing yet. Keep going!", p.fixed, true)),
    kinds(p.lessons),
    el("details", { class: "explain" }, el("summary", {}, "How is the level worked out?"),
      el("p", {}, "Each lesson's level is the lowest value your share of correctly accented phrases is likely to be. " +
        "It grows with how much you said: two correct phrases give about 42, 19 of 20 about 80, 285 of 300 about 92. " +
        "So staying quiet can't score high, and speaking a lot only helps when the accents are right. " +
        "Only phrases Platina could judge count. Unclear phrases and words whose dictionary accent is unsure don't count either way.")),
  );
}
