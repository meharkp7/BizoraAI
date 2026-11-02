import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  useApplyPatch,
  useApplyPatchBatch,
  useGraphEntities,
  useGraphRevision,
  usePaperDiagrams,
  useRemovalPreflight,
} from "../../app/queries.ts";
import { BizoraApiError } from "../../lib/api.ts";
import type { CanvasView } from "../../app/routeElements.tsx";
import { useLibrarySelection, useWorkspaceSelection } from "../../lib/store.ts";
import type {
  GraphEdge,
  GraphEntities,
  GraphNode,
  GraphPatch,
  MethodologyGraph,
  ResearchBrief,
} from "../../lib/types.ts";
import { EmptyState, ErrorState, LoadingState } from "../../components/states.tsx";
import { DomainBadge } from "../canvas/EntityLegend.tsx";
import { CopilotBot } from "../copilot/CopilotBot.tsx";
import { FigureOverlay } from "../figures/FigureOverlay.tsx";
import { ReportedPanel } from "./ReportedPanel.tsx";
import { ComponentDetailView } from "../library/ComponentDetail.tsx";
import { LibraryPanel } from "../library/LibraryPanel.tsx";
import { CanvasToolbar } from "../canvas/CanvasToolbar.tsx";
import { PatchStatus } from "../canvas/PatchStatus.tsx";
import { MethodologyDiagramView } from "../diagrams/MethodologyDiagramView.tsx";
import { SchematicDiagramView } from "../diagrams/SchematicDiagramView.tsx";
import { StructureDiagramView } from "../diagrams/StructureDiagramView.tsx";
import { figureIdFromSource } from "../diagrams/provenance.ts";
import type { DiagramSelection } from "../diagrams/selection.ts";
import { useRevisionHistory } from "./history.ts";
import { InspectorPanel } from "./InspectorPanel.tsx";
import { NotesPanel } from "../notes/NotesPanel.tsx";
import { replaceNodePatch, updateConfigPatch } from "./patchBuilders.ts";
import { EvidencePanel } from "./EvidencePanel.tsx";
import { RunPanel } from "../runs/RunPanel.tsx";
import { SimulationPreview } from "../runs/SimulationPreview.tsx";
import { DiffPanel } from "./DiffPanel.tsx";
import { VersionHistory } from "./VersionHistory.tsx";
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
  view: CanvasView;
  onVersionChange: (version: number) => void;
  onViewChange: (view: CanvasView) => void;
}) {
  const revision = useGraphRevision(projectId, graphId, version);
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
      entities={entities.data ?? null}
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
      onSelectVersion={(next) => history.go(next)}
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
  entities,
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
  onSelectVersion,
  onUndo,
  onRedo,
  onSelectNodes,
  onSelectEdges,
  onSubmit,
  onDismissStatus,
}: {
  projectId: string;
  graph: MethodologyGraph;
  layoutVersion: number;
  view: CanvasView;
  onViewChange: (view: CanvasView) => void;
  entities: GraphEntities | null;
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
  onSelectVersion: (version: number) => void;
  onUndo: () => void;
  onRedo: () => void;
  onSelectNodes: (nodeIds: string[]) => void;
  onSelectEdges: (edgeIds: string[]) => void;
  onSubmit: (patches: GraphPatch[]) => void;
  onDismissStatus: () => void;
}) {
  const selectedNode: GraphNode | null =
    graph.nodes.find((node) => node.id === selectedNodeIds[0]) ?? null;
  const selectedEdge: GraphEdge | null =
    graph.edges.find((edge) => edge.id === selectedEdgeIds[0]) ?? null;
  const selectedEntity = selectedNode
    ? (entities?.entities.find((entity) => entity.node_id === selectedNode.id) ?? null)
    : null;
  const nodeLabels = useMemo(
    () => new Map(graph.nodes.map((node) => [node.id, node.label])),
    [graph],
  );
  // The canvas feeds solely from the paper's diagram IRs. The paper is
  // the graph's first source: figure ingest stores figures under it.
  const paperId = graph.source_ids[0] ?? null;
  const [diagramSelection, setDiagramSelection] = useState<DiagramSelection | null>(null);
  // Any graph selection (index, figure overlay, ...) suppresses the
  // diagram selection, so the two can never disagree or go stale.
  const effectiveDiagram =
    selectedNodeIds.length === 0 && selectedEdgeIds.length === 0 ? diagramSelection : null;
  const [removalTarget, setRemovalTarget] = useState<string | null>(null);
  const [compareRequest, setCompareRequest] = useState<{
    base: number;
    target: number;
  } | null>(null);
  const removalPreflight = useRemovalPreflight(
    projectId,
    graph.graph_id,
    layoutVersion,
    removalTarget,
  );
  const canvasSectionRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    // Deep links (?view=3d, ...) land at the top of the page; bring the
    // canvas into view instead of stranding newcomers above the fold.
    if (view !== "methodology") canvasSectionRef.current?.scrollIntoView?.({ block: "nearest" });
  }, [view]);

  function handleSelectNodes(nodeIds: string[]): void {
    setDiagramSelection(null);
    onSelectNodes(nodeIds);
  }

  function handleSelectEdges(edgeIds: string[]): void {
    setDiagramSelection(null);
    onSelectEdges(edgeIds);
  }

  // Stable across renders (store setters are stable) so the 3D
  // canvas effect below never rebuilds for a mere re-render.
  const handleDiagramSelect = useCallback(
    (selection: DiagramSelection): void => {
      onSelectNodes([]);
      setDiagramSelection(selection);
    },
    [onSelectNodes],
  );

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
              Component identities unavailable ({entitiesError}). Identity-driven views
              are degraded until the backend serves them again.
            </p>
          ) : null}
        </div>
        <div className={styles.stepper} role="group" aria-label="Revision">
          <button type="button" onClick={onUndo} disabled={!canUndo || mutating} title="Undo (Ctrl+Z)">
            Undo
          </button>
          <button
            type="button"
            onClick={onRedo}
            disabled={!canRedo || mutating}
            title="Redo (Ctrl+Shift+Z)"
          >
            Redo
          </button>
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
          onSelectNodes={handleSelectNodes}
          onSelectEdges={handleSelectEdges}
          onSubmit={onSubmit}
        />

        <section
          ref={canvasSectionRef}
          className={`${styles.panel} ${styles.canvasPanel}`}
          aria-label="Canvas"
        >
          <CanvasToolbar view={view} onViewChange={onViewChange} disabled={mutating} />
          <DiagramCanvas
            paperId={paperId}
            projectId={projectId}
            graphId={graph.graph_id}
            view={view}
            nodeLabels={nodeLabels}
            onSelect={handleDiagramSelect}
          />
        </section>

        <div className={styles.side}>
          <InspectorPanel
            node={selectedNode}
            edge={selectedEdge}
            diagram={effectiveDiagram}
            paperId={paperId}
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
            removal={removalPreflight.data ?? null}
            removalPending={removalPreflight.isFetching}
            removalError={
              removalPreflight.error instanceof Error ? removalPreflight.error.message : null
            }
            nodeLabels={Object.fromEntries(nodeLabels)}
            onPreviewRemoval={setRemovalTarget}
            onClearRemoval={() => setRemovalTarget(null)}
          />
          <FigureOverlay
            projectId={projectId}
            graphId={graph.graph_id}
            version={graph.version}
            nodeLabels={nodeLabels}
          />
          <EvidencePanel node={selectedNode} edge={selectedEdge} />
          <ReportedPanel projectId={projectId} graphId={graph.graph_id} />
          <SimulationPreview
            projectId={projectId}
            graphId={graph.graph_id}
            version={graph.version}
          />
          <RunPanel projectId={projectId} graph={graph} />
          <NotesPanel paperId={paperId} />
        </div>
      </div>
      <CopilotBot
        projectId={projectId}
        graph={graph}
        disabled={mutating}
        view={view}
        selection={effectiveDiagram}
        onSubmit={onSubmit}
      />

      <VersionHistory
        projectId={projectId}
        graphId={graph.graph_id}
        currentVersion={graph.version}
        onSelectVersion={onSelectVersion}
        onCompare={(base) => setCompareRequest({ base, target: graph.version })}
      />

      <DiffPanel
        projectId={projectId}
        graphId={graph.graph_id}
        currentVersion={graph.version}
        compareRequest={compareRequest}
      />
    </div>
  );
}

