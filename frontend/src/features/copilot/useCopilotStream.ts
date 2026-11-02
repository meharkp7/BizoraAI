import { useEffect, useRef, useState } from "react";
import { api } from "../../lib/api.ts";
import type { CopilotResponse } from "../../lib/types.ts";

export interface CopilotStreamCallbacks {
  onStatus: (message: string) => void;
  onDone: (response: CopilotResponse) => void;
  onError: (error: Error) => void;
}

interface StreamFrame {
  kind: string;
  payload: unknown;
}

/** Split one raw SSE frame into its event kind and parsed JSON payload. */
export function parseStreamFrame(frame: string): StreamFrame | null {
  let kind: string | null = null;
  let data: string | null = null;
  for (const line of frame.split("\n")) {
    if (line.startsWith("event: ")) kind = line.slice("event: ".length);
    else if (line.startsWith("data: ")) data = line.slice("data: ".length);
  }
  if (kind === null || data === null) return null;
  try {
    return { kind, payload: JSON.parse(data) as unknown };
  } catch {
    return null;
  }
}

function isCopilotResponse(value: unknown): value is CopilotResponse {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as { reply?: unknown }).reply === "string" &&
    Array.isArray((value as { cards?: unknown }).cards)
  );
}

/**
 * POST one copilot turn to the streaming endpoint and fan out its frames.
 * Only one turn streams at a time; unmounting aborts the in-flight turn.
 */
export function useCopilotStream(projectId: string, graphId: string, version: number) {
  const [isPending, setIsPending] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  async function ask(
    message: string,
    selectedNodeId: string | null,
    diagramContext: string | null,
    callbacks: CopilotStreamCallbacks,
    threadId?: string | null,
  ): Promise<void> {
    if (abortRef.current) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setIsPending(true);
    let sawDone = false;
    try {
      const response = await api.postCopilotStream(
        projectId,
        graphId,
        version,
        message,
        selectedNodeId,
        diagramContext,
        controller.signal,
        threadId ?? null,
      );
      const reader = response.body?.getReader();
      if (!reader) throw new Error("The copilot stream had no body.");
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let cut = buffer.indexOf("\n\n");
        while (cut >= 0) {
          const frame = parseStreamFrame(buffer.slice(0, cut));
          buffer = buffer.slice(cut + 2);
          if (frame?.kind === "status") {
            const status = frame.payload as { message?: unknown };
            if (typeof status.message === "string") callbacks.onStatus(status.message);
          } else if (frame?.kind === "done") {
            const donePayload = frame.payload as { response?: unknown };
            if (isCopilotResponse(donePayload.response)) {
              sawDone = true;
              callbacks.onDone(donePayload.response);
            }
          }
          cut = buffer.indexOf("\n\n");
        }
      }
      if (!sawDone) throw new Error("The copilot stream ended without an answer.");
    } catch (error) {
      if (controller.signal.aborted) return;
      callbacks.onError(error instanceof Error ? error : new Error("The copilot failed."));
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setIsPending(false);
    }
  }

  return { ask, isPending };
}
