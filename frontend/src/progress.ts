// Progress across lessons: your level over time (only lessons long enough to
// be reliable count), how much you spoke, and words that keep going wrong —
// or that you've fixed.

import * as api from "./api";
import type { Progress, ProgressLesson, WordProgress } from "./api";
import { locale, tr } from "./i18n";
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
  return new Date(ts * 1000).toLocaleDateString(locale(), { day: "numeric", month: "short" });
}

function headline(p: Progress): HTMLElement {
  const card = (value: string, label: string, note: string) =>
    el("div", { class: "stat" }, el("span", { class: "stat-value" }, value), el("span", { class: "stat-label" }, label),
      el("span", { class: "stat-note" }, note));
  const d = tr();
  const minMin = Math.round(p.min_speaking_s / 60);
  return el("div", { class: "stats" },
    card(p.current_level === null ? "—" : String(Math.round(p.current_level)), d.yourLevel,
      p.current_level === null ? d.levelAppears(p.min_judged, minMin) : d.levelAverage),
    card(p.change === null ? "—" : `${p.change >= 0 ? "+" : "−"}${Math.abs(Math.round(p.change))}`, d.change,
      p.change === null ? d.changeLater : d.changeSince),
    card(minutes(p.speaking_s), d.youveSpoken, d.inLessons(p.lessons.length)));
}

/** Level per lesson with its likely range; short lessons hollow and grey. */
function chart(lessons: ProgressLesson[]): HTMLElement {
  const d = tr();
  const W = 720, H = 240, L = 40, R = 16, T = 14, B = 30;
  const n = lessons.length;
  const x = (i: number) => (n === 1 ? (L + W - R) / 2 : L + (i / (n - 1)) * (W - L - R));
  const low = Math.min(...lessons.map((s) => s.level_range[0]));
  const yMin = Math.max(0, Math.floor((low - 5) / 10) * 10);
  const y = (v: number) => T + (1 - (v - yMin) / (100 - yMin)) * (H - T - B);

  const box = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": d.chartAria });
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
    g.append(svg("title", {}, d.pointTitle(dateOf(s.created_at), s.title, Math.round(s.level),
      Math.round(s.level_range[0]), Math.round(s.level_range[1]), s.judged, s.reliable)));
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
  const bars = svg("svg", { viewBox: `0 0 ${W} ${SH}`, role: "img", "aria-label": d.barsAria });
  const bw = Math.min(24, (W - L - R) / Math.max(n, 1) * 0.6);
  lessons.forEach((s, i) => {
    const h = (s.speaking_s / most) * (SH - 18);
    bars.append(svg("rect", { x: x(i) - bw / 2, y: SH - 4 - h, width: bw, height: Math.max(h, 1),
      class: s.reliable ? "bar" : "bar short" }));
  });
  bars.append(svg("text", { x: L - 6, y: 12, class: "tick", "text-anchor": "end" }, d.minutesShort(Math.round(most / 60))));

  const legend = el("div", { class: "legend" },
    el("span", { class: "key counted" }, d.countedKey),
    el("span", { class: "key short" }, d.tooShort));
  return el("figure", { class: "chart progress-chart" }, legend, box,
    el("figcaption", { class: "muted" }, d.spokeCaption), bars, table(lessons));
}

function pct(c: number, n: number): string {
  return n ? `${Math.round((100 * c) / n)} % (${c}/${n})` : "—";
}

function table(lessons: ProgressLesson[]): HTMLElement {
  const d = tr();
  const t = el("table", {},
    el("thead", {}, el("tr", {}, ...d.progressHeaders.map((h) => el("th", {}, h)))));
  const body = el("tbody");
  for (const s of [...lessons].reverse()) {
    body.append(el("tr", {},
      el("td", {}, el("a", { href: `#lessons/${s.id}` }, `${shortDate(s.created_at)} · ${s.title}`)),
      el("td", {}, String(Math.round(s.level))),
      el("td", {}, `${Math.round(s.level_range[0])}–${Math.round(s.level_range[1])}`),
      el("td", {}, s.accuracy === null ? "—" : `${Math.round(s.accuracy * 100)} %`),
      el("td", {}, String(s.judged)),
      el("td", {}, minutes(s.speaking_s)),
      el("td", {}, s.reliable ? d.yes : d.noTooShort)));
  }
  t.append(body);
  return el("details", {}, el("summary", {}, d.showTable), t);
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
    const what = fixed ? tr().wrongBefore(w.wrong) : tr().wrongOf(w.wrong, w.total, w.lessons);
    ul.append(el("li", {},
      el("span", { lang: "ja", class: "word" }, `${w.lemma}（${w.reading}）`), ` — ${what} · `,
      el("a", { href: `#lessons/${o.lesson}/${o.utterance}/${o.phrase}` }, fixed ? tr().lastMistake : tr().latestMistake)));
  }
  box.append(ul);
  return box;
}

function kinds(lessons: ProgressLesson[]): HTMLElement {
  const KINDS = ["flat for accented", "accented for flat", "1 mora off", "2+ moras off"];
  const d = tr();
  const t = el("table", {},
    el("thead", {}, el("tr", {}, ...d.kindHeaders.map((h) => el("th", {}, h)))));
  const body = el("tbody");
  for (const s of [...lessons].reverse()) {
    body.append(el("tr", {},
      el("td", {}, `${shortDate(s.created_at)} · ${s.title}`),
      el("td", {}, pct(s.by_type.flat.correct, s.by_type.flat.judged)),
      el("td", {}, pct(s.by_type.accented.correct, s.by_type.accented.judged)),
      ...KINDS.map((k) => el("td", {}, String(s.kinds[k] ?? 0)))));
  }
  t.append(body);
  return el("details", { class: "kinds" }, el("summary", {}, d.byKind), el("p", { class: "muted" }, d.byKindIntro), t);
}

export async function showProgress(): Promise<void> {
  const d = tr();
  const host = document.getElementById("progress-view")!;
  let p: Progress;
  try {
    p = await api.progress();
  } catch {
    host.replaceChildren(el("p", { class: "muted" }, d.cantReach));
    return;
  }
  if (!p.lessons.length) {
    host.replaceChildren(
      el("p", {}, d.noLessonsProgress[0], el("a", { href: "#lessons" }, d.tabLessons), d.noLessonsProgress[1]),
      el("p", { class: "muted" }, d.countsWhen(p.min_judged, Math.round(p.min_speaking_s / 60))));
    return;
  }
  host.replaceChildren(headline(p));
  if (p.outdated) {
    const again = el("button", { type: "button", class: "secondary" }, d.recheckThem);
    again.addEventListener("click", async () => {
      again.disabled = true;
      const n = await api.reanalyzeLessons();
      again.replaceWith(el("span", {}, d.queued(n)));
    });
    host.append(el("p", { class: "note" }, d.outdatedLessons(p.outdated), again));
  }
  host.append(
    el("h3", {}, d.levelPerLesson),
    chart(p.lessons),
    el("div", { class: "word-columns" },
      words(d.workOn, d.workOnIntro, d.workOnEmpty, p.work_on),
      words(d.fixed, d.fixedIntro, d.fixedEmpty, p.fixed, true)),
    kinds(p.lessons),
    el("details", { class: "explain" }, el("summary", {}, d.howLevel), el("p", {}, d.progressLevelExplain)),
  );
}
