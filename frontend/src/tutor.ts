// Tutor voice buttons: play Platina's expected accent through VOICEVOX.
// The first 503 (engine not running) disables every tutor button with an
// explanation instead of failing on each click.

import { TutorUnavailable } from "./api";
import { el } from "./render";

let current: HTMLAudioElement | undefined;
let unavailable: string | undefined;
const buttons = new Set<HTMLButtonElement>();

function disable(b: HTMLButtonElement): void {
  b.disabled = true;
  b.title = `Tutor voice unavailable — ${unavailable}`;
}

export function tutorButton(label: string, fetchAudio: () => Promise<Blob>, title = "Hear the expected accent"): HTMLButtonElement {
  const b = el("button", { type: "button", class: "secondary tutor", title }, label);
  if (unavailable) disable(b);
  buttons.add(b);
  b.addEventListener("click", async () => {
    current?.pause();
    b.classList.add("busy");
    try {
      const url = URL.createObjectURL(await fetchAudio());
      current = new Audio(url);
      current.addEventListener("ended", () => URL.revokeObjectURL(url), { once: true });
      await current.play();
    } catch (e) {
      if (e instanceof TutorUnavailable) {
        unavailable = e.message;
        buttons.forEach((x) => (x.isConnected ? disable(x) : buttons.delete(x)));
      } else {
        b.title = `Couldn't play: ${(e as Error).message}`;
      }
    } finally {
      b.classList.remove("busy");
    }
  });
  return b;
}
