import { useState } from "react";
import type { GraphEdge, GraphNode } from "../../lib/types.ts";
import styles from "./InspectorPanel.module.css";

function ProvenanceBadge({ value }: { value: string }) {
  return <span className={`${styles.badge} ${styles[value] ?? ""}`}>{value}</span>;
}

function SelectionHead({
  eyebrow,
  title,
  detail,
}: {
  eyebrow: string;
  title: string;
  detail: string;
}) {
  return (
    <div className={styles.head}>
      <div className={styles.eyebrow}>{eyebrow}</div>
      <div className={styles.title}>{title}</div>
      <div className={`${styles.detail} mono`}>{detail}</div>
    </div>
  );
}

function ConfigEditor({
  node,
  disabled,
  onApply,
}: {
  node: GraphNode;
  disabled: boolean;
  onApply: (config: Record<string, unknown>) => void;
}) {
  const [text, setText] = useState(() => JSON.stringify(node.config, null, 2));
  const [error, setError] = useState<string | null>(null);

  function apply(): void {
    let parsed: unknown;
    try {
      parsed = JSON.parse(text) as unknown;
    } catch {
      setError("Configuration must be valid JSON.");
      return;
    }
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      setError("Configuration must be a JSON object.");
      return;
    }
    setError(null);
    onApply(parsed as Record<string, unknown>);
  }

  return (
    <div className={styles.editor}>
      <textarea
        value={text}
        onChange={(event) => setText(event.target.value)}
        rows={5}
        spellCheck={false}
        aria-label="Node configuration JSON"
        disabled={disabled}
      />
      <div className={styles.editorRow}>
        <button type="button" onClick={apply} disabled={disabled}>
          Apply configuration
        </button>
        <span className={styles.mergeNote}>Merges into existing keys.</span>
      </div>
      {error ? (
        <p className={styles.editorError} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function InspectorPanel({
  node,
  edge,
  formatShape,
  disabled,
  onUpdateConfig,
}: {
  node: GraphNode | null;
  edge: GraphEdge | null;
  formatShape: (shape: (number | null)[] | null) => string;
  disabled?: boolean;
  onUpdateConfig?: (config: Record<string, unknown>) => void;
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
        <SelectionHead
          eyebrow={`Connection · ${edge.relation}`}
          title={`${edge.source} → ${edge.target}`}
          detail={edge.id}
        />
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
      <SelectionHead
        eyebrow={`Component · ${node.kind}`}
        title={node.label}
        detail={node.id}
      />
      <dl className={styles.facts}>
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
      {onUpdateConfig ? (
        <ConfigEditor
          key={node.id}
          node={node}
          disabled={disabled === true}
          onApply={onUpdateConfig}
        />
      ) : null}
    </section>
  );
}
