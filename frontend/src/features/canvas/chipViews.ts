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

/** Narrow one graph to the nodes a chip view can draw: only physical
 *  nodes whose resolution names the electronics domain appear. Generic
 *  placeholders inside the domain render as labeled generic boxes,
 *  never guessed parts; process nodes stay in the flow view and
 *  everything else stays in the structure diagram. */
export function chipScope(graph: MethodologyGraph, entities: GraphEntities | null): ChipScope {
  const resolutions = resolutionsByNodeId(entities);
  const nodes = graph.nodes.filter((node) => {
    const resolution = resolutions.get(node.id);
    return resolution?.domain === "electronics" && resolution?.physical !== false;
  });
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

export interface ArrayDimensions {
  rows: number;
  columns: number;
  /** Node whose config or text stated the geometry. */
  sourceNodeId: string;
  /** Config keys win; explicit "NxM array" text is the fallback. */
  source: "config" | "text";
}

const ARRAY_TEXT = /\b(\d{1,4})\s*[x×]\s*(\d{1,4})\b/i;
const COLUMN_KEY = /col(umn)?s?/i;
const ROW_KEY = /rows?|cells?_per/i;

function positiveInt(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) && value > 0 && value <= 4096
    ? value
    : null;
}

/** Array geometry stated by the paper, or null when unstated. Reads
 *  structured config first (`array: "16x16"` or row/column count
 *  pairs), then explicit "NxM array/grid" text. Never derives
 *  dimensions from the node count — an absent return hides the
 *  floorplan mode instead of inventing a layout. */
export function arrayDimensions(scope: ChipScope): ArrayDimensions | null {
  for (const node of scope.graph.nodes) {
    const config = node.config ?? {};
    const array = config["array"];
    if (typeof array === "string") {
      const match = ARRAY_TEXT.exec(array);
      if (match) {
        const rows = Number(match[1]);
        const columns = Number(match[2]);
        if (rows > 0 && columns > 0 && rows <= 4096 && columns <= 4096) {
          return { rows, columns, sourceNodeId: node.id, source: "config" };
        }
      }
    }
    let columns: number | null = null;
    let rows: number | null = null;
    for (const [key, value] of Object.entries(config)) {
      const count = positiveInt(value);
      if (count === null) continue;
      if (ROW_KEY.test(key) && key !== "array" && rows === null) rows = count;
      else if (COLUMN_KEY.test(key) && columns === null) columns = count;
    }
    if (rows !== null && columns !== null) {
      return { rows, columns, sourceNodeId: node.id, source: "config" };
    }
  }
  for (const node of scope.graph.nodes) {
    const text = `${node.label} ${node.description ?? ""}`;
    if (!/array|grid|bitcell/i.test(text)) continue;
    const match = ARRAY_TEXT.exec(text);
    if (match) {
      const rows = Number(match[1]);
      const columns = Number(match[2]);
      if (rows > 0 && columns > 0) {
        return { rows, columns, sourceNodeId: node.id, source: "text" };
      }
    }
  }
  return null;
}

/** The schematic mode needs real connections: at least one edge
 *  between scoped electronics parts. Otherwise the mode stays hidden
 *  instead of showing floating symbols. */
export function schematicSupport(scope: ChipScope): boolean {
  return scope.graph.edges.length > 0;
}

/** Narrow a scope to parts with at least one internal edge, counting
 *  the dropped unconnected parts so the view can say so honestly. */
