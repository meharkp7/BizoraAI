import { useEffect, useMemo, useRef, useState } from "react";
import {
  useApplyPatch,
  useApplyPatchBatch,
  useGraphEntities,
  useGraphLayout,
  useGraphRevision,
  useSaveLayout,
} from "../../app/queries.ts";
import { BizoraApiError } from "../../lib/api.ts";
import { WORKSPACE_ACTOR } from "../../lib/constants.ts";
import { useLibrarySelection, useWorkspaceSelection } from "../../lib/store.ts";
import type {
  GraphEdge,
  GraphEntities,
  GraphLayout,
  GraphNode,
  GraphPatch,
  GraphRevisionDiff,
  MethodologyGraph,
  ResearchBrief,
  ViewportState,
} from "../../lib/types.ts";
import { EmptyState, ErrorState, LoadingState } from "../../components/states.tsx";
import { GraphCanvas } from "../canvas/GraphCanvas.tsx";
import { GraphCanvas3D } from "../canvas/GraphCanvas3D.tsx";
import { DomainBadge } from "../canvas/EntityLegend.tsx";
import { CopilotPanel } from "../copilot/CopilotPanel.tsx";
import { ComponentDetailView } from "../library/ComponentDetail.tsx";
import { LibraryPanel } from "../library/LibraryPanel.tsx";
import { CanvasToolbar } from "../canvas/CanvasToolbar.tsx";
import type { LayoutSaveStatus, NewNodeSpec } from "../canvas/CanvasToolbar.tsx";
import { diffStatusMaps } from "../canvas/flowElements.ts";
import { suggestEdgeId } from "../canvas/ids.ts";
import type { Point } from "../canvas/layout.ts";
import { autoLayout, matchesSavedPositions, toNodePositions } from "../canvas/layout.ts";
import { PatchStatus } from "../canvas/PatchStatus.tsx";
import { useRevisionHistory } from "./history.ts";
import { InspectorPanel } from "./InspectorPanel.tsx";
import {
  addEdgePatch,
  addNodePatch,
  removalBatch,
  replaceNodePatch,
  updateConfigPatch,
} from "./patchBuilders.ts";
import { EvidencePanel } from "./EvidencePanel.tsx";
import { RunPanel } from "../runs/RunPanel.tsx";
import { SimulationPreview } from "../runs/SimulationPreview.tsx";
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

