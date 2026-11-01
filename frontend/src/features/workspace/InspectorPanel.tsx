import { useState } from "react";
import { NODE_KINDS } from "../../lib/constants.ts";
import type {
  EntityResolution,
  GraphEdge,
  GraphNode,
  NodeKind,
  RemovalPreflight,
} from "../../lib/types.ts";
import { SymbolGlyph } from "../canvas/SymbolGlyph.tsx";
import { categoryLabel, domainLabel, prettyEntityType, symbolLabel } from "../canvas/graph3d.ts";
import { ProvenanceTag } from "../diagrams/ProvenanceTag.tsx";
import type { DiagramSelection } from "../diagrams/selection.ts";
import type { NodeReplacement } from "./patchBuilders.ts";
import { WhatIfEditor } from "./WhatIfEditor.tsx";
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

function ReplaceForm({
  node,
  disabled,
  onReplace,
}: {
  node: GraphNode;
  disabled: boolean;
  onReplace: (replacement: NodeReplacement) => void;
}) {
  const [kind, setKind] = useState<NodeKind>(node.kind);
  const [label, setLabel] = useState(node.label);
  const [description, setDescription] = useState(node.description ?? "");
  const [configText, setConfigText] = useState(() => JSON.stringify(node.config, null, 2));
  const [error, setError] = useState<string | null>(null);

  function replace(): void {
    if (!label.trim()) {
      setError("A replacement label is required.");
      return;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(configText) as unknown;
    } catch {
      setError("Configuration must be valid JSON.");
      return;
    }
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      setError("Configuration must be a JSON object.");
      return;
    }
    setError(null);
    onReplace({
      kind,
      label: label.trim(),
      description: description.trim() === "" ? null : description.trim(),
      config: parsed as Record<string, unknown>,
    });
  }

  return (
    <form
      className={styles.replaceForm}
      aria-label="Replace component"
      onSubmit={(event) => {
        event.preventDefault();
        replace();
      }}
    >
      <h3>Replace component</h3>
      <label>
        Kind
        <select
          value={kind}
          onChange={(event) => setKind(event.target.value as NodeKind)}
          disabled={disabled}
        >
          {NODE_KINDS.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>
      <label>
        Label
        <input
          value={label}
          onChange={(event) => setLabel(event.target.value)}
          autoComplete="off"
          spellCheck={false}
          disabled={disabled}
        />
      </label>
      <label>
        Description
        <textarea
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          rows={2}
          spellCheck={false}
          disabled={disabled}
        />
      </label>
      <label>
        Configuration JSON
        <textarea
          value={configText}
          onChange={(event) => setConfigText(event.target.value)}
          rows={4}
          spellCheck={false}
          aria-label="Replacement configuration JSON"
          disabled={disabled}
        />
      </label>
      <div className={styles.editorRow}>
        <button type="submit" disabled={disabled}>
          Replace component
        </button>
        <span className={styles.mergeNote}>Keeps the ID, so connections survive.</span>
      </div>
      {error ? (
        <p className={styles.editorError} role="alert">
          {error}
        </p>
      ) : null}
    </form>
  );
}

