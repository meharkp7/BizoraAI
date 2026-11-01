/* Wire-following routes for the walkthrough pulse. The engine draws
   every wire as one SVG path; this module parses it into a routable
   graph so the pulse travels along copper instead of jumping straight
   across the schematic. Pure geometry over the rendered SVG: no
   paper-specific constants anywhere. */

export interface WirePoint {
  x: number;
  y: number;
}

const round2 = (value: number): number => Math.round(value * 100) / 100;
const keyOf = (point: WirePoint): string => `${point.x},${point.y}`;
const dist = (a: WirePoint, b: WirePoint): number =>
  Math.hypot(a.x - b.x, a.y - b.y);

/** Split the engine's merged wire path ("M..L..M..L..") into segments. */
export function parseWireSegments(d: string): [WirePoint, WirePoint][] {
  const tokens = d.match(/[ML]|-?\d+(?:\.\d+)?/g) ?? [];
  const segments: [WirePoint, WirePoint][] = [];
  let pen: WirePoint | null = null;
  let lineTo = false;
  let index = 0;
  while (index < tokens.length) {
    const token = tokens[index];
    if (token === "M" || token === "L") {
      lineTo = token === "L";
      index += 1;
      continue;
    }
    const x = Number.parseFloat(token);
    const y = Number.parseFloat(tokens[index + 1] ?? "");
    index += 2;
    if (!Number.isFinite(x) || !Number.isFinite(y)) {
      pen = null;
      continue;
    }
    const point = { x: round2(x), y: round2(y) };
    if (lineTo && pen) segments.push([pen, point]);
    pen = point;
  }
  return segments;
}

interface WireGraph {
  points: Map<string, WirePoint>;
  edges: Map<string, { to: string; length: number }[]>;
}

/** A device body in SVG units: copper touching one body conducts
 *  through it, bridging the islands the symbols cut the wires into. */
