import { useState } from "react";
import { api, BizoraApiError } from "../../lib/api.ts";
import { useWhatIfScenario } from "../../lib/store.ts";
import type { PaperWhatIfResponse } from "../../lib/types.ts";
import styles from "./ScenarioPanel.module.css";

interface ScenarioResult {
  nodeId: string;
  nodeLabel: string;
  outcome: PaperWhatIfResponse | null;
  error: string | null;
}

/** Multi-node what-if scenarios: steps staged from their Inspectors run
 *  together and report side by side. Each outcome is still estimated
 *  independently per step (that is what the endpoint computes); the
 *  panel says so. */
export function ScenarioPanel({ paperId }: { paperId: string }) {
  const staged = useWhatIfScenario((state) => state.staged);
  const unstageNode = useWhatIfScenario((state) => state.unstageNode);
  const clearScenario = useWhatIfScenario((state) => state.clearScenario);
  const [results, setResults] = useState<ScenarioResult[] | null>(null);
  const [running, setRunning] = useState(false);
  const mine = staged.filter((entry) => entry.paperId === paperId);
  if (mine.length === 0 && results === null) return null;

  async function runAll(): Promise<void> {
    setRunning(true);
    try {
      const settled = await Promise.all(
        mine.map(async (entry): Promise<ScenarioResult> => {
          try {
            const outcome = await api.runPaperWhatIf(paperId, entry.nodeId, entry.params);
            return { nodeId: entry.nodeId, nodeLabel: entry.nodeLabel, outcome, error: null };
          } catch (thrown) {
            return {
              nodeId: entry.nodeId,
              nodeLabel: entry.nodeLabel,
              outcome: null,
              error:
                thrown instanceof BizoraApiError
                  ? `${thrown.code}: ${thrown.message}`
                  : "What-if failed.",
            };
          }
        }),
      );
      setResults(settled);
    } finally {
      setRunning(false);
    }
  }

  return (
    <section className={styles.panel} aria-label="What-if scenario">
      <div className={styles.head}>
        <h3>Scenario ({mine.length} step{mine.length === 1 ? "" : "s"})</h3>
        <div className={styles.actions}>
          <button type="button" disabled={mine.length === 0 || running} onClick={() => void runAll()}>
            {running ? "Estimating…" : "Run all"}
          </button>
          <button
            type="button"
            disabled={mine.length === 0}
            onClick={() => {
              clearScenario(paperId);
              setResults(null);
            }}
          >
            Clear
          </button>
        </div>
      </div>
      <p className={styles.note}>
        Stage steps from their Inspectors, then run them together. Each outcome is
        estimated independently per step — never a measured result.
      </p>
      {mine.length > 0 ? (
        <ul className={styles.staged}>
          {mine.map((entry) => (
            <li key={entry.nodeId}>
              <span className={styles.stagedLabel}>{entry.nodeLabel}</span>
              <span className={styles.stagedParams}>
                {Object.entries(entry.params)
                  .map(([key, value]) => `${key}: ${value}`)
                  .join(", ")}
              </span>
              <button type="button" onClick={() => unstageNode(paperId, entry.nodeId)}>
                Remove
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {results !== null ? (
        <ul className={styles.results}>
          {results.map((result) => (
            <li key={result.nodeId}>
              <span className={styles.stagedLabel}>{result.nodeLabel}</span>
              {result.outcome ? (
                <>
                  <span className={styles.outcome}>{result.outcome.outcome}</span>
                  <span className={styles.meta}>
                    Confidence {result.outcome.confidence.toFixed(2)} ·{" "}
                    {result.outcome.basis.length} quote
                    {result.outcome.basis.length === 1 ? "" : "s"}
                    {result.outcome.from_cache ? " · cached" : ""}
                  </span>
                </>
              ) : (
                <span className={styles.error} role="alert">
                  {result.error}
                </span>
              )}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
