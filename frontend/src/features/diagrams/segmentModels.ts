/* Figure-true 3D parts: SAM outlines extruded into solid models.
 *
 * A segment polygon is the paper's own drawn shape (normalized figure
 * coords, y down). Extruding it gives a part that looks like the
 * figure instead of a generic procedural stand-in. Models follow the
 * dressPartMeshes convention: unit footprint (max dim 1, centered),
 * ~0.5 tall, base at y=0, MeshStandardMaterial so hover and
 * spotlight keep working.
 */
import * as THREE from "three";
import type { FigureSegment } from "../../lib/types.ts";

/** Minimum label overlap (token Jaccard) to dress a block as a segment. */
export const SEGMENT_MATCH_SIMILARITY = 0.5;

function labelTokens(label: string): Set<string> {
  const matches = label.toLowerCase().match(/[a-z0-9]+/g);
  return new Set(matches ?? []);
}

/** Token-set Jaccard similarity of two labels (0 when either is empty). */
export function labelSimilarity(left: string, right: string): number {
  const a = labelTokens(left);
  const b = labelTokens(right);
  if (a.size === 0 || b.size === 0) return 0;
  let intersection = 0;
  for (const token of a) if (b.has(token)) intersection += 1;
  return intersection / (a.size + b.size - intersection);
}

/** Best segment for a block, or null below the match threshold.
 *  Matches the segment label against both the block label ("N1")
 *  and its part family ("nmos"): SAM prompts name concepts, while
 *  blocks carry instance names. */
export function matchSegmentToBlock(
  block: { label: string; part?: string | null },
  segments: readonly FigureSegment[],
): FigureSegment | null {
  let best: FigureSegment | null = null;
  let bestScore = 0;
  for (const segment of segments) {
    const score = Math.max(
      labelSimilarity(block.label, segment.label),
      block.part ? labelSimilarity(block.part, segment.label) : 0,
    );
    if (score > bestScore) {
      best = segment;
      bestScore = score;
    }
  }
  return bestScore >= SEGMENT_MATCH_SIMILARITY ? best : null;
}

/** Distinct polygon vertices (collapses exact repeats, keeps ring order). */
function distinctPoints(polygon: readonly [number, number][]): [number, number][] {
  const seen = new Set<string>();
  const out: [number, number][] = [];
  for (const [x, y] of polygon) {
    const key = `${x},${y}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push([x, y]);
  }
  return out;
}

const TRACED_TRANSISTOR = 0x4e7a51;
const TRACED_PASSIVE = 0xb08d4f;
const TRACED_LOGIC = 0x5a6e8c;
const TRACED_POWER = 0x9c4f38;
const TRACED_DATA = 0x4f8a8b;
const TRACED_IO = 0x80838c;
const TRACED_DECISION = 0xa8813c;
const TRACED_FALLBACK = 0xb46a28;

/** Type tint for a traced extrusion: tracing changes the silhouette,
 *  never the type color language. Copper edges (below) still mark a
 *  part as traced rather than procedural. */
export function tracedColorForBlock(part: string | null | undefined): number {
  switch ((part ?? "").toLowerCase()) {
    case "nmos":
    case "pmos":
      return TRACED_TRANSISTOR;
    case "resistor":
    case "capacitor":
    case "inductor":
    case "diode":
      return TRACED_PASSIVE;
    case "inverter":
    case "buffer":
    case "amp":
    case "comparator":
    case "process":
      return TRACED_LOGIC;
    case "vsource":
    case "isource":
    case "ground":
      return TRACED_POWER;
    case "model":
    case "store":
    case "dataset":
      return TRACED_DATA;
    case "input":
    case "output":
      return TRACED_IO;
    case "decision":
    case "evaluation":
      return TRACED_DECISION;
    default:
      return TRACED_FALLBACK;
  }
}

/** Extrude one outline into a unit-footprint solid, or null when degenerate. */
export function buildSegmentModel(
  polygon: readonly [number, number][],
  part: string | null | undefined = null,
): THREE.Group | null {
  const points = distinctPoints(polygon);
  if (points.length < 3) return null;
  const xs = points.map(([x]) => x);
  const ys = points.map(([, y]) => y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const span = Math.max(maxX - minX, maxY - minY);
  if (!(span > 0)) return null;
  // Figure coords (y down) to shape coords (y up), centered, max dim 1.
  const shape = new THREE.Shape();
  points.forEach(([x, y], index) => {
    const sx = (x - minX - (maxX - minX) / 2) / span;
    const sy = -((y - minY - (maxY - minY) / 2) / span);
    if (index === 0) shape.moveTo(sx, sy);
    else shape.lineTo(sx, sy);
  });
  shape.closePath();
  const depth = 0.46;
  const geometry = new THREE.ExtrudeGeometry(shape, {
    steps: 1,
    depth,
    bevelEnabled: true,
    bevelThickness: 0.015,
    bevelSize: 0.008,
    bevelSegments: 1,
  });
  // Lay flat: shape plane becomes the ground plane, extrusion rises in +Y.
  geometry.rotateX(-Math.PI / 2);
  geometry.computeBoundingBox();
  const box = geometry.boundingBox;
  if (box) geometry.translate(0, -box.min.y, 0);
  const group = new THREE.Group();
  const mesh = new THREE.Mesh(
    geometry,
    new THREE.MeshStandardMaterial({
      color: tracedColorForBlock(part),
      roughness: 0.5,
      metalness: 0.3,
    }),
  );
  group.add(mesh);
  // Silhouette edges only: the default 1° threshold would trace every
  // triangulation line of the extrusion.
  const edges = new THREE.LineSegments(
    new THREE.EdgesGeometry(geometry, 30),
    new THREE.LineBasicMaterial({ color: 0x8a4d26, transparent: true, opacity: 0.8 }),
  );
  edges.position.copy(mesh.position);
  group.add(edges);
  return group;
}
