import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../lib/api.ts";
import {
  captureSupported,
  captureUtterance,
  encodeWavPcm16,
  type UtteranceCapture,
} from "./voiceCapture.ts";

/** Minimal speech-synthesis shapes (DOM libs vary). */
interface UtteranceLike {
  text: string;
  voice: unknown;
  rate: number;
  onend: (() => void) | null;
  onerror: (() => void) | null;
}

type UtteranceCtor = new (text: string) => UtteranceLike;

interface SynthesisVoiceLike {
  name: string;
  lang: string;
}

interface SynthesisLike {
  speak: (utterance: UtteranceLike) => void;
  cancel: () => void;
  getVoices: () => SynthesisVoiceLike[];
}

function synthesis(): { synth: SynthesisLike; Utterance: UtteranceCtor } | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    speechSynthesis?: SynthesisLike;
    SpeechSynthesisUtterance?: UtteranceCtor;
  };
  if (!w.speechSynthesis || !w.SpeechSynthesisUtterance) return null;
  return { synth: w.speechSynthesis, Utterance: w.SpeechSynthesisUtterance };
}

/** Prefer a lively neural voice, fall back to any English voice. */
function pickVoice(synth: SynthesisLike): SynthesisVoiceLike | null {
  const voices = synth.getVoices();
  return (
    voices.find(
      (voice) => /neural|natural|premium/i.test(voice.name) && voice.lang.startsWith("en"),
    ) ??
    voices.find((voice) => /google us english|samantha/i.test(voice.name)) ??
    voices.find((voice) => voice.lang.startsWith("en")) ??
    null
  );
}

/** Split spoken text into sentence-sized utterances. */
export function splitUtterances(text: string): string[] {
  const sentences = text.match(/[^.!?…]+[.!?…]+|[^.!?…]+$/g) ?? [];
  const out: string[] = [];
  for (const sentence of sentences) {
    const trimmed = sentence.trim();
    if (trimmed === "") continue;
    if (trimmed.length <= 240) {
      out.push(trimmed);
      continue;
    }
    const parts = trimmed.split(/[,;:]\s+/);
    const wordSplit = parts.some((part) => part.length > 240);
    const pieces = wordSplit ? trimmed.split(/\s+/) : parts;
    const joiner = wordSplit ? " " : ", ";
    let current = "";
    for (const part of pieces) {
      const next = current === "" ? part : `${current}${joiner}${part}`;
      if (next.length > 240 && current !== "") {
        out.push(current);
        current = part;
      } else {
        current = next;
      }
    }
    if (current !== "") out.push(current);
  }
  return out;
}

export type VoiceAgentState = "idle" | "listening" | "thinking" | "speaking";

export interface VoiceAgentScope {
  projectId: string;
  graphId: string;
}

export interface VoiceAgentCallbacks {
  /** A final user transcript: the caller asks and later calls speak(). */
  onUserTurn: (transcript: string) => void;
  /** The user started talking over the agent's speech. */
  onInterrupted?: () => void;
  /** The voice loop died with a fatal error. */
  onError?: (message: string) => void;
}

/** After speech ends, trailing echo transcripts are still filtered briefly. */
const ECHO_TAIL_MS = 1200;

