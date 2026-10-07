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
  lesson?: string; // cut the clip from this lesson's audio (no upload)
  text: string;
  phrase_index: number;
  said: number | null;
  start?: number;
  end?: number;
  verdict?: string | null;
}

export async function addLabel(audio: Blob | null, meta: LabelMeta): Promise<LabelStats> {
  const form = new FormData();
  if (audio) form.append("audio", audio, "recording");
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

// --- lessons: a whole class recorded, analyzed afterwards -----------------------

export interface Occurrence {
  utterance: number;
  phrase: number;
  start: number;
  end: number;
}

export interface MistakeItem extends Occurrence {
  text: string;
  moras: string[];
  accent: number;
  said: number;
  score: number;
}

export interface RepeatedMistake {
  text: string;
  moras: string[];
  accent: number;
  said: number;
  count: number;
  occurrences: Occurrence[];
}

export interface TypeCount {
  correct: number;
  judged: number;
}

export interface LessonSummary {
  speaking_s: number;
  utterances: number;
  counts: Partial<Record<Status, number>>;
  judged: number;
  correct: number;
  mistakes: number;
  accuracy: number | null;
  level: number;
  level_range: [number, number];
  reliable: boolean;
  by_type: { flat: TypeCount; accented: TypeCount };
  kinds: Record<string, number>;
  obvious: MistakeItem[];
  repeated: RepeatedMistake[];
}

export type LessonStatus = "recording" | "queued" | "processing" | "done" | "failed";

export interface Lesson {
  id: string;
  created_at: number;
  title: string;
  status: LessonStatus;
  done: number;
  total: number;
  duration: number | null;
  error: string | null;
  summary: LessonSummary | null;
  outdated: boolean;
}

export interface LessonUtterance {
  idx: number;
  start: number;
  end: number;
  text: string;
  edited: boolean;
  skipped: string | null;
  result: { text: string; phrases: AnalyzedPhrase[] } | null;
}

export interface LessonDetail extends Lesson {
  utterances: LessonUtterance[];
}

export async function createLesson(title = ""): Promise<string> {
  return (await check<{ id: string }>(await post("/api/lessons", { title }))).id;
}

/** One recorded piece; resolves to how many pieces the server has. */
export async function sendLessonChunk(id: string, seq: number, piece: Blob): Promise<number> {
  const res = await fetch(`/api/lessons/${id}/chunk?seq=${seq}`, { method: "POST", body: piece });
  return (await check<{ saved: number }>(res)).saved;
}

export async function finishLesson(id: string): Promise<void> {
  await check(await fetch(`/api/lessons/${id}/finish`, { method: "POST" }));
}

export async function uploadLesson(file: File): Promise<string> {
  const form = new FormData();
  form.append("audio", file, file.name);
  return (await check<{ id: string }>(await fetch("/api/lessons/upload", { method: "POST", body: form }))).id;
}

export async function listLessons(): Promise<Lesson[]> {
  return check(await fetch("/api/lessons"));
}

export async function getLesson(id: string): Promise<LessonDetail> {
  return check(await fetch(`/api/lessons/${id}`));
}

export function lessonAudioUrl(id: string): string {
  return `/api/lessons/${id}/audio`;
}

export async function renameLesson(id: string, title: string): Promise<void> {
  await check(await fetch(`/api/lessons/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  }));
}

export async function deleteLesson(id: string): Promise<void> {
  await check(await fetch(`/api/lessons/${id}`, { method: "DELETE" }));
}

export async function retryLesson(id: string): Promise<void> {
  await check(await fetch(`/api/lessons/${id}/retry`, { method: "POST" }));
}

export async function fixLessonLine(id: string, idx: number, text: string):
    Promise<{ utterance: LessonUtterance; summary: LessonSummary }> {
  return check(await fetch(`/api/lessons/${id}/utterances/${idx}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  }));
}

export async function reanalyzeLessons(): Promise<number> {
  return (await check<{ queued: number }>(await fetch("/api/lessons/reanalyze", { method: "POST" }))).queued;
}

// --- progress across lessons ---------------------------------------------------------

export interface ProgressLesson {
  id: string;
  title: string;
  created_at: number;
  level: number;
  level_range: [number, number];
  accuracy: number | null;
  judged: number;
  speaking_s: number;
  reliable: boolean;
  by_type: { flat: TypeCount; accented: TypeCount };
  kinds: Record<string, number>;
  outdated: boolean;
}

export interface WordProgress {
  lemma: string;
  reading: string;
  wrong: number;
  total: number;
  lessons: number;
  last_wrong: Occurrence & { lesson: string; text: string };
}

export interface Progress {
  lessons: ProgressLesson[];
  current_level: number | null;
  change: number | null;
  speaking_s: number;
  reliable_lessons: number;
  min_judged: number;
  min_speaking_s: number;
  work_on: WordProgress[];
  fixed: WordProgress[];
  outdated: number;
}

export async function progress(): Promise<Progress> {
  return check(await fetch("/api/progress"));
}
