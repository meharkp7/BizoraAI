/* Pure graph-to-React-Flow mapping, unit-testable without a browser. */

import type { Edge } from "@xyflow/react";
import type {
  GraphLayout,
  GraphRevisionDiff,
  MeasuredOverlay,
  MethodologyGraph,
  OverlayValue,
} from "../../lib/types.ts";
import { ASSUMED_CONFIG_KEY } from "../correction/assumptions.ts";
import { resolvePositions } from "./layout.ts";
import type { MethodNodeType, NodeDiffStatus } from "./MethodNode.tsx";

export interface CanvasDiffStatuses {
  nodes: Map<string, NodeDiffStatus>;
  edges: Map<string, NodeDiffStatus>;
}

export type FlowEdge = Edge<{
  relation: string;
  diffStatus: NodeDiffStatus | null;
  fullLabel: string | null;
  measured: OverlayValue[];
}>;

/** Only the selected connection shows its narrative on canvas; everything
 *  else would collide in dense graphs. Full labels always live in the
 *  Connections list and the edge inspector. */
export const MAX_EDGE_LABEL = 40;

export function truncateEdgeLabel(label: string | null | undefined): string | undefined {
  if (!label) return undefined;
  if (label.length <= MAX_EDGE_LABEL) return label;
  return `${label.slice(0, MAX_EDGE_LABEL - 1).trimEnd()}…`;
}

/** One-line overlay summary for labels: first value plus overflow
 *  count. Undefined when unmeasured so callers fall back cleanly. */
export function measuredSummary(values: OverlayValue[] | undefined): string | undefined {
  if (!values || values.length === 0) return undefined;
  const first = values[0];
  const head = `${first.signal}=${first.value}${first.unit ?? ""}`;
  return values.length === 1 ? head : `${head} +${values.length - 1}`;
}

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
  overlay: MeasuredOverlay | null = null,
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
        assumed: node.config[ASSUMED_CONFIG_KEY] === true,
        measured: overlay?.nodes[node.id] ?? [],
      },
      selected: selectedNodeIds.includes(node.id),
    };
  });
  const edges: FlowEdge[] = graph.edges.map((edge) => {
    const measured = overlay?.edges[edge.id] ?? [];
    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label:
        measuredSummary(measured) ??
        (selectedEdgeIds.includes(edge.id) ? truncateEdgeLabel(edge.label) : undefined),
      data: {
        relation: edge.relation,
        diffStatus: diffStatuses?.edges.get(edge.id) ?? null,
        fullLabel: edge.label ?? null,
        measured,
      },
      selected: selectedEdgeIds.includes(edge.id),
    };
  });
  return { nodes, edges };
}
