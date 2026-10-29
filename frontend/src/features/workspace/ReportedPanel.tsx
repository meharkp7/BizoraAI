import { useState } from "react";
import { useGraphReportedMetrics } from "../../app/queries.ts";
import styles from "./ReportedPanel.module.css";

function locatorSummary(tableId: string | null, page: number | null): string | null {
  const parts: string[] = [];
  if (tableId) parts.push(tableId);
  if (page !== null) parts.push(`p. ${page}`);
  return parts.length > 0 ? parts.join(" · ") : null;
}

/** Reported-results panel: the paper's own numbers from its tables,
 *  labelled "reported by paper". The baseline Stage 2 measured
 *  results will be compared against; no simulated numbers appear. */
export function ReportedPanel({
  projectId,
  graphId,
}: {
  projectId: string;
  graphId: string;
}) {
  const reported = useGraphReportedMetrics(projectId, graphId);
  const [filter, setFilter] = useState("");
  const entries = reported.data ?? [];
  const needle = filter.trim().toLowerCase();
  const visible =
    needle === ""
      ? entries
      : entries.filter((entry) => entry.name.toLowerCase().includes(needle));

  return (
    <section className={styles.panel} aria-label="Reported results">
      <h2>Reported results</h2>
      {reported.isPending ? (
        <p className={styles.hint}>Loading reported numbers…</p>
      ) : reported.isError ? (
        <p className={styles.hint}>Reported numbers are unavailable for this graph.</p>
      ) : entries.length === 0 ? (
        <p className={styles.hint}>
          No reported numbers in this graph&apos;s tables. Numbers appear here once
          results tables are extracted.
        </p>
      ) : (
        <>
          <input
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder="Filter metrics"
            aria-label="Filter reported metrics"
            autoComplete="off"
            spellCheck={false}
            className={styles.filter}
          />
          {visible.length === 0 ? (
            <p className={styles.hint}>No reported metrics match this filter.</p>
          ) : (
            <ul className={styles.list}>
              {visible.map((entry, index) => (
                <li key={`${entry.name}-${entry.locator ?? index}`} className={styles.item}>
                  <div className={styles.head}>
                    <span className={styles.name}>{entry.name}</span>
                    <span className={styles.tag}>reported by paper</span>
                  </div>
                  <div className={styles.value}>
                    {entry.raw_value}
                    {entry.unit ? ` ${entry.unit}` : ""}
                  </div>
                  {locatorSummary(entry.table_id, entry.page) ?? entry.locator ? (
                    <div className={styles.locator} title={entry.locator ?? undefined}>
                      {locatorSummary(entry.table_id, entry.page) ?? entry.locator}
                    </div>
                  ) : null}
                  {entry.quote ? (
                    <blockquote className={styles.quote}>{entry.quote}</blockquote>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
