// Microphone recording. Browser voice processing is switched off: noise
// suppression and auto gain distort the pitch contour we want to measure.

export class Recorder {
  private media?: MediaRecorder;
  private chunks: Blob[] = [];
  stream?: MediaStream;
  startedAt = 0;

  get recording(): boolean {
    return this.media?.state === "recording";
  }

  /** With `onPiece`, every `sliceMs` of audio is handed over as it is
   * recorded (long recordings: nothing piles up in memory) and stop()
   * resolves to an empty blob. */
  async start(onPiece?: (piece: Blob) => void, sliceMs = 250): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 },
    });
    this.chunks = [];
    this.media = new MediaRecorder(this.stream);
    this.media.ondataavailable = (e) => {
      if (!e.data.size) return;
      if (onPiece) onPiece(e.data);
      else this.chunks.push(e.data);
    };
    this.media.start(sliceMs);
    this.startedAt = performance.now();
  }

  stop(): Promise<Blob> {
    return new Promise((resolve) => {
      const media = this.media!;
      media.onstop = () => {
        this.stream?.getTracks().forEach((t) => t.stop());
        resolve(new Blob(this.chunks, { type: media.mimeType }));
      };
      media.stop();
    });
  }
}

/** Plays one time range of a recording (a blob, or a URL the server streams).
 * Playback stops by watching the actual position, not a timer: a timer
 * started before the seek and buffering finish cuts short words off. */
export class Clip {
  private audio = new Audio();
  private stopAt = 0;
  private raf = 0;
  private token = 0;

  constructor(source: Blob | string) {
    this.audio.src = typeof source === "string" ? source : URL.createObjectURL(source);
    this.audio.preload = "auto";
    // backup for background tabs, where animation frames pause
    this.audio.addEventListener("timeupdate", () => {
      if (this.audio.currentTime >= this.stopAt) this.audio.pause();
    });
  }

  /** `before`/`after`: extra audio around the range (aligned word edges are tight). */
  play(start: number, end: number, before = 0.2, after = 0.4): void {
    const token = ++this.token;
    cancelAnimationFrame(this.raf);
    this.audio.pause();
    const from = Math.max(0, start - before);
    this.stopAt = end + after;
    const begin = () => {
      if (token !== this.token) return; // another clip was asked for meanwhile
      void this.audio.play().then(() => this.watch(token));
    };
    const seek = () => {
      if (token !== this.token) return;
      if (Math.abs(this.audio.currentTime - from) < 0.005) return begin();
      this.audio.addEventListener("seeked", begin, { once: true });
      this.audio.currentTime = from;
    };
    // a streamed file can only be seeked once its metadata is in
    if (this.audio.readyState >= HTMLMediaElement.HAVE_METADATA) seek();
    else this.audio.addEventListener("loadedmetadata", seek, { once: true });
  }

  private watch(token: number): void {
    const tick = () => {
      if (token !== this.token || this.audio.paused) return;
      if (this.audio.currentTime >= this.stopAt) {
        this.audio.pause();
        return;
      }
      this.raf = requestAnimationFrame(tick);
    };
    this.raf = requestAnimationFrame(tick);
  }

  dispose(): void {
    this.token++;
    cancelAnimationFrame(this.raf);
    this.audio.pause();
    if (this.audio.src.startsWith("blob:")) URL.revokeObjectURL(this.audio.src);
  }
}
