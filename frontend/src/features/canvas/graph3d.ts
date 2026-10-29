/* Pure 3D mapping: deterministic world positions and kind colors derived
   from the same 2D layout source of truth. No three.js imports here so unit
   tests never need WebGL. */

import type {
  EntityResolution,
  GraphEntities,
  GraphLayout,
  MethodologyGraph,
  NodeKind,
} from "../../lib/types.ts";
import { layerByNodeId, resolvePositions } from "./layout.ts";

export interface WorldPoint {
  x: number;
  y: number;
  z: number;
}

/** 2D pixels per world unit: a 280px sibling pitch becomes 5.6 units. */
export const WORLD_SCALE = 50;
/** Vertical rise per depth layer, lifting layers into a cascade. */
export const LAYER_RISE = 3.2;
/** Radius of the depth helix that keeps chain-like graphs explorable. */
export const HELIX_RADIUS = 6;
/** Helix turn per depth layer (radians). */
export const HELIX_STEP = 0.65;

/** Muted earth-tone palette matching the warm studio theme. */
export const KIND_COLORS: Record<NodeKind, number> = {
  input: 0x5f6636,
  dataset: 0x7a6f4f,
  preprocessing: 0x8b8471,
  model: 0x8a4d26,
  operation: 0xa06a35,
  loss: 0xa83a2a,
  optimizer: 0x5c6650,
  evaluation: 0x476063,
  output: 0x23211b,
  component: 0xa08c5b,
};

export const EDGE_COLOR = 0x8b8471;
export const SELECT_COLOR = 0x8a4d26;

/** Lift the resolved 2D arrangement into world space: x carries the 2D
 *  sibling spread, y rises with graph depth, and a deterministic helix
 *  coils each level so deep stacks become explorable towers instead of
 *  diagonal snakes. Depth drives y alone: reusing the 2D vertical run
 *  for z would stretch chains along a single diagonal. */
export function toWorldPositions(
  graph: MethodologyGraph,
  layout: GraphLayout | null,
): Map<string, WorldPoint> {
  const flat = resolvePositions(graph, layout);
  const layers = layerByNodeId(graph);
  const positions = new Map<string, WorldPoint>();
  for (const node of graph.nodes) {
    const point = flat.get(node.id) ?? { x: 0, y: 0 };
    const depth = layers.get(node.id) ?? 0;
    const angle = depth * HELIX_STEP;
    positions.set(node.id, {
      x: point.x / WORLD_SCALE + Math.sin(angle) * HELIX_RADIUS,
      y: depth * LAYER_RISE,
      z: (Math.cos(angle) - 1) * HELIX_RADIUS,
    });
  }
  return positions;
}

type Vec3 = [number, number, number];

function sub(a: Vec3, b: Vec3): Vec3 {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}

function dot(a: Vec3, b: Vec3): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

function cross(a: Vec3, b: Vec3): Vec3 {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
}

function norm(a: Vec3): Vec3 {
  const length = Math.hypot(a[0], a[1], a[2]) || 1;
  return [a[0] / length, a[1] / length, a[2] / length];
}

/** Exact camera distance fitting every node (plus `pad` world units) inside
 *  the frame for a camera looking from `direction` at the positions' center.
 *  Unlike axis-aligned fits, diagonal views cannot clip corners. */
export function fitDistance(
  positions: Map<string, WorldPoint>,
  direction: WorldPoint,
  fovDegrees: number,
  aspect: number,
  pad = 0,
  margin = 1.06,
): number {
  const points = [...positions.values()];
  if (points.length === 0) return 10;
  const min: Vec3 = [Infinity, Infinity, Infinity];
  const max: Vec3 = [-Infinity, -Infinity, -Infinity];
  for (const point of points) {
    min[0] = Math.min(min[0], point.x - pad);
    min[1] = Math.min(min[1], point.y - pad);
    min[2] = Math.min(min[2], point.z - pad);
    max[0] = Math.max(max[0], point.x + pad);
    max[1] = Math.max(max[1], point.y + pad);
    max[2] = Math.max(max[2], point.z + pad);
  }
  const center: Vec3 = [(min[0] + max[0]) / 2, (min[1] + max[1]) / 2, (min[2] + max[2]) / 2];
  const viewDir = norm([-direction.x, -direction.y, -direction.z]);
  const right = norm(cross(viewDir, [0, 1, 0]));
  const up = cross(right, viewDir);
  const tanV = Math.tan(((fovDegrees / 2) * Math.PI) / 180);
  const tanH = tanV * Math.max(aspect, 0.01);
  const corners: Vec3[] = [];
  for (let i = 0; i < 8; i++) {
    corners.push([
      (i & 1) === 0 ? min[0] : max[0],
      (i & 2) === 0 ? min[1] : max[1],
      (i & 4) === 0 ? min[2] : max[2],
    ]);
  }
  // Vertical fit uses the true box (Y-rotation preserves heights). The
  // horizontal fit uses the ring the footprint sweeps, so orbiting around
  // Y can never clip the sides.
  let ring = 0;
  for (const point of points) {
    ring = Math.max(ring, Math.hypot(point.x - center[0], point.z - center[2]));
  }
  ring += pad;
  const ringCorners: Vec3[] = [];
  for (const sx of [-1, 1]) {
    for (const sy of [min[1], max[1]]) {
      for (const sz of [-1, 1]) {
        ringCorners.push([center[0] + sx * ring, sy, center[2] + sz * ring]);
      }
    }
  }
  const need = (corner: Vec3, axis: Vec3, tan: number): number => {
    const relative = sub(corner, center);
    return Math.abs(dot(relative, axis)) / tan - dot(relative, viewDir);
  };
  let distance = 1;
  for (const corner of corners) {
    distance = Math.max(distance, need(corner, up, tanV));
  }
  for (const corner of ringCorners) {
    distance = Math.max(distance, need(corner, right, tanH));
  }
  return distance * margin;
}

