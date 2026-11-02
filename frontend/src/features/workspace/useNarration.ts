import { useCallback, useEffect, useRef, useState } from "react";
import type { NarrationLine } from "../../lib/types.ts";

/** Minimal SpeechSynthesis shapes (DOM libs vary). */
interface UtteranceLike {
  text: string;
  onend: (() => void) | null;
  onerror: (() => void) | null;
}

type UtteranceCtor = new (text: string) => UtteranceLike;

interface SynthesisLike {
  speak: (utterance: UtteranceLike) => void;
  cancel: () => void;
}

function synthesis(): SynthesisLike | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    speechSynthesis?: SynthesisLike;
    SpeechSynthesisUtterance?: UtteranceCtor;
  };
  if (!w.speechSynthesis || !w.SpeechSynthesisUtterance) return null;
  return w.speechSynthesis;
}

function utterance(text: string): UtteranceLike | null {
  const w = window as unknown as { SpeechSynthesisUtterance?: UtteranceCtor };
  if (!w.SpeechSynthesisUtterance) return null;
  return new w.SpeechSynthesisUtterance(text);
}

interface SpeechRun {
  queue: NarrationLine[];
  onLineDone: (seq: number) => void;
  setActive: (seq: number | null) => void;
  /** False once a newer run (or stop) supersedes this one. */
  isCurrent: () => boolean;
}

/** Speak one queued line, chaining to the next on end or error.
 *  Stale runs stay silent: cancelling speech fires error events on
 *  the cut-off utterance, which must not resume a stopped guide. */
function speakAt(run: SpeechRun, index: number): void {
  if (!run.isCurrent()) return;
  const synth = synthesis();
  if (!synth || index >= run.queue.length) {
    run.setActive(null);
    return;
  }
  const line = run.queue[index]!;
  const spoken = utterance(line.text);
  if (!spoken) {
    run.setActive(null);
    return;
  }
  run.setActive(line.seq);
  const advance = () => {
    if (!run.isCurrent()) return;
    run.onLineDone(line.seq);
    speakAt(run, index + 1);
  };
  spoken.onend = advance;
  spoken.onerror = advance;
  synth.speak(spoken);
}

export interface Narrator {
  supported: boolean;
  /** Seq of the line being read, or null when idle. */
  activeSeq: number | null;
  narrating: boolean;
  play: (intro: string, lines: NarrationLine[]) => void;
  stop: () => void;
}

/** Read narration lines aloud in order, highlighting each step.
 *  `onLineDone` fires per finished line so the caller can check
 *  steps off as they are narrated. */
export function useNarration(onLineDone: (seq: number) => void): Narrator {
  const [activeSeq, setActiveSeq] = useState<number | null>(null);
  const onLineDoneRef = useRef(onLineDone);
  const runRef = useRef(0);

  useEffect(() => {
    onLineDoneRef.current = onLineDone;
  }, [onLineDone]);

  const stop = useCallback(() => {
    runRef.current += 1;
    synthesis()?.cancel();
    setActiveSeq(null);
  }, []);

  const play = useCallback((intro: string, lines: NarrationLine[]) => {
    const synth = synthesis();
    if (!synth) return;
    synth.cancel();
    runRef.current += 1;
    const runId = runRef.current;
    const run: SpeechRun = {
      queue: lines,
      onLineDone: (seq) => onLineDoneRef.current(seq),
      setActive: setActiveSeq,
      isCurrent: () => runRef.current === runId,
    };
    const spokenIntro = utterance(intro);
    if (!spokenIntro) return;
    setActiveSeq(lines[0]?.seq ?? null);
    const begin = () => speakAt(run, 0);
    spokenIntro.onend = begin;
    spokenIntro.onerror = begin;
    synth.speak(spokenIntro);
  }, []);

  // Silence speech when the panel unmounts mid-narration.
  useEffect(() => stop, [stop]);

  return {
    supported: synthesis() !== null,
    activeSeq,
    narrating: activeSeq !== null,
    play,
    stop,
  };
}
