// Microphone recording. Browser voice processing is switched off: noise
// suppression and auto gain distort the pitch contour we want to measure.

export class Recorder {
  private media?: MediaRecorder;
  private chunks: Blob[] = [];
  private stream?: MediaStream;
  startedAt = 0;

  get recording(): boolean {
    return this.media?.state === "recording";
  }

  async start(): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 },
    });
    this.chunks = [];
    this.media = new MediaRecorder(this.stream);
    this.media.ondataavailable = (e) => e.data.size && this.chunks.push(e.data);
    this.media.start(250);
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

/** Plays one time range of a recording. */
export class Clip {
  private audio = new Audio();
  private timer?: number;

  constructor(blob: Blob) {
    this.audio.src = URL.createObjectURL(blob);
  }

  play(start: number, end: number): void {
    window.clearTimeout(this.timer);
    this.audio.currentTime = Math.max(0, start - 0.05);
    void this.audio.play();
    this.timer = window.setTimeout(() => this.audio.pause(), (end - start + 0.15) * 1000);
  }

  dispose(): void {
    URL.revokeObjectURL(this.audio.src);
  }
}
