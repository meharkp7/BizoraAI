import { useState } from "react";
import type { FormEvent } from "react";
import { useRunComparison } from "../../app/queries.ts";
import type { ComparisonVerdict } from "../../lib/types.ts";
import { EmptyState, ErrorState, LoadingState } from "../../components/states.tsx";
import { MeasuredVsReportedTable } from "./MeasuredVsReportedTable.tsx";
import styles from "./ComparePage.module.css";

function VerdictBadge({ verdict }: { verdict: ComparisonVerdict }) {
  return <span className={`${styles.verdict} ${styles[verdict]}`}>{verdict}</span>;
}

export function ComparePage() {
  const [baseline, setBaseline] = useState("");
  const [variant, setVariant] = useState("");
  const [submitted, setSubmitted] = useState<{ baseline: string; variant: string } | null>(null);

  const comparison = useRunComparison(
    submitted?.baseline ?? "",
    submitted?.variant ?? "",
    submitted !== null,
  );

  function compare(event: FormEvent): void {
    event.preventDefault();
    const base = baseline.trim();
    const varId = variant.trim();
    if (base && varId) setSubmitted({ baseline: base, variant: varId });
  }

  return (
    <div className={styles.page}>
      <h1>Compare runs</h1>
      <form className={styles.form} onSubmit={compare}>
        <label>
          Baseline run ID
          <input
            value={baseline}
            onChange={(event) => setBaseline(event.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
        </label>
        <label>
          Variant run ID
          <input
            value={variant}
            onChange={(event) => setVariant(event.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
        </label>
        <button type="submit" disabled={!baseline.trim() || !variant.trim()}>
          Compare
        </button>
      </form>

      {submitted === null ? (
        <EmptyState
          title="No comparison yet."
          detail="Enter two run IDs to compare measured results. Only valid comparisons report metric changes."
        />
      ) : comparison.isPending ? (
        <LoadingState label="Comparing runs…" />
      ) : comparison.isError ? (
        <ErrorState
          title="Could not compare runs."
          detail={comparison.error instanceof Error ? comparison.error.message : undefined}
          onRetry={() => void comparison.refetch()}
        />
      ) : (
        <section className={styles.result} aria-label="Comparison result">
          <div className={styles.head}>
            <VerdictBadge verdict={comparison.data.verdict} />
            <span className={styles.pair}>
              <span className="mono">{comparison.data.baseline_run_id}</span> vs{" "}
              <span className="mono">{comparison.data.variant_run_id}</span>
            </span>
          </div>

          {comparison.data.reasons.length > 0 ? (
            <ul className={styles.reasons}>
              {comparison.data.reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          ) : null}

          <p className={styles.hint}>
            Graphs:{" "}
            <span className="mono">
              {comparison.data.graph.baseline_graph_id} v
              {comparison.data.graph.baseline_graph_version}
            </span>{" "}
            vs{" "}
            <span className="mono">
              {comparison.data.graph.variant_graph_id} v
              {comparison.data.graph.variant_graph_version}
            </span>
          </p>

          {comparison.data.config_differences.length > 0 ? (
            <>
              <h2>Configuration differences</h2>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th scope="col">Field</th>
                    <th scope="col">Baseline</th>
                    <th scope="col">Variant</th>
                  </tr>
                </thead>
                <tbody>
                  {comparison.data.config_differences.map((difference) => (
                    <tr key={difference.field}>
                      <td className="mono">{difference.field}</td>
                      <td className="mono">{JSON.stringify(difference.baseline)}</td>
                      <td className="mono">{JSON.stringify(difference.variant)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : null}

          {comparison.data.metrics.length > 0 ? (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">Metric</th>
                  <th scope="col">Baseline</th>
                  <th scope="col">Variant</th>
                  <th scope="col">Change</th>
                </tr>
              </thead>
              <tbody>
                {comparison.data.metrics.map((metric) => (
                  <tr key={metric.name}>
                    <td className="mono">{metric.name}</td>
                    <td className="mono">{metric.baseline_value}</td>
                    <td className="mono">{metric.variant_value}</td>
                    <td className="mono">
                      {metric.absolute_change}
                      {metric.relative_change !== null
                        ? ` (${(metric.relative_change * 100).toFixed(1)}%)`
                        : ` (${metric.relative_undefined_reason})`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className={styles.hint}>No shared measured metrics to report.</p>
          )}

          <MeasuredVsReportedTable comparison={comparison.data} reported={[]} />

          {comparison.data.skipped_metrics.length > 0 ? (
            <>
              <h2>Skipped</h2>
              <ul className={styles.skipped}>
                {comparison.data.skipped_metrics.map((skipped) => (
                  <li key={skipped.name}>
                    <span className="mono">{skipped.name}</span>: {skipped.reason}
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </section>
      )}
    </div>
  );
}
