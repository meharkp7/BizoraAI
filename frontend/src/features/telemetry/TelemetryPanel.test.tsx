import { act, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TelemetryPanel } from "./TelemetryPanel.tsx";

/** Clearly-marked fake: an in-memory EventSource for panel tests. */
class FakeEventSource {
  url: string;
  closed = false;
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
}

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

describe("TelemetryPanel", () => {
  it("shows an illustrative placeholder before data arrives", () => {
    const sources: FakeEventSource[] = [];
    render(
      <TelemetryPanel
        runId="run-1"
        eventSourceFactory={(url: string) => {
          const source = new FakeEventSource(url);
          sources.push(source);
          return source as unknown as EventSource;
        }}
      />,
    );
    expect(screen.getByText("Waiting for live telemetry…")).toBeInTheDocument();
    expect(screen.getByText("Illustrative")).toBeInTheDocument();
  });

  it("tags live metrics, signals, and steps measured", async () => {
    let source: FakeEventSource | null = null;
    render(
      <TelemetryPanel
        runId="run-1"
        eventSourceFactory={(url: string) => {
          source = new FakeEventSource(url);
          return source as unknown as EventSource;
        }}
      />,
    );
    act(() => {
      source?.emit("metric", streamPayload(0, "metric", {
        metric: { metric_id: "m-1", name: "loss", value: 0.25, unit: null, step_index: 0 },
      }));
      source?.emit("pack_signal", streamPayload(1, "pack_signal", {
        pack_signal: { signal_id: "sig", label: "Signal", values: [3.3], unit: "V", node_ids: [] },
      }));
      source?.emit("log", streamPayload(2, "log", {
        log: { level: "info", message: "step finished", step_index: 0 },
      }));
    });
    expect(await screen.findByText("loss")).toBeInTheDocument();
    expect(screen.getByText("0.2500")).toBeInTheDocument();
    expect(screen.getByText("Signal")).toBeInTheDocument();
    expect(screen.getByText("step finished")).toBeInTheDocument();
    expect(screen.getAllByText("Measured").length).toBeGreaterThan(0);
    expect(screen.queryByText("Waiting for live telemetry…")).not.toBeInTheDocument();
  });

  it("reports honestly when the stream cannot open", async () => {
    render(
      <TelemetryPanel
        runId="run-1"
        eventSourceFactory={() => {
          throw new Error("EventSource is not defined");
        }}
      />,
    );
    expect(
      await screen.findByText("Live telemetry is unavailable in this browser."),
    ).toBeInTheDocument();
  });
});
