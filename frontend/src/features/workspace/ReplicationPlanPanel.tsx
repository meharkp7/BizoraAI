import { useState } from "react";
import { useReplicationPlan } from "../../app/queries.ts";
import styles from "./ReportedPanel.module.css";

function storageKey(projectId: string, graphId: string, version: number): string {
  return `bizora.replication.${projectId}::${graphId}::v${version}`;
}

function loadChecked(key: string): Set<number> {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return new Set();
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return new Set();
    return new Set(parsed.filter((value): value is number => typeof value === "number"));
  } catch {
    return new Set();
  }
}

/** Replication plan panel: the graph's ordered build-and-verify
 *  checklist. Checkmarks persist per graph revision in localStorage
 *  so a bench session survives reloads. */
export function ReplicationPlanPanel({
  projectId,
  graphId,
}: {
  projectId: string;
  graphId: string;
}) {
  const plan = useReplicationPlan(projectId, graphId);
  const version = plan.data?.version ?? 0;
  const [checked, setChecked] = useState<Set<number>>(new Set());
  const [loadedKey, setLoadedKey] = useState("");

  // Reload persisted checkmarks when the plan (or its revision) arrives.
  const key = version > 0 ? storageKey(projectId, graphId, version) : "";
  if (key !== "" && key !== loadedKey) {
    setLoadedKey(key);
    setChecked(loadChecked(key));
  }

  function toggle(seq: number): void {
    setChecked((current) => {
      const next = new Set(current);
      if (next.has(seq)) next.delete(seq);
      else next.add(seq);
      try {
        window.localStorage.setItem(
          storageKey(projectId, graphId, version),
          JSON.stringify([...next].sort((a, b) => a - b)),
        );
      } catch {
        // Private mode: checkmarks still work for this session.
      }
      return next;
    });
  }

  return (
    <section className={styles.panel} aria-label="Replication plan">
      <h2>Replication plan</h2>
      {plan.isPending ? (
        <p className={styles.hint}>Loading replication plan…</p>
      ) : plan.isError || !plan.data ? (
        <p className={styles.hint}>The replication plan is unavailable for this graph.</p>
      ) : plan.data.steps.length === 0 ? (
        <p className={styles.hint}>This graph has no nodes to plan.</p>
      ) : (
        <>
          <p className={styles.hint}>
            {checked.size} of {plan.data.steps.length} steps done · revision {plan.data.version}
          </p>
          <ol className={styles.list}>
            {plan.data.steps.map((step) => (
              <li key={step.seq} className={styles.item}>
                <label>
                  <input
                    type="checkbox"
                    checked={checked.has(step.seq)}
                    onChange={() => toggle(step.seq)}
                    aria-label={`Step ${step.seq}: ${step.label}`}
                  />{" "}
                  <strong>
                    {step.seq}. {step.action}
                  </strong>
                </label>
                <ul>
                  {step.verify.map((hint) => (
                    <li key={hint}>{hint}</li>
                  ))}
                </ul>
              </li>
            ))}
          </ol>
        </>
      )}
    </section>
  );
}