export function InspectorPanel({
  node,
  edge,
  formatShape,
  disabled,
  onUpdateConfig,
  onReplaceNode,
  entity,
  entityError = null,
  removal = null,
  removalPending = false,
  removalError = null,
  nodeLabels = {},
  onPreviewRemoval,
  onClearRemoval,
  diagram = null,
  paperId = null,
}: {
  node: GraphNode | null;
  edge: GraphEdge | null;
  /** A clicked diagram element; graph selection stays empty while set. */
  diagram?: DiagramSelection | null;
  /** Source paper for diagram what-if runs; null hides the editor. */
  paperId?: string | null;
  formatShape: (shape: (number | null)[] | null) => string;
  disabled?: boolean;
  onUpdateConfig?: (config: Record<string, unknown>) => void;
  onReplaceNode?: (replacement: NodeReplacement) => void;
  entity?: EntityResolution | null;
  entityError?: string | null;
  removal?: RemovalPreflight | null;
  removalPending?: boolean;
  removalError?: string | null;
  nodeLabels?: Record<string, string>;
  onPreviewRemoval?: (nodeId: string) => void;
  onClearRemoval?: () => void;
}) {
  if (!node && !edge) {
    if (diagram) return <DiagramInspector diagram={diagram} paperId={paperId} />;
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
        <dt>System entity</dt>
        <dd>
          {entityError ? (
            <span className={styles.entityNote} role="alert">
              Identities unavailable ({entityError}); restart the backend and retry.
            </span>
          ) : entity ? (
            <>
              {entity.generic ? (
                <span className={styles.badge}>generic placeholder</span>
              ) : (
                <span>
                  {entity.display_label} · {prettyEntityType(entity.entity_type)}
                </span>
              )}{" "}
              <span className={styles.entityMeta}>
                <SymbolGlyph symbol={entity.symbol || "generic"} />{" "}
                {domainLabel(entity.domain)} · {categoryLabel(entity.category)} ·{" "}
                {symbolLabel(entity.symbol || "generic")} ·{" "}
                {entity.physical === false ? "Process" : "Structure"} ·{" "}
                {Math.round(entity.confidence * 100)}%
              </span>
              {entity.generic ? (
                <span className={styles.entityNote}>
                  The paper does not name an exact part here; the 3D view only shows catalog
                  part models.
                </span>
              ) : null}
              {entity.interfaces.length > 0 ? (
                <span className={styles.entityMeta}>
                  Interfaces:{" "}
                  {entity.interfaces
                    .map((iface) =>
                      Object.keys(iface.params).length === 0
                        ? iface.kind
                        : `${iface.kind} (${Object.entries(iface.params)
                            .map(([key, value]) => `${key}=${value}`)
                            .join(", ")})`,
                    )
                    .join(" · ")}
                </span>
              ) : null}
              {entity.matched_terms.length > 0 ? (
                <span className={styles.entityMeta}>
                  Grounded by: {entity.matched_terms.join(", ")}
                </span>
              ) : null}
            </>
          ) : (
            "resolving…"
          )}
        </dd>
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
      {onReplaceNode ? (
        <ReplaceForm
          key={`replace-${node.id}`}
          node={node}
          disabled={disabled === true}
          onReplace={onReplaceNode}
        />
      ) : null}
      {onPreviewRemoval ? (
        <div className={styles.editor}>
          <h3 className={styles.title}>What-if: remove this block</h3>
          <p className={styles.hint}>
            Graph-level preflight only — nothing is changed. Shows connected blocks,
            dropped connections, and paper claims tied to this block.
          </p>
          <div className={styles.editorRow}>
            <button
              type="button"
              disabled={disabled === true || removalPending}
              onClick={() => onPreviewRemoval(node.id)}
            >
              {removalPending ? "Checking…" : "Preview removal"}
            </button>
            {removal || removalError ? (
              <button type="button" onClick={() => onClearRemoval?.()}>
                Clear
              </button>
            ) : null}
          </div>
          {removalError ? (
            <p className={styles.editorError} role="alert">
              {removalError}
            </p>
          ) : null}
          {removal && removal.target_node_id === node.id ? (
            <dl className={styles.facts}>
              <dt>Connected blocks</dt>
              <dd>
                {removal.neighbor_node_ids.length === 0
                  ? "none — this block is isolated"
                  : removal.neighbor_node_ids
                      .map((id) => nodeLabels[id] ?? id)
                      .join(", ")}
              </dd>
              <dt>Dropped connections</dt>
              <dd>
                {removal.dropped_edge_ids.length === 0
                  ? "none"
                  : removal.dropped_edge_ids.join(", ")}
              </dd>
              <dt>Paper claims</dt>
              <dd>
                {removal.evidence.length === 0 ? (
                  "none cited on this block or its connections"
                ) : (
                  <ul className={styles.config}>
                    {removal.evidence.map((ref, index) => (
                      <li key={`${ref.source_id}-${index}`}>
                        {ref.quote ?? ref.figure_label ?? ref.locator ?? "reference"}
                        {ref.page !== null ? ` (p. ${ref.page})` : null}
                      </li>
                    ))}
                  </ul>
                )}
              </dd>
            </dl>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

const DIAGRAM_VIEW_LABEL: Record<DiagramSelection["view"], string> = {
  methodology: "Methodology",
  schematic: "Schematic",
  structure: "3D structure",
};

/** Inspector body for a clicked diagram element: read-only paper
 *  content with its evidence. Diagram elements are not graph nodes,
 *  so no patch editors are offered here. */
function DiagramInspector({
  diagram,
  paperId,
}: {
  diagram: DiagramSelection;
  paperId: string | null;
}) {
  const evidence = diagram.evidence;
  // Methodology extras are the step's stated settings: editable knobs
  // with a what-if estimate behind them. Other views keep read-only rows.
  const whatIf = diagram.view === "methodology" && paperId !== null;
  return (
    <section className={styles.panel} aria-label="Inspector">
      <h2>Inspector</h2>
      <SelectionHead
        eyebrow={`Diagram · ${DIAGRAM_VIEW_LABEL[diagram.view]}`}
        title={diagram.label}
        detail={diagram.elementId}
      />
      <dl className={styles.facts}>
        <dt>Element</dt>
        <dd className="mono">{diagram.elementId}</dd>
        {diagram.kind ? (
          <>
            <dt>Kind</dt>
            <dd>{diagram.kind}</dd>
          </>
        ) : null}
        {diagram.detail ? (
          <>
            <dt>About</dt>
            <dd>{diagram.detail}</dd>
          </>
        ) : null}
        <dt>Provenance</dt>
        <dd>
          <ProvenanceTag value={diagram.provenance} />
        </dd>
        <dt>Confidence</dt>
        <dd>{diagram.confidence === null ? "unknown" : diagram.confidence.toFixed(2)}</dd>
        {whatIf && paperId ? (
          <WhatIfEditor
            key={diagram.elementId}
            paperId={paperId}
            nodeId={diagram.elementId}
            nodeLabel={diagram.label}
            params={diagram.extra}
          />
        ) : (
          diagram.extra.map((row) => (
            <div key={row.label} style={{ display: "contents" }}>
              <dt>{row.label}</dt>
              <dd className="mono">{row.value}</dd>
            </div>
          ))
        )}
        <dt>Evidence</dt>
        <dd>
          {!evidence ||
          (evidence.figure_id === null &&
            evidence.page === null &&
            evidence.quote === null) ? (
            <span className={styles.entityNote}>
              No evidence recorded for this element; treat it as unverified.
            </span>
          ) : (
            <ul className={styles.config}>
              {evidence.figure_id ? (
                <li>
                  Figure <span className="mono">{evidence.figure_id}</span>
                </li>
              ) : null}
              {evidence.page !== null ? <li>Page {evidence.page}</li> : null}
              {evidence.bbox ? (
                <li>
                  Figure box{" "}
                  <span className="mono">[{evidence.bbox.join(", ")}]</span> (0–100)
                </li>
              ) : null}
              {evidence.quote ? <li>“{evidence.quote}”</li> : null}
            </ul>
          )}
        </dd>
      </dl>
    </section>
  );
}
