import { useMemo } from "react";
import type { RunComparison } from "../../lib/types.ts";
import { ProvenanceBadge } from "../telemetry/ProvenanceBadge.tsx";
import type { PaperReportedMetric } from "./reportedTypes.ts";
import { buildReportedRows, formatReportedSource } from "./reportedView.ts";
import styles from "./MeasuredVsReportedTable.module.css";

/**
 * Baseline-vs-variant table with the paper's own reported numbers in
 * a separate column. Measured cells (ours, from real runs) are tagged
 * Measured; reported cells (theirs, quoted with evidence) are tagged
 * Assumed-comparable, because treating them as directly comparable
 * assumes matching datasets and conditions the UI cannot verify.
 *
 * Rendered inside ComparePage next to the measured comparison.
 * Reported entries come from the baseline run's graph tables via the
 * run reported-metrics endpoint; an empty list honestly reports that
 * no paper numbers are linked for these metrics.
 */
export function MeasuredVsReportedTable({
  comparison,
  reported,
}: {
  comparison: RunComparison;
  reported: readonly PaperReportedMetric[];
}) {
  const rows = useMemo(
    () => buildReportedRows(comparison, reported),
    [comparison, reported],
  );

  return (
    <section className={styles.panel} aria-label="Measured versus paper-reported">
      <h2>Measured vs paper-reported</h2>
      <p className={styles.hint}>
        Measured values come from real runs. Paper-reported values are quoted
        with their evidence and kept separate.
      </p>
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">Metric</th>
            <th scope="col">
              Baseline <ProvenanceBadge provenance="measured" />
            </th>
            <th scope="col">
              Variant <ProvenanceBadge provenance="measured" />
            </th>
            <th scope="col">
              Paper-reported{" "}
              <ProvenanceBadge
                provenance="assumed"
                reason="Assumed comparable: verify the paper's dataset and conditions match this run."
              />
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.name}>
              <td className="mono">{row.name}</td>
              <td className="mono">
                {row.baseline_measured === null ? "—" : row.baseline_measured}
              </td>
              <td className="mono">
                {row.variant_measured === null ? "—" : row.variant_measured}
              </td>
              <td>
                {row.reported.length === 0 ? (
                  <span className={styles.none}>—</span>
                ) : (
                  <ul className={styles.reported}>
                    {row.reported.map((entry, index) => (
                      <li key={`${entry.source_id}-${entry.raw_value}-${index}`}>
                        <span className="mono">
                          {entry.raw_value}
                          {entry.unit !== null && entry.unit !== "" ? ` ${entry.unit}` : ""}
                        </span>{" "}
                        <span
                          className={styles.source}
                          title={entry.locator ?? undefined}
                        >
                          ({formatReportedSource(entry)})
                        </span>
                        {entry.quote !== null ? (
                          <span className={styles.quote}>“{entry.quote}”</span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {reported.length === 0 ? (
        <p className={styles.hint}>No paper-reported numbers linked yet.</p>
      ) : null}
    </section>
  );
}
