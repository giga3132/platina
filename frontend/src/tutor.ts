// Tutor voice buttons: play Platina's expected accent through VOICEVOX.
// The first 503 (engine not running) disables every tutor button with an
// explanation instead of failing on each click.

import { TutorUnavailable } from "./api";
import { tr } from "./i18n";
import { btn } from "./render";

let current: HTMLAudioElement | undefined;
let unavailable: string | undefined;
const buttons = new Set<HTMLButtonElement>();

function disable(b: HTMLButtonElement): void {
  b.disabled = true;
  b.title = tr().tutorUnavailable(unavailable ?? "");
}

export function tutorButton(label: string, fetchAudio: () => Promise<Blob>, title = tr().hearExpected): HTMLButtonElement {
  const b = btn(label.replace(/^▶\s*/, ""), { play: true, title });
  b.classList.add("tutor");
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
        b.title = tr().couldntPlay((e as Error).message);
      }
    } finally {
      b.classList.remove("busy");
    }
  });
  return b;
}
