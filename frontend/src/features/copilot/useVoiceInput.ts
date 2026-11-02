import { useCallback, useEffect, useRef, useState } from "react";

/** Minimal Web Speech API shapes (not all DOM libs ship them). */
interface SpeechRecognitionAlternative {
  transcript: string;
}

interface SpeechRecognitionResultItem {
  isFinal: boolean;
  0: SpeechRecognitionAlternative;
}

interface SpeechRecognitionResultList {
  length: number;
  [index: number]: SpeechRecognitionResultItem;
}

interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: SpeechRecognitionResultList;
}

interface SpeechRecognitionErrorLike {
  error: string;
}

interface SpeechRecognitionLike {
  lang: string;
  interimResults: boolean;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorLike) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

function recognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as Record<string, SpeechRecognitionCtor | undefined>;
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export interface VoiceInput {
  supported: boolean;
  listening: boolean;
  interim: string;
  error: string | null;
  toggle: () => void;
  stop: () => void;
}

/**
 * Dictate into a callback using the browser's speech recognition.
 * Final transcripts are delivered for the caller to append and edit;
 * interim transcripts surface live while listening.
 */
export function useVoiceInput(
  lang: string,
  onFinal: (transcript: string) => void,
): VoiceInput {
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<string | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const finalRef = useRef(onFinal);
  const supported = recognitionCtor() !== null;

  useEffect(() => {
    finalRef.current = onFinal;
  });

  const stop = useCallback(() => {
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    setListening(false);
    setInterim("");
  }, []);

  useEffect(() => {
    return () => {
      recognitionRef.current?.abort();
      recognitionRef.current = null;
    };
  }, []);

  const toggle = useCallback(() => {
    if (listening) {
      stop();
      return;
    }
    const Ctor = recognitionCtor();
    if (!Ctor) {
      setError("Voice input is not supported in this browser.");
      return;
    }
    setError(null);
    setInterim("");
    const recognition = new Ctor();
    recognition.lang = lang;
    recognition.interimResults = true;
    recognition.onresult = (event) => {
      let pending = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        if (result.isFinal) finalRef.current(result[0].transcript);
        else pending += result[0].transcript;
      }
      setInterim(pending);
    };
    recognition.onerror = (event) => {
      if (event.error === "aborted" || event.error === "no-speech") {
        setInterim("");
        return;
      }
      setError(
        event.error === "not-allowed"
          ? "Microphone access was blocked."
          : "Voice input failed; type instead.",
      );
    };
    recognition.onend = () => {
      recognitionRef.current = null;
      setListening(false);
      setInterim("");
    };
    recognitionRef.current = recognition;
    try {
      recognition.start();
    } catch {
      recognitionRef.current = null;
      setError("Voice input failed; type instead.");
      return;
    }
    setListening(true);
  }, [lang, listening, stop]);

  return { supported, listening, interim, error, toggle, stop };
}
