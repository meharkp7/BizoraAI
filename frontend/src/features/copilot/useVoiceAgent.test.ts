import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../lib/api.ts";
import { splitUtterances, useVoiceAgent } from "./useVoiceAgent.ts";
import * as voiceCapture from "./voiceCapture.ts";

vi.mock("../../lib/api.ts", () => ({
  api: { transcribeVoice: vi.fn() },
}));

const transcribeVoice = vi.mocked(api.transcribeVoice);

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

interface FakeCapture {
  done: Promise<Float32Array>;
  resolve: (samples: Float32Array) => void;
  stop: () => void;
  cancel: () => void;
  fireSpeechStart: () => void;
  cancelled: boolean;
}

const captures: FakeCapture[] = [];

function fakeCaptureFactory(
  _stream: MediaStream,
  options: voiceCapture.CaptureOptions = {},
): voiceCapture.UtteranceCapture {
  let resolve!: (samples: Float32Array) => void;
  let reject!: (error: Error) => void;
  const done = new Promise<Float32Array>((pass, fail) => {
    resolve = pass;
    reject = fail;
  });
  // An un-awaited rejection (cancelled captures) must not fail the run.
  done.catch(() => {});
  const capture: FakeCapture = {
    done,
    resolve,
    stop: () => {},
    cancel: () => {
      capture.cancelled = true;
      reject(new Error("cancelled"));
    },
    fireSpeechStart: () => options.onSpeechStart?.(),
    cancelled: false,
  };
  captures.push(capture);
  return capture;
}

const SAMPLES = Float32Array.from([0.1, 0.2, 0.3]);

function installSpeech(): void {
  const w = window as unknown as Record<string, unknown>;
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
  w["AudioContext"] = vi.fn();
  w["MediaStream"] = vi.fn();
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia: vi.fn().mockResolvedValue(fakeStream()) },
  });
}

function fakeStream(): MediaStream {
  return { getTracks: () => [{ stop: vi.fn() }] } as unknown as MediaStream;
}

function renderAgent(callbacks: {
  onUserTurn?: (text: string) => void;
  onInterrupted?: () => void;
  onError?: (message: string) => void;
}) {
  return renderHook(() =>
    useVoiceAgent("en-IN", { projectId: "p", graphId: "g" }, {
      onUserTurn: callbacks.onUserTurn ?? (() => {}),
      onInterrupted: callbacks.onInterrupted,
      onError: callbacks.onError,
    }),
  );
}

async function startAgent(agent: { current: { start: () => void } }): Promise<void> {
  await act(async () => {
    agent.current.start();
  });
  await waitFor(() => expect(captures.length).toBeGreaterThan(0));
}

