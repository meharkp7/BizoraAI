import { useCallback, useEffect, useRef, useState } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
} from "@xyflow/react";
import type {
  Connection,
  EdgeChange,
  NodeChange,
  OnNodeDrag,
} from "@xyflow/react";
import { useWorkspaceSelection } from "../../lib/store.ts";
import type {
  GraphLayout,
  MeasuredOverlay,
  MethodologyGraph,
  ViewportState,
} from "../../lib/types.ts";
import { EMPTY_OVERLAY } from "../../lib/types.ts";
import { measuredSummary, toFlowElements, truncateEdgeLabel } from "./flowElements.ts";
import type { CanvasDiffStatuses, FlowEdge } from "./flowElements.ts";
import type { Point } from "./layout.ts";
import { MethodNode } from "./MethodNode.tsx";
import type { MethodNodeType } from "./MethodNode.tsx";
import styles from "./GraphCanvas.module.css";

export interface LayoutResetRequest {
  id: number;
  positions: Map<string, Point>;
}

export interface GraphCanvasProps {
  graph: MethodologyGraph;
  layout: GraphLayout | null;
  layoutReset?: LayoutResetRequest | null;
  diffStatuses: CanvasDiffStatuses | null;
  /** Measured-overlay channel; empty until a real run exists. */
  overlay?: MeasuredOverlay;
  onNodesMoved?: (positions: Map<string, Point>, viewport: ViewportState) => void;
  onConnectRequest?: (source: string, target: string) => void;
  onDeleteRequest?: (nodeIds: string[], edgeIds: string[]) => void;
  mutating?: boolean;
}

const nodeTypes = { method: MethodNode };

