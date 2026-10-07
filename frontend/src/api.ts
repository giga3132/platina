// Types and calls for the Platina backend (proxied at /api by Vite).

export type Confidence = "nhk" | "agree" | "uncertain";
export type Status = "correct" | "error" | "uncertain" | "unverified";

export interface Word {
  surface: string;
  lemma: string;
  reading: string;
  pos: string;
  accents: number[];
  source: "override" | "unidic" | "none";
  n_moras: number;
}

export interface Phrase {
  start: number;
  end: number;
  text: string;
  moras: string[];
  accent: number;
  alternatives: number[];
  confidence: Confidence;
  notation: string;
  pitch: boolean[];
  words: Word[];
  reasons: string[];
  merge_accents: number[];
  native_variants: number[];
  proposed_variants: number[];
}

export interface AnalyzedPhrase extends Phrase {
  status: Status;
  unclear_reason: "no-pitch" | "unclear" | "alignment" | "native-variant" | null;
  said_as_one?: boolean;
  expected_contour?: number[][] | null;
  observed: number | null;
  observed_notation: string | null;
  p_expected: number | null;
  detect_confidence: number;
  mora_times: [number, number][];
  mora_pitch: (number | null)[];
}

export interface Utterance {
  start: number;
  end: number;
  text: string;
  phrases: AnalyzedPhrase[];
}

export interface AnalyzeResult {
  duration: number;
  utterances: Utterance[];
  summary: Partial<Record<Status, number>>;
}

export interface ExpectedResult {
  text: string;
  notation: string;
  phrases: Phrase[];
}

export interface Override {
  lemma: string;
  reading: string;
  accents: number[];
  note: string;
}

async function check<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${await res.text()}`);
  return res.json() as Promise<T>;
}

export async function analyze(audio: Blob, text?: string): Promise<AnalyzeResult> {
  const form = new FormData();
  form.append("audio", audio, "recording");
  if (text?.trim()) form.append("text", text.trim());
  return check(await fetch("/api/analyze", { method: "POST", body: form }));
}

export async function expected(text: string): Promise<ExpectedResult> {
  return check(
    await fetch("/api/expected", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    }),
  );
}

export async function listOverrides(): Promise<Override[]> {
  return check(await fetch("/api/overrides"));
}

export async function putOverride(o: Override): Promise<void> {
  await check(
    await fetch("/api/overrides", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(o),
    }),
  );
}

export async function deleteOverride(lemma: string, reading: string): Promise<void> {
  const q = new URLSearchParams({ lemma, reading });
  await check(await fetch(`/api/overrides?${q}`, { method: "DELETE" }));
}

export async function addGold(text: string, expected: string, note = ""): Promise<void> {
  await check(
    await fetch("/api/gold", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, expected, note }),
    }),
  );
}

// --- tutor voice (VOICEVOX, saying Platina's expected accent) ---------------

export class TutorUnavailable extends Error {}

async function audio(res: Response): Promise<Blob> {
  if (res.status === 503) throw new TutorUnavailable((await res.json()).detail);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${await res.text()}`);
  return res.blob();
}

function post(path: string, body: unknown): Promise<Response> {
  return fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function speak(text: string, speed = 1, accents?: Record<number, number>): Promise<Blob> {
  return audio(await post("/api/speak", { text, speed, accents }));
}

export async function speakPhrase(moras: string[], accent: number, speed = 1): Promise<Blob> {
  return audio(await post("/api/speak/phrase", { moras, accent, speed }));
}

export async function tutorCredit(): Promise<string> {
  return (await check<{ credit: string }>(await fetch("/api/speak/credit"))).credit;
}

// --- labelled recordings ------------------------------------------------------

export interface LabelStats {
  total: number;
  by_source: Record<string, number>;
  your_phrases: number;
  your_correct: number;
  your_mistakes: number;
  sessions: number;
}

export interface LabelMeta {
  source: "practice" | "report";
  text: string;
  phrase_index: number;
  said: number | null;
  start?: number;
  end?: number;
  verdict?: string | null;
}

export async function addLabel(audio: Blob, meta: LabelMeta): Promise<LabelStats> {
  const form = new FormData();
  form.append("audio", audio, "recording");
  form.append("meta", JSON.stringify(meta));
  return (await check<{ stats: LabelStats }>(await fetch("/api/labels", { method: "POST", body: form }))).stats;
}

export async function labelStats(): Promise<LabelStats> {
  return check(await fetch("/api/labels/stats"));
}

export interface PracticeItem {
  text: string;
  phrases: Phrase[];
  phrase_index: number;
  speak_index: number;
  target: number;
  kind: string;
}

export async function practiceNext(text?: string): Promise<PracticeItem> {
  const q = text ? `?${new URLSearchParams({ text })}` : "";
  return check(await fetch(`/api/practice/next${q}`));
}

export interface ReviewItem {
  id: string;
  text: string;
  spk: string;
  phrase: number;
  moras: string[];
  expected: number[];
  heard: number;
  heard_notation: string;
  start: number;
  end: number;
  remaining: number;
}

export async function reviewNext(): Promise<ReviewItem | { remaining: 0 }> {
  return check(await fetch("/api/review/next"));
}

export async function reviewAnswer(id: string, answer: "variant" | "misheard" | "dictionary" | "unsure"): Promise<void> {
  await check(await post("/api/review", { id, answer }));
}

// --- native variants (tools/mine_variants.py) ------------------------------------

export interface Variant {
  key: string;
  accent: number;
  status: "proposed" | "approved" | "rejected";
  speakers: number;
  total: number;
  examples: string[];
}

export async function listVariants(): Promise<Variant[]> {
  return check(await fetch("/api/variants"));
}

export async function setVariant(key: string, accent: number, status: Variant["status"]): Promise<void> {
  await check(await fetch("/api/variants", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, accent, status }),
  }));
}
