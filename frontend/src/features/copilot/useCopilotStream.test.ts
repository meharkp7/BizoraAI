import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../lib/api.ts";
import { copilotFixture } from "../../test/fixtures.ts";
import { parseStreamFrame, useCopilotStream } from "./useCopilotStream.ts";

function streamedResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(body, { headers: { "Content-Type": "text/event-stream" } });
}

describe("parseStreamFrame", () => {
  it("parses an event kind with its JSON payload", () => {
    expect(parseStreamFrame('event: status\ndata: {"message":"hi"}')).toEqual({
      kind: "status",
      payload: { message: "hi" },
    });
  });

  it("rejects frames missing an event, data, or valid JSON", () => {
    expect(parseStreamFrame('data: {"message":"hi"}')).toBeNull();
    expect(parseStreamFrame("event: status")).toBeNull();
    expect(parseStreamFrame("event: status\ndata: not-json")).toBeNull();
  });
});

describe("useCopilotStream", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("fans split chunks out into ordered statuses and one done", async () => {
    const body =
      `event: status\ndata: ${JSON.stringify({ message: "Thinking (round 1)…" })}\n\n` +
      `event: done\ndata: ${JSON.stringify({ response: copilotFixture })}\n\n`;
    // Split mid-frame so the test proves buffering across chunk boundaries.
    const cut = body.indexOf("round 1");
    vi.spyOn(api, "postCopilotStream").mockResolvedValue(
      streamedResponse([body.slice(0, cut), body.slice(cut)]),
    );
    const { result } = renderHook(() => useCopilotStream("p", "g", 1));
    const statuses: string[] = [];
    const calls = {
      onStatus: (message: string) => statuses.push(message),
      onDone: vi.fn(),
      onError: vi.fn(),
    };

    let pending: Promise<void> | null = null;
    act(() => {
      pending = result.current.ask("hello", null, null, calls);
    });
    expect(result.current.isPending).toBe(true);
    await act(async () => {
      await pending;
    });

    expect(statuses).toEqual(["Thinking (round 1)…"]);
    expect(calls.onDone).toHaveBeenCalledOnce();
    expect(calls.onDone).toHaveBeenCalledWith(copilotFixture);
    expect(calls.onError).not.toHaveBeenCalled();
    expect(result.current.isPending).toBe(false);
  });

  it("reports an error when the stream ends without done", async () => {
    vi.spyOn(api, "postCopilotStream").mockResolvedValue(streamedResponse([]));
    const { result } = renderHook(() => useCopilotStream("p", "g", 1));
    const calls = { onStatus: vi.fn(), onDone: vi.fn(), onError: vi.fn() };

    let pending: Promise<void> | null = null;
    act(() => {
      pending = result.current.ask("hello", null, null, calls);
    });
    await act(async () => {
      await pending;
    });

    expect(calls.onDone).not.toHaveBeenCalled();
    expect(calls.onError).toHaveBeenCalledOnce();
    expect(result.current.isPending).toBe(false);
  });
});