export interface DeviceSpan {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Long runs carry nodes only at their corners, so a component
 *  sitting beside a run's middle would find nothing to snap to;
 *  chaining intermediate nodes keeps every stretch of copper
 *  within snap reach without changing any route length. */
const DENSIFY_GAP = 25;

function buildWireGraph(d: string): WireGraph {
  const points = new Map<string, WirePoint>();
  const edges = new Map<string, { to: string; length: number }[]>();
  const link = (a: WirePoint, b: WirePoint): void => {
    if (a.x === b.x && a.y === b.y) return;
    const ka = keyOf(a);
    const kb = keyOf(b);
    points.set(ka, a);
    points.set(kb, b);
    const length = dist(a, b);
    const ab = edges.get(ka) ?? [];
    ab.push({ to: kb, length });
    edges.set(ka, ab);
    const ba = edges.get(kb) ?? [];
    ba.push({ to: ka, length });
    edges.set(kb, ba);
  };
  for (const [a, b] of parseWireSegments(d)) {
    const pieces = Math.max(1, Math.ceil(dist(a, b) / DENSIFY_GAP));
    let prev = a;
    for (let i = 1; i <= pieces; i++) {
      const next =
        i === pieces
          ? b
          : {
              x: round2(a.x + ((b.x - a.x) * i) / pieces),
              y: round2(a.y + ((b.y - a.y) * i) / pieces),
            };
      link(prev, next);
      prev = next;
    }
  }
  return { points, edges };
}

/** Bridge copper islands through device bodies: every wire node
 *  inside one span joins a clique, so current can pass through the
 *  device the way the schematic reads. Doubled cost keeps pure
 *  copper preferred; spans only run as a fallback. */
function stitchDevices(graph: WireGraph, spans: DeviceSpan[]): void {
  const pad = 3;
  for (const span of spans) {
    if (span.w + span.h < 1) continue;
    const inside = [...graph.points.entries()]
      .filter(
        ([, point]) =>
          point.x >= span.x - pad &&
          point.x <= span.x + span.w + pad &&
          point.y >= span.y - pad &&
          point.y <= span.y + span.h + pad,
      )
      .map(([key]) => key);
    for (let i = 0; i < inside.length; i++) {
      for (let j = i + 1; j < inside.length; j++) {
        const a = graph.points.get(inside[i]);
        const b = graph.points.get(inside[j]);
        if (!a || !b) continue;
        const length = dist(a, b) * 2;
        const ab = graph.edges.get(inside[i]) ?? [];
        ab.push({ to: inside[j], length });
        graph.edges.set(inside[i], ab);
        const ba = graph.edges.get(inside[j]) ?? [];
        ba.push({ to: inside[i], length });
        graph.edges.set(inside[j], ba);
      }
    }
  }
}

/** A snap is the glide from a component center to its own pin
 *  copper. For small symbols that is pin-scale, tens of SVG units;
 *  for a large block it reaches the block's own edge. Each endpoint
 *  gets the window of the device span it sits in, so big blocks
 *  route along their wires instead of fading across. The window
 *  only admits candidates — lexicographic pick still prefers the
 *  nearest connected copper — and copper beyond your own body plus
 *  margin stays out, which keeps disconnected endpoints
 *  unroutable: a wide window would let the route ride one island
 *  and air-jump the gap inside the goal snap, connected-looking
 *  but a lie. */
const MAX_SNAP = 40;

function windowFor(spans: DeviceSpan[], point: WirePoint): number {
  const pad = 3;
  let window = MAX_SNAP;
  for (const span of spans) {
    if (
      point.x >= span.x - pad &&
      point.x <= span.x + span.w + pad &&
      point.y >= span.y - pad &&
      point.y <= span.y + span.h + pad
    ) {
      window = Math.max(window, MAX_SNAP + Math.max(span.w, span.h) / 2);
    }
  }
  return window;
}

/** K nearest graph nodes within snap range: the closest copper to a
 *  component center is often a dead stub (supply rails, open pins),
 *  so routing tries each near node until one connects. */
function nearestNodes(
  graph: WireGraph,
  point: WirePoint,
  count: number,
  maxSnap: number,
): { key: string; snap: number }[] {
  const ranked: { key: string; snap: number }[] = [];
  for (const [key, node] of graph.points) {
    const snap = dist(node, point);
    if (snap <= maxSnap) ranked.push({ key, snap });
  }
  ranked.sort((a, b) => a.snap - b.snap);
  return ranked.slice(0, count);
}

/** Length-weighted distances from one node (Dijkstra). */
function shortestPaths(
  graph: WireGraph,
  start: string,
): { cost: Map<string, number>; prev: Map<string, string> } {
  const cost = new Map<string, number>([[start, 0]]);
  const prev = new Map<string, string>();
  const done = new Set<string>();
  for (;;) {
    let current: string | null = null;
    let currentCost = Infinity;
    for (const [key, value] of cost) {
      if (!done.has(key) && value < currentCost) {
        current = key;
        currentCost = value;
      }
    }
    if (current === null) break;
    done.add(current);
    for (const edge of graph.edges.get(current) ?? []) {
      if (done.has(edge.to)) continue;
      const next = currentCost + edge.length;
      if (next < (cost.get(edge.to) ?? Infinity)) {
        cost.set(edge.to, next);
        prev.set(edge.to, current);
      }
    }
  }
  return { cost, prev };
}

/** Route from one component center to the next along the drawn wires:
 *  exact endpoints plus the wire nodes between them. Pure copper
 *  first; when the symbols cut the copper into islands, device spans
 *  bridge through the bodies as a fallback. Null only when the
 *  endpoints stay disconnected (or there is no wire path), in which
 *  case the caller fades across instead of drawing a false wire. */
export function routeAlongWires(
  d: string,
  from: WirePoint,
  to: WirePoint,
  spans: DeviceSpan[] = [],
): WirePoint[] | null {
  const graph = buildWireGraph(d);
  if (graph.points.size === 0) return null;
  const copper = tryRoute(graph, from, to, spans);
  if (copper || spans.length === 0) return copper;
  stitchDevices(graph, spans);
  return tryRoute(graph, from, to, spans);
}

function tryRoute(
  graph: WireGraph,
  from: WirePoint,
  to: WirePoint,
  spans: DeviceSpan[],
): WirePoint[] | null {
  // Sixteen candidates comfortably cover every pin stub around a
  // component, so the live net wins over closer dead copper.
  const starts = nearestNodes(graph, from, 16, windowFor(spans, from));
  const goals = nearestNodes(graph, to, 16, windowFor(spans, to));
  // Lexicographic pick: nearest connected copper first, shortest
  // wire second. Densified nodes sit everywhere, so a flat
  // snap+wire total would let a far node plus a short wire beat
  // the component's own pin copper: an air-jump dressed as a
  // route. Snaps are off-wire glides, wire is honest travel; the
  // glide must never undercut the copper it leaves from.
  let best: {
    start: string;
    goal: string;
    prev: Map<string, string>;
    snap: number;
    wire: number;
  } | null = null;
  for (const start of starts) {
    const { cost, prev } = shortestPaths(graph, start.key);
    for (const goal of goals) {
      // Same-node "routes" travel no wire at all, so they always win
      // on cost while cutting across empty space: require an edge.
      // (The caller lands short hops instantly without routing.)
      if (goal.key === start.key) continue;
      const wire = cost.get(goal.key);
      if (wire === undefined) continue;
      const snap = start.snap + goal.snap;
      if (
        !best ||
        snap < best.snap - 1e-9 ||
        (Math.abs(snap - best.snap) <= 1e-9 && wire < best.wire)
      ) {
        best = { start: start.key, goal: goal.key, prev, snap, wire };
      }
    }
  }
  if (!best) return null;
  const keys = [best.goal];
  while (keys[0] !== best.start) {
    const step = best.prev.get(keys[0]);
    if (step === undefined) return null;
    keys.unshift(step);
  }
  const nodes = keys.map((key) => graph.points.get(key)) as WirePoint[];
  const route = [from, ...nodes, to];
  return pruneCollinear(
    route.filter(
      (point, index) =>
        index === 0 ||
        point.x !== route[index - 1].x ||
        point.y !== route[index - 1].y,
    ),
  );
}

/** Drop waypoints on a straight stretch: densified nodes snap well
 *  but would bloat every route, and the flight interpolates
 *  linearly between waypoints anyway, so the motion is identical. */
function pruneCollinear(route: WirePoint[]): WirePoint[] {
  if (route.length < 3) return route;
  const kept: WirePoint[] = [route[0]];
  for (let i = 1; i < route.length - 1; i++) {
    const prev = kept[kept.length - 1];
    const curr = route[i];
    const next = route[i + 1];
    const cross =
      (curr.x - prev.x) * (next.y - prev.y) -
      (curr.y - prev.y) * (next.x - prev.x);
    const dot =
      (curr.x - prev.x) * (next.x - curr.x) +
      (curr.y - prev.y) * (next.y - curr.y);
    if (Math.abs(cross) < 1e-6 && dot > 0) continue;
    kept.push(curr);
  }
  kept.push(route[route.length - 1]);
  return kept;
}

export function polylineLength(points: WirePoint[]): number {
  let total = 0;
  for (let i = 1; i < points.length; i++) total += dist(points[i - 1], points[i]);
  return total;
}

/** Point at an arclength distance along a polyline (clamped). */
export function pointAtLength(points: WirePoint[], distance: number): WirePoint {
  if (points.length === 0) return { x: 0, y: 0 };
  let remaining = Math.max(0, distance);
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1];
    const b = points[i];
    const length = dist(a, b);
    if (length <= 0) continue;
    if (remaining <= length) {
      const k = remaining / length;
      return { x: a.x + (b.x - a.x) * k, y: a.y + (b.y - a.y) * k };
    }
    remaining -= length;
  }
  return points[points.length - 1];
}