/** Canvas body: the three diagram views fed only by the paper's
 *  diagram IRs. `diagrams` is read here (not passed down) so the
 *  loading/error states live next to the tabs. */
function DiagramCanvas({
  paperId,
  projectId,
  graphId,
  view,
  nodeLabels,
  onSelect,
}: {
  paperId: string | null;
  projectId: string;
  graphId: string;
  view: CanvasView;
  nodeLabels: Map<string, string>;
  onSelect: (selection: DiagramSelection) => void;
}) {
  const diagrams = usePaperDiagrams(paperId);

  if (paperId === null) {
    return <EmptyState title="This graph is not linked to a paper." />;
  }
  if (diagrams.isPending) {
    return <LoadingState label="Loading paper diagrams…" />;
  }
  if (diagrams.isError) {
    const error = diagrams.error;
    if (error instanceof BizoraApiError && error.isNotFound) {
      return (
        <EmptyState
          title="No diagrams for this paper yet."
          detail="Upload ingests figures and text automatically — this paper has neither, so there is nothing to derive diagrams from."
        />
      );
    }
    return (
      <ErrorState
        title="Could not load the paper diagrams."
        detail={error instanceof Error ? error.message : undefined}
        onRetry={() => void diagrams.refetch()}
      />
    );
  }

  const response = diagrams.data;
  if (view === "schematic") {
    return (
      <SchematicDiagramView
        circuits={response.circuits}
        validation={response.validation}
        projectId={projectId}
        graphId={graphId}
        nodeLabels={nodeLabels}
        onSelect={onSelect}
      />
    );
  }
  if (view === "3d") {
    return (
      <StructureDiagramView
        structure={response.structure}
        circuits={response.circuits}
        sourceFigureId={figureIdFromSource(response.sources["structure"])}
        warnings={response.validation["structure"]?.warnings ?? []}
        projectId={projectId}
        graphId={graphId}
        nodeLabels={nodeLabels}
        onSelect={onSelect}
      />
    );
  }
  return (
    <MethodologyDiagramView
      methodology={response.methodology}
      sourceFigureId={figureIdFromSource(response.sources["methodology"])}
      warnings={response.validation["methodology"]?.warnings ?? []}
      projectId={projectId}
      graphId={graphId}
      paperId={paperId}
      nodeLabels={nodeLabels}
      onSelect={onSelect}
    />
  );
}

