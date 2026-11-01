import { useState } from "react";
import { usePaperWhatIf } from "../../app/queries.ts";
import { useWhatIfScenario } from "../../lib/store.ts";
import type { PaperWhatIfResponse } from "../../lib/types.ts";
import styles from "./WhatIfEditor.module.css";

interface PastRun {
  values: Record<string, string>;
  outcome: string;
  confidence: number;
  fromCache: boolean;
  basis: number;
}

/** One-line summary of what changed: `a: 1 → 2, b: x → y`. */
function describeChange(
  params: { label: string; value: string }[],
  values: Record<string, string>,
): string {
  return params
    .filter((param) => (values[param.label] ?? "") !== param.value)
    .map((param) => `${param.label}: ${param.value} → ${values[param.label] ?? ""}`)
    .join(", ");
}

/** Editable settings for one methodology step plus its estimated
 *  outcome. Renders definition rows for the Inspector's fact list:
 *  the parent keys this editor by node so switching steps resets it.
 *  Past runs accumulate below for comparison, and the current values
 *  can join a multi-node scenario. Estimates are labeled as such;
 *  nothing here is a measurement. */
export function WhatIfEditor({
  paperId,
  nodeId,
  nodeLabel,
  params,
}: {
  paperId: string;
  nodeId: string;
  nodeLabel: string;
  params: { label: string; value: string }[];
}) {
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(params.map((param) => [param.label, param.value])),
  );
  const [history, setHistory] = useState<PastRun[]>([]);
  const stageNode = useWhatIfScenario((state) => state.stageNode);
  const staged = useWhatIfScenario((state) =>
    state.staged.some((entry) => entry.paperId === paperId && entry.nodeId === nodeId),
  );
  const whatif = usePaperWhatIf(paperId);

  if (params.length === 0) {
    return (
      <div style={{ display: "contents" }}>
        <dt>Settings</dt>
        <dd>
          <span className={styles.note}>
            The paper states no settings for this step, so there is nothing to vary.
          </span>
        </dd>
      </div>
    );
  }

  const changed = params.some((param) => (values[param.label] ?? "") !== param.value);
  const valid = params.every((param) => (values[param.label] ?? "").trim() !== "");
  const data = whatif.data ?? null;
  const error =
    whatif.error instanceof Error ? whatif.error.message : whatif.error ? "What-if failed." : null;

  function reset(): void {
    whatif.reset();
    setValues(Object.fromEntries(params.map((param) => [param.label, param.value])));
  }

  return (
    <>
      {params.map((param) => (
        <div key={param.label} style={{ display: "contents" }}>
          <dt>{param.label}</dt>
          <dd>
            <input
              className={styles.input}
              aria-label={param.label}
              value={values[param.label] ?? ""}
              onChange={(event) =>
                setValues((current) => ({ ...current, [param.label]: event.target.value }))
              }
            />
          </dd>
        </div>
      ))}
      <div style={{ display: "contents" }}>
        <dt>What-if</dt>
        <dd>
          <div className={styles.actions}>
            <button
              type="button"
              disabled={!changed || !valid || whatif.isPending}
              onClick={() =>
                whatif.mutate(
                  { nodeId, params: values },
                  {
                    onSuccess: (response: PaperWhatIfResponse) =>
                      setHistory((current) => [
                        {
                          values: { ...values },
                          outcome: response.outcome,
                          confidence: response.confidence,
                          fromCache: response.from_cache,
                          basis: response.basis.length,
                        },
                        ...current,
                      ]),
                  },
                )
              }
            >
              {whatif.isPending ? "Estimating…" : "Run what-if"}
            </button>
            <button
              type="button"
              disabled={!changed || !valid}
              title="Stage these settings for a multi-node scenario run."
              onClick={() => stageNode({ paperId, nodeId, nodeLabel, params: { ...values } })}
            >
              {staged ? "Staged ✓" : "Stage"}
            </button>
            {(changed || data || error) && !whatif.isPending ? (
              <button type="button" onClick={reset}>
                Reset
              </button>
            ) : null}
          </div>
          {!valid ? (
            <span className={styles.note}>Settings must be non-empty to run.</span>
          ) : null}
          {error ? (
            <p className={styles.error} role="alert">
              {error}
            </p>
          ) : null}
          {data ? (
            <div className={styles.outcome} aria-live="polite">
              <p className={styles.outcomeText}>{data.outcome}</p>
              <p className={styles.estimateNote}>
                Estimated from the paper&apos;s stated numbers — not a measured result.
                {data.from_cache ? " Served from cache." : ""}
              </p>
              {data.basis.length > 0 ? (
                <ul className={styles.basis}>
                  {data.basis.map((entry, index) => (
                    <li key={`${entry.quote}-${index}`}>
                      &ldquo;{entry.quote}&rdquo;
                      {entry.page !== null ? ` (p. ${entry.page})` : ""}
                    </li>
                  ))}
                </ul>
              ) : null}
              {data.assumptions.length > 0 ? (
                <ul className={styles.assumptions}>
                  {data.assumptions.map((assumption) => (
                    <li key={assumption}>{assumption}</li>
                  ))}
                </ul>
              ) : null}
              <p className={styles.confidence}>
                Confidence {data.confidence.toFixed(2)}
              </p>
            </div>
          ) : null}
          {history.length > 1 ? (
            <div className={styles.history}>
              <p className={styles.historyHead}>Past runs this session ({history.length})</p>
              <ul className={styles.historyList}>
                {history.map((run, index) => (
                  <li key={`${run.outcome.slice(0, 24)}-${index}`}>
                    <span className={styles.historyChange}>
                      {describeChange(params, run.values) || "unchanged"}
                    </span>
                    <span className={styles.historyOutcome}>{run.outcome}</span>
                    <span className={styles.historyMeta}>
                      Confidence {run.confidence.toFixed(2)} · {run.basis} quote
                      {run.basis === 1 ? "" : "s"}
                      {run.fromCache ? " · cached" : ""}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </dd>
      </div>
    </>
  );
}
