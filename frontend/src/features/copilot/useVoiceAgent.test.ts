import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { splitUtterances, useVoiceAgent } from "./useVoiceAgent.ts";

interface FakeResult {
  isFinal: boolean;
  0: { transcript: string };
}

class FakeRecognition {
  static instances: FakeRecognition[] = [];
  lang = "";
  continuous = false;
  interimResults = false;
  onresult: ((event: { resultIndex: number; results: FakeResult[] }) => void) | null = null;
  onerror: ((event: { error: string }) => void) | null = null;
  onend: (() => void) | null = null;
  onspeechstart: (() => void) | null = null;
  started = 0;
  stopped = 0;
  aborted = 0;

  constructor() {
    FakeRecognition.instances.push(this);
  }

  start(): void {
    this.started += 1;
  }
  stop(): void {
    this.stopped += 1;
  }
  abort(): void {
    this.aborted += 1;
  }

  emitFinal(transcript: string): void {
    this.onresult?.({ resultIndex: 0, results: [{ isFinal: true, 0: { transcript } }] });
  }

  emitInterim(transcript: string): void {
    this.onresult?.({ resultIndex: 0, results: [{ isFinal: false, 0: { transcript } }] });
  }
}

class FakeUtterance {
  text: string;
  voice: unknown = null;
  rate = 1;
  onend: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(text: string) {
    this.text = text;
  }
}

const spoken: FakeUtterance[] = [];
let autoEnd = true;
let cancelled = 0;

function installSpeech(): void {
  const w = window as unknown as Record<string, unknown>;
  w["SpeechRecognition"] = FakeRecognition;
  w["SpeechSynthesisUtterance"] = FakeUtterance;
  w["speechSynthesis"] = {
    speak: (utterance: FakeUtterance) => {
      spoken.push(utterance);
      if (autoEnd) utterance.onend?.();
    },
    cancel: () => {
      cancelled += 1;
    },
    getVoices: () => [{ name: "Test Voice", lang: "en-US" }],
  };
}

describe("splitUtterances", () => {
  it("splits sentences and long clauses", () => {
    expect(splitUtterances("Hello there. How are you?")).toEqual([
      "Hello there.",
      "How are you?",
    ]);
    expect(splitUtterances("")).toEqual([]);
    const long = `First clause, ${"word ".repeat(60)}last clause.`;
    const parts = splitUtterances(long);
    expect(parts.length).toBeGreaterThan(1);
    expect(parts.every((part) => part.length <= 260)).toBe(true);
  });
});

