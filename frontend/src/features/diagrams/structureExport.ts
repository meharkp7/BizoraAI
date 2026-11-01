/* Vector + raster snapshots of the 3D scenes. PNG is the canvas
pixels; SVG is a genuine projected vector drawing — the caller
projects each 3D point through the live camera, and this module
draws part bounds, net arcs, and labels from those projections, far
parts first. Pure string building: no three.js, no DOM, so the
drawing logic is unit-testable and the canvas stays thin. */

export type Point3 = readonly [number, number, number];

export interface SvgPart {
  label: string;
  /** CSS color for the part bounds. */
  color: string;
  /** The 8 bounding-box corners in world units. */
  corners: Point3[];
}

export interface SvgWireLeg {
  hub: Point3;
  mid: Point3;
  spoke: Point3;
}

export interface SvgWire {
  net: string;
  /** CSS color for the arcs. */
  color: string;
  legs: SvgWireLeg[];
}

export interface Projected {
  x: number;
  y: number;
  /** Depth for paint order: larger draws first (farther). */
  z: number;
}

function escapeXml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

interface Drawable {
  depth: number;
  svg: string;
}

function partDrawable(part: SvgPart, project: (point: Point3) => Projected | null): Drawable | null {
  const projected: Projected[] = [];
  for (const corner of part.corners) {
    const point = project(corner);
    if (point) projected.push(point);
  }
  if (projected.length === 0) return null;
  const xs = projected.map((point) => point.x);
  const ys = projected.map((point) => point.y);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const width = Math.max(Math.max(...xs) - minX, 2);
  const height = Math.max(Math.max(...ys) - minY, 2);
  const depth = projected.reduce((sum, point) => sum + point.z, 0) / projected.length;
  const label = escapeXml(part.label);
  return {
    depth,
    svg:
      `<rect x="${minX.toFixed(1)}" y="${minY.toFixed(1)}" width="${width.toFixed(1)}" ` +
      `height="${height.toFixed(1)}" fill="${part.color}" fill-opacity="0.18" stroke="${part.color}" stroke-width="1.5"/>` +
      `<text x="${minX.toFixed(1)}" y="${(minY - 4).toFixed(1)}" font-size="12" fill="currentColor">${label}</text>`,
  };
}

function wireDrawables(wire: SvgWire, project: (point: Point3) => Projected | null): Drawable[] {
  const out: Drawable[] = [];
  wire.legs.forEach((leg, index) => {
    const hub = project(leg.hub);
    const mid = project(leg.mid);
    const spoke = project(leg.spoke);
    // Any endpoint behind the camera kills the leg: a clipped arc
    // would point somewhere the wire does not go.
    if (!hub || !mid || !spoke) return;
    out.push({
      depth: (hub.z + mid.z + spoke.z) / 3,
      svg:
        `<polyline points="${hub.x.toFixed(1)},${hub.y.toFixed(1)} ${mid.x.toFixed(1)},${mid.y.toFixed(1)} ` +
        `${spoke.x.toFixed(1)},${spoke.y.toFixed(1)}" fill="none" stroke="${wire.color}" stroke-width="1.5"/>`,
    });
    if (index === 0) {
      out.push({
        depth: mid.z - 0.001,
        svg: `<text x="${mid.x.toFixed(1)}" y="${(mid.y - 4).toFixed(1)}" font-size="11" fill="${wire.color}">Net ${escapeXml(wire.net)}</text>`,
      });
    }
  });
  return out;
}

export function buildStructureSvg(args: {
  title: string;
  caption: string;
  width: number;
  height: number;
  background: string;
  parts: SvgPart[];
  wires: SvgWire[];
  project: (point: Point3) => Projected | null;
}): string {
  const drawables: Drawable[] = [];
  for (const part of args.parts) {
    const drawable = partDrawable(part, args.project);
    if (drawable) drawables.push(drawable);
  }
  for (const wire of args.wires) {
    drawables.push(...wireDrawables(wire, args.project));
  }
  drawables.sort((a, b) => b.depth - a.depth);
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" width="${args.width}" height="${args.height}" ` +
    `viewBox="0 0 ${args.width} ${args.height}" role="img">` +
    `<title>${escapeXml(args.title)}</title>` +
    `<rect width="${args.width}" height="${args.height}" fill="${args.background}"/>` +
    `<text x="12" y="22" font-size="14" font-weight="600" fill="currentColor">${escapeXml(args.title)}</text>` +
    `<text x="12" y="${args.height - 12}" font-size="11" fill="currentColor" opacity="0.7">${escapeXml(args.caption)}</text>` +
    drawables.map((drawable) => drawable.svg).join("") +
    `</svg>`
  );
}

/** Download filename for a 3D snapshot: bizora-3d-<slugged-title>.<ext>. */
export function structureFilename(title: string, ext: "png" | "svg"): string {
  const slug =
    title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "structure";
  return `bizora-3d-${slug}.${ext}`;
}
