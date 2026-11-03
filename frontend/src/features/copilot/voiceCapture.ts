/** Browser-side utterance capture for Muse Voice Transcribe.
 *
 * The one-shot endpoint reads whole WAV clips, so the browser owns the
 * microphone: it records one utterance, endpoints it on silence, encodes
 * mono 16-bit PCM WAV at 16 kHz, and uploads it for transcription.
 * Silence endpointing replaces the Web Speech API's interim results —
 * there are no partial transcripts, only finished utterances.
 */

export interface VadConfig {
  /** RMS energy at or above this counts as speech. */
  threshold: number;
  /** Speech must persist this long before the utterance starts. */
  onsetMs: number;
  /** The utterance ends after this much silence. */
  silenceMs: number;
  /** Silence only ends an utterance with at least this much speech. */
  minSpeechMs: number;
  /** Hard cap on one utterance. */
  maxMs: number;
}

export const DEFAULT_VAD: VadConfig = {
  threshold: 0.015,
  onsetMs: 120,
  silenceMs: 1200,
  minSpeechMs: 350,
  maxMs: 30000,
};

export interface VadState {
  phase: "waiting" | "speech";
  /** Milliseconds of continuous energy while waiting. */
  onsetMs: number;
  /** Milliseconds of speech in the utterance so far. */
  speechMs: number;
  /** Milliseconds of continuous silence during speech. */
  silenceMs: number;
  /** Milliseconds since capture started. */
  elapsedMs: number;
}

export type VadEvent = "speech-start" | "utterance-end" | null;

export function initialVadState(): VadState {
  return { phase: "waiting", onsetMs: 0, speechMs: 0, silenceMs: 0, elapsedMs: 0 };
}

/** Fold one RMS frame into the endpointing state machine. Pure: the
 *  capture loop feeds it audio frames; tests feed it numbers. */
export function updateVad(
  state: VadState,
  rms: number,
  dtMs: number,
  config: VadConfig,
): { state: VadState; event: VadEvent } {
  const next: VadState = { ...state, elapsedMs: state.elapsedMs + dtMs };
  if (next.elapsedMs >= config.maxMs) {
    return { state: next, event: state.phase === "speech" ? "utterance-end" : null };
  }
  const loud = rms >= config.threshold;
  if (next.phase === "waiting") {
    next.onsetMs = loud ? next.onsetMs + dtMs : 0;
    if (next.onsetMs >= config.onsetMs) {
      next.phase = "speech";
      next.speechMs = next.onsetMs;
      next.silenceMs = 0;
      return { state: next, event: "speech-start" };
    }
    return { state: next, event: null };
  }
  if (loud) {
    next.speechMs += dtMs;
    next.silenceMs = 0;
    return { state: next, event: null };
  }
  next.silenceMs += dtMs;
  if (next.silenceMs >= config.silenceMs && next.speechMs >= config.minSpeechMs) {
    return { state: next, event: "utterance-end" };
  }
  return { state: next, event: null };
}

/** Root-mean-square energy of one mono frame. */
export function frameRms(frame: ArrayLike<number>): number {
  if (frame.length === 0) return 0;
  let sum = 0;
  for (let i = 0; i < frame.length; i += 1) {
    const sample = frame[i];
    sum += sample * sample;
  }
  return Math.sqrt(sum / frame.length);
}

/** Linear-resample mono float samples to a new rate. */
export function resampleMono(samples: Float32Array, fromRate: number, toRate: number): Float32Array {
  if (samples.length === 0 || fromRate === toRate) return samples.slice();
  const ratio = toRate / fromRate;
  const outLength = Math.max(1, Math.round(samples.length * ratio));
  const out = new Float32Array(outLength);
  for (let i = 0; i < outLength; i += 1) {
    const position = i / ratio;
    const before = Math.floor(position);
    const after = Math.min(before + 1, samples.length - 1);
    const fraction = position - before;
    out[i] = samples[before] * (1 - fraction) + samples[after] * fraction;
  }
  return out;
}

function writeAscii(view: DataView, offset: number, text: string): void {
  for (let i = 0; i < text.length; i += 1) view.setUint8(offset + i, text.charCodeAt(i));
}

