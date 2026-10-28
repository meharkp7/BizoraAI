import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { TelemetryEventKind } from "./telemetryTypes.ts";
import { useTelemetryStream } from "./useTelemetry.ts";

/** Clearly-marked fake: an in-memory EventSource for stream tests. */
class FakeEventSource {
  url: string;
  closed = false;
  onerror: ((cause: unknown) => void) | null = null;
  private listeners = new Map<string, Set<(message: MessageEvent) => void>>();

  constructor(url: string) {
    this.url = url;
  }

  addEventListener(kind: string, callback: (message: MessageEvent) => void): void {
    const group = this.listeners.get(kind) ?? new Set();
    group.add(callback);
    this.listeners.set(kind, group);
  }

  removeEventListener(kind: string, callback: (message: MessageEvent) => void): void {
    this.listeners.get(kind)?.delete(callback);
  }

  close(): void {
    this.closed = true;
  }

  emit(kind: string, data: string): void {
    for (const callback of this.listeners.get(kind) ?? []) {
      callback({ data } as MessageEvent);
    }
  }

  fail(cause: unknown): void {
    this.onerror?.(cause);
  }
}

interface SourceHolder {
  source: FakeEventSource | null;
}

function streamPayload(seq: number, kind: TelemetryEventKind, payload: object): string {
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

describe("useTelemetryStream", () => {
  it("accumulates steps, metrics, logs, and signals", () => {
    const holder: SourceHolder = { source: null };
    const { result } = renderHook(() =>
      useTelemetryStream("run-1", true, {
        eventSourceFactory: (url: string) => {
          holder.source = new FakeEventSource(url);
          return holder.source as unknown as EventSource;
        },
      }),
    );
    expect(holder.source?.url).toContain("run-1/telemetry/stream");
    act(() => {
      holder.source?.emit("step", streamPayload(0, "step", {
        step: { step_index: 1, label: "train", total_steps: 4 },
      }));
      holder.source?.emit("metric", streamPayload(1, "metric", {
        metric: { metric_id: "m-1", name: "loss", value: 0.5, unit: null, step_index: 1 },
      }));
      holder.source?.emit("log", streamPayload(2, "log", {
        log: { level: "info", message: "epoch done", step_index: 1 },
      }));
      holder.source?.emit("pack_signal", streamPayload(3, "pack_signal", {
        pack_signal: { signal_id: "sig", label: "Signal", values: [1.5], unit: "V", node_ids: [] },
      }));
    });
    expect(result.current.status).toBe("streaming");
    expect(result.current.eventCount).toBe(4);
    expect(result.current.latestSeq).toBe(3);
    expect(result.current.steps).toHaveLength(1);
    expect(result.current.latestMetrics["loss"]?.value).toBe(0.5);
    expect(result.current.metricHistory["loss"]).toEqual([0.5]);
    expect(result.current.logs).toHaveLength(1);
    expect(result.current.packSignals).toHaveLength(1);
  });

  it("closes itself on terminal state (stopping ends the stream)", () => {
    const holder: SourceHolder = { source: null };
    const { result } = renderHook(() =>
      useTelemetryStream("run-1", true, {
        eventSourceFactory: (url: string) => {
          holder.source = new FakeEventSource(url);
          return holder.source as unknown as EventSource;
        },
      }),
    );
    act(() => {
      holder.source?.emit("state", streamPayload(0, "state", {
        state: { state: "running", error: null },
      }));
    });
    expect(result.current.runState).toBe("running");
    expect(holder.source?.closed).toBe(false);
    act(() => {
      holder.source?.emit("state", streamPayload(1, "state", {
        state: { state: "succeeded", error: null },
      }));
    });
    expect(result.current.runState).toBe("succeeded");
    expect(result.current.status).toBe("closed");
  });

  it("bounds logs and history instead of growing forever", () => {
    const holder: SourceHolder = { source: null };
    const { result } = renderHook(() =>
      useTelemetryStream("run-1", true, {
        maxLogs: 2,
        maxHistory: 2,
        eventSourceFactory: (url: string) => {
          holder.source = new FakeEventSource(url);
          return holder.source as unknown as EventSource;
        },
      }),
    );
    act(() => {
      for (let index = 0; index < 4; index += 1) {
        holder.source?.emit("log", streamPayload(index, "log", {
          log: { level: "info", message: `line ${index}`, step_index: null },
        }));
      }
    });
    expect(result.current.logs.map((log) => log.message)).toEqual(["line 2", "line 3"]);
    expect(result.current.eventCount).toBe(4);
  });

  it("stays idle when disabled", () => {
    let created = false;
    const { result } = renderHook(() =>
      useTelemetryStream("run-1", false, {
        eventSourceFactory: (url: string) => {
          created = true;
          return new FakeEventSource(url) as unknown as EventSource;
        },
      }),
    );
    expect(created).toBe(false);
    expect(result.current.status).toBe("idle");
  });
});
