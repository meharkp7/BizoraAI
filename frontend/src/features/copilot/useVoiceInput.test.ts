import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useVoiceInput } from "./useVoiceInput.ts";

interface FakeResult {
  isFinal: boolean;
  0: { transcript: string };
}

class FakeRecognition {
  static instances: FakeRecognition[] = [];
  lang = "";
  interimResults = false;
  onresult: ((event: { resultIndex: number; results: FakeResult[] }) => void) | null =
    null;
  onerror: ((event: { error: string }) => void) | null = null;
  onend: (() => void) | null = null;
  started = false;

  constructor() {
    FakeRecognition.instances.push(this);
  }

  start(): void {
    this.started = true;
  }

  stop(): void {
    this.started = false;
    this.onend?.();
  }

  abort(): void {
    this.started = false;
  }

  emit(transcript: string, isFinal: boolean): void {
    this.onresult?.({ resultIndex: 0, results: [{ isFinal, 0: { transcript } }] });
  }
}

function installFake(): void {
  (window as unknown as Record<string, unknown>).SpeechRecognition = FakeRecognition;
}

describe("useVoiceInput", () => {
  afterEach(() => {
    FakeRecognition.instances = [];
    delete (window as unknown as Record<string, unknown>).SpeechRecognition;
    delete (window as unknown as Record<string, unknown>).webkitSpeechRecognition;
    vi.restoreAllMocks();
  });

  it("reports unsupported without the browser API", () => {
    const { result } = renderHook(() => useVoiceInput("en-IN", () => {}));

    expect(result.current.supported).toBe(false);

    act(() => {
      result.current.toggle();
    });
    expect(result.current.error).toMatch(/not supported/);
    expect(result.current.listening).toBe(false);
  });

  it("streams interim transcripts and delivers finals", () => {
    installFake();
    const onFinal = vi.fn();
    const { result } = renderHook(() => useVoiceInput("en-IN", onFinal));

    expect(result.current.supported).toBe(true);
    act(() => {
      result.current.toggle();
    });
    expect(result.current.listening).toBe(true);
    expect(FakeRecognition.instances).toHaveLength(1);
    expect(FakeRecognition.instances[0]?.lang).toBe("en-IN");

    act(() => {
      FakeRecognition.instances[0]?.emit("find npn", false);
    });
    expect(result.current.interim).toBe("find npn");
    expect(onFinal).not.toHaveBeenCalled();

    act(() => {
      FakeRecognition.instances[0]?.emit("find npn transistor", true);
    });
    expect(onFinal).toHaveBeenCalledWith("find npn transistor");
    expect(result.current.interim).toBe("");

    act(() => {
      result.current.stop();
    });
    expect(result.current.listening).toBe(false);
  });

  it("explains blocked microphones and ignores aborts", () => {
    installFake();
    const { result } = renderHook(() => useVoiceInput("en-IN", () => {}));
    act(() => {
      result.current.toggle();
    });

    act(() => {
      FakeRecognition.instances[0]?.onerror?.({ error: "aborted" });
    });
    expect(result.current.error).toBeNull();

    act(() => {
      FakeRecognition.instances[0]?.onerror?.({ error: "not-allowed" });
    });
    expect(result.current.error).toBe("Microphone access was blocked.");
  });
});