/** Encode mono float samples (-1..1) as 16-bit PCM WAV bytes. */
export function encodeWavPcm16(samples: Float32Array, sampleRate: number): ArrayBuffer {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  writeAscii(view, 0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeAscii(view, 8, "WAVE");
  writeAscii(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeAscii(view, 36, "data");
  view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i += 1) {
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, clamped < 0 ? Math.round(clamped * 32768) : Math.round(clamped * 32767), true);
  }
  return buffer;
}

export interface CaptureOptions {
  /** First speech energy: the agent uses it for barge-in. */
  onSpeechStart?: () => void;
  vad?: Partial<VadConfig>;
  /** Target sample rate for the resolved samples (the endpoint's native rate). */
  targetRate?: number;
}

export interface UtteranceCapture {
  /** Resolves with 16 kHz mono samples — empty when nothing was said. */
  done: Promise<Float32Array>;
  /** Finish now with whatever was captured. */
  stop: () => void;
  /** Abandon the capture; done rejects. */
  cancel: () => void;
}

const CAPTURE_RATE = 16000;

/** Record one utterance from a live mic stream, ending on silence.
 *  The caller owns the stream (acquire/release); this owns the decode
 *  graph only. Never rejects except through cancel(). */
export function captureUtterance(stream: MediaStream, options: CaptureOptions = {}): UtteranceCapture {
  const config: VadConfig = { ...DEFAULT_VAD, ...options.vad };
  const targetRate = options.targetRate ?? CAPTURE_RATE;
  const context = new AudioContext({ sampleRate: targetRate });
  const source = context.createMediaStreamSource(stream);
  // ScriptProcessor is legacy but needs no worklet bundle; the graph is
  // short-lived (one utterance) so its quirks stay contained.
  const processor = context.createScriptProcessor(4096, 1, 1);
  const mute = context.createGain();
  mute.gain.value = 0;
  source.connect(processor);
  processor.connect(mute);
  mute.connect(context.destination);

  const chunks: Float32Array[] = [];
  let total = 0;
  let vad = initialVadState();
  let settled = false;
  let resolveDone: (samples: Float32Array) => void = () => {};
  let rejectDone: (error: Error) => void = () => {};
  const done = new Promise<Float32Array>((resolve, reject) => {
    resolveDone = resolve;
    rejectDone = reject;
  });

  function teardown(): void {
    try {
      processor.disconnect();
      source.disconnect();
      mute.disconnect();
    } catch {
      // Already torn down; finishing twice must stay silent.
    }
    void context.close().catch(() => {});
  }

  function finish(): void {
    if (settled) return;
    settled = true;
    teardown();
    const merged = new Float32Array(total);
    let offset = 0;
    for (const chunk of chunks) {
      merged.set(chunk, offset);
      offset += chunk.length;
    }
    // Only speech reaches the transcript: leading silence never does.
    const speech = vad.phase === "speech" ? merged : new Float32Array(0);
    if (context.sampleRate === targetRate) {
      resolveDone(speech);
      return;
    }
    resolveDone(resampleMono(speech, context.sampleRate, targetRate));
  }

  processor.onaudioprocess = (event) => {
    if (settled) return;
    const input = event.inputBuffer.getChannelData(0);
    const frame = new Float32Array(input);
    const dtMs = (frame.length / context.sampleRate) * 1000;
    const step = updateVad(vad, frameRms(frame), dtMs, config);
    vad = step.state;
    if (step.event === "speech-start") options.onSpeechStart?.();
    if (vad.phase === "speech") {
      chunks.push(frame);
      total += frame.length;
    }
    if (step.event === "utterance-end") finish();
  };

  return {
    done,
    stop: finish,
    cancel: () => {
      if (settled) return;
      settled = true;
      teardown();
      rejectDone(new Error("Voice capture was cancelled."));
    },
  };
}

/** Whether this browser can capture mic audio for transcription. */
export function captureSupported(): boolean {
  if (typeof window === "undefined" || typeof navigator === "undefined") return false;
  const w = window as unknown as Record<string, unknown>;
  return (
    typeof AudioContext !== "undefined" &&
    typeof w.MediaStream !== "undefined" &&
    typeof navigator.mediaDevices?.getUserMedia === "function"
  );
}