describe("useVoiceAgent", () => {
  beforeEach(() => {
    FakeRecognition.instances.length = 0;
    spoken.length = 0;
    autoEnd = true;
    cancelled = 0;
    installSpeech();
  });

  afterEach(() => {
    const w = window as unknown as Record<string, unknown>;
    delete w["SpeechRecognition"];
    delete w["SpeechSynthesisUtterance"];
    delete w["speechSynthesis"];
    vi.useRealTimers();
  });

  it("reports unsupported without speech APIs", () => {
    const w = window as unknown as Record<string, unknown>;
    delete w["SpeechRecognition"];
    const { result } = renderHook(() => useVoiceAgent("en-IN", { onUserTurn: () => {} }));

    expect(result.current.supported).toBe(false);
    act(() => result.current.start());
    expect(result.current.state).toBe("idle");
    expect(result.current.error).toMatch(/speech support/);
  });

  it("listens and delivers final transcripts as turns", () => {
    const turns: string[] = [];
    const { result } = renderHook(() =>
      useVoiceAgent("en-IN", { onUserTurn: (text) => turns.push(text) }),
    );

    act(() => result.current.start());
    expect(result.current.state).toBe("listening");
    const recognition = FakeRecognition.instances[0];
    expect(recognition?.started).toBe(1);

    act(() => recognition?.emitInterim("hello th"));
    expect(result.current.interim).toBe("hello th");
    act(() => recognition?.emitFinal("hello there"));
    expect(turns).toEqual(["hello there"]);
    expect(result.current.interim).toBe("");
  });

  it("restarts recognition after silence ends it", () => {
    const { result } = renderHook(() => useVoiceAgent("en-IN", { onUserTurn: () => {} }));

    act(() => result.current.start());
    act(() => FakeRecognition.instances[0]?.onend?.());

    expect(FakeRecognition.instances.length).toBe(2);
    expect(result.current.state).toBe("listening");
  });

  it("speaks sentence by sentence and returns to listening", () => {
    const done: string[] = [];
    const { result } = renderHook(() => useVoiceAgent("en-IN", { onUserTurn: () => {} }));

    act(() => result.current.start());
    act(() => result.current.speak("First. Second!", () => done.push("ok")));

    expect(spoken.map((utterance) => utterance.text)).toEqual(["First.", "Second!"]);
    expect(spoken[0]?.rate).toBeCloseTo(1.06);
    expect(done).toEqual(["ok"]);
    expect(result.current.state).toBe("listening");
  });

  it("takes barge-in speech as the new turn", () => {
    vi.useFakeTimers();
    const turns: string[] = [];
    let interrupted = 0;
    const { result } = renderHook(() =>
      useVoiceAgent("en-IN", {
        onUserTurn: (text) => turns.push(text),
        onInterrupted: () => {
          interrupted += 1;
        },
      }),
    );
    autoEnd = false;

    act(() => result.current.start());
    act(() => result.current.speak("A very long answer that keeps going."));
    expect(result.current.state).toBe("speaking");

    // Inside the grace period the agent's own echo is ignored.
    act(() => FakeRecognition.instances[0]?.onspeechstart?.());
    expect(result.current.state).toBe("speaking");

    act(() => {
      vi.advanceTimersByTime(900);
    });
    // Real Date.now moved only via fake timers: force the grace check
    // by advancing past it, then barge in.
    act(() => FakeRecognition.instances[0]?.onspeechstart?.());
    expect(result.current.state).toBe("listening");
    expect(interrupted).toBe(1);
    act(() => FakeRecognition.instances[0]?.emitFinal("stop, what about N2?"));
    expect(turns).toEqual(["stop, what about N2?"]);
  });

  it("skips past utterances the synthesizer rejects", () => {
    const w = window as unknown as Record<string, unknown>;
    const synth = w["speechSynthesis"] as { speak: (utterance: unknown) => void };
    synth.speak = () => {
      throw new Error("not a SpeechSynthesisUtterance");
    };
    const done: string[] = [];
    const { result } = renderHook(() => useVoiceAgent("en-IN", { onUserTurn: () => {} }));

    act(() => result.current.start());
    act(() => result.current.speak("First. Second!", () => done.push("ok")));

    expect(done).toEqual(["ok"]);
    expect(result.current.state).toBe("listening");
  });

  it("marks thinking and steps back without touching speech", () => {
    const { result } = renderHook(() => useVoiceAgent("en-IN", { onUserTurn: () => {} }));
    autoEnd = false;

    act(() => result.current.start());
    act(() => result.current.setThinking(true));
    expect(result.current.state).toBe("thinking");
    act(() => result.current.setThinking(false));
    expect(result.current.state).toBe("listening");

    act(() => result.current.speak("Still talking."));
    expect(result.current.state).toBe("speaking");
    act(() => result.current.setThinking(false));
    expect(result.current.state).toBe("speaking");
  });

  it("ignores its own echo but hears real interruptions", () => {
    const turns: string[] = [];
    let interrupted = 0;
    const { result } = renderHook(() =>
      useVoiceAgent("en-IN", {
        onUserTurn: (text) => turns.push(text),
        onInterrupted: () => {
          interrupted += 1;
        },
      }),
    );
    autoEnd = false;

    act(() => result.current.start());
    act(() => result.current.speak("The bitcell holds one bit."));
    expect(result.current.state).toBe("speaking");

    // The speaker feeds back into the mic: same words are echo, not a turn.
    act(() => FakeRecognition.instances[0]?.emitFinal("The bitcell holds one bit."));
    expect(turns).toEqual([]);
    expect(interrupted).toBe(0);
    expect(result.current.state).toBe("speaking");

    // Interim echo never interrupts either, though it still displays.
    act(() => FakeRecognition.instances[0]?.emitInterim("The bitcell holds"));
    expect(result.current.interim).toBe("The bitcell holds");
    expect(interrupted).toBe(0);

    // Different words mid-speech are the user barging in.
    act(() => FakeRecognition.instances[0]?.emitFinal("stop, what about N2?"));
    expect(interrupted).toBe(1);
    expect(turns).toEqual(["stop, what about N2?"]);
  });

  it("ignores echo tails just after speech ends", () => {
    vi.useFakeTimers();
    try {
      const turns: string[] = [];
      const { result } = renderHook(() => useVoiceAgent("en-IN", {
        onUserTurn: (text) => turns.push(text),
      }));

      act(() => result.current.start());
      act(() => result.current.speak("The bitcell holds one bit."));
      expect(result.current.state).toBe("listening");

      // A trailing echo final lands right after speech ends: ignore it.
      act(() => FakeRecognition.instances[0]?.emitFinal("The bitcell holds one bit."));
      expect(turns).toEqual([]);

      // Past the tail window the same words are a deliberate repeat.
      act(() => {
        vi.advanceTimersByTime(2000);
      });
      act(() => FakeRecognition.instances[0]?.emitFinal("The bitcell holds one bit."));
      expect(turns).toEqual(["The bitcell holds one bit."]);
    } finally {
      vi.useRealTimers();
    }
  });

  it("stops everything on demand", () => {
    const { result, unmount } = renderHook(() =>
      useVoiceAgent("en-IN", { onUserTurn: () => {} }),
    );

    act(() => result.current.start());
    act(() => result.current.speak("Hello."));
    act(() => result.current.stop());

    expect(result.current.state).toBe("idle");
    expect(FakeRecognition.instances[0]?.aborted).toBe(1);
    const calls = cancelled;
    unmount();
    expect(cancelled).toBeGreaterThanOrEqual(calls);
  });

  it("surfaces fatal microphone errors", () => {
    const { result } = renderHook(() => useVoiceAgent("en-IN", { onUserTurn: () => {} }));

    act(() => result.current.start());
    act(() => FakeRecognition.instances[0]?.onerror?.({ error: "not-allowed" }));

    expect(result.current.state).toBe("idle");
    expect(result.current.error).toMatch(/blocked/);
  });

  it("ignores transient recognition errors", () => {
    const { result } = renderHook(() => useVoiceAgent("en-IN", { onUserTurn: () => {} }));

    act(() => result.current.start());
    act(() => FakeRecognition.instances[0]?.onerror?.({ error: "no-speech" }));

    expect(result.current.state).toBe("listening");
    expect(result.current.error).toBeNull();
  });
});