/** Three.js primitive vocabulary shared by every 3D visual. Pack
 *  `model_3d` keys name one of these directly; unknown keys fall back
 *  to the sphere so new backend values never break the renderer. */
export type ArchetypeGeometry =
  | "sphere"
  | "box"
  | "slab"
  | "cylinder"
  | "cone"
  | "torus"
  | "octahedron"
  | "tetrahedron"
  | "icosahedron"
  | "dodecahedron";

const ARCHETYPES: ReadonlySet<string> = new Set([
  "sphere",
  "box",
  "slab",
  "cylinder",
  "cone",
  "torus",
  "octahedron",
  "tetrahedron",
  "icosahedron",
  "dodecahedron",
]);

/** Library-catalog glyphs per component category. Shapes repeat across
 *  domains only where the domains never share a graph (power/storage
 *  cylinders, package/compute boxes), so one key stays unambiguous.
 *  Canvas and 3D shapes never derive from this table: they follow the
 *  pack-declared render spec (symbol, model_3d) instead. */
export const CATEGORY_GEOMETRY: Record<string, ArchetypeGeometry> = {
  package: "box",
  discrete: "cone",
  passive: "torus",
  power: "cylinder",
  sensor: "octahedron",
  compute: "box",
  network: "torus",
  format: "icosahedron",
  signal: "tetrahedron",
  service: "dodecahedron",
  storage: "cylinder",
  layer: "slab",
  generic: "sphere",
};

export function archetypeFor(category: string | null | undefined): ArchetypeGeometry {
  if (!category) return "sphere";
  return CATEGORY_GEOMETRY[category] ?? "sphere";
}

/** Representative 3D solid per pack-declared symbol: the interim mapping
 *  until packs pin representative visuals in `model_3d` themselves.
 *  Process symbols map to the same solids only as a safety net — the
 *  structure scene excludes non-physical nodes via splitGraph instead
 *  of rendering them as hardware. */
export const SYMBOL_GEOMETRY: Record<string, ArchetypeGeometry> = {
  generic: "sphere",
  bitcell: "box",
  transistor: "cone",
  gate: "box",
  source: "cylinder",
  bias: "box",
  senseamp: "box",
  meter: "octahedron",
  passive: "torus",
  diode: "cone",
  chip: "box",
  adc: "box",
  mcu: "box",
  sensor: "octahedron",
  actuator: "box",
  radio: "torus",
  cloud: "torus",
  supply: "cylinder",
  tensor: "icosahedron",
  format: "icosahedron",
  engine: "box",
  evaluator: "box",
  sampler: "tetrahedron",
  encoder: "tetrahedron",
  modulator: "tetrahedron",
  channel: "torus",
  demodulator: "tetrahedron",
  decoder: "tetrahedron",
  filter: "tetrahedron",
  client: "dodecahedron",
  coordinator: "dodecahedron",
  worker: "dodecahedron",
  storage: "cylinder",
  queue: "torus",
  "load-balancer": "torus",
  embedding: "slab",
  attention: "slab",
  feedforward: "slab",
  normalization: "slab",
  loss: "box",
  optimizer: "box",
  dataset: "cylinder",
};

/** 3D solid for one resolution: an explicit `model_3d` key wins, then the
 *  pack-declared symbol, then the neutral sphere. Unknown symbols and
 *  missing resolutions stay spheres so new backend types never break
 *  the renderer — and the category is never consulted. */
export function visualFor(resolution: EntityResolution | null | undefined): ArchetypeGeometry {
  const model = resolution?.model_3d;
  if (model && ARCHETYPES.has(model)) return model as ArchetypeGeometry;
  if (model) return "sphere";
  const symbol = resolution?.symbol;
  if (!symbol) return "sphere";
  return SYMBOL_GEOMETRY[symbol] ?? "sphere";
}

