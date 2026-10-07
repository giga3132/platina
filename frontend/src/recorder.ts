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

/** Plays one time range of a recording (a blob, or a URL the server streams). */
export class Clip {
  private audio = new Audio();
  private timer?: number;

  constructor(source: Blob | string) {
    this.audio.src = typeof source === "string" ? source : URL.createObjectURL(source);
    this.audio.preload = "metadata";
  }

  play(start: number, end: number): void {
    window.clearTimeout(this.timer);
    const go = () => {
      this.audio.currentTime = Math.max(0, start - 0.05);
      void this.audio.play();
      this.timer = window.setTimeout(() => this.audio.pause(), (end - start + 0.15) * 1000);
    };
    // a streamed file can only be seeked once its metadata is in
    if (this.audio.readyState >= HTMLMediaElement.HAVE_METADATA) go();
    else this.audio.addEventListener("loadedmetadata", go, { once: true });
  }

  dispose(): void {
    this.audio.pause();
    if (this.audio.src.startsWith("blob:")) URL.revokeObjectURL(this.audio.src);
  }
}
