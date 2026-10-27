/* Deterministic layout helpers: merge saved positions over a layered
   auto-layout fallback. Pure functions; the API stays the source of truth. */

import type { GraphLayout, MethodologyGraph, NodePosition } from "../../lib/types.ts";

export interface Point {
  x: number;
  y: number;
}

const LAYER_DX = 230;
const LAYER_DY = 170;

/** Assign each node a layer by longest-path depth. Terminates always:
 *  cyclic leftovers (rejected by the backend, tolerated here) stack in id
 *  order below the acyclic layers. */
export function layerByNodeId(graph: MethodologyGraph): Map<string, number> {
  const ids = new Set(graph.nodes.map((node) => node.id));
  const indegree = new Map<string, number>();
  const outgoing = new Map<string, string[]>();
  for (const node of graph.nodes) {
    indegree.set(node.id, 0);
    outgoing.set(node.id, []);
  }
  for (const edge of graph.edges) {
    if (!ids.has(edge.source) || !ids.has(edge.target)) continue;
    indegree.set(edge.target, (indegree.get(edge.target) as number) + 1);
    (outgoing.get(edge.source) as string[]).push(edge.target);
  }

  const layers = new Map<string, number>();
  const queue = [...ids].filter((id) => indegree.get(id) === 0).sort();
  for (const id of queue) layers.set(id, 0);
  while (queue.length > 0) {
    const current = queue.shift() as string;
    const depth = layers.get(current) as number;
    for (const next of outgoing.get(current) as string[]) {
      layers.set(next, Math.max(layers.get(next) ?? 0, depth + 1));
      const remaining = (indegree.get(next) as number) - 1;
      indegree.set(next, remaining);
      if (remaining === 0) queue.push(next);
    }
  }

  const leftovers = [...ids].filter((id) => !layers.has(id)).sort();
  let base = 0;
  for (const depth of layers.values()) base = Math.max(base, depth + 1);
  leftovers.forEach((id, index) => layers.set(id, base + index));
  return layers;
}

/** Deterministic fallback positions: layers flow downward, ids order left-right. */
export function autoLayout(graph: MethodologyGraph): Map<string, Point> {
  const layers = layerByNodeId(graph);
  const members = new Map<number, string[]>();
  for (const [id, depth] of layers) {
    const list = members.get(depth) ?? [];
    list.push(id);
    members.set(depth, list);
  }
  const positions = new Map<string, Point>();
  for (const [depth, ids] of members) {
    const ordered = [...ids].sort();
    ordered.forEach((id, index) => {
      positions.set(id, { x: index * LAYER_DX, y: depth * LAYER_DY });
    });
  }
  return positions;
}

/** Saved positions win; missing nodes fall back to auto-layout. */
export function resolvePositions(
  graph: MethodologyGraph,
  layout: GraphLayout | null,
): Map<string, Point> {
  const fallback = autoLayout(graph);
  if (!layout) return fallback;
  const saved = new Map(layout.positions.map((p) => [p.node_id, { x: p.x, y: p.y }]));
  const positions = new Map<string, Point>();
  for (const node of graph.nodes) {
    positions.set(node.id, saved.get(node.id) ?? (fallback.get(node.id) as Point));
  }
  return positions;
}

/** Serialize positioned nodes for the layout API. */
export function toNodePositions(
  graph: MethodologyGraph,
  positions: Map<string, Point>,
): NodePosition[] {
  return graph.nodes.map((node) => {
    const point = positions.get(node.id) ?? { x: 0, y: 0 };
    return { node_id: node.id, x: point.x, y: point.y, z: 0 };
  });
}

/** True when a position map matches saved layout entries exactly. */
export function matchesSavedPositions(
  saved: readonly NodePosition[],
  positions: Map<string, Point>,
): boolean {
  if (saved.length !== positions.size) return false;
  return saved.every((entry) => {
    const point = positions.get(entry.node_id);
    return point !== undefined && point.x === entry.x && point.y === entry.y;
  });
}
