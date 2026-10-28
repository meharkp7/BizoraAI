/* Native EventSource client for the run-telemetry SSE stream.
   No dependencies beyond the DOM: parsing and URL building are pure
   and unit-tested, and the EventSource constructor is injectable so
   tests never need a network connection. */

import type { TelemetryEvent, TelemetryEventKind } from "./telemetryTypes.ts";

const EVENT_KINDS: readonly TelemetryEventKind[] = [
  "step",
  "metric",
  "log",
  "pack_signal",
  "state",
];

/** SSE endpoint for one run, resuming after `fromSeq`. */
export function telemetryStreamUrl(runId: string, fromSeq = 0): string {
  const base = import.meta.env.VITE_API_BASE_URL ?? "";
  return `${base}/api/v1/experiments/runs/${encodeURIComponent(runId)}/telemetry/stream?from_seq=${fromSeq}`;
}

function isTelemetryEventKind(value: unknown): value is TelemetryEventKind {
  return (
    typeof value === "string" &&
    (EVENT_KINDS as readonly string[]).includes(value)
  );
}

/** Parse one SSE `data` payload; null when malformed (never throws). */
export function parseTelemetryEvent(data: string): TelemetryEvent | null {
  let value: unknown;
  try {
    value = JSON.parse(data) as unknown;
  } catch {
    return null;
  }
  if (typeof value !== "object" || value === null) return null;
  const event = value as Record<string, unknown>;
  if (typeof event["run_id"] !== "string") return null;
  if (typeof event["seq"] !== "number" || !Number.isInteger(event["seq"])) {
    return null;
  }
  if (typeof event["emitted_at"] !== "string") return null;
  if (!isTelemetryEventKind(event["kind"])) return null;
  return value as TelemetryEvent;
}

/** True for lifecycle states that end the stream. */
export function isTerminalState(state: string): boolean {
  return state === "succeeded" || state === "failed" || state === "cancelled";
}

export interface TelemetryStreamHandlers {
  onEvent(event: TelemetryEvent): void;
  onError?(cause: unknown): void;
  onOpenError?(cause: unknown): void;
}

export interface TelemetryStreamOptions {
  fromSeq?: number;
  eventSourceFactory?: (url: string) => EventSource;
}

/**
 * Open the telemetry stream for one run. Returns a close function.
 * The caller closes on unmount and when a terminal state arrives.
 */
export function openTelemetryStream(
  runId: string,
  handlers: TelemetryStreamHandlers,
  options: TelemetryStreamOptions = {},
): () => void {
  const url = telemetryStreamUrl(runId, options.fromSeq ?? 0);
  const factory = options.eventSourceFactory ?? ((target: string) => new EventSource(target));
  let source: EventSource;
  try {
    source = factory(url);
  } catch (cause) {
    handlers.onOpenError?.(cause);
    return () => {};
  }
  const onMessage = (message: MessageEvent): void => {
    const event = parseTelemetryEvent(String(message.data));
    if (event !== null) handlers.onEvent(event);
  };
  for (const kind of EVENT_KINDS) source.addEventListener(kind, onMessage);
  source.onerror = (cause: unknown): void => {
    handlers.onError?.(cause);
  };
  return () => source.close();
}
