import { useCallback, useEffect, useRef, useState } from "react";

/** Minimal Web Speech API shapes (DOM libs vary). */
interface RecognitionAlternative {
  transcript: string;
}

interface RecognitionResultItem {
  isFinal: boolean;
  0: RecognitionAlternative;
}

interface RecognitionResultList {
  length: number;
  [index: number]: RecognitionResultItem;
}

interface RecognitionEventLike {
  resultIndex: number;
  results: RecognitionResultList;
}

interface RecognitionErrorLike {
  error: string;
}

interface RecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: RecognitionEventLike) => void) | null;
  onerror: ((event: RecognitionErrorLike) => void) | null;
  onend: (() => void) | null;
  onspeechstart: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

type RecognitionCtor = new () => RecognitionLike;

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

function recognitionCtor(): RecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as Record<string, RecognitionCtor | undefined>;
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
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

export interface VoiceAgentCallbacks {
  /** A final user transcript: the caller asks and later calls speak(). */
  onUserTurn: (transcript: string) => void;
  /** The user started talking over the agent's speech. */
  onInterrupted?: () => void;
  /** Recognition died with a fatal error. */
  onError?: (message: string) => void;
}

/** Grace period per utterance before barge-in counts: the agent's own
 *  voice through speakers can trip speech-start immediately. */
const BARGE_IN_GRACE_MS = 800;

const FATAL_ERRORS = new Set(["not-allowed", "service-not-allowed", "network", "audio-capture"]);

/**
 * A full-duplex voice conversation loop: the agent listens, the caller
 * answers via speak(), the user barges in by talking over it.
 * Recognition restarts itself so the conversation continues until
 * stop() or unmount.
 */
export function useVoiceAgent(lang: string, callbacks: VoiceAgentCallbacks) {
  const [state, setState] = useState<VoiceAgentState>("idle");
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<string | null>(null);
  const activeRef = useRef(false);
  const stateRef = useRef<VoiceAgentState>("idle");
  const recognitionRef = useRef<RecognitionLike | null>(null);
  const callbacksRef = useRef(callbacks);
  const speakQueueRef = useRef<string[]>([]);
  const speakDoneRef = useRef<(() => void) | null>(null);
  const utteranceStartRef = useRef(0);
  const runRef = useRef(0);

  useEffect(() => {
    callbacksRef.current = callbacks;
  });

  function setBoth(next: VoiceAgentState): void {
    stateRef.current = next;
    setState(next);
  }

  const listen = useCallback(() => {
    if (!activeRef.current) return;
    const Ctor = recognitionCtor();
    if (!Ctor) {
      setError("Voice conversation is not supported in this browser.");
      activeRef.current = false;
      setBoth("idle");
      return;
    }
    const recognition = new Ctor();
    recognition.lang = lang;
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.onresult = (event) => {
      if (!activeRef.current) return;
      let pending = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        if (result.isFinal) {
          const transcript = result[0].transcript.trim();
          setInterim("");
          if (transcript !== "") callbacksRef.current.onUserTurn(transcript);
        } else {
          pending += result[0].transcript;
        }
      }
      setInterim(pending);
    };
    recognition.onspeechstart = () => {
      // Barge-in: user speech during agent speech takes the turn.
      if (stateRef.current !== "speaking") return;
      if (Date.now() - utteranceStartRef.current < BARGE_IN_GRACE_MS) return;
      const pair = synthesis();
      pair?.synth.cancel();
      runRef.current += 1;
      speakQueueRef.current = [];
      speakDoneRef.current = null;
      setInterim("");
      setBoth("listening");
      callbacksRef.current.onInterrupted?.();
    };
    recognition.onerror = (event) => {
      if (event.error === "aborted" || event.error === "no-speech") return;
      if (!FATAL_ERRORS.has(event.error)) return;
      setError(
        event.error === "not-allowed" || event.error === "service-not-allowed"
          ? "Microphone access was blocked."
          : "Voice conversation failed.",
      );
      activeRef.current = false;
      setBoth("idle");
      callbacksRef.current.onError?.(event.error);
    };
    recognition.onend = () => {
      recognitionRef.current = null;
      // Chrome ends recognition after silence: restart while active.
      if (activeRef.current) listen();
    };
    recognitionRef.current = recognition;
    try {
      recognition.start();
    } catch {
      recognitionRef.current = null;
    }
  }, [lang]);

  const speakNext = useCallback(() => {
    const pair = synthesis();
    const queue = speakQueueRef.current;
    if (!pair || queue.length === 0) {
      const done = speakDoneRef.current;
      speakDoneRef.current = null;
      if (activeRef.current) setBoth("listening");
      done?.();
      return;
    }
    const run = runRef.current;
    const text = queue.shift()!;
    const utterance = new pair.Utterance(text);
    const voice = pickVoice(pair.synth);
    if (voice) utterance.voice = voice;
    utterance.rate = 1.06;
    utteranceStartRef.current = Date.now();
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
      setInterim("");
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
    recognitionRef.current?.abort();
    recognitionRef.current = null;
    synthesis()?.synth.cancel();
    setInterim("");
    setBoth("idle");
  }, []);

  const start = useCallback(() => {
    if (activeRef.current) return;
    if (!recognitionCtor() || !synthesis()) {
      setError("Voice conversation needs a browser with speech support.");
      return;
    }
    setError(null);
    setInterim("");
    activeRef.current = true;
    runRef.current += 1;
    setBoth("listening");
    listen();
  }, [listen]);

  const interrupt = useCallback(() => {
    if (stateRef.current !== "speaking") return;
    synthesis()?.synth.cancel();
    runRef.current += 1;
    speakQueueRef.current = [];
    speakDoneRef.current = null;
    setInterim("");
    setBoth("listening");
    callbacksRef.current.onInterrupted?.();
  }, []);

  useEffect(() => stop, [stop]);

  return {
    supported: recognitionCtor() !== null && synthesis() !== null,
    state,
    interim,
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
