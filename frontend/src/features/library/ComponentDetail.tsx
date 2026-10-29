import { useMemo, useState } from "react";
import { useComponentDetail, usePreflight } from "../../app/queries.ts";
import { BizoraApiError } from "../../lib/api.ts";
import { useLibrarySelection, useWorkspaceSelection } from "../../lib/store.ts";
import type {
  ComponentDetail,
  GraphEdge,
  GraphNode,
  GraphPatch,
  MethodologyGraph,
  NodeKind,
} from "../../lib/types.ts";
import { EmptyState, ErrorState, LoadingState } from "../../components/states.tsx";
import { SymbolGlyph } from "../canvas/SymbolGlyph.tsx";
import { categoryLabel, domainLabel } from "../canvas/graph3d.ts";
import { replaceNodePatch } from "../workspace/patchBuilders.ts";
import { ConfigForm } from "./ConfigForm.tsx";
import { PinDiagram } from "./PinDiagram.tsx";
import styles from "./ComponentDetail.module.css";

function initialConfig(detail: ComponentDetail, node: GraphNode | null): Record<string, unknown> {
  const values: Record<string, unknown> = { ...detail.default_config };
  if (node) {
    for (const field of detail.config_schema) {
      if (node.config[field.key] !== undefined) values[field.key] = node.config[field.key];
    }
  }
  return values;
}

function edgeSummary(edge: GraphEdge): string {
  return `${edge.source} → ${edge.target} (${edge.relation})`;
}