function normalizeEchoText(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Whether a final transcript is the speaker feeding back into the mic:
 * it matches (or is mostly covered by) recently spoken agent text.
 * Real interruptions use different words, so they pass through.
 */
export function isEchoTranscript(transcript: string, spoken: readonly string[]): boolean {
  const clean = normalizeEchoText(transcript);
  if (clean === "") return false;
  const words = clean.split(" ");
  for (const utterance of spoken) {
    const said = normalizeEchoText(utterance);
    if (said === "") continue;
    if (said.includes(clean) || clean.includes(said)) return true;
    const saidWords = new Set(said.split(" "));
    const overlap = words.filter((word) => saidWords.has(word)).length;
    if (overlap / words.length >= 0.6) return true;
  }
  return false;
}

function release(stream: MediaStream | null): void {
  if (!stream) return;
  for (const track of stream.getTracks()) track.stop();
}

/**
 * A full-duplex voice conversation loop on Muse Voice Transcribe: the
 * mic records utterances, silence ends them, the server transcribes
 * each clip, the caller answers via speak(), and the user barges in
 * by talking over it. Capture restarts itself so the conversation
 * continues until stop() or unmount.
 */
export function useVoiceAgent(lang: string, scope: VoiceAgentScope, callbacks: VoiceAgentCallbacks) {
  const [state, setState] = useState<VoiceAgentState>("idle");
  const [error, setError] = useState<string | null>(null);
  const activeRef = useRef(false);
  const stateRef = useRef<VoiceAgentState>("idle");
  const streamRef = useRef<MediaStream | null>(null);
  const captureRef = useRef<UtteranceCapture | null>(null);
  const callbacksRef = useRef(callbacks);
  const scopeRef = useRef(scope);
  const langRef = useRef(lang);
  const speakQueueRef = useRef<string[]>([]);
  const speakDoneRef = useRef<(() => void) | null>(null);
  const speechEndRef = useRef(0);
  const spokenRef = useRef<string[]>([]);
  const runRef = useRef(0);

  useEffect(() => {
    callbacksRef.current = callbacks;
  });

  useEffect(() => {
    scopeRef.current = scope;
    langRef.current = lang;
  });

  function setBoth(next: VoiceAgentState): void {
    stateRef.current = next;
    setState(next);
  }

  // Stop talking now: the barge-in transcript below forces its way
  // in even though the turn moved through "thinking" first.
  const interruptForced = useCallback(() => {
    synthesis()?.synth.cancel();
    runRef.current += 1;
    speakQueueRef.current = [];
    speakDoneRef.current = null;
    // A barge-in's own transcript must never be echo-filtered.
    speechEndRef.current = 0;
    setBoth("listening");
    callbacksRef.current.onInterrupted?.();
  }, []);

  const interrupt = useCallback(() => {
    if (stateRef.current !== "speaking") return;
    interruptForced();
  }, [interruptForced]);

  const listen = useCallback(() => {
    const stream = streamRef.current;
    if (!activeRef.current || !stream) return;
    // One capture at a time: a stale one is orphaned (its completion is
    // ignored below) and cancelled so its decode graph is released.
    captureRef.current?.cancel();
    const capture = captureUtterance(stream);
    captureRef.current = capture;
    void capture.done.then(
      (samples) => {
        if (captureRef.current !== capture || !activeRef.current) return;
        captureRef.current = null;
        // Snapshot the overlap at capture end: transcription lands
        // later, after the turn has moved through "thinking".
        const overlapped = stateRef.current === "speaking";
        if (samples.length === 0) {
          setBoth(overlapped ? "speaking" : "listening");
          listen();
          return;
        }
        setBoth("thinking");
        const clip = new Blob([encodeWavPcm16(samples, 16000)], { type: "audio/wav" });
        const { projectId, graphId } = scopeRef.current;
        const language = langRef.current.split("-")[0] || langRef.current;
        api
          .transcribeVoice(projectId, graphId, clip, language)
          .then((result) => {
            if (!activeRef.current) return;
            const transcript = result.transcript.trim();
            if (transcript === "") {
              // Sub-second turns transcribe empty: keep listening.
              setBoth(overlapped ? "speaking" : "listening");
              listen();
              return;
            }
            // The speaker feeds back into the mic while talking and just
            // after: same-words transcripts are echo, never user turns.
            // Barge-in is decided HERE, on words — mic energy alone
            // cannot tell echo from an interruption, so the agent never
            // stops talking until a real transcript says otherwise.
            const echoWindow =
              overlapped || Date.now() - speechEndRef.current < ECHO_TAIL_MS;
            if (echoWindow && isEchoTranscript(transcript, spokenRef.current)) {
              setBoth(overlapped ? "speaking" : "listening");
              listen();
              return;
            }
            if (overlapped) interruptForced();
            else setBoth("listening");
            listen();
            callbacksRef.current.onUserTurn(transcript);
          })
          .catch(() => {
            if (!activeRef.current) return;
            // One failed turn must not end the conversation.
            setError("Voice transcription failed.");
            setBoth("listening");
            listen();
          });
      },
      () => {
        // Cancelled via stop(): state is settled there.
      },
    );
  }, [interruptForced]);

  const speakNext = useCallback(() => {
    const pair = synthesis();
    const queue = speakQueueRef.current;
    if (!pair || queue.length === 0) {
      const done = speakDoneRef.current;
      speakDoneRef.current = null;
      speechEndRef.current = Date.now();
      if (activeRef.current) setBoth("listening");
      done?.();
      return;
    }
    const run = runRef.current;
    const text = queue.shift()!;
    spokenRef.current = [...spokenRef.current.slice(-7), text];
    const utterance = new pair.Utterance(text);
    const voice = pickVoice(pair.synth);
    if (voice) utterance.voice = voice;
    utterance.rate = 1.06;
    const advance = () => {
      if (runRef.current !== run || !activeRef.current) return;
      speakNext();
    };
    utterance.onend = advance;
    utterance.onerror = advance;
    try {
      pair.synth.speak(utterance);
    } catch {
      // A rejected utterance must never wedge the agent in "speaking".
      advance();
    }
  }, []);

  /** Read text aloud sentence by sentence; onDone fires when the
   *  last sentence finishes uninterrupted. */
  const speak = useCallback(
    (text: string, onDone?: () => void) => {
      const pair = synthesis();
      if (!pair || !activeRef.current) return;
      pair.synth.cancel();
      runRef.current += 1;
      speakQueueRef.current = splitUtterances(text);
      speakDoneRef.current = onDone ?? null;
      setBoth("speaking");
      speakNext();
    },
    [speakNext],
  );

  const stop = useCallback(() => {
    activeRef.current = false;
    runRef.current += 1;
    speakQueueRef.current = [];
    speakDoneRef.current = null;
    spokenRef.current = [];
    speechEndRef.current = 0;
    captureRef.current?.cancel();
    captureRef.current = null;
    release(streamRef.current);
    streamRef.current = null;
    synthesis()?.synth.cancel();
    setBoth("idle");
  }, []);

  const start = useCallback(() => {
    if (activeRef.current) return;
    if (!captureSupported() || !synthesis()) {
      setError("Voice conversation needs a browser with speech support.");
      return;
    }
    setError(null);
    activeRef.current = true;
    runRef.current += 1;
    setBoth("listening");
    navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then((stream) => {
        if (!activeRef.current) {
          release(stream);
          return;
        }
        streamRef.current = stream;
        listen();
      })
      .catch(() => {
        if (!activeRef.current) return;
        setError("Microphone access was blocked.");
        activeRef.current = false;
        setBoth("idle");
        callbacksRef.current.onError?.("not-allowed");
      });
  }, [listen]);

  useEffect(() => stop, [stop]);

  return {
    supported: captureSupported() && synthesis() !== null,
    state,
    interim: "",
    error,
    start,
    stop,
    interrupt,
    speak,
    /**
     * Mark the thinking phase (LLM working) for the status line.
     * Clearing only steps back from thinking, never over speech.
     */
    setThinking: (thinking: boolean) => {
      if (!activeRef.current) return;
      if (thinking) setBoth("thinking");
      else if (stateRef.current === "thinking") setBoth("listening");
    },
  };
}
