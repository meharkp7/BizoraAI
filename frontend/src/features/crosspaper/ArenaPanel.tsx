import { useState } from "react";
import type { FormEvent } from "react";
import { useArenaComparison } from "../../app/queries.ts";
import { EmptyState, ErrorState, LoadingState } from "../../components/states.tsx";
import type { ArenaComparison } from "../../lib/types.ts";
import styles from "./CrossPaperPage.module.css";
import { trayKey, type TrayEntry } from "./tray.ts";

function metricText(value: { raw_value: string } | null): string {
  return value ? value.raw_value : "—";
}

function ArenaResult({ comparison }: { comparison: ArenaComparison }) {
  const kinds = Array.from(
    new Set([
      ...Object.keys(comparison.structure_a.kinds),
      ...Object.keys(comparison.structure_b.kinds),
    ]),
  ).sort();
  return (
    <div className={styles.arenaResult}>
      <section className={styles.card} aria-label="Structure">
        <h3>
          Structure: {comparison.a.title} vs {comparison.b.title}
        </h3>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Kind</th>
              <th scope="col">{comparison.a.title}</th>
              <th scope="col">{comparison.b.title}</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">Nodes</th>
              <td>{comparison.structure_a.node_count}</td>
              <td>{comparison.structure_b.node_count}</td>
            </tr>
            <tr>
              <th scope="row">Edges</th>
              <td>{comparison.structure_a.edge_count}</td>
              <td>{comparison.structure_b.edge_count}</td>
            </tr>
            {kinds.map((kind) => (
              <tr key={kind}>
                <th scope="row">{kind}</th>
                <td>{comparison.structure_a.kinds[kind] ?? 0}</td>
                <td>{comparison.structure_b.kinds[kind] ?? 0}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className={styles.card} aria-label="Shared entities">
        <h3>Shared entities ({comparison.shared_labels.length})</h3>
        {comparison.shared_labels.length === 0 ? (
          <p className={styles.hint}>No entity labels appear on both sides.</p>
        ) : (
          <ul className={styles.plain}>
            {comparison.shared_labels.map((entry) => (
              <li key={entry.label}>
                {entry.label}{" "}
                <span className={styles.meta}>
                  ({entry.a_node_ids.join(", ")} vs {entry.b_node_ids.join(", ")})
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className={styles.card} aria-label="Reported metrics">
        <h3>Reported metrics ({comparison.metrics.length})</h3>
        {comparison.metrics.length === 0 ? (
          <p className={styles.hint}>Neither paper reports numeric results.</p>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Metric</th>
                <th scope="col">{comparison.a.title}</th>
                <th scope="col">{comparison.b.title}</th>
              </tr>
            </thead>
            <tbody>
              {comparison.metrics.map((row) => (
                <tr key={row.name}>
                  <th scope="row">{row.name}</th>
                  <td>{metricText(row.a)}</td>
                  <td>{metricText(row.b)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

export function ArenaPanel({ tray }: { tray: TrayEntry[] }) {
  const [sideA, setSideA] = useState("");
  const [sideB, setSideB] = useState("");
  const [submitted, setSubmitted] = useState<{ a: string; b: string } | null>(null);

  const byKey = new Map(tray.map((entry) => [trayKey(entry), entry]));
  const submittedA = submitted ? (byKey.get(submitted.a) ?? null) : null;
  const submittedB = submitted ? (byKey.get(submitted.b) ?? null) : null;
  const comparison = useArenaComparison(submittedA, submittedB, submitted !== null);

  function compare(event: FormEvent): void {
    event.preventDefault();
    if (sideA && sideB && sideA !== sideB) setSubmitted({ a: sideA, b: sideB });
  }

  if (tray.length < 2) {
    return (
      <EmptyState
        title="Add two graphs to the tray to compare them."
        detail="The arena lines up structure, shared entities, and reported numbers."
      />
    );
  }

  return (
    <div className={styles.arena}>
      <form className={styles.arenaForm} onSubmit={compare} aria-label="Pick arena sides">
        <label>
          Side A
          <select value={sideA} onChange={(event) => setSideA(event.target.value)}>
            <option value="">Choose a graph…</option>
            {tray.map((entry) => (
              <option key={trayKey(entry)} value={trayKey(entry)}>
                {entry.title}
              </option>
            ))}
          </select>
        </label>
        <label>
          Side B
          <select value={sideB} onChange={(event) => setSideB(event.target.value)}>
            <option value="">Choose a graph…</option>
            {tray.map((entry) => (
              <option key={trayKey(entry)} value={trayKey(entry)}>
                {entry.title}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" disabled={!sideA || !sideB || sideA === sideB}>
          Compare
        </button>
      </form>

      {comparison.isPending && submitted ? (
        <LoadingState label="Comparing graphs…" />
      ) : null}
      {comparison.isError ? (
        <ErrorState
          title="Could not compare the graphs."
          detail={comparison.error instanceof Error ? comparison.error.message : undefined}
          onRetry={() => void comparison.refetch()}
        />
      ) : null}
      {comparison.data ? <ArenaResult comparison={comparison.data} /> : null}
    </div>
  );
}
