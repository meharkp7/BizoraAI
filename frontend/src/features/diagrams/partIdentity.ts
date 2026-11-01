/* Generic 3D part identity: shape by closed IR enum, plates from IR text.
 *
 * Every part gets a distinct form plus an engraved identity plate naming it,
 * so a database, a compute module and a plain block are spottable at a
 * glance without any per-paper or per-technology special-casing. The shape
 * reads ONLY the block's `kind`/`part` enum values (never the label: no
 * substring or keyword matching exists in this module), the body tint
 * groups the IR's closed kind/type vocabularies the way the engine's own
 * kind colors do, and the plate prints the IR's own label/kind/part
 * text. Anything unrecognized falls back to the slate box; unknown
 * technologies degrade to a labeled box, never to a wrong lookalike.
 *
 * Unit footprint: x/z in [-0.5, 0.5], base at y = 0, height 0.5; the
 * canvas scales the group onto the engine box.
 *
 * Every build mints fresh materials and textures (never shared): the
 * spotlight dims meshes in place and teardown disposes them, so shared
 * instances would leak highlight state across parts or double-dispose. */

import * as THREE from "three";

export type PartShape = "box" | "slab" | "cylinder";

/** Closed MethodologyNodeKind values that read as stores. Membership in
 *  this set — exact, case-folded — is the only label-adjacent test, and it
 *  runs on the typed `part` enum, never on free text. */
const STORE_PARTS = new Set(["store", "dataset"]);

/** Categorical body tints over the IR's closed vocabularies
 *  (MethodologyNodeKind + ComponentType): transistors read steel-blue,
 *  passives sand, logic sage, power graphite. Exact, case-folded match
 *  only — a tint groups a kind, it never mimics anatomy — and anything
 *  absent here renders the default slate box. */
const BODY_TINTS: Record<string, number> = {
  decision: 0x9a6234,
  input: 0x3f5a66,
  output: 0x3f5a66,
  nmos: 0x4a6a8a,
  pmos: 0x4a6a8a,
  resistor: 0x8a7350,
  capacitor: 0x8a7350,
  inductor: 0x8a7350,
  diode: 0x8a7350,
  inverter: 0x5f7052,
  buffer: 0x5f7052,
  amp: 0x2e343b,
  comparator: 0x2e343b,
  vsource: 0x2e343b,
  isource: 0x2e343b,
  ground: 0x2e343b,
};

const SLATE_BODY = 0x5a6470;
const SLAB_BODY = 0x3a4250;
const STEEL_BODY = 0x9aa4ae;

export interface PartIdentity {
  kind: string;
  part: string | null;
  label: string;
}

/** Shape for a block: stores read as canisters, modules as dark slabs,
 *  everything else as a box (tinted for a few closed kinds). */
export function partShapeFor(block: Pick<PartIdentity, "kind" | "part">): PartShape {
  const part = (block.part ?? "").toLowerCase();
  if (STORE_PARTS.has(part)) return "cylinder";
  if (block.kind === "module") return "slab";
  return "box";
}

function bodyTint(block: Pick<PartIdentity, "kind" | "part">): number {
  const key = (block.part ?? block.kind).toLowerCase();
  return BODY_TINTS[key] ?? SLATE_BODY;
}

export interface PlateLayout {
  title: string[];
  sub: string;
}

const TITLE_CHARS = 22;
const TITLE_LINES = 2;

const TAG_CHARS = 18;

/** Short floating tag for a part label: small enough that neighbors
 *  stay readable, cut at a word boundary. The full label returns on
 *  hover, on click (tag expands), and in the Inspector. Pure. */
export function shortTagLabel(text: string): string {
  if (text.length <= TAG_CHARS) return text;
  const cut = text.slice(0, TAG_CHARS - 1);
  const space = cut.lastIndexOf(" ");
  const kept = (space > 8 ? cut.slice(0, space) : cut).trimEnd();
  return `${kept}…`;
}

/** Wrap the IR label onto at most two plate lines (pure: tested without
 *  canvas or WebGL). The sub-line names the kind and typed part. */
export function plateLayout(
  label: string,
  kind: string,
  part: string | null,
): PlateLayout {
  const words = label.split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  let rest = words;
  for (let row = 0; row < TITLE_LINES && rest.length > 0; row++) {
    let line = "";
    while (rest.length > 0) {
      const word =
        rest[0].length <= TITLE_CHARS ? rest[0] : rest[0].slice(0, TITLE_CHARS);
      const next = line === "" ? word : `${line} ${word}`;
      if (next.length > TITLE_CHARS) break;
      line = next;
      rest = rest.slice(1);
    }
    if (line === "" && rest.length > 0) {
      line = rest[0].slice(0, TITLE_CHARS);
      rest = rest.slice(1);
    }
    lines.push(line);
  }
  if (rest.length > 0 && lines.length > 0) {
    const last = lines.length - 1;
    lines[last] = `${lines[last].slice(0, TITLE_CHARS - 1)}…`;
  }
  return { title: lines, sub: part ? `${kind} · ${part}` : kind };
}

