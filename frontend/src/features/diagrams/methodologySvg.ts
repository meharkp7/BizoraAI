/* Presentation repairs for engine methodology SVGs (the engine files
   stay untouched):
   - dashing follows provenance, not engine kind: the engine dashes
     every evaluation node even when it comes straight from the paper,
     while the legend promises dashed means assumed.
   - decision diamonds grow to fit their text: dagre routes edges to
     the node rectangle, but the inscribed diamond is narrower, so
     long titles overflow the shape and side-exiting edges start in
     mid-air. The enlarged diamond covers both.
   - nodes with stated settings carry a what-if badge: the Inspector
     editor behind a bare node is undiscoverable, so param nodes get
     a marker that opens the same Inspector on click. */

import type { DiagramNode } from "../../lib/types.ts";
import { elementProvenance } from "./provenance.ts";

const round2 = (value: number): number => Math.round(value * 100) / 100;

interface Diamond {
  points: [number, number][];
  cx: number;
  cy: number;
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

function toDiamond(points: string): Diamond | null {
  const coords = points
    .trim()
    .split(/\s+/)
    .map((pair) => pair.split(",").map(Number));
  if (
    coords.length !== 4 ||
    coords.some((pair) => pair.length !== 2 || pair.some((n) => !Number.isFinite(n)))
  ) {
    return null;
  }
  const xs = coords.map(([x]) => x);
  const ys = coords.map(([, y]) => y);
  return {
    points: coords as [number, number][],
    cx: (Math.min(...xs) + Math.max(...xs)) / 2,
    cy: (Math.min(...ys) + Math.max(...ys)) / 2,
    minX: Math.min(...xs),
    maxX: Math.max(...xs),
    minY: Math.min(...ys),
    maxY: Math.max(...ys),
  };
}

/** True when a point sits inside the convex diamond. */
function insideDiamond(diamond: Diamond, x: number, y: number): boolean {
  let sign = 0;
  const pts = diamond.points;
  for (let i = 0; i < pts.length; i++) {
    const [ax, ay] = pts[i];
    const [bx, by] = pts[(i + 1) % pts.length];
    const cross = (bx - ax) * (y - ay) - (by - ay) * (x - ax);
    if (cross !== 0) {
      const side = Math.sign(cross);
      if (sign !== 0 && side !== sign) return false;
      sign = side;
    }
  }
  return true;
}

/** Border crossing along the ray from the diamond center through a
 *  point just outside it. */
function borderCrossing(
  diamond: Diamond,
  x: number,
  y: number,
): [number, number] | null {
  const dx = x - diamond.cx;
  const dy = y - diamond.cy;
  if (dx === 0 && dy === 0) return null;
  let best: [number, number] | null = null;
  let bestT = Infinity;
  const pts = diamond.points;
  for (let i = 0; i < pts.length; i++) {
    const [ax, ay] = pts[i];
    const [bx, by] = pts[(i + 1) % pts.length];
    const ex = bx - ax;
    const ey = by - ay;
    const denom = dx * ey - dy * ex;
    if (denom === 0) continue;
    const t = ((ax - diamond.cx) * ey - (ay - diamond.cy) * ex) / denom;
    const u = ((ax - diamond.cx) * dy - (ay - diamond.cy) * dx) / denom;
    if (t > 0 && t < bestT && u >= 0 && u <= 1) {
      bestT = t;
      best = [diamond.cx + t * dx, diamond.cy + t * dy];
    }
  }
  return best;
}

/** Grow a decision diamond about its centroid (x1.4, y1.2). */
function scaleDiamond(points: string): string {
  const coords = points
    .trim()
    .split(/\s+/)
    .map((pair) => pair.split(",").map(Number));
  if (coords.some((pair) => pair.length !== 2 || pair.some((n) => !Number.isFinite(n)))) {
    return points;
  }
  const cx = coords.reduce((sum, [x]) => sum + x, 0) / coords.length;
  const cy = coords.reduce((sum, [, y]) => sum + y, 0) / coords.length;
  return coords
    .map(([x, y]) => `${round2(cx + (x - cx) * 1.4)},${round2(cy + (y - cy) * 1.2)}`)
    .join(" ");
}

export function fitMethodologySvg(svg: string, nodes: DiagramNode[]): string {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const diamonds: Diamond[] = [];
  const fitted = svg.replace(
    /<g\b[^>]*data-node-id="([^"]+)"[^>]*>([\s\S]*?)<\/g>/g,
    (group, id: string, inner: string) => {
      const node = byId.get(id);
      if (!node) return group;
      const assumed =
        elementProvenance(node.evidence, node.confidence) === "assumed";
      let fixed = inner;
      if (assumed) {
        const dashed = (name: string, attrs: string): string => {
          if (attrs.includes("stroke-dasharray")) {
            return `<${name}${attrs.replace(/stroke-dasharray="[^"]*"/, 'stroke-dasharray="5 4"')}>`;
          }
          const selfClose = attrs.trimEnd().endsWith("/");
          const body = selfClose ? attrs.replace(/\s*\/$/, "") : attrs;
          return `<${name}${body} stroke-dasharray="5 4"${selfClose ? "/" : ""}>`;
        };
        fixed = fixed
          .replace(
            /<(rect|polygon)\b([^>]*?)>/g,
            (_tag: string, name: string, attrs: string) => dashed(name, attrs),
          )
          .replace(/<path\b([^>]*?)>/g, (tag: string, attrs: string) =>
            attrs.includes("class=") ? tag : dashed("path", attrs),
          );
      } else {
        fixed = fixed.replace(/ stroke-dasharray="[^"]*"/g, "");
      }
      fixed = fixed.replace(
        /<polygon\b([^>]*?)points="([^"]+)"([^>]*?)>/g,
        (
          tag: string,
          before: string,
          points: string,
          after: string,
        ) => {
          const scaled = scaleDiamond(points);
          // Engine polygons are centered with a translate transform;
          // edges use absolute coordinates, so offset the diamond.
          const shift =
            /transform="translate\(\s*(-?[\d.]+)\s*,?\s*(-?[\d.]+)\s*\)"/.exec(
              tag,
            );
          const dx = shift ? Number(shift[1]) : 0;
          const dy = shift ? Number(shift[2]) : 0;
          const diamond = toDiamond(scaled);
          if (diamond) {
            diamonds.push({
              points: diamond.points.map(
                ([x, y]) => [x + dx, y + dy] as [number, number],
              ),
              cx: diamond.cx + dx,
              cy: diamond.cy + dy,
              minX: diamond.minX + dx,
              maxX: diamond.maxX + dx,
              minY: diamond.minY + dy,
              maxY: diamond.maxY + dy,
            });
          }
          return `<polygon${before}points="${scaled}"${after}>`;
        },
      );
      return group.replace(inner, fixed);
    },
  );
  // Bridge edge ends floating just off a diamond: dagre routes to the
  // node rectangle, which the inscribed shape undercuts at the sides.
  // Only endpoints inside the diamond's own neighborhood qualify, so
  // edges belonging to neighboring nodes are never hijacked.
  const MARGIN = 25;
  const near = (diamond: Diamond, x: number, y: number): boolean =>
    !insideDiamond(diamond, x, y) &&
    x >= diamond.minX - MARGIN &&
    x <= diamond.maxX + MARGIN &&
    y >= diamond.minY - MARGIN &&
    y <= diamond.maxY + MARGIN;
  const fmt = (point: [number, number]): string =>
    `${round2(point[0])},${round2(point[1])}`;
  return fitted.replace(
    // NOTE: ` d="` (leading space) so marker-end="url(...)" never wins the
    // match; `edge[\s"]` because the engine emits class="edge " with a
    // trailing space (or class="edge fb"/"edge ctl" for special edges).
    /<path\b(?=[^>]*class="edge[\s"])[^>]*?\sd="([^"]+)"[^>]*>/g,
    (tag: string, d: string) => {
      const start = /^M\s*(-?[\d.]+)\s*,?\s*(-?[\d.]+)/.exec(d);
      const end = /(-?[\d.]+)\s*,?\s*(-?[\d.]+)\s*$/.exec(d);
      if (!start || !end) return tag;
      const [sx, sy] = [Number(start[1]), Number(start[2])];
      const [ex, ey] = [Number(end[1]), Number(end[2])];
      let bridged = d;
      for (const diamond of diamonds) {
        if (near(diamond, sx, sy)) {
          const cross = borderCrossing(diamond, sx, sy);
          if (cross) {
            bridged = bridged.replace(
              /^M\s*-?[\d.]+\s*,?\s*-?[\d.]+\s*/,
              `M ${fmt(cross)} L ${sx},${sy} `,
            );
          }
        }
        if (near(diamond, ex, ey)) {
          const cross = borderCrossing(diamond, ex, ey);
          if (cross) bridged = `${bridged} L ${fmt(cross)}`;
        }
      }
      return tag.replace(`d="${d}"`, `d="${bridged}"`);
    },
  );
}

