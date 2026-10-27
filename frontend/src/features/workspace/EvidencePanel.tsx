import type { EvidenceRef, GraphEdge, GraphNode } from "../../lib/types.ts";
import styles from "./EvidencePanel.module.css";

function locatorSummary(ref: EvidenceRef): string {
  const parts: string[] = [];
  if (ref.page !== null) parts.push(`p. ${ref.page}`);
  if (ref.figure_label) parts.push(ref.figure_label);
  if (ref.locator) parts.push(ref.locator);
  return parts.join(" · ") || "cited source";
}

export function EvidencePanel({
  node,
  edge,
}: {
  node: GraphNode | null;
  edge: GraphEdge | null;
}) {
  const refs = node?.evidence ?? edge?.evidence ?? [];
  return (
    <section className={styles.panel} aria-label="Evidence">
      <h2>Evidence</h2>
      {!node && !edge ? (
        <p className={styles.hint}>Evidence for the current selection appears here.</p>
      ) : refs.length === 0 ? (
        <p className={styles.hint}>
          No source references recorded for this selection. Treat its details as
          unverified.
        </p>
      ) : (
        <ul className={styles.list}>
          {refs.map((ref, index) => (
            <li key={`${ref.source_id}-${index}`} className={styles.item}>
              <div className={styles.head}>
                <span className="mono">{ref.source_id}</span>
                <span className={styles.status}>{ref.status}</span>
              </div>
              <div className={styles.locator}>{locatorSummary(ref)}</div>
              {ref.quote ? <blockquote className={styles.quote}>{ref.quote}</blockquote> : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
