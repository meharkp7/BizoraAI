import { ProvenanceBadge } from "./ProvenanceBadge.tsx";
import type { TelemetryStatus } from "./useTelemetry.ts";
import { useTelemetryStream } from "./useTelemetry.ts";
import styles from "./TelemetryPanel.module.css";

function statusLabel(status: TelemetryStatus): string {
  if (status === "streaming") return "Live";
  if (status === "closed") return "Stream ended";
  if (status === "error") return "Stream error";
  if (status === "connecting") return "Connecting…";
  return "Idle";
}

function formatValue(value: number, unit: string | null): string {
  const text = Number.isInteger(value) ? String(value) : value.toPrecision(4);
  return unit === null || unit === "" ? text : `${text} ${unit}`;
}

/**
 * Live run-telemetry view: step progress, latest metric values, log
 * tail, and pack signals. Every live element is tagged Measured;
 * placeholders shown before data arrives are tagged Illustrative.
 *
 * Rendered for active runs on the run-detail page and for the
 * finished run inside RunPanel. `eventSourceFactory` is a test seam
 * and defaults to the native EventSource.
 */
export function TelemetryPanel({
  runId,
  enabled = true,
  eventSourceFactory,
}: {
  runId: string;
  enabled?: boolean;
  eventSourceFactory?: (url: string) => EventSource;
}) {
  const telemetry = useTelemetryStream(runId, enabled, { eventSourceFactory });
  const metricNames = Object.keys(telemetry.latestMetrics).sort();
  const latestStep = telemetry.steps[telemetry.steps.length - 1] ?? null;
  const hasData = telemetry.eventCount > 0;

  return (
    <section className={styles.panel} aria-label="Live run telemetry">
      <div className={styles.head}>
        <h2>Live telemetry</h2>
        <span className={styles.status}>{statusLabel(telemetry.status)}</span>
        {telemetry.runState !== null ? (
          <span className={`mono ${styles.runState}`}>{telemetry.runState}</span>
        ) : null}
      </div>

      {telemetry.error !== null ? (
        <p className={styles.error} role="alert">
          {telemetry.error}
        </p>
      ) : null}

      {!hasData ? (
        <p className={styles.placeholder}>
          <ProvenanceBadge
            provenance="illustrative"
            reason="Waiting for the first live event from this run."
          />{" "}
          Waiting for live telemetry…
        </p>
      ) : null}

      {latestStep !== null ? (
        <p className={styles.step}>
          <ProvenanceBadge provenance="measured" /> Step {latestStep.step_index}
          {latestStep.total_steps !== null ? ` of ${latestStep.total_steps}` : ""}
          {latestStep.label !== "" ? ` — ${latestStep.label}` : ""}
        </p>
      ) : null}

      {metricNames.length > 0 ? (
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Metric</th>
              <th scope="col">Latest</th>
              <th scope="col">Samples</th>
              <th scope="col">Source</th>
            </tr>
          </thead>
          <tbody>
            {metricNames.map((name) => {
              const sample = telemetry.latestMetrics[name];
              const count = telemetry.metricHistory[name]?.length ?? 0;
              return (
                <tr key={name}>
                  <td className="mono">{name}</td>
                  <td className="mono">{formatValue(sample.value, sample.unit)}</td>
                  <td className="mono">{count}</td>
                  <td>
                    <ProvenanceBadge provenance="measured" />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : null}

      {telemetry.packSignals.length > 0 ? (
        <>
          <h3 className={styles.subhead}>Pack signals</h3>
          <ul className={styles.signals}>
            {telemetry.packSignals.map((signal, index) => (
              <li key={`${signal.signal_id}-${index}`} className={styles.signal}>
                <ProvenanceBadge provenance="measured" />{" "}
                <span className="mono">{signal.label}</span>:{" "}
                <span className="mono">
                  {signal.values.map((value) => formatValue(value, signal.unit)).join(", ")}
                </span>
              </li>
            ))}
          </ul>
        </>
      ) : null}

      {telemetry.logs.length > 0 ? (
        <>
          <h3 className={styles.subhead}>Logs</h3>
          <ol className={styles.logs}>
            {telemetry.logs.map((log, index) => (
              <li key={`${log.message.slice(0, 48)}-${index}`}>
                <span className={`mono ${styles.level}`}>[{log.level}]</span> {log.message}
              </li>
            ))}
          </ol>
        </>
      ) : null}
    </section>
  );
}
