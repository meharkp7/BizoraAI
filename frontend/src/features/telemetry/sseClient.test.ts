import { describe, expect, it, vi } from "vitest";
import {
  isTerminalState,
  openTelemetryStream,
  parseTelemetryEvent,
  telemetryStreamUrl,
} from "./sseClient.ts";

function streamPayload(seq: number, kind: string, payload: object): string {
  return JSON.stringify({
    run_id: "run-1",
    seq,
    emitted_at: "2026-01-01T00:00:00Z",
    kind,
    provenance: "measured",
    step: null,
    metric: null,
    log: null,
    pack_signal: null,
    state: null,
    ...payload,
  });
}

describe("telemetryStreamUrl", () => {
  it("targets the run stream with a resume cursor", () => {
    expect(telemetryStreamUrl("run-1")).toContain(
      "/api/v1/experiments/runs/run-1/telemetry/stream?from_seq=0",
    );
    expect(telemetryStreamUrl("run 1", 7)).toContain(
      "/api/v1/experiments/runs/run%201/telemetry/stream?from_seq=7",
    );
  });
});

describe("parseTelemetryEvent", () => {
  it("parses a valid metric frame", () => {
    const event = parseTelemetryEvent(
      streamPayload(2, "metric", {
        metric: { metric_id: "m-1", name: "loss", value: 0.5, unit: null, step_index: 1 },
      }),
    );
    expect(event?.seq).toBe(2);
    expect(event?.metric?.value).toBe(0.5);
  });

  it("rejects malformed payloads without throwing", () => {
    expect(parseTelemetryEvent("not json")).toBeNull();
    expect(parseTelemetryEvent("[]")).toBeNull();
    expect(parseTelemetryEvent(JSON.stringify({ run_id: "run-1" }))).toBeNull();
    expect(
      parseTelemetryEvent(streamPayload(1, "teleport", {})),
    ).toBeNull();
  });
});

describe("isTerminalState", () => {
  it("ends the stream on terminal states only", () => {
    expect(isTerminalState("succeeded")).toBe(true);
    expect(isTerminalState("failed")).toBe(true);
    expect(isTerminalState("cancelled")).toBe(true);
    expect(isTerminalState("running")).toBe(false);
    expect(isTerminalState("pending")).toBe(false);
  });
});

describe("openTelemetryStream", () => {
  it("dispatches named events and closes on request", () => {
    const listeners = new Map<string, (message: MessageEvent) => void>();
    const close = vi.fn();
    const seen: string[] = [];
    const stop = openTelemetryStream(
      "run-1",
      { onEvent: (event) => seen.push(event.kind) },
      {
        fromSeq: 3,
        eventSourceFactory: (url: string) => {
          expect(url).toContain("from_seq=3");
          return {
            addEventListener: (kind: string, callback: (message: MessageEvent) => void) => {
              listeners.set(kind, callback);
            },
            close,
          } as unknown as EventSource;
        },
      },
    );
    listeners.get("step")?.({ data: streamPayload(3, "step", {}) } as MessageEvent);
    listeners.get("metric")?.({ data: "garbage" } as MessageEvent);
    expect(seen).toEqual(["step"]);
    stop();
    expect(close).toHaveBeenCalledOnce();
  });
});
