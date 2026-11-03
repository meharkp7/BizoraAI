import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../lib/api.ts";
import {
  captureSupported,
  captureUtterance,
  encodeWavPcm16,
  type UtteranceCapture,
} from "./voiceCapture.ts";

export interface VoiceInputScope {
  projectId: string;
  graphId: string;
}

export interface VoiceInput {
  supported: boolean;
  listening: boolean;
  interim: string;
  error: string | null;
  toggle: () => void;
  stop: () => void;
}

/** Dictation pauses run longer than chat turns before they end. */
const DICTATION_SILENCE_MS = 2500;

function release(stream: MediaStream | null): void {
  if (!stream) return;
  for (const track of stream.getTracks()) track.stop();
}

/**
 * Dictate into a callback through Muse Voice Transcribe: the mic
 * records one utterance, silence (or a second tap) ends it, and the
 * server transcript is delivered for the caller to append and edit.
 * There are no interim transcripts — one-shot turns only.
 */
export function useVoiceInput(
  lang: string,
  onFinal: (transcript: string) => void,
  scope: VoiceInputScope,
): VoiceInput {
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const captureRef = useRef<UtteranceCapture | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const finalRef = useRef(onFinal);
  const scopeRef = useRef(scope);
  const supported = captureSupported();

  useEffect(() => {
    finalRef.current = onFinal;
  });

  useEffect(() => {
    scopeRef.current = scope;
  });

  const stop = useCallback(() => {
    captureRef.current?.cancel();
    captureRef.current = null;
    release(streamRef.current);
    streamRef.current = null;
    setListening(false);
  }, []);

  useEffect(() => stop, [stop]);

  const toggle = useCallback(() => {
    if (captureRef.current) {
      // Second tap ends the utterance now; transcription follows.
      captureRef.current.stop();
      return;
    }
    if (listening) return;
    if (!captureSupported()) {
      setError("Voice input is not supported in this browser.");
      return;
    }
    setError(null);
    setListening(true);
    const language = lang.split("-")[0] || lang;
    navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then((stream) => {
        streamRef.current = stream;
        const capture = captureUtterance(stream, { vad: { silenceMs: DICTATION_SILENCE_MS } });
        captureRef.current = capture;
        return capture.done.then(
          (samples) => {
            captureRef.current = null;
            release(streamRef.current);
            streamRef.current = null;
            if (samples.length === 0) {
              setListening(false);
              return;
            }
            const clip = new Blob([encodeWavPcm16(samples, 16000)], { type: "audio/wav" });
            const { projectId, graphId } = scopeRef.current;
            return api
              .transcribeVoice(projectId, graphId, clip, language)
              .then((result) => {
                setListening(false);
                const clean = result.transcript.trim();
                if (clean !== "") finalRef.current(result.transcript);
              })
              .catch(() => {
                setListening(false);
                setError("Voice input failed; type instead.");
              });
          },
          () => {
            // Cancelled via stop(): state is already settled there.
          },
        );
      })
      .catch(() => {
        setListening(false);
        setError("Microphone access was blocked.");
      });
  }, [lang, listening]);

  return { supported, listening, interim: "", error, toggle, stop };
}