function FlowView({
  graph,
  layout,
  layoutReset = null,
  diffStatuses,
  overlay = EMPTY_OVERLAY,
  onNodesMoved,
  onConnectRequest,
  onDeleteRequest,
  mutating,
}: GraphCanvasProps) {
  const { selectedNodeIds, selectedEdgeIds } = useWorkspaceSelection();
  const { setViewport, getViewport, getNodes } = useReactFlow();

  // Mount-only snapshot: FlowView remounts per revision via key, and
  // selection/data drift syncs through the effects below.
  const [initial] = useState(() =>
    toFlowElements(graph, layout, diffStatuses, selectedNodeIds, selectedEdgeIds, overlay),
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(initial.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initial.edges);

  // Restore the saved viewport once per revision, including when the
  // layout arrives after first paint; otherwise fit the graph.
  const savedViewport = layout?.viewport ?? null;
  const hasViewport = savedViewport !== null;
  useEffect(() => {
    if (savedViewport) {
      const { x, y, zoom } = savedViewport;
      void setViewport({ x, y, zoom }, { duration: 0 });
    }
  }, [graph.version, savedViewport, setViewport]);

  // Apply saved node positions once per revision, including when the
  // layout arrives after first paint (the mount snapshot above usually
  // sees layout=null while the query is still fetching). User drags win:
  // once nodes are touched, a late layout never clobbers the live
  // arrangement; the debounced save persists the user's positions instead.
  const savedPositions = layout?.positions ?? null;
  const layoutAppliedRef = useRef(false);
  const nodesTouchedRef = useRef(false);
  useEffect(() => {
    if (!savedPositions || layoutAppliedRef.current || nodesTouchedRef.current) return;
    layoutAppliedRef.current = true;
    const points = new Map(savedPositions.map((entry) => [entry.node_id, entry]));
    setNodes((current) =>
      current.map((node) => {
        const point = points.get(node.id);
        if (!point || (node.position.x === point.x && node.position.y === point.y)) {
          return node;
        }
        return { ...node, position: { x: point.x, y: point.y } };
      }),
    );
  }, [savedPositions, setNodes]);

  // Apply an explicit layout reset exactly once per request. The parent
  // persists the same positions, so the saved layout and canvas agree.
  const lastResetId = useRef(0);
  useEffect(() => {
    if (!layoutReset || layoutReset.id === lastResetId.current) return;
    lastResetId.current = layoutReset.id;
    const points = layoutReset.positions;
    setNodes((current) =>
      current.map((node) => {
        const point = points.get(node.id);
        if (!point || (node.position.x === point.x && node.position.y === point.y)) {
          return node;
        }
        return { ...node, position: { x: point.x, y: point.y } };
      }),
    );
  }, [layoutReset, setNodes]);

  // Reflect external (list-driven) selection inside the canvas. The
  // updater returns the previous state when nothing differs so React Flow
  // never churns on already-synced selection.
  useEffect(() => {
    setNodes((current) => {
      let changed = false;
      const next = current.map((node) => {
        const selected = selectedNodeIds.includes(node.id);
        if (node.selected === selected) return node;
        changed = true;
        return { ...node, selected };
      });
      return changed ? next : current;
    });
  }, [selectedNodeIds, setNodes]);
  useEffect(() => {
    setEdges((current) => {
      let changed = false;
      const next = current.map((edge) => {
        const selected = selectedEdgeIds.includes(edge.id);
        const measured = overlay.edges[edge.id] ?? [];
        const label =
          measuredSummary(measured) ??
          (selected ? truncateEdgeLabel(edge.data?.fullLabel) : undefined);
        if (
          edge.selected === selected &&
          edge.label === label &&
          edge.data?.measured === measured
        ) {
          return edge;
        }
        changed = true;
        return {
          ...edge,
          selected,
          label,
          data: {
            ...(edge.data ?? {
              relation: "",
              diffStatus: null,
              fullLabel: null,
              measured: [],
            }),
            measured,
          },
        };
      });
      return changed ? next : current;
    });
  }, [selectedEdgeIds, overlay, setEdges]);

  // Reflect live measured values without disturbing positions or
  // selection. Overlay updates arrive without a revision change.
  useEffect(() => {
    setNodes((current) => {
      let changed = false;
      const next = current.map((node) => {
        const measured = overlay.nodes[node.id] ?? [];
        if (node.data.measured === measured) return node;
        changed = true;
        return { ...node, data: { ...node.data, measured } };
      });
      return changed ? next : current;
    });
  }, [overlay, setNodes]);

  // Reflect compare highlighting without disturbing positions or selection.
  useEffect(() => {
    setNodes((current) => {
      let changed = false;
      const next = current.map((node) => {
        const diffStatus = diffStatuses?.nodes.get(node.id) ?? null;
        if (node.data.diffStatus === diffStatus) return node;
        changed = true;
        return { ...node, data: { ...node.data, diffStatus } };
      });
      return changed ? next : current;
    });
    setEdges((current) => {
      let changed = false;
      const next = current.map((edge) => {
        const diffStatus = diffStatuses?.edges.get(edge.id) ?? null;
        if (edge.data?.diffStatus === diffStatus) return edge;
        changed = true;
        return {
          ...edge,
          data: {
            ...(edge.data ?? {
              relation: "",
              fullLabel: null,
              measured: [],
            }),
            diffStatus,
          },
        };
      });
      return changed ? next : current;
    });
  }, [diffStatuses, setNodes, setEdges]);

  // Canvas-to-store selection flows through discrete click events only.
  // (Mirroring React Flow's onSelectionChange back into the store creates a
  // two-master echo: each side re-applies the other's previous value.)
  const handleNodeClick = useCallback((_event: unknown, node: MethodNodeType): void => {
    useWorkspaceSelection.getState().selectNodes([node.id]);
  }, []);

  const handleEdgeClick = useCallback((_event: unknown, edge: FlowEdge): void => {
    useWorkspaceSelection.getState().selectEdges([edge.id]);
  }, []);

  const handlePaneClick = useCallback((): void => {
    useWorkspaceSelection.getState().clearSelection();
  }, []);

  // Combine node+edge removals from one gesture into a single request.
  const pendingDelete = useRef<{ nodes: string[]; edges: string[] } | null>(null);
  const queueDelete = useCallback(
    (nodeIds: string[], edgeIds: string[]): void => {
      if (!onDeleteRequest) return;
      const pending = pendingDelete.current ?? { nodes: [], edges: [] };
      pending.nodes.push(...nodeIds);
      pending.edges.push(...edgeIds);
      if (!pendingDelete.current) {
        pendingDelete.current = pending;
        queueMicrotask(() => {
          pendingDelete.current = null;
          onDeleteRequest?.(pending.nodes, pending.edges);
        });
      }
    },
    [onDeleteRequest],
  );

  const handleNodesChange = useCallback(
    (changes: NodeChange<MethodNodeType>[]): void => {
      const kept = changes.filter((change) => change.type !== "remove");
      if (kept.length > 0) onNodesChange(kept);
      const removed = changes
        .filter((change) => change.type === "remove")
        .map((change) => change.id);
      if (removed.length > 0) queueDelete(removed, []);
    },
    [onNodesChange, queueDelete],
  );

  const handleEdgesChange = useCallback(
    (changes: EdgeChange<FlowEdge>[]): void => {
      const kept = changes.filter((change) => change.type !== "remove");
      if (kept.length > 0) onEdgesChange(kept);
      const removed = changes
        .filter((change) => change.type === "remove")
        .map((change) => change.id);
      if (removed.length > 0) queueDelete([], removed);
    },
    [onEdgesChange, queueDelete],
  );

  const handleConnect = useCallback(
    (connection: Connection): void => {
      if (connection.source && connection.target) {
        onConnectRequest?.(connection.source, connection.target);
      }
    },
    [onConnectRequest],
  );

  const handleNodeDragStop: OnNodeDrag<MethodNodeType> = useCallback(
    (_event, _node, _dragged) => {
      nodesTouchedRef.current = true;
      if (!onNodesMoved) return;
      // Read full canvas state: the drag callback only carries the dragged
      // nodes, so serializing it would reset every other node to the origin.
      const positions = new Map<string, Point>();
      for (const item of getNodes()) {
        positions.set(item.id, { x: item.position.x, y: item.position.y });
      }
      const view = getViewport();
      onNodesMoved(positions, { x: view.x, y: view.y, zoom: view.zoom });
    },
    [onNodesMoved, getViewport, getNodes],
  );

  return (
    <div className={styles.canvas} data-mutating={mutating === true}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onNodeClick={handleNodeClick}
        onEdgeClick={handleEdgeClick}
        onPaneClick={handlePaneClick}
        onConnect={onConnectRequest ? handleConnect : undefined}
        onNodeDragStop={onNodesMoved ? handleNodeDragStop : undefined}
        nodesConnectable={onConnectRequest !== undefined}
        deleteKeyCode={onDeleteRequest ? "Delete" : null}
        multiSelectionKeyCode="Shift"
        fitView={!hasViewport}
        fitViewOptions={{ padding: 0.2, maxZoom: 1 }}
        minZoom={0.2}
        maxZoom={2}
        proOptions={{ hideAttribution: false }}
      >
        <Background variant={BackgroundVariant.Dots} gap={24} size={1} />
        <MiniMap pannable zoomable />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}

export function GraphCanvas(props: GraphCanvasProps) {
  return (
    <ReactFlowProvider>
      <FlowView key={props.graph.version} {...props} />
    </ReactFlowProvider>
  );
}
