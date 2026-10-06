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
}

export interface AnalyzedPhrase extends Phrase {
  status: Status;
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
