import { useQualitySummary } from "../../app/queries.ts";
import { EmptyState, ErrorState, LoadingState } from "../../components/states.tsx";
import styles from "./QualityPage.module.css";

function formatInstant(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function formatPercent(rate: number): string {
  return `${Math.round(rate * 100)}%`;
}

export function QualityPage() {
  const summary = useQualitySummary();

  if (summary.isPending) {
    return <LoadingState label="Loading extraction quality…" />;
  }
  if (summary.isError || !summary.data) {
    return (
      <ErrorState
        title="Could not load extraction quality."
        detail={summary.error instanceof Error ? summary.error.message : undefined}
        onRetry={() => void summary.refetch()}
      />
    );
  }

  const data = summary.data;
  const copilot = data.copilot_eval;
  return (
    <div className={styles.page}>
      <h1>Extraction quality</h1>
      <p className={styles.hint}>
        Last eval runs, not vibes. Generated {formatInstant(data.generated_at)}.
      </p>

      <section className={styles.card} aria-label="Copilot eval">
        <h2>Copilot answers</h2>
        {!copilot ? (
          <EmptyState
            title="Copilot eval has not run yet."
            detail="Scores appear here once tests/copilot_eval runs."
          />
        ) : (
          <dl className={styles.facts}>
            <div>
              <dt>Questions passed</dt>
              <dd>
                {copilot.passed} of {copilot.total}
              </dd>
            </div>
            <div>
              <dt>Citation accuracy</dt>
              <dd>{formatPercent(copilot.citation_accuracy)}</dd>
            </div>
            <div>
              <dt>Citation recall</dt>
              <dd>{formatPercent(copilot.citation_recall)}</dd>
            </div>
            <div>
              <dt>Writes detected</dt>
              <dd>{copilot.writes_detected ? "Yes" : "No"}</dd>
            </div>
            <div>
              <dt>Eval tokens</dt>
              <dd>
                {copilot.input_tokens.toLocaleString()} in /{" "}
                {copilot.output_tokens.toLocaleString()} out
              </dd>
            </div>
            <div>
              <dt>Recorded</dt>
              <dd>{formatInstant(copilot.recorded_at)}</dd>
            </div>
          </dl>
        )}
      </section>

      <section className={styles.card} aria-label="Diagram evals">
        <h2>Diagram extraction</h2>
        {data.diagram_evals.length === 0 ? (
          <EmptyState
            title="No diagram evals yet."
            detail="Per-paper reports appear here once scripts/eval_diagrams.py runs."
          />
        ) : (
          <div className={styles.scroll}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">Paper</th>
                  <th scope="col">Validators</th>
                  <th scope="col">Errors</th>
                  <th scope="col">Warnings</th>
                  <th scope="col">Tokens</th>
                  <th scope="col">Gold</th>
                  <th scope="col">Recorded</th>
                </tr>
              </thead>
              <tbody>
                {data.diagram_evals.map((entry) => (
                  <tr key={entry.paper_id}>
                    <td className="mono">{entry.paper_id}</td>
                    <td>{formatPercent(entry.validator_pass_rate)}</td>
                    <td>{entry.error_count}</td>
                    <td>{entry.warning_count}</td>
                    <td>
                      {(entry.input_tokens + entry.output_tokens).toLocaleString()} (
                      {entry.provider_calls} calls)
                    </td>
                    <td>{entry.gold_present ? "Compared" : "No gold set"}</td>
                    <td>{formatInstant(entry.recorded_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
