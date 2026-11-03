import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../lib/api.ts";
import { useVoiceInput } from "./useVoiceInput.ts";
import * as voiceCapture from "./voiceCapture.ts";

vi.mock("../../lib/api.ts", () => ({
  api: { transcribeVoice: vi.fn() },
}));

const transcribeVoice = vi.mocked(api.transcribeVoice);

function fakeStream(): MediaStream {
  return { getTracks: () => [{ stop: vi.fn() }] } as unknown as MediaStream;
}

function installMic(stream: MediaStream | null = fakeStream()): void {
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: {
      getUserMedia: stream === null ? vi.fn().mockRejectedValue(new Error("denied")) : vi.fn().mockResolvedValue(stream),
    },
  });
  (window as unknown as Record<string, unknown>).AudioContext = vi.fn();
  (window as unknown as Record<string, unknown>).MediaStream = vi.fn();
}

function fakeCapture(samples: Float32Array = Float32Array.from([0.1, 0.2])) {
  const capture = {
    done: Promise.resolve(samples),
    stop: vi.fn(),
    cancel: vi.fn(),
  };
  const spy = vi.spyOn(voiceCapture, "captureUtterance").mockReturnValue(capture);
  return { capture, spy };
}

describe("useVoiceInput", () => {
  afterEach(() => {
    delete (window as unknown as Record<string, unknown>).AudioContext;
    delete (window as unknown as Record<string, unknown>).MediaStream;
    vi.restoreAllMocks();
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

  it("reports unsupported without capture APIs", () => {
    const { result } = renderHook(() =>
      useVoiceInput("en-IN", () => {}, { projectId: "p", graphId: "g" }),
    );

    expect(result.current.supported).toBe(false);

    act(() => {
      result.current.toggle();
    });
    expect(result.current.error).toMatch(/not supported/);
    expect(result.current.listening).toBe(false);
  });

  it("captures one utterance and delivers the server transcript", async () => {
    installMic();
    fakeCapture();
    transcribeVoice.mockResolvedValue({ transcript: "tilt the rails", audio_duration_ms: 900, session_id: "s-1" });
    const onFinal = vi.fn();
    const { result } = renderHook(() =>
      useVoiceInput("en-IN", onFinal, { projectId: "p", graphId: "g" }),
    );

    expect(result.current.supported).toBe(true);
    act(() => {
      result.current.toggle();
    });
    expect(result.current.listening).toBe(true);

    await waitFor(() => expect(onFinal).toHaveBeenCalledWith("tilt the rails"));
    expect(transcribeVoice).toHaveBeenCalledWith("p", "g", expect.any(Blob), "en");
    expect(result.current.listening).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("stays silent when nothing was said", async () => {
    installMic();
    fakeCapture(new Float32Array(0));
    const onFinal = vi.fn();
    const { result } = renderHook(() =>
      useVoiceInput("en-IN", onFinal, { projectId: "p", graphId: "g" }),
    );

    act(() => {
      result.current.toggle();
    });

    await waitFor(() => expect(result.current.listening).toBe(false));
    expect(onFinal).not.toHaveBeenCalled();
    expect(transcribeVoice).not.toHaveBeenCalled();
    expect(result.current.error).toBeNull();
  });

  it("reports blocked microphones and failed turns", async () => {
    installMic(null);
    const { result } = renderHook(() =>
      useVoiceInput("en-IN", () => {}, { projectId: "p", graphId: "g" }),
    );

    act(() => {
      result.current.toggle();
    });

    await waitFor(() => expect(result.current.error).toMatch(/blocked/));
    expect(result.current.listening).toBe(false);
  });

  it("reports transcription failures without losing the error", async () => {
    installMic();
    fakeCapture();
    transcribeVoice.mockRejectedValue(new Error("down"));
    const { result } = renderHook(() =>
      useVoiceInput("en-IN", () => {}, { projectId: "p", graphId: "g" }),
    );

    act(() => {
      result.current.toggle();
    });

    await waitFor(() => expect(result.current.error).toMatch(/type instead/));
    expect(result.current.listening).toBe(false);
  });
});