function BriefList({ items }: { items: string[] }) {
  if (items.length === 0) {
    return <p className={styles.unknown}>Not stated in the paper.</p>;
  }
  return (
    <ul className={styles.briefList}>
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

function ResearchBriefPanel({ brief }: { brief: ResearchBrief }) {
  return (
    <section className={styles.brief} aria-label="Research brief">
      <h2>Research brief</h2>
      <div className={styles.briefGrid}>
        <div>
          <h3>Problem</h3>
          {brief.problem ? <p>{brief.problem}</p> : <p className={styles.unknown}>Not stated in the paper.</p>}
        </div>
        <div>
          <h3>Objectives</h3>
          <BriefList items={brief.objectives} />
        </div>
        <div>
          <h3>Findings</h3>
          <BriefList items={brief.findings} />
        </div>
        <div>
          <h3>Limitations</h3>
          <BriefList items={brief.limitations} />
        </div>
      </div>
    </section>
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

function IndexPanel({
  graph,
  selectedNode,
  selectedEdge,
  mutating,
  onSelectNodes,
  onSelectEdges,
  onSubmit,
}: {
  graph: MethodologyGraph;
  selectedNode: GraphNode | null;
  selectedEdge: GraphEdge | null;
  mutating: boolean;
  onSelectNodes: (nodeIds: string[]) => void;
  onSelectEdges: (edgeIds: string[]) => void;
  onSubmit: (patches: GraphPatch[]) => void;
}) {
  const { indexTab, setIndexTab, selectedComponentId } = useLibrarySelection();
  return (
    <section className={`${styles.panel} ${styles.indexPanel}`} aria-label="Index">
      <div className={styles.tabs} role="tablist" aria-label="Index tabs">
        <button
          type="button"
          role="tab"
          aria-selected={indexTab === "graph"}
          className={indexTab === "graph" ? styles.activeTab : undefined}
          onClick={() => setIndexTab("graph")}
        >
          Graph
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={indexTab === "library"}
          className={indexTab === "library" ? styles.activeTab : undefined}
          onClick={() => setIndexTab("library")}
        >
          Library
        </button>
      </div>
      {indexTab === "graph" ? (
        <>
          <div className={styles.sectionHead}>
            <h2>Components</h2>
            <span className={styles.count} aria-hidden="true">
              {graph.nodes.length}
            </span>
          </div>
          <NodeList
            nodes={graph.nodes}
            selectedId={selectedNode?.id ?? null}
            onSelect={(nodeId) => onSelectNodes([nodeId])}
          />
          <div className={`${styles.sectionHead} ${styles.edgesHeading}`}>
            <h2>Connections</h2>
            <span className={styles.count} aria-hidden="true">
              {graph.edges.length}
            </span>
          </div>
          <EdgeList
            edges={graph.edges}
            selectedId={selectedEdge?.id ?? null}
            onSelect={(edgeId) => onSelectEdges([edgeId])}
          />
        </>
      ) : selectedComponentId ? (
        <ComponentDetailView graph={graph} onSubmit={onSubmit} disabled={mutating} />
      ) : (
        <LibraryPanel />
      )}
    </section>
  );
}

export function WorkspacePage({
  projectId,
  graphId,
  version,
  view,
  onVersionChange,
  onViewChange,
}: {
  projectId: string;
  graphId: string;
  version: number;
  view: "2d" | "3d";
  onVersionChange: (version: number) => void;
  onViewChange: (view: "2d" | "3d") => void;
}) {
  const revision = useGraphRevision(projectId, graphId, version);
  const savedLayout = useGraphLayout(projectId, graphId, version);
  const entities = useGraphEntities(projectId, graphId, version);
  const patch = useApplyPatch(projectId, graphId);
  const batch = useApplyPatchBatch(projectId, graphId);
  const history = useRevisionHistory(version, onVersionChange);
  const [patchError, setPatchError] = useState<BizoraApiError | null>(null);
  const [savedVersion, setSavedVersion] = useState<number | null>(null);
  const {
    selectedNodeIds,
    selectedEdgeIds,
    selectNodes,
    selectEdges,
    clearSelection,
  } = useWorkspaceSelection();
  const mutating = patch.isPending || batch.isPending;

  const historyRef = useRef(history);
  useEffect(() => {
    historyRef.current = history;
  }, [history]);
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent): void {
      if (!event.ctrlKey && !event.metaKey) return;
      const target = event.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.tagName === "SELECT" ||
          target.isContentEditable)
      ) {
        return;
      }
      const key = event.key.toLowerCase();
      if (key === "z" && !event.shiftKey) {
        event.preventDefault();
        historyRef.current.undo();
      } else if ((key === "z" && event.shiftKey) || key === "y") {
        event.preventDefault();
        historyRef.current.redo();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

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

  return (
    <WorkspaceLoaded
      projectId={projectId}
      graph={revision.data}
      layoutVersion={version}
      view={view}
      onViewChange={onViewChange}
      savedLayout={savedLayout.data ?? null}
      entities={entities.data ?? null}
      entitiesPending={entities.isPending}
      entitiesError={entities.error instanceof Error ? entities.error.message : null}
      selectedNodeIds={selectedNodeIds}
      selectedEdgeIds={selectedEdgeIds}
      mutating={mutating}
      patchError={patchError}
      savedVersion={savedVersion}
      canUndo={history.canUndo}
      canRedo={history.canRedo}
      onOlder={() => history.go(version - 1)}
      onNewer={() => history.go(version + 1)}
      onUndo={history.undo}
      onRedo={history.redo}
      onSelectNodes={selectNodes}
      onSelectEdges={selectEdges}
      onSubmit={(patches) => {
        setPatchError(null);
        setSavedVersion(null);
        const callbacks = {
          onSuccess: (next: MethodologyGraph) => {
            clearSelection();
            setSavedVersion(next.version);
            history.go(next.version);
          },
          onError: (cause: unknown) => {
            setPatchError(
              cause instanceof BizoraApiError
                ? cause
                : new BizoraApiError(0, "UNKNOWN", "The change failed.", {}),
            );
          },
        };
        if (patches.length === 1) patch.mutate(patches[0], callbacks);
        else batch.mutate({ patches }, callbacks);
      }}
      onLocalError={setPatchError}
      onDismissStatus={() => {
        setPatchError(null);
        setSavedVersion(null);
      }}
    />
  );
}

function WorkspaceLoaded({
  projectId,
  graph,
  layoutVersion,
  view,
  onViewChange,
  savedLayout,
  entities,
  entitiesPending,
  entitiesError,
  selectedNodeIds,
  selectedEdgeIds,
  mutating,
  patchError,
  savedVersion,
  canUndo,
  canRedo,
  onOlder,
  onNewer,
  onUndo,
  onRedo,
  onSelectNodes,
  onSelectEdges,
  onSubmit,
  onLocalError,
  onDismissStatus,
}: {
  projectId: string;
  graph: MethodologyGraph;
  layoutVersion: number;
  view: "2d" | "3d";
  onViewChange: (view: "2d" | "3d") => void;
  savedLayout: GraphLayout | null;
  entities: GraphEntities | null;
  entitiesPending: boolean;
  entitiesError: string | null;
  selectedNodeIds: string[];
  selectedEdgeIds: string[];
  mutating: boolean;
  patchError: BizoraApiError | null;
  savedVersion: number | null;
  canUndo: boolean;
  canRedo: boolean;
  onOlder: () => void;
  onNewer: () => void;
  onUndo: () => void;
  onRedo: () => void;
  onSelectNodes: (nodeIds: string[]) => void;
  onSelectEdges: (edgeIds: string[]) => void;
  onSubmit: (patches: GraphPatch[]) => void;
  onLocalError: (error: BizoraApiError) => void;
  onDismissStatus: () => void;
}) {
  const selectedNode: GraphNode | null =
    graph.nodes.find((node) => node.id === selectedNodeIds[0]) ?? null;
  const selectedEdge: GraphEdge | null =
    graph.edges.find((edge) => edge.id === selectedEdgeIds[0]) ?? null;
  const selectedEntity = selectedNode
    ? (entities?.entities.find((entity) => entity.node_id === selectedNode.id) ?? null)
    : null;
  const takenIds = useMemo(
    () => new Set([...graph.nodes.map((node) => node.id), ...graph.edges.map((edge) => edge.id)]),
    [graph],
  );
  const saveLayout = useSaveLayout(graph.project_id, graph.graph_id, graph.version);
  const [layoutStatus, setLayoutStatus] = useState<LayoutSaveStatus>("idle");
  const [layoutReset, setLayoutReset] = useState<{
    id: number;
    positions: Map<string, Point>;
  } | null>(null);
  const [activeDiff, setActiveDiff] = useState<GraphRevisionDiff | null>(null);
  const saveTimer = useRef<number | null>(null);
  const canvasSectionRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    // Deep links (?view=3d) land at the top of the page; bring the canvas
    // into view instead of stranding newcomers above the fold.
    if (view === "3d") canvasSectionRef.current?.scrollIntoView?.({ block: "nearest" });
  }, [view]);

  useEffect(() => {
    const timer = saveTimer;
    return () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
    };
  }, []);

  const diffStatuses = useMemo(
    () => (activeDiff ? diffStatusMaps(activeDiff) : null),
    [activeDiff],
  );

  function handleNodesMoved(positions: Map<string, Point>, viewport: ViewportState): void {
    if (savedLayout && matchesSavedPositions(savedLayout.positions, positions)) {
      return;
    }
    if (saveTimer.current !== null) window.clearTimeout(saveTimer.current);
    setLayoutStatus("saving");
    saveTimer.current = window.setTimeout(() => {
      saveLayout.mutate(
        {
          project_id: graph.project_id,
          graph_id: graph.graph_id,
          version: graph.version,
          positions: toNodePositions(graph, positions),
          viewport,
          camera: savedLayout?.camera ?? null,
          updated_by: WORKSPACE_ACTOR,
        },
        {
          onSuccess: () => setLayoutStatus("saved"),
          onError: () => setLayoutStatus("error"),
        },
      );
    }, 800);
  }

  function handleResetLayout(): void {
    if (saveTimer.current !== null) window.clearTimeout(saveTimer.current);
    const positions = autoLayout(graph);
    setLayoutStatus("saving");
    saveLayout.mutate(
      {
        project_id: graph.project_id,
        graph_id: graph.graph_id,
        version: graph.version,
        positions: toNodePositions(graph, positions),
        viewport: null,
        camera: savedLayout?.camera ?? null,
        updated_by: WORKSPACE_ACTOR,
      },
      {
        onSuccess: () => {
          setLayoutStatus("saved");
          setLayoutReset({ id: Date.now(), positions });
        },
        onError: () => setLayoutStatus("error"),
      },
    );
  }

  function handleConnect(source: string, target: string): void {
    if (source === target) {
      onLocalError(new BizoraApiError(422, "INVALID_GRAPH_PATCH", "A connection cannot start and end on the same component.", {}));
      return;
    }
    const takenEdges = new Set(graph.edges.map((edge) => edge.id));
    onSubmit([addEdgePatch(graph, suggestEdgeId(source, target, takenEdges), source, target)]);
  }

  function handleDelete(nodeIds: string[], edgeIds: string[]): void {
    if (nodeIds.length === 0 && edgeIds.length === 0) return;
    onSubmit(removalBatch(graph, nodeIds, edgeIds));
  }

  function handleAddNode(spec: NewNodeSpec): void {
    onSubmit([addNodePatch(graph, spec)]);
  }

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
          <DomainBadge entities={entities} />
          {entitiesError ? (
            <p className={styles.entitiesError} role="alert">
              Component identities unavailable ({entitiesError}). The 3D view shows
              generic markers until the backend serves them again.
            </p>
          ) : null}
        </div>
        <div className={styles.stepper} role="group" aria-label="Revision">
          <button type="button" disabled={layoutVersion <= 1 || mutating} onClick={onOlder}>
            ← Older
          </button>
          <span className={styles.versionBadge} aria-live="polite">
            v{layoutVersion}
          </span>
          <button type="button" disabled={mutating} onClick={onNewer}>
            Newer →
          </button>
        </div>
      </div>

      <PatchStatus
        pending={mutating}
        error={patchError}
        savedVersion={savedVersion}
        onDismiss={onDismissStatus}
      />

      {graph.brief ? <ResearchBriefPanel brief={graph.brief} /> : null}

      <div className={styles.grid}>
        <IndexPanel
          graph={graph}
          selectedNode={selectedNode}
          selectedEdge={selectedEdge}
          mutating={mutating}
          onSelectNodes={onSelectNodes}
          onSelectEdges={onSelectEdges}
          onSubmit={onSubmit}
        />

        <section
          ref={canvasSectionRef}
          className={`${styles.panel} ${styles.canvasPanel}`}
          aria-label="Canvas"
        >
          <CanvasToolbar
            takenIds={takenIds}
            canUndo={canUndo}
            canRedo={canRedo}
            onUndo={onUndo}
            onRedo={onRedo}
            onAddNode={handleAddNode}
            disabled={mutating}
            layoutStatus={layoutStatus}
            onResetLayout={handleResetLayout}
            view={view}
            onViewChange={onViewChange}
          />
          {view === "3d" ? (
            <GraphCanvas3D
              key={`3d-${graph.version}`}
              graph={graph}
              layout={savedLayout}
              entities={entities}
              entitiesPending={entitiesPending}
              entitiesError={entitiesError}
            />
          ) : (
            <GraphCanvas
              graph={graph}
              layout={savedLayout}
              layoutReset={layoutReset}
              diffStatuses={diffStatuses}
              mutating={mutating}
              onConnectRequest={handleConnect}
              onDeleteRequest={handleDelete}
              onNodesMoved={handleNodesMoved}
            />
          )}
        </section>

        <div className={styles.side}>
          <InspectorPanel
            node={selectedNode}
            edge={selectedEdge}
            entity={selectedEntity}
            entityError={entitiesError}
            formatShape={formatShape}
            disabled={mutating}
            onUpdateConfig={
              selectedNode
                ? (config) => onSubmit([updateConfigPatch(graph, selectedNode, config)])
                : undefined
            }
            onReplaceNode={
              selectedNode
                ? (replacement) =>
                    onSubmit([replaceNodePatch(graph, selectedNode, replacement)])
                : undefined
            }
          />
          <EvidencePanel node={selectedNode} edge={selectedEdge} />
          <SimulationPreview
            projectId={projectId}
            graphId={graph.graph_id}
            version={graph.version}
          />
          <RunPanel projectId={projectId} graph={graph} />
          <CopilotPanel
            projectId={projectId}
            graph={graph}
            disabled={mutating}
            onSubmit={onSubmit}
          />
        </div>
      </div>

      <DiffPanel
        projectId={projectId}
        graphId={graph.graph_id}
        currentVersion={graph.version}
        onDiffChange={setActiveDiff}
      />
    </div>
  );
}