export const CATEGORY_LABELS: Record<string, string> = {
  package: "Package",
  discrete: "Discrete",
  passive: "Passive",
  power: "Power",
  sensor: "Sensor",
  compute: "Compute",
  network: "Network",
  format: "Data format",
  signal: "Signal stage",
  service: "Service",
  storage: "Storage",
  layer: "Model layer",
  process: "Process",
  generic: "Generic",
};

export function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category] ?? "Generic";
}

/** Display names for symbols the kebab-case fallback mangles (acronyms
 *  and compressions). Every other symbol prettifies as-is. */
export const SYMBOL_LABELS: Record<string, string> = {
  senseamp: "Sense amplifier",
  adc: "Data converter",
  mcu: "Microcontroller",
};

export function symbolLabel(symbol: string): string {
  return SYMBOL_LABELS[symbol] ?? prettyEntityType(symbol);
}

export const DOMAIN_LABELS: Record<string, string> = {
  electronics: "Electronics",
  iot: "IoT system",
  quantization: "Quantization",
  "signal-processing": "Signal processing",
  "distributed-systems": "Distributed system",
  "deep-learning": "Deep learning",
  generic: "Generic",
};

export function domainLabel(domain: string): string {
  return DOMAIN_LABELS[domain] ?? "Generic";
}

/** Prettify a kebab-case entity type id for legend display. */
export function prettyEntityType(entityType: string): string {
  return entityType
    .split("-")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export interface LegendEntry {
  symbol: string;
  label: string;
  geometry: ArchetypeGeometry;
  count: number;
  entityTypes: string[];
}

/** Group resolved entities by pack-declared symbol for the 3D legend, so
 *  each row names what the entity is and shows the solid the scene
 *  renders for it. Truly generic nodes carry the "generic" symbol and
 *  keep their own entry, so placeholders stay visibly generic. */
export function legendEntries(entities: GraphEntities | null): LegendEntry[] {
  if (!entities) return [];
  const groups = new Map<string, { count: number; types: Set<string> }>();
  const order: string[] = [];
  for (const entity of entities.entities) {
    const symbol = entity.symbol || "generic";
    const group = groups.get(symbol);
    if (group) {
      group.count += 1;
      group.types.add(entity.entity_type);
    } else {
      groups.set(symbol, { count: 1, types: new Set([entity.entity_type]) });
      order.push(symbol);
    }
  }
  return order.map((symbol) => {
    const group = groups.get(symbol) ?? { count: 0, types: new Set<string>() };
    const geometry = SYMBOL_GEOMETRY[symbol] ?? "sphere";
    return {
      symbol,
      label: symbolLabel(symbol),
      geometry,
      count: group.count,
      entityTypes: [...group.types].sort().map(prettyEntityType),
    };
  });
}

/** Index resolutions by node id for mesh building and the inspector. */
export function resolutionsByNodeId(
  entities: GraphEntities | null,
): Map<string, EntityResolution> {
  const index = new Map<string, EntityResolution>();
  if (!entities) return index;
  for (const entity of entities.entities) index.set(entity.node_id, entity);
  return index;
}

/** True unless the resolution explicitly marks the node non-physical.
 *  Unknown and unflagged nodes stay structural, matching the backend's
 *  generic default — a node only leaves the structure scene when the
 *  backend proves it is process or data. */
export function isStructural(resolution: EntityResolution | null | undefined): boolean {
  return resolution?.physical !== false;
}

export interface SplitGraph {
  structure: MethodologyGraph;
  process: MethodologyGraph;
}

/** Split one graph into its physical structure and its process/data side.
 *  Edges spanning the split belong to neither side; both halves keep the
 *  graph metadata so either renders as a standalone view. */
export function splitGraph(graph: MethodologyGraph, entities: GraphEntities | null): SplitGraph {
  const resolutions = resolutionsByNodeId(entities);
  const structural = new Set<string>();
  const procedural = new Set<string>();
  for (const node of graph.nodes) {
    (isStructural(resolutions.get(node.id)) ? structural : procedural).add(node.id);
  }
  const pick = (ids: Set<string>): MethodologyGraph => ({
    ...graph,
    nodes: graph.nodes.filter((node) => ids.has(node.id)),
    edges: graph.edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target)),
  });
  return { structure: pick(structural), process: pick(procedural) };
}

/** Center and radius of the smallest sphere containing every node. */
export function boundingSphere(positions: Map<string, WorldPoint>): {
  center: WorldPoint;
  radius: number;
} {
  const points = [...positions.values()];
  if (points.length === 0) return { center: { x: 0, y: 0, z: 0 }, radius: 1 };
  const center = {
    x: points.reduce((sum, p) => sum + p.x, 0) / points.length,
    y: points.reduce((sum, p) => sum + p.y, 0) / points.length,
    z: points.reduce((sum, p) => sum + p.z, 0) / points.length,
  };
  let radius = 1;
  for (const point of points) {
    radius = Math.max(
      radius,
      Math.hypot(point.x - center.x, point.y - center.y, point.z - center.z),
    );
  }
  return { center, radius };
}
