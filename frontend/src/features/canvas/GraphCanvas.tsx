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
import type { GraphLayout, MethodologyGraph, ViewportState } from "../../lib/types.ts";
import { toFlowElements } from "./flowElements.ts";
import type { CanvasDiffStatuses, FlowEdge } from "./flowElements.ts";
import type { Point } from "./layout.ts";
import { MethodNode } from "./MethodNode.tsx";
import type { MethodNodeType } from "./MethodNode.tsx";
import styles from "./GraphCanvas.module.css";

export interface GraphCanvasProps {
  graph: MethodologyGraph;
  layout: GraphLayout | null;
  diffStatuses: CanvasDiffStatuses | null;
  onNodesMoved?: (positions: Map<string, Point>, viewport: ViewportState) => void;
  onConnectRequest?: (source: string, target: string) => void;
  onDeleteRequest?: (nodeIds: string[], edgeIds: string[]) => void;
  mutating?: boolean;
}

const nodeTypes = { method: MethodNode };

function FlowView({
  graph,
  layout,
  diffStatuses,
  onNodesMoved,
  onConnectRequest,
  onDeleteRequest,
  mutating,
}: GraphCanvasProps) {
  const { selectedNodeIds, selectedEdgeIds } = useWorkspaceSelection();
  const { setViewport, getViewport } = useReactFlow();

  // Mount-only snapshot: FlowView remounts per revision via key, and
  // selection/data drift syncs through the effects below.
  const [initial] = useState(() =>
    toFlowElements(graph, layout, diffStatuses, selectedNodeIds, selectedEdgeIds),
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
        if (edge.selected === selected) return edge;
        changed = true;
        return { ...edge, selected };
      });
      return changed ? next : current;
    });
  }, [selectedEdgeIds, setEdges]);

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
        return { ...edge, data: { ...(edge.data ?? { relation: "" }), diffStatus } };
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
    (_event, _node, all) => {
      if (!onNodesMoved) return;
      const positions = new Map<string, Point>();
      for (const item of all) {
        positions.set(item.id, { x: item.position.x, y: item.position.y });
      }
      const view = getViewport();
      onNodesMoved(positions, { x: view.x, y: view.y, zoom: view.zoom });
    },
    [onNodesMoved, getViewport],
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
