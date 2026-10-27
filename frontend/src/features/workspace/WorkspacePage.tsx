import { useGraphRevision } from "../../app/queries.ts";
import { BizoraApiError } from "../../lib/api.ts";
import { useWorkspaceSelection } from "../../lib/store.ts";
import type { GraphEdge, GraphNode } from "../../lib/types.ts";
import { EmptyState, ErrorState, LoadingState } from "../../components/states.tsx";
import { InspectorPanel } from "./InspectorPanel.tsx";
import { EvidencePanel } from "./EvidencePanel.tsx";
import { DiffPanel } from "./DiffPanel.tsx";
import styles from "./WorkspacePage.module.css";

function formatShape(shape: (number | null)[] | null): string {
  if (!shape) return "—";
  return `[${shape.map((dim) => (dim === null ? "?" : String(dim))).join(", ")}]`;
}

function NodeList({
  nodes,
  selectedId,
  onSelect,
}: {
  nodes: GraphNode[];
  selectedId: string | null;
  onSelect: (nodeId: string) => void;
}) {
  if (nodes.length === 0) return <EmptyState title="No nodes in this revision." />;
  return (
    <ul className={styles.nodeList} aria-label="Graph nodes">
      {nodes.map((node) => (
        <li key={node.id}>
          <button
            type="button"
            className={selectedId === node.id ? styles.selected : undefined}
            onClick={() => onSelect(node.id)}
            aria-pressed={selectedId === node.id}
          >
            <span className={styles.nodeLabel}>{node.label}</span>
            <span className={styles.nodeMeta}>
              {node.kind} · <span className="mono">{node.id}</span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function EdgeList({
  edges,
  selectedId,
  onSelect,
}: {
  edges: GraphEdge[];
  selectedId: string | null;
  onSelect: (edgeId: string) => void;
}) {
  if (edges.length === 0) return <EmptyState title="No edges in this revision." />;
  return (
    <ul className={styles.nodeList} aria-label="Graph edges">
      {edges.map((edge) => (
        <li key={edge.id}>
          <button
            type="button"
            className={selectedId === edge.id ? styles.selected : undefined}
            onClick={() => onSelect(edge.id)}
            aria-pressed={selectedId === edge.id}
          >
            <span className={styles.nodeLabel}>
              <span className="mono">{edge.source}</span> →{" "}
              <span className="mono">{edge.target}</span>
            </span>
            <span className={styles.nodeMeta}>
              {edge.relation} · <span className="mono">{edge.id}</span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

export function WorkspacePage({
  projectId,
  graphId,
  version,
  onVersionChange,
}: {
  projectId: string;
  graphId: string;
  version: number;
  onVersionChange: (version: number) => void;
}) {
  const revision = useGraphRevision(projectId, graphId, version);
  const { selectedNodeIds, selectedEdgeIds, selectNodes, selectEdges } =
    useWorkspaceSelection();

  if (revision.isPending) {
    return <LoadingState label={`Loading revision ${version}…`} />;
  }

  if (revision.isError) {
    const error = revision.error;
    const notFound = error instanceof BizoraApiError && error.isNotFound;
    return (
      <ErrorState
        title={notFound ? `Revision ${version} does not exist.` : "Could not load the revision."}
        detail={
          notFound
            ? "Step back to an existing revision."
            : error instanceof Error
              ? error.message
              : undefined
        }
        onRetry={() => void revision.refetch()}
      />
    );
  }

  const graph = revision.data;
  const selectedNode: GraphNode | null =
    graph.nodes.find((node) => node.id === selectedNodeIds[0]) ?? null;
  const selectedEdge: GraphEdge | null =
    graph.edges.find((edge) => edge.id === selectedEdgeIds[0]) ?? null;

  return (
    <div className={styles.page}>
      <div className={styles.heading}>
        <div>
          <h1>{graph.title}</h1>
          <p className={styles.subtitle}>
            <span className="mono">
              {graph.project_id}/{graph.graph_id}
            </span>{" "}
            · revision {graph.version}
            {graph.parent_version ? ` (from ${graph.parent_version})` : " (initial)"} ·{" "}
            {graph.nodes.length} node{graph.nodes.length === 1 ? "" : "s"} ·{" "}
            {graph.edges.length} edge{graph.edges.length === 1 ? "" : "s"}
          </p>
        </div>
        <div className={styles.stepper} role="group" aria-label="Revision">
          <button
            type="button"
            disabled={version <= 1}
            onClick={() => onVersionChange(version - 1)}
          >
            ← Older
          </button>
          <span className={styles.versionBadge} aria-live="polite">
            v{version}
          </span>
          <button type="button" onClick={() => onVersionChange(version + 1)}>
            Newer →
          </button>
        </div>
      </div>

      <div className={styles.grid}>
        <section className={styles.panel} aria-label="Components">
          <h2>Components</h2>
          <NodeList
            nodes={graph.nodes}
            selectedId={selectedNode?.id ?? null}
            onSelect={(nodeId) => selectNodes([nodeId])}
          />
          <h2 className={styles.edgesHeading}>Connections</h2>
          <EdgeList
            edges={graph.edges}
            selectedId={selectedEdge?.id ?? null}
            onSelect={(edgeId) => selectEdges([edgeId])}
          />
        </section>

        <section className={styles.panel} aria-label="Canvas">
          <h2>Canvas</h2>
          <EmptyState
            title="Interactive canvas arrives in Phase E."
            detail="Selection, layout, and editing bind to this same revision data. Layout persistence is already live in the API."
          />
        </section>

        <div className={styles.side}>
          <InspectorPanel node={selectedNode} edge={selectedEdge} formatShape={formatShape} />
          <EvidencePanel node={selectedNode} edge={selectedEdge} />
        </div>
      </div>

      <DiffPanel projectId={projectId} graphId={graphId} currentVersion={graph.version} />
    </div>
  );
}
