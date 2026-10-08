// Annotated transcript: one chip per accent phrase, kana in ＼/━ notation,
// colored by verdict.

import type { AnalyzedPhrase, Confidence, Phrase, Status } from "./api";
import { tr } from "./i18n";

export const statusLabel = (s: Status): string => tr()[`status_${s}`];

export const confidenceLabel = (c: Confidence): string => tr()[`conf_${c}`];

export function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attrs: Record<string, string> = {},
  ...children: (Node | string)[]
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else node.setAttribute(k, v);
  }
  node.append(...children);
  return node;
}

/** ＼/━ notation, with moras that differ from `other` highlighted. */
export function notationNode(phrase: Pick<Phrase, "moras">, accent: number, diffWith?: number): HTMLElement {
  const out = el("span", { class: "notation" });
  const highs = pattern(phrase.moras.length, accent);
  const ref = diffWith === undefined ? null : pattern(phrase.moras.length, diffWith);
  phrase.moras.forEach((m, i) => {
    const span = el("span", { class: "mora" + (highs[i] ? " high" : "") }, m);
    if (ref && ref[i] !== highs[i]) span.classList.add("diff");
    out.append(span);
    if (accent === i + 1) out.append(el("span", { class: "drop", "aria-label": tr().pitchDrop }, "＼"));
  });
  if (accent === 0) out.append(el("span", { class: "flat", "aria-label": tr().flatAria }, "━"));
  return out;
}

export function pattern(n: number, accent: number): boolean[] {
  if (n === 0) return [];
  if (accent === 1) return [true, ...Array(n - 1).fill(false)];
  const end = accent === 0 ? n : accent;
  return Array.from({ length: n }, (_, i) => i > 0 && i < end);
}

function chip(p: Phrase | AnalyzedPhrase, onSelect: () => void): HTMLElement {
  const status: Status | "text" = "status" in p ? p.status : "text";
  const node = el("button", { class: `phrase s-${status} c-${p.confidence}`, type: "button" });
  node.append(el("span", { class: "surface" }, p.text));
  node.append(notationNode(p, p.accent));
  // the verdict in words, not only as a colour
  if ("status" in p) node.append(el("span", { class: "sr-only" }, `: ${statusLabel(p.status)}`));
  if ("status" in p && (p.status === "error" || p.status === "unverified") && p.observed !== null) {
    const heard = el("span", { class: "heard" }, tr().youColon);
    heard.append(notationNode(p, p.observed, p.accent));
    node.append(heard);
  }
  node.title = "status" in p ? statusLabel(p.status) : confidenceLabel(p.confidence);
  node.addEventListener("click", () => {
    document.querySelectorAll(".phrase.selected").forEach((n) => n.classList.remove("selected"));
    node.classList.add("selected");
    onSelect();
  });
  return node;
}

export function phraseRow<T extends Phrase>(phrases: T[], onSelect: (p: T) => void): HTMLElement {
  const row = el("div", { class: "phrases" });
  for (const p of phrases) row.append(chip(p, () => onSelect(p)));
  return row;
}

/** Small inline action button (play, jump, edit…). `play` and `icon` draw
 * an icon in CSS; with an empty label it is icon-only and `title` names it. */
export function btn(label: string,
    opts: { play?: boolean; quiet?: boolean; danger?: boolean; title?: string; icon?: "close" | "trash" } = {}):
    HTMLButtonElement {
  const cls = ["btn-sm", opts.play && "play", opts.quiet && "quiet", opts.danger && "danger", !label && "icon",
    opts.icon && `ico-${opts.icon}`].filter(Boolean).join(" ");
  const b = el("button", { type: "button", class: cls }, label);
  if (opts.title) {
    b.title = opts.title;
    if (!label) b.setAttribute("aria-label", opts.title);
  }
  return b;
}

/** How to read the marks: ＼, ━, red and grey. Lives in the help panels of
 * pages that show phrases. */
export function legend(): HTMLElement {
  const d = tr();
  return el("div", { class: "notation-key" },
    el("h3", {}, d.legendTitle),
    el("ul", {},
      el("li", {}, el("span", { class: "notation", lang: "ja" }, el("span", { class: "mora high" }, "ト"),
        el("span", { class: "drop" }, "＼")), " ", d.legendDrop),
      el("li", {}, el("span", { class: "notation" }, el("span", { class: "flat" }, "━")), " ", d.legendFlat),
      el("li", {}, el("span", { class: "sample s-error" }, d.legendRed), " ", d.legendRedText),
      el("li", {}, el("span", { class: "sample s-unverified" }, d.legendGrey), " ", d.legendGreyText)));
}

/** The ⓘ button of a page and its help panel (closed). main.ts toggles every
 * .help-btn through aria-controls. */
export function helpToggle(id: string, open: boolean, ...content: (Node | string)[]): [HTMLButtonElement, HTMLElement] {
  const label = tr().aboutPage;
  const b = el("button", { type: "button", class: "help-btn", "aria-expanded": String(open), "aria-controls": id,
    title: label, "aria-label": label });
  const panel = el("div", { id, class: "help-panel" }, ...content);
  panel.hidden = !open;
  return [b, panel];
}

/** Wires a segmented control: its buttons (data-view) show the matching
 * panel (data-panel) inside `scope` and hide the others. Returns show(view). */
export function segments(group: HTMLElement, scope: HTMLElement, onPick?: (view: string) => void):
    (view: string) => void {
  const show = (view: string) => {
    group.querySelectorAll<HTMLButtonElement>("button[data-view]").forEach((b) =>
      b.setAttribute("aria-pressed", String(b.dataset.view === view)));
    scope.querySelectorAll<HTMLElement>("[data-panel]").forEach((p) => (p.hidden = p.dataset.panel !== view));
  };
  group.addEventListener("click", (e) => {
    const b = (e.target as HTMLElement).closest<HTMLButtonElement>("button[data-view]");
    if (!b) return;
    show(b.dataset.view!);
    onPick?.(b.dataset.view!);
  });
  return show;
}
