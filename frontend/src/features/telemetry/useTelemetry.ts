import { useEffect, useState } from "react";
import type { RunState } from "../../lib/types.ts";
import { isTerminalState, openTelemetryStream } from "./sseClient.ts";
import type {
  PackSignalSample,
  TelemetryLogRecord,
  TelemetryMetricSample,
  TelemetryStep,
} from "./telemetryTypes.ts";

export type TelemetryStatus = "idle" | "connecting" | "streaming" | "closed" | "error";

export interface TelemetrySnapshot {
  status: TelemetryStatus;
  error: string | null;
  eventCount: number;
  latestSeq: number | null;
  steps: TelemetryStep[];
  latestMetrics: Record<string, TelemetryMetricSample>;
  metricHistory: Record<string, number[]>;
  logs: TelemetryLogRecord[];
  packSignals: PackSignalSample[];
  runState: RunState | null;
}

export interface UseTelemetryOptions {
  fromSeq?: number;
  maxLogs?: number;
  maxHistory?: number;
  eventSourceFactory?: (url: string) => EventSource;
}

const DEFAULT_MAX_LOGS = 200;
const DEFAULT_MAX_HISTORY = 500;

const INITIAL: TelemetrySnapshot = {
  status: "idle",
  error: null,
  eventCount: 0,
  latestSeq: null,
  steps: [],
  latestMetrics: {},
  metricHistory: {},
  logs: [],
  packSignals: [],
  runState: null,
};

/**
 * Subscribe to one run's live telemetry. Accumulates bounded step,
 * metric, log, and pack-signal views; closes itself on terminal
 * state and on unmount. Safe under StrictMode double-mounting.
 *
 * Options are read as primitives so callers may pass inline objects
 * without resubscribing; only `eventSourceFactory` must be stable.
 */
export function useTelemetryStream(
  runId: string,
  enabled = true,
  options: UseTelemetryOptions = {},
): TelemetrySnapshot {
  const fromSeq = options.fromSeq ?? 0;
  const logCap = options.maxLogs ?? DEFAULT_MAX_LOGS;
  const historyCap = options.maxHistory ?? DEFAULT_MAX_HISTORY;
  const eventSourceFactory = options.eventSourceFactory;
  const [snapshot, setSnapshot] = useState<TelemetrySnapshot>(INITIAL);
  const [tracked, setTracked] = useState({ runId, enabled });
  const active = enabled && runId !== "";
  // Render-phase reset (React-endorsed derived-state pattern): a new
  // run or a re-enabled subscription starts from empty state so stale
  // events never mix with the new stream.
  if (tracked.runId !== runId || tracked.enabled !== enabled) {
    setTracked({ runId, enabled });
    setSnapshot(INITIAL);
  }

  useEffect(() => {
    if (!active) return;
    let close: (() => void) | null = null;
    let finished = false;

    const finish = (status: TelemetryStatus): void => {
      finished = true;
      setSnapshot((current) => ({ ...current, status }));
      close?.();
    };

    close = openTelemetryStream(
      runId,
      {
        onEvent: (event) => {
          if (finished) return;
          setSnapshot((current) => {
            const next: TelemetrySnapshot = {
              ...current,
              status: current.status === "idle" ? "streaming" : current.status,
              eventCount: current.eventCount + 1,
              latestSeq: event.seq,
            };
            if (event.step !== null) {
              next.steps = [...current.steps, event.step].slice(-historyCap);
            }
            if (event.metric !== null) {
              const sample = event.metric;
              next.latestMetrics = { ...current.latestMetrics, [sample.name]: sample };
              next.metricHistory = {
                ...current.metricHistory,
                [sample.name]: [...(current.metricHistory[sample.name] ?? []), sample.value].slice(
                  -historyCap,
                ),
              };
            }
            if (event.log !== null) {
              next.logs = [...current.logs, event.log].slice(-logCap);
            }
            if (event.pack_signal !== null) {
              next.packSignals = [...current.packSignals, event.pack_signal].slice(-historyCap);
            }
            if (event.state !== null) {
              next.runState = event.state.state;
              if (isTerminalState(event.state.state)) {
                next.status = "closed";
              }
            }
            return next;
          });
          if (
            event.state !== null &&
            isTerminalState(event.state.state) &&
            !finished
          ) {
            finish("closed");
          }
        },
        onError: () => {
          if (finished) return;
          setSnapshot((current) => ({
            ...current,
            error: "The telemetry stream disconnected.",
          }));
          finish("error");
        },
      },
      { fromSeq, eventSourceFactory },
    );
    return () => {
      finished = true;
      close?.();
    };
  }, [runId, active, fromSeq, logCap, historyCap, eventSourceFactory]);

  if (!active) return INITIAL;
  if (snapshot.status === "idle") return { ...snapshot, status: "connecting" };
  return snapshot;
}