function plateDark(): boolean {
  const themed = document.documentElement.dataset.theme;
  if (themed === "dark") return true;
  if (themed === "light") return false;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

/** Engraved top plate for a part. Null when canvas 2D is unavailable
 *  (jsdom): the caller falls back to a plain top face. The canvas
 *  aspect follows the face aspect so the text never stretches. */
function plateTexture(
  layout: PlateLayout,
  faceAspect: number,
): THREE.CanvasTexture | null {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = Math.min(
    512,
    Math.max(128, Math.round(256 / Math.min(2.5, Math.max(0.4, faceAspect)))),
  );
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  const dark = plateDark();
  const bg = dark ? "#222a33" : "#f3ead8";
  const fg = dark ? "#f0e9d8" : "#2a2620";
  const rule = dark ? "#8a94a0" : "#8a7d5f";
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.strokeStyle = rule;
  ctx.lineWidth = 6;
  ctx.strokeRect(8, 8, canvas.width - 16, canvas.height - 16);
  ctx.fillStyle = fg;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  const titleSize = layout.title.length > 1 ? 40 : 48;
  ctx.font = `600 ${titleSize}px system-ui, sans-serif`;
  const cx = canvas.width / 2;
  const titleTop = canvas.height * 0.32;
  layout.title.forEach((text, index) => {
    ctx.fillText(text, cx, titleTop + index * (titleSize + 8));
  });
  ctx.font = "500 30px system-ui, sans-serif";
  ctx.fillStyle = rule;
  ctx.fillText(layout.sub.toUpperCase(), cx, canvas.height * 0.78);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  return texture;
}

function standard(color: number, roughness: number, metalness = 0): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({ color, roughness, metalness });
}

/** Build the identity group for one block: shaped body, engraved top
 *  plate, crisp edges. `faceAspect` is the top face's width/depth so
 *  the plate text keeps its proportions under the canvas's scale. */
export function buildPartIdentity(
  block: PartIdentity,
  faceAspect = 1,
): THREE.Group {
  const shape = partShapeFor(block);
  const group = new THREE.Group();
  const layout = plateLayout(block.label, block.kind, block.part);
  const texture = plateTexture(layout, faceAspect);
  const top = texture
    ? new THREE.MeshStandardMaterial({ map: texture, roughness: 0.7 })
    : standard(0xd8d2c2, 0.7);
  const bottom = standard(0x22262c, 0.9);

  let mesh: THREE.Mesh;
  if (shape === "cylinder") {
    const side = standard(STEEL_BODY, 0.35, 0.65);
    const geometry = new THREE.CylinderGeometry(0.5, 0.5, 0.5, 28);
    // Cylinder groups order: side, top cap, bottom cap.
    mesh = new THREE.Mesh(geometry, [side, top, bottom]);
    mesh.position.y = 0.25;
    group.add(mesh);
    group.add(rimLines(geometry));
  } else {
    const body = standard(
      shape === "slab" ? SLAB_BODY : bodyTint(block),
      shape === "slab" ? 0.6 : 0.75,
    );
    const geometry = new THREE.BoxGeometry(1, 0.5, 1);
    // Box groups order: +x, -x, +y, -y, +z, -z; the plate faces up.
    mesh = new THREE.Mesh(geometry, [body, body, top, bottom, body, body]);
    mesh.position.y = 0.25;
    group.add(mesh);
    const edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(geometry),
      new THREE.LineBasicMaterial({ color: 0x14181d, transparent: true, opacity: 0.55 }),
    );
    edges.position.y = 0.25;
    group.add(edges);
  }
  return group;
}

/** Top and bottom rims for a canister: the threshold keeps the side
 *  seam out so the steel reads smooth. */
function rimLines(geometry: THREE.CylinderGeometry): THREE.LineSegments {
  const lines = new THREE.LineSegments(
    new THREE.EdgesGeometry(geometry, 25),
    new THREE.LineBasicMaterial({ color: 0x2b3138, transparent: true, opacity: 0.6 }),
  );
  lines.position.y = 0.25;
  return lines;
}

/** Every paintable material in an identity group (spotlight and hover
 *  walk the group instead, but snapshots reuse this shape). */
export function identityMaterials(model: THREE.Group): THREE.MeshStandardMaterial[] {
  const out: THREE.MeshStandardMaterial[] = [];
  model.traverse((child) => {
    if (child instanceof THREE.Mesh) {
      const raw = child.material as THREE.Material | THREE.Material[] | undefined;
      const mats = Array.isArray(raw) ? raw : raw ? [raw] : [];
      for (const mat of mats) {
        if (mat instanceof THREE.MeshStandardMaterial) out.push(mat);
      }
    }
  });
  return out;
}