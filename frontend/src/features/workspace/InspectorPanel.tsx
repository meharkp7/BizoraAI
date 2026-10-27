import type { GraphEdge, GraphNode } from "../../lib/types.ts";
import styles from "./InspectorPanel.module.css";

function ProvenanceBadge({ value }: { value: string }) {
  return <span className={styles.badge}>{value}</span>;
}

export function InspectorPanel({
  node,
  edge,
  formatShape,
}: {
  node: GraphNode | null;
  edge: GraphEdge | null;
  formatShape: (shape: (number | null)[] | null) => string;
}) {
  if (!node && !edge) {
    return (
      <section className={styles.panel} aria-label="Inspector">
        <h2>Inspector</h2>
        <p className={styles.hint}>Select a component or connection to inspect it.</p>
      </section>
    );
  }

  if (edge) {
    return (
      <section className={styles.panel} aria-label="Inspector">
        <h2>Inspector</h2>
        <dl className={styles.facts}>
          <dt>Connection</dt>
          <dd className="mono">{edge.id}</dd>
          <dt>From</dt>
          <dd className="mono">{edge.source}</dd>
          <dt>To</dt>
          <dd className="mono">{edge.target}</dd>
          <dt>Relation</dt>
          <dd>{edge.relation}</dd>
          {edge.label ? (
            <>
              <dt>Label</dt>
              <dd>{edge.label}</dd>
            </>
          ) : null}
          <dt>Provenance</dt>
          <dd>
            <ProvenanceBadge value={edge.provenance} />
          </dd>
          <dt>Evidence</dt>
          <dd>{edge.evidence.length} reference(s)</dd>
        </dl>
      </section>
    );
  }

  if (!node) return null;
  const configEntries = Object.entries(node.config);
  return (
    <section className={styles.panel} aria-label="Inspector">
      <h2>Inspector</h2>
      <dl className={styles.facts}>
        <dt>Component</dt>
        <dd>{node.label}</dd>
        <dt>ID</dt>
        <dd className="mono">{node.id}</dd>
        <dt>Kind</dt>
        <dd>{node.kind}</dd>
        {node.description ? (
          <>
            <dt>About</dt>
            <dd>{node.description}</dd>
          </>
        ) : null}
        <dt>Input shape</dt>
        <dd className="mono">{formatShape(node.input_shape)}</dd>
        <dt>Output shape</dt>
        <dd className="mono">{formatShape(node.output_shape)}</dd>
        <dt>Provenance</dt>
        <dd>
          <ProvenanceBadge value={node.provenance} />
        </dd>
        <dt>Confidence</dt>
        <dd>{node.confidence === null ? "unknown" : node.confidence.toFixed(2)}</dd>
        <dt>Configuration</dt>
        <dd>
          {configEntries.length === 0 ? (
            "none"
          ) : (
            <ul className={styles.config}>
              {configEntries.map(([key, value]) => (
                <li key={key}>
                  <span className="mono">{key}</span>:{" "}
                  <span className="mono">{JSON.stringify(value) ?? "—"}</span>
                </li>
              ))}
            </ul>
          )}
        </dd>
      </dl>
    </section>
  );
}
