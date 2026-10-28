/* Telemetry stream contract types. Field names mirror the backend
   JSON verbatim; keep in sync with src/bizora/contracts/streaming.py.
   Rule zero: signal ids, metric names, and labels are free text from
   packs and adapters, never an enumerated vocabulary here. */

import type { RunState } from "../../lib/types.ts";

export type TelemetryEventKind = "step" | "metric" | "log" | "pack_signal" | "state";

export type VisualProvenance = "measured" | "assumed" | "illustrative";

export type TelemetryLogLevel = "debug" | "info" | "warning" | "error";

export interface TelemetryStep {
  step_index: number;
  label: string;
  total_steps: number | null;
}

export interface TelemetryMetricSample {
  metric_id: string;
  name: string;
  value: number;
  unit: string | null;
  step_index: number | null;
}

export interface TelemetryLogRecord {
  level: TelemetryLogLevel;
  message: string;
  step_index: number | null;
}

export interface PackSignalSample {
  signal_id: string;
  label: string;
  values: number[];
  unit: string | null;
  node_ids: string[];
}

export interface RunStatePayload {
  state: RunState;
  error: string | null;
}

export interface TelemetryEvent {
  run_id: string;
  seq: number;
  emitted_at: string;
  kind: TelemetryEventKind;
  provenance: VisualProvenance;
  step: TelemetryStep | null;
  metric: TelemetryMetricSample | null;
  log: TelemetryLogRecord | null;
  pack_signal: PackSignalSample | null;
  state: RunStatePayload | null;
}