/** Node shape bounding box from its own attributes (no layout): the
 *  first rect, the polygon extremes for decision diamonds, or the
 *  absolute moveto/lineto points of the first path (dataset/store
 *  outlines; arc bulges read a few units low, still on the node). */
function shapeBox(inner: string): { maxX: number; minY: number } | null {
  const rect = /<rect\b[^>]*?\bx="(-?[\d.]+)"[^>]*?\by="(-?[\d.]+)"[^>]*?\bwidth="(-?[\d.]+)"/.exec(
    inner,
  );
  if (rect) {
    return { maxX: Number(rect[1]) + Number(rect[3]), minY: Number(rect[2]) };
  }
  const polygon = /<polygon\b([^>]*?)\bpoints="([^"]+)"([^>]*?)>/.exec(inner);
  if (polygon) {
    const coords = polygon[2]
      .trim()
      .split(/\s+/)
      .map((pair) => pair.split(",").map(Number));
    if (
      coords.length > 0 &&
      coords.every((pair) => pair.length === 2 && pair.every((n) => Number.isFinite(n)))
    ) {
      // Centered points plus a translate transform: offset the box.
      const shift =
        /transform="translate\(\s*(-?[\d.]+)\s*,?\s*(-?[\d.]+)\s*\)"/.exec(
          `${polygon[1]}${polygon[3]}`,
        );
      const dx = shift ? Number(shift[1]) : 0;
      const dy = shift ? Number(shift[2]) : 0;
      return {
        maxX: Math.max(...coords.map(([x]) => x)) + dx,
        minY: Math.min(...coords.map(([, y]) => y)) + dy,
      };
    }
  }
  const path = /<path\b[^>]*?\bd="([^"]+)"[^>]*?>/.exec(inner);
  if (path) {
    const points = [...path[1].matchAll(/[ML]\s*(-?[\d.]+)\s*,?\s*(-?[\d.]+)/g)].map(
      (match) => [Number(match[1]), Number(match[2])] as [number, number],
    );
    if (
      points.length > 1 &&
      points.every((pair) => pair.every((n) => Number.isFinite(n)))
    ) {
      return {
        maxX: Math.max(...points.map(([x]) => x)),
        minY: Math.min(...points.map(([, y]) => y)),
      };
    }
  }
  return null;
}

/** Badge the nodes that carry stated settings: a ± dot riding the
 *  shape's top-right corner, inside the node's own group so it clicks
 *  through to the same Inspector (and editor). Nodes without params,
 *  and nodes whose shape cannot be read, stay unbadged. */
export function markWhatIfNodes(svg: string, nodes: DiagramNode[]): string {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  return svg.replace(
    /<g\b[^>]*data-node-id="([^"]+)"[^>]*>([\s\S]*?)<\/g>/g,
    (group, id: string, inner: string) => {
      const node = byId.get(id);
      if (!node || Object.keys(node.params ?? {}).length === 0) return group;
      const box = shapeBox(inner);
      if (!box) return group;
      const cx = round2(box.maxX - 11);
      const cy = round2(box.minY + 11);
      const badge =
        `<g class="whatif" transform="translate(${cx},${cy})">` +
        `<title>Editable settings — click for the what-if editor</title>` +
        `<circle r="9" class="whatif-dot" />` +
        `<text text-anchor="middle" dy="3.5" class="whatif-t">±</text></g>`;
      return group.replace(inner, `${inner}${badge}`);
    },
  );
}