export function connectedScope(scope: ChipScope): { scope: ChipScope; droppedCount: number } {
  const wired = new Set<string>();
  for (const edge of scope.graph.edges) {
    wired.add(edge.source);
    wired.add(edge.target);
  }
  const nodes = scope.graph.nodes.filter((node) => wired.has(node.id));
  return {
    scope: {
      graph: { ...scope.graph, nodes },
      resolutions: scope.resolutions,
      hiddenCount: scope.hiddenCount + (scope.graph.nodes.length - nodes.length),
    },
    droppedCount: scope.graph.nodes.length - nodes.length,
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
/** Minimum sheet size: tiny schematics would otherwise blow up to fill
 *  the panel, magnifying labels to poster size. */
export const SCHEMATIC_MIN_W = 640;
export const SCHEMATIC_MIN_H = 400;

/** Center one box per scoped node on the deterministic auto-layout. The
 *  schematic always re-lays out: saved canvas positions pack nodes for
 *  the flow view, not for symbol footprints. Boxes shift so the whole
 *  arrangement sits inside the sheet with a padding margin. */
export function schematicBoxes(scope: ChipScope): {
  boxes: SchematicBox[];
  width: number;
  height: number;
} {
  const positions = autoLayout(scope.graph);
  const raw = scope.graph.nodes.map((node) => {
    const point = positions.get(node.id) ?? { x: 0, y: 0 };
    const symbol = scope.resolutions.get(node.id)?.symbol || "generic";
    const expanded = symbol === "bitcell";
    const w = expanded ? BITCELL_W : SCHEMATIC_SYMBOL_W;
    const h = expanded ? BITCELL_H : SCHEMATIC_SYMBOL_H;
    return { nodeId: node.id, symbol, x: point.x - w / 2, y: point.y - h / 2, w, h, expanded };
  });
  const minX = raw.length === 0 ? 0 : Math.min(...raw.map((box) => box.x));
  const minY = raw.length === 0 ? 0 : Math.min(...raw.map((box) => box.y));
  const dx = SCHEMATIC_PAD - minX;
  const dy = SCHEMATIC_PAD - minY;
  const boxes = raw.map((box) => ({ ...box, x: box.x + dx, y: box.y + dy }));
  let width = SCHEMATIC_MIN_W;
  let height = SCHEMATIC_MIN_H;
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

export const FLOORPLAN_BLOCK_W = 132;
export const FLOORPLAN_BLOCK_H = 60;
export const FLOORPLAN_PAD = 24;
/** Minimum sheet size, for the same poster-scale reason as schematics. */
export const FLOORPLAN_MIN_W = 560;
export const FLOORPLAN_MIN_H = 360;
/** Widest the array may grow before cells shrink to fit. */
export const FLOORPLAN_MAX_ARRAY_W = 840;
/** Most SVG cells ever drawn; bigger arrays downsample. */
export const FLOORPLAN_MAX_CELLS = 2500;

/** Lay the paper's stated array geometry with periphery blocks below.
 *  The grid comes from `dims` (see arrayDimensions), never from the
 *  node count; every cell links to the bitcell node when the graph
 *  has one, else to the node that stated the geometry. */
export function floorplanLayout(
  scope: ChipScope,
  dims: ArrayDimensions,
): {
  items: FloorplanItem[];
  width: number;
  height: number;
  columns: number;
  rows: number;
  downsampled: boolean;
} {
  const labels = new Map(scope.graph.nodes.map((node) => [node.id, node.label]));
  const bitcell = scope.graph.nodes.find(
    (node) => scope.resolutions.get(node.id)?.symbol === "bitcell",
  );
  const cellNodeId = bitcell?.id ?? dims.sourceNodeId;
  const cellLabel = labels.get(cellNodeId) ?? cellNodeId;
  const blocks = scope.graph.nodes.filter(
    (node) => scope.resolutions.get(node.id)?.symbol !== "bitcell",
  );
  const total = dims.rows * dims.columns;
  const downsampled = total > FLOORPLAN_MAX_CELLS;
  const scale = downsampled ? Math.sqrt(FLOORPLAN_MAX_CELLS / total) : 1;
  const columns = Math.max(1, Math.round(dims.columns * scale));
  const rows = Math.max(1, Math.round(dims.rows * scale));
  const pitch = Math.max(3, Math.min(32, Math.floor(FLOORPLAN_MAX_ARRAY_W / columns)));
  const gap = pitch > 8 ? 3 : 1;
  const size = Math.max(1, pitch - gap);
  const items: FloorplanItem[] = [];
  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < columns; column += 1) {
      items.push({
        nodeId: cellNodeId,
        label: cellLabel,
        symbol: "bitcell",
        x: FLOORPLAN_PAD + column * pitch,
        y: FLOORPLAN_PAD + row * pitch,
        w: size,
        h: size,
        kind: "cell",
      });
    }
  }
  const blockTop = FLOORPLAN_PAD + rows * pitch + FLOORPLAN_PAD;
  blocks.forEach((node, index) => {
    items.push({
      nodeId: node.id,
      label: labels.get(node.id) ?? node.id,
      symbol: scope.resolutions.get(node.id)?.symbol || "generic",
      x: FLOORPLAN_PAD + index * (FLOORPLAN_BLOCK_W + FLOORPLAN_PAD / 2),
      y: blockTop,
      w: FLOORPLAN_BLOCK_W,
      h: FLOORPLAN_BLOCK_H,
      kind: "block",
    });
  });
  let width = FLOORPLAN_MIN_W;
  let height = FLOORPLAN_MIN_H;
  for (const item of items) {
    width = Math.max(width, item.x + item.w + FLOORPLAN_PAD);
    height = Math.max(height, item.y + item.h + FLOORPLAN_PAD);
  }
  return { items, width, height, columns, rows, downsampled };
}