function ReplacePreview({
  graph,
  node,
  detail,
  config,
  onConfigChange,
  disabled,
  onSubmit,
}: {
  graph: MethodologyGraph;
  node: GraphNode;
  detail: ComponentDetail;
  config: Record<string, unknown>;
  onConfigChange: (key: string, value: unknown) => void;
  disabled: boolean;
  onSubmit: (patches: GraphPatch[]) => void;
}) {
  const preflight = usePreflight(
    graph.project_id,
    graph.graph_id,
    graph.version,
    node.id,
    detail.component_id,
    config,
  );
  const edgesById = useMemo(() => new Map(graph.edges.map((edge) => [edge.id, edge])), [graph]);

  return (
    <section className={styles.preview} aria-label="Replacement preview">
      <h3>Replace {node.label}</h3>
      <ConfigForm
        schema={detail.config_schema}
        values={config}
        onChange={onConfigChange}
        disabled={disabled}
      />
      {preflight.isPending ? <LoadingState label="Validating the replacement…" /> : null}
      {preflight.isError ? (
        <ErrorState
          title="Validation failed."
          detail={
            preflight.error instanceof BizoraApiError
              ? preflight.error.message
              : preflight.error instanceof Error
                ? preflight.error.message
                : undefined
          }
          onRetry={() => void preflight.refetch()}
        />
      ) : null}
      {preflight.data ? (
        <div className={styles.verdict}>
          {preflight.data.compatible ? (
            <p className={styles.compatible} role="status">
              Compatible: all known interfaces are preserved.
            </p>
          ) : (
            <div role="alert">
              <p className={styles.incompatible}>Not compatible with {node.label}.</p>
              <ul className={styles.missing}>
                {preflight.data.missing_interfaces.map((missing) => (
                  <li key={missing.kind}>
                    <span className="mono">{missing.kind}</span>: {missing.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <p className={styles.preserved}>
            {preflight.data.preserved_edge_ids.length === 0
              ? "No connections touch this node."
              : `Preserved connections (${preflight.data.preserved_edge_ids.length}):`}
          </p>
          {preflight.data.preserved_edge_ids.length > 0 ? (
            <ul className={styles.preservedList}>
              {preflight.data.preserved_edge_ids.map((edgeId) => (
                <li key={edgeId} className="mono">
                  {edgesById.get(edgeId) ? edgeSummary(edgesById.get(edgeId) as GraphEdge) : edgeId}
                </li>
              ))}
            </ul>
          ) : null}
          {preflight.data.warnings.length > 0 ? (
            <ul className={styles.warnings}>
              {preflight.data.warnings.map((warning) => (
                <li key={warning.code}>{warning.message}</li>
              ))}
            </ul>
          ) : null}
          <button
            type="button"
            disabled={disabled || !preflight.data.compatible}
            onClick={() =>
              onSubmit([
                replaceNodePatch(graph, node, {
                  kind: detail.kind as NodeKind,
                  label: detail.label,
                  description: detail.description,
                  config,
                }),
              ])
            }
          >
            Apply replacement (new revision)
          </button>
        </div>
      ) : null}
    </section>
  );
}

function DetailBody({
  graph,
  detail,
  onSubmit,
  disabled,
}: {
  graph: MethodologyGraph;
  detail: ComponentDetail;
  onSubmit: (patches: GraphPatch[]) => void;
  disabled: boolean;
}) {
  const { selectedNodeIds } = useWorkspaceSelection();
  const node = graph.nodes.find((candidate) => candidate.id === selectedNodeIds[0]) ?? null;
  const [config, setConfig] = useState<Record<string, unknown>>(() => initialConfig(detail, node));
  const reference = detail.datasheet_url ?? detail.reference_url;
  const constraintEntries = Object.entries(detail.constraints);

  return (
    <div className={styles.detail}>
      <div className={styles.head}>
        <SymbolGlyph symbol={detail.symbol || "generic"} size={20} />
        <div>
          <div className={styles.title}>{detail.label}</div>
          <div className={styles.meta}>
            {detail.generic ? (
              <span className={styles.genericBadge}>correctly identified generic</span>
            ) : (
              <span>
                {detail.manufacturer} · <span className="mono">{detail.part_number}</span>
              </span>
            )}
          </div>
          <div className={styles.meta}>
            {domainLabel(detail.domain)} · {categoryLabel(detail.category)}
          </div>
        </div>
      </div>
      <p className={styles.description}>{detail.description}</p>
      <p className={styles.reference}>
        {reference ? (
          <a href={reference} target="_blank" rel="noreferrer">
            {detail.datasheet_url ? "Open datasheet" : "Open reference"}
          </a>
        ) : (
          "No verified datasheet or reference yet."
        )}
      </p>

      {node ? (
        <ReplacePreview
          graph={graph}
          node={node}
          detail={detail}
          config={config}
          onConfigChange={(key, value) => setConfig((current) => ({ ...current, [key]: value }))}
          disabled={disabled}
          onSubmit={onSubmit}
        />
      ) : (
        <p className={styles.hint}>Select a graph node to replace it with this component.</p>
      )}

      {detail.specs.length > 0 ? (
        <section aria-label="Specifications">
          <h3>Specifications</h3>
          <dl className={styles.specs}>
            {detail.specs.map((spec) => (
              <div key={spec.name} className={styles.specRow}>
                <dt>{spec.name}</dt>
                <dd>
                  {spec.value}
                  {spec.unit ? ` ${spec.unit}` : ""}
                </dd>
              </div>
            ))}
          </dl>
          <p className={styles.nominal}>Nominal catalog values; confirm limits in the reference.</p>
        </section>
      ) : null}

      {constraintEntries.length > 0 ? (
        <section aria-label="Limits">
          <h3>Limits</h3>
          <dl className={styles.specs}>
            {constraintEntries.map(([key, value]) => (
              <div key={key} className={styles.specRow}>
                <dt className="mono">{key}</dt>
                <dd className="mono">{value}</dd>
              </div>
            ))}
          </dl>
        </section>
      ) : null}

      {detail.pinout.length > 0 ? (
        <section aria-label="Pinout">
          <h3>Pinout</h3>
          <PinDiagram pins={detail.pinout} />
          <ul className={styles.pins}>
            {detail.pinout.map((pin) => (
              <li key={`${pin.designator}-${pin.name}`}>
                <span className="mono">{pin.designator}</span> · <strong>{pin.name}</strong>
                {pin.function ? ` — ${pin.function}` : ""}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {detail.interfaces.length > 0 ? (
        <section aria-label="Interfaces">
          <h3>Interfaces</h3>
          <ul className={styles.interfaces}>
            {detail.interfaces.map((iface) => (
              <li key={iface.name}>
                <span className="mono">{iface.kind}</span> · {iface.name}
                {Object.keys(iface.params).length > 0
                  ? ` (${Object.entries(iface.params)
                      .map(([key, value]) => `${key}=${value}`)
                      .join(", ")})`
                  : ""}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {detail.evidence.length > 0 ? (
        <section aria-label="Evidence">
          <h3>Evidence</h3>
          <ul className={styles.evidence}>
            {detail.evidence.map((entry) => (
              <li key={entry.source}>
                {entry.source}
                {entry.note ? ` — ${entry.note}` : ""}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

    </div>
  );
}

export function ComponentDetailView({
  graph,
  onSubmit,
  disabled,
}: {
  graph: MethodologyGraph;
  onSubmit: (patches: GraphPatch[]) => void;
  disabled: boolean;
}) {
  const { selectedComponentId, selectComponent } = useLibrarySelection();
  const detail = useComponentDetail(selectedComponentId);

  if (selectedComponentId === null) return null;
  return (
    <div className={styles.panel}>
      <button type="button" className={styles.back} onClick={() => selectComponent(null)}>
        ← Library results
      </button>
      {detail.isPending ? <LoadingState label="Loading component…" /> : null}
      {detail.isError ? (
        <ErrorState
          title="Could not load the component."
          detail={detail.error instanceof Error ? detail.error.message : undefined}
          onRetry={() => void detail.refetch()}
        />
      ) : null}
      {detail.data ? (
        <DetailBody
          key={detail.data.component_id}
          graph={graph}
          detail={detail.data}
          onSubmit={onSubmit}
          disabled={disabled}
        />
      ) : null}
      {detail.data === undefined && !detail.isPending && !detail.isError ? (
        <EmptyState title="No component selected." />
      ) : null}
    </div>
  );
}
