/* Pure graph-to-React-Flow mapping, unit-testable without a browser. */

import type { Edge } from "@xyflow/react";
import type { GraphLayout, GraphRevisionDiff, MethodologyGraph } from "../../lib/types.ts";
import { resolvePositions } from "./layout.ts";
import type { MethodNodeType, NodeDiffStatus } from "./MethodNode.tsx";

export interface CanvasDiffStatuses {
  nodes: Map<string, NodeDiffStatus>;
  edges: Map<string, NodeDiffStatus>;
}

export type FlowEdge = Edge<{ relation: string; diffStatus: NodeDiffStatus | null }>;

/** Translate a revision diff into canvas highlight statuses. Removed
 *  elements are absent from the current graph, so only added/changed map. */
export function diffStatusMaps(diff: GraphRevisionDiff): CanvasDiffStatuses {
  const nodes = new Map<string, NodeDiffStatus>();
  for (const node of diff.added_nodes) nodes.set(node.id, "added");
  for (const change of diff.changed_nodes) nodes.set(change.node_id, "changed");
  const edges = new Map<string, NodeDiffStatus>();
  for (const edge of diff.added_edges) edges.set(edge.id, "added");
  for (const change of diff.changed_edges) edges.set(change.edge_id, "changed");
  return { nodes, edges };
}

export function toFlowElements(
  graph: MethodologyGraph,
  layout: GraphLayout | null,
  diffStatuses: CanvasDiffStatuses | null,
  selectedNodeIds: string[],
  selectedEdgeIds: string[],
): { nodes: MethodNodeType[]; edges: FlowEdge[] } {
  const positions = resolvePositions(graph, layout);
  const nodes: MethodNodeType[] = graph.nodes.map((node) => {
    const point = positions.get(node.id) ?? { x: 0, y: 0 };
    return {
      id: node.id,
      type: "method",
      position: { x: point.x, y: point.y },
      data: {
        label: node.label,
        kind: node.kind,
        provenance: node.provenance,
        confidence: node.confidence,
        diffStatus: diffStatuses?.nodes.get(node.id) ?? null,
      },
      selected: selectedNodeIds.includes(node.id),
    };
  });
  const edges: FlowEdge[] = graph.edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    label: edge.label ?? undefined,
    data: {
      relation: edge.relation,
      diffStatus: diffStatuses?.edges.get(edge.id) ?? null,
    },
    selected: selectedEdgeIds.includes(edge.id),
  }));
  return { nodes, edges };
}