async function finishCapture(index: number, transcript: string): Promise<void> {
  transcribeVoice.mockResolvedValueOnce({
    transcript,
    audio_duration_ms: 900,
    session_id: "s-1",
  });
  await act(async () => {
    captures[index]?.resolve(SAMPLES);
  });
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
    captures.length = 0;
    spoken.length = 0;
    autoEnd = true;
    cancelled = 0;
    installSpeech();
    vi.spyOn(voiceCapture, "captureUtterance").mockImplementation(fakeCaptureFactory);
  });

  afterEach(() => {
    const w = window as unknown as Record<string, unknown>;
    delete w["SpeechSynthesisUtterance"];
    delete w["speechSynthesis"];
    delete w["AudioContext"];
    delete w["MediaStream"];
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.clearAllMocks();
  });

  it("reports unsupported without capture APIs", () => {
    const w = window as unknown as Record<string, unknown>;
    delete w["AudioContext"];
    const { result } = renderAgent({});

    expect(result.current.supported).toBe(false);
    act(() => result.current.start());
    expect(result.current.state).toBe("idle");
    expect(result.current.error).toMatch(/speech support/);
  });

  it("captures, transcribes, and delivers turns, then listens again", async () => {
    const turns: string[] = [];
    const { result } = renderAgent({ onUserTurn: (text) => turns.push(text) });

    await startAgent(result);
    expect(result.current.state).toBe("listening");

    await finishCapture(0, "hello there");
    await waitFor(() => expect(turns).toEqual(["hello there"]));
    expect(transcribeVoice).toHaveBeenCalledWith("p", "g", expect.any(Blob), "en");
    expect(result.current.state).toBe("listening");
    // The loop restarts capture for the next turn.
    expect(captures.length).toBe(2);
  });

  it("speaks sentence by sentence and returns to listening", async () => {
    const done: string[] = [];
    const { result } = renderAgent({});

    await startAgent(result);
    act(() => result.current.speak("First. Second!", () => done.push("ok")));

    expect(spoken.map((utterance) => utterance.text)).toEqual(["First.", "Second!"]);
    expect(spoken[0]?.rate).toBeCloseTo(1.06);
    expect(done).toEqual(["ok"]);
    expect(result.current.state).toBe("listening");
  });

  it("takes barge-in speech as the new turn", async () => {
    const turns: string[] = [];
    let interrupted = 0;
    const { result } = renderAgent({
      onUserTurn: (text) => turns.push(text),
      onInterrupted: () => {
        interrupted += 1;
      },
    });
    autoEnd = false;

    await startAgent(result);
    act(() => result.current.speak("A very long answer that keeps going."));
    expect(result.current.state).toBe("speaking");

    // Mic energy alone never interrupts: echo trips the VAD too.
    act(() => captures[0]?.fireSpeechStart());
    expect(result.current.state).toBe("speaking");
    expect(interrupted).toBe(0);

    // A real transcript over agent speech is the barge-in.
    await finishCapture(0, "stop, what about N2?");
    await waitFor(() => expect(turns).toEqual(["stop, what about N2?"]));
    expect(interrupted).toBe(1);
    expect(result.current.state).toBe("listening");
  });

  it("skips past utterances the synthesizer rejects", async () => {
    const w = window as unknown as Record<string, unknown>;
    const synth = w["speechSynthesis"] as { speak: (utterance: unknown) => void };
    synth.speak = () => {
      throw new Error("not a SpeechSynthesisUtterance");
    };
    const done: string[] = [];
    const { result } = renderAgent({});

    await startAgent(result);
    act(() => result.current.speak("First. Second!", () => done.push("ok")));

    expect(done).toEqual(["ok"]);
    expect(result.current.state).toBe("listening");
  });

  it("marks thinking and steps back without touching speech", async () => {
    const { result } = renderAgent({});
    autoEnd = false;

    await startAgent(result);
    act(() => result.current.setThinking(true));
    expect(result.current.state).toBe("thinking");
    act(() => result.current.setThinking(false));
    expect(result.current.state).toBe("listening");

    act(() => result.current.speak("Still talking."));
    expect(result.current.state).toBe("speaking");
    act(() => result.current.setThinking(false));
    expect(result.current.state).toBe("speaking");
  });

  it("ignores its own echo but hears real interruptions", async () => {
    const turns: string[] = [];
    let interrupted = 0;
    const { result } = renderAgent({
      onUserTurn: (text) => turns.push(text),
      onInterrupted: () => {
        interrupted += 1;
      },
    });
    autoEnd = false;

    await startAgent(result);
    act(() => result.current.speak("The bitcell holds one bit."));
    expect(result.current.state).toBe("speaking");

    // The speaker feeds back into the mic: same words are echo, not a turn.
    await finishCapture(0, "The bitcell holds one bit.");
    await waitFor(() => expect(captures.length).toBe(2));
    expect(turns).toEqual([]);
    expect(interrupted).toBe(0);
    expect(result.current.state).toBe("speaking");

    // Different words mid-speech are the user barging in.
    await finishCapture(1, "stop, what about N2?");
    await waitFor(() => expect(turns).toEqual(["stop, what about N2?"]));
    expect(interrupted).toBe(1);
  });

  it("ignores echo tails just after speech ends", async () => {
    const turns: string[] = [];
    const { result } = renderAgent({ onUserTurn: (text) => turns.push(text) });

    await startAgent(result);
    // Fake timers start only after the async setup settles: waitFor
    // below would never tick under them.
    vi.useFakeTimers();
    try {
      act(() => result.current.speak("The bitcell holds one bit."));
      expect(result.current.state).toBe("listening");

      // A trailing echo transcript lands right after speech ends: ignore it.
      await finishCapture(0, "The bitcell holds one bit.");
      await act(async () => {});
      expect(turns).toEqual([]);
      expect(captures.length).toBe(2);

      // Past the tail window the same words are a deliberate repeat.
      act(() => {
        vi.advanceTimersByTime(2000);
      });
      await finishCapture(1, "The bitcell holds one bit.");
      await act(async () => {});
      expect(turns).toEqual(["The bitcell holds one bit."]);
    } finally {
      vi.useRealTimers();
    }
  });

  it("keeps listening through empty and failed turns", async () => {
    const turns: string[] = [];
    const { result } = renderAgent({ onUserTurn: (text) => turns.push(text) });

    await startAgent(result);
    await finishCapture(0, "  ");
    await waitFor(() => expect(captures.length).toBe(2));
    expect(turns).toEqual([]);
    expect(result.current.error).toBeNull();

    transcribeVoice.mockRejectedValueOnce(new Error("down"));
    await act(async () => {
      captures[1]?.resolve(SAMPLES);
    });
    await waitFor(() => expect(result.current.error).toMatch(/failed/));
    expect(result.current.state).toBe("listening");
    expect(captures.length).toBe(3);
  });

  it("stops everything on demand", async () => {
    const { result, unmount } = renderAgent({});

    await startAgent(result);
    act(() => result.current.speak("Hello."));
    act(() => result.current.stop());

    expect(result.current.state).toBe("idle");
    expect(captures[0]?.cancelled).toBe(true);
    const calls = cancelled;
    unmount();
    expect(cancelled).toBeGreaterThanOrEqual(calls);
  });

  it("surfaces blocked microphones", async () => {
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn().mockRejectedValue(new Error("denied")) },
    });
    const errors: string[] = [];
    const { result } = renderAgent({ onError: (message) => errors.push(message) });

    await startAgent(result).catch(() => {});

    await waitFor(() => expect(result.current.state).toBe("idle"));
    expect(result.current.error).toMatch(/blocked/);
    expect(errors).toEqual(["not-allowed"]);
  });
});
