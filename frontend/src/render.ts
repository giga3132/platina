// Annotated transcript: one chip per accent phrase, kana in ＼/━ notation,
// colored by verdict.

import type { AnalyzedPhrase, Phrase, Status } from "./api";

export const STATUS_LABEL: Record<Status, string> = {
  correct: "Correct",
  error: "Mistake",
  uncertain: "Unclear",
  unverified: "Check the dictionary",
};

export const CONFIDENCE_LABEL = {
  nhk: "checked by you in NHK",
  agree: "UniDic and OpenJTalk agree",
  uncertain: "dictionaries disagree / unknown — not counted as your mistake",
} as const;

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
    if (accent === i + 1) out.append(el("span", { class: "drop", "aria-label": "pitch drop" }, "＼"));
  });
  if (accent === 0) out.append(el("span", { class: "flat", "aria-label": "flat (heiban)" }, "━"));
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
  if ("status" in p) node.append(el("span", { class: "sr-only" }, `: ${STATUS_LABEL[p.status]}`));
  if ("status" in p && (p.status === "error" || p.status === "unverified") && p.observed !== null) {
    const heard = el("span", { class: "heard" }, "you: ");
    heard.append(notationNode(p, p.observed, p.accent));
    node.append(heard);
  }
  node.title = "status" in p ? STATUS_LABEL[p.status] : CONFIDENCE_LABEL[p.confidence];
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

/** Small inline action button (play, jump, edit…). `play` draws a ▶ icon in
 * CSS; with an empty label it is icon-only and `title` names it. */
export function btn(label: string, opts: { play?: boolean; quiet?: boolean; danger?: boolean; title?: string } = {}):
    HTMLButtonElement {
  const cls = ["btn-sm", opts.play && "play", opts.quiet && "quiet", opts.danger && "danger", !label && "icon"]
    .filter(Boolean).join(" ");
  const b = el("button", { type: "button", class: cls }, label);
  if (opts.title) {
    b.title = opts.title;
    if (!label) b.setAttribute("aria-label", opts.title);
  }
  return b;
}
