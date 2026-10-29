/* Pure chip-view mapping: electronics scope, schematic boxes, and array
   floorplan grids. No renderer imports so unit tests stay dependency-free. */

import type {
  EntityResolution,
  GraphEntities,
  MethodologyGraph,
} from "../../lib/types.ts";
import { resolutionsByNodeId } from "./graph3d.ts";
import { autoLayout } from "./layout.ts";

export interface ChipScope {
  /** Electronics-resolved nodes plus their internal edges. */
  graph: MethodologyGraph;
  resolutions: Map<string, EntityResolution>;
  /** Nodes without an identified electronics part, hidden from chip views. */
  hiddenCount: number;
}

/** Narrow one graph to the nodes a chip view can draw: only nodes whose
 *  resolution names the electronics domain appear. Generic placeholders
 *  inside the domain render as labeled generic boxes, never guessed
 *  parts; everything outside the domain stays in the canvas/structure
 *  views. */
export function chipScope(graph: MethodologyGraph, entities: GraphEntities | null): ChipScope {
  const resolutions = resolutionsByNodeId(entities);
  const nodes = graph.nodes.filter(
    (node) => resolutions.get(node.id)?.domain === "electronics",
  );
  const ids = new Set(nodes.map((node) => node.id));
  return {
    graph: {
      ...graph,
      nodes,
      edges: graph.edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target)),
    },
    resolutions,
    hiddenCount: graph.nodes.length - nodes.length,
  };
}

export interface SchematicBox {
  nodeId: string;
  symbol: string;
  x: number;
  y: number;
  w: number;
  h: number;
  /** Bitcells expand into the canonical 6T sub-circuit. */
  expanded: boolean;
}

/** Default symbol footprint; the 280px auto-layout pitch clears it. */
export const SCHEMATIC_SYMBOL_W = 128;
export const SCHEMATIC_SYMBOL_H = 88;
/** Canonical 6T bitcell footprint, still inside the 280px pitch. */
export const BITCELL_W = 224;
export const BITCELL_H = 176;
export const SCHEMATIC_PAD = 24;

/** Center one box per scoped node on the deterministic auto-layout. The
 *  schematic always re-lays out: saved canvas positions pack nodes for
 *  the flow view, not for symbol footprints. */
export function schematicBoxes(scope: ChipScope): {
  boxes: SchematicBox[];
  width: number;
  height: number;
} {
  const positions = autoLayout(scope.graph);
  const boxes = scope.graph.nodes.map((node) => {
    const point = positions.get(node.id) ?? { x: 0, y: 0 };
    const symbol = scope.resolutions.get(node.id)?.symbol || "generic";
    const expanded = symbol === "bitcell";
    const w = expanded ? BITCELL_W : SCHEMATIC_SYMBOL_W;
    const h = expanded ? BITCELL_H : SCHEMATIC_SYMBOL_H;
    return { nodeId: node.id, symbol, x: point.x - w / 2, y: point.y - h / 2, w, h, expanded };
  });
  let width = SCHEMATIC_PAD * 2;
  let height = SCHEMATIC_PAD * 2;
  for (const box of boxes) {
    width = Math.max(width, box.x + box.w + SCHEMATIC_PAD);
    height = Math.max(height, box.y + box.h + SCHEMATIC_PAD);
  }
  return { boxes, width, height };
}

export interface FloorplanItem {
  nodeId: string;
  label: string;
  symbol: string;
  x: number;
  y: number;
  w: number;
  h: number;
  kind: "cell" | "block";
}

export const FLOORPLAN_CELL = 56;
export const FLOORPLAN_GAP = 6;
export const FLOORPLAN_BLOCK_W = 132;
export const FLOORPLAN_BLOCK_H = 60;
export const FLOORPLAN_PAD = 24;

/** Lay bitcells in a square-ish array with periphery blocks below. The
 *  paper gives no array dimensions, so the grid derives from the node
 *  count and the view labels the arrangement illustrative. */
export function floorplanLayout(scope: ChipScope): {
  items: FloorplanItem[];
  width: number;
  height: number;
  columns: number;
  rows: number;
} {
  const labels = new Map(scope.graph.nodes.map((node) => [node.id, node.label]));
  const cells = scope.graph.nodes.filter(
    (node) => scope.resolutions.get(node.id)?.symbol === "bitcell",
  );
  const blocks = scope.graph.nodes.filter(
    (node) => scope.resolutions.get(node.id)?.symbol !== "bitcell",
  );
  const columns = cells.length === 0 ? 0 : Math.ceil(Math.sqrt(cells.length));
  const rows = columns === 0 ? 0 : Math.ceil(cells.length / columns);
  const items: FloorplanItem[] = cells.map((node, index) => ({
    nodeId: node.id,
    label: labels.get(node.id) ?? node.id,
    symbol: "bitcell",
    x: FLOORPLAN_PAD + (index % columns) * (FLOORPLAN_CELL + FLOORPLAN_GAP),
    y: FLOORPLAN_PAD + Math.floor(index / columns) * (FLOORPLAN_CELL + FLOORPLAN_GAP),
    w: FLOORPLAN_CELL,
    h: FLOORPLAN_CELL,
    kind: "cell",
  }));
  const arrayBottom =
    rows === 0 ? FLOORPLAN_PAD : FLOORPLAN_PAD + rows * (FLOORPLAN_CELL + FLOORPLAN_GAP);
  const blockTop = arrayBottom + (rows === 0 ? 0 : FLOORPLAN_GAP * 2);
  blocks.forEach((node, index) => {
    items.push({
      nodeId: node.id,
      label: labels.get(node.id) ?? node.id,
      symbol: scope.resolutions.get(node.id)?.symbol || "generic",
      x: FLOORPLAN_PAD + index * (FLOORPLAN_BLOCK_W + FLOORPLAN_GAP * 2),
      y: blockTop,
      w: FLOORPLAN_BLOCK_W,
      h: FLOORPLAN_BLOCK_H,
      kind: "block",
    });
  });
  let width = FLOORPLAN_PAD * 2;
  let height = FLOORPLAN_PAD * 2;
  for (const item of items) {
    width = Math.max(width, item.x + item.w + FLOORPLAN_PAD);
    height = Math.max(height, item.y + item.h + FLOORPLAN_PAD);
  }
  return { items, width, height, columns, rows };
}
