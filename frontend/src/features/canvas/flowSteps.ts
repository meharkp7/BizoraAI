/* Flow-step model: the walkthrough order over the flow subgraph.
   Pure derivation from node ids and edges; step ids are graph node
   ids, so the same model drives the stepper today and live
   telemetry highlighting tomorrow (MeasuredOverlay keys by node). */

import type { MethodologyGraph } from "../../lib/types.ts";
import { layerByNodeId } from "./layout.ts";

export interface FlowStep {
  /** Graph node id this step walks through. */
  nodeId: string;
  /** Zero-based position in the walkthrough. */
  index: number;
  prevIds: string[];
  nextIds: string[];
}

/** Derive the walkthrough order: layers flow first, ids break ties.
 *  Deterministic for any input order; disconnected nodes keep their
 *  own steps; cyclic leftovers stack last (see layerByNodeId). */
export function deriveFlowSteps(graph: MethodologyGraph): FlowStep[] {
  const ids = new Set(graph.nodes.map((node) => node.id));
  const layers = layerByNodeId(graph);
  const ordered = [...ids].sort((a, b) => {
    const depth = (layers.get(a) ?? 0) - (layers.get(b) ?? 0);
    return depth !== 0 ? depth : a.localeCompare(b);
  });
  const prev = new Map<string, string[]>();
  const next = new Map<string, string[]>();
  for (const id of ids) {
    prev.set(id, []);
    next.set(id, []);
  }
  for (const edge of graph.edges) {
    if (!ids.has(edge.source) || !ids.has(edge.target)) continue;
    next.get(edge.source)?.push(edge.target);
    prev.get(edge.target)?.push(edge.source);
  }
  return ordered.map((nodeId, index) => ({
    nodeId,
    index,
    prevIds: [...(prev.get(nodeId) ?? [])].sort(),
    nextIds: [...(next.get(nodeId) ?? [])].sort(),
  }));
}
