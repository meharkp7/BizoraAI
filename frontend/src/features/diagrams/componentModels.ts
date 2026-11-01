/* Textbook 3D structures for schematic component types.

The engine draws every part as one box, which makes an NMOS, a PMOS
and an inverter look identical. This module dresses a part mesh with
the standard textbook structure of its component type (diffusions, a
poly gate, a well tub, plates, ...) so parts that are physically
different also look different. Keyed ONLY by the IR component type —
generic over any paper — with honest limits: terminal left/right and
all dimensions are illustrative, not the paper's layout, and unknown
types keep the engine box. Unit footprint: x/z in [-0.5, 0.5], base
at y = 0, height at most 0.5; the canvas scales to the engine box.

Every build mints fresh materials (never shared): the spotlight dims
and glows meshes in place, so shared instances would leak highlight
state across parts. */

import * as THREE from "three";

export type ComponentModelKind =
  | "nmos"
  | "pmos"
  | "nmosPair"
  | "pmosPair"
  | "inverter"
  | "capacitor"
  | "resistor"
  | "inductor"
  | "ground";

/** Map a structure block to a model kind: the typed `part` field
 *  first, else whole-word device keywords in the paper's own label
 *  (structure extraction reports "NMOS pair N1-N2", not a type).
 *  Null keeps the honest engine box: switches, keepers and anything
 *  unrecognized stay boxes rather than guessing wrong. */
export function modelKindForBlock(block: {
  part: string | null;
  label: string;
}): ComponentModelKind | null {
  const typed = modelKindForType(block.part);
  if (typed) return typed;
  const words = new Set(block.label.toLowerCase().split(/[^a-z0-9]+/));
  const pair = words.has("pair") || words.has("pairs");
  if (words.has("nmos") || words.has("nmosfet") || words.has("nfet")) {
    return pair ? "nmosPair" : "nmos";
  }
  if (words.has("pmos") || words.has("pmosfet") || words.has("pfet")) {
    return pair ? "pmosPair" : "pmos";
  }
  if (words.has("inverter") || words.has("inv") || words.has("not")) return "inverter";
  if (words.has("capacitor") || words.has("cap")) return "capacitor";
  if (words.has("resistor") || words.has("res")) return "resistor";
  if (words.has("inductor") || words.has("ind") || words.has("coil")) return "inductor";
  if (words.has("ground") || words.has("gnd")) return "ground";
  return null;
}

/** Map an IR component type to a model kind, or null to keep the box. */
export function modelKindForType(type: string | null | undefined): ComponentModelKind | null {
  const key = (type ?? "").toLowerCase().replace(/[^a-z0-9]/g, "");
  switch (key) {
    case "nmos":
    case "nmosfet":
    case "nfet":
      return "nmos";
    case "pmos":
    case "pmosfet":
    case "pfet":
      return "pmos";
    case "inverter":
    case "not":
    case "inv":
      return "inverter";
    case "capacitor":
    case "cap":
      return "capacitor";
    case "resistor":
    case "res":
      return "resistor";
    case "inductor":
    case "ind":
    case "coil":
      return "inductor";
    case "ground":
    case "gnd":
      return "ground";
    default:
      return null;
  }
}

interface LayerPalette {
  sub: THREE.MeshStandardMaterial;
  well: THREE.MeshStandardMaterial;
  nplus: THREE.MeshStandardMaterial;
  pplus: THREE.MeshStandardMaterial;
  poly: THREE.MeshStandardMaterial;
  oxide: THREE.MeshStandardMaterial;
  metal: THREE.MeshStandardMaterial;
  glass: THREE.MeshStandardMaterial;
}

function makePalette(): LayerPalette {
  const mat = (color: number, roughness: number, metalness = 0): THREE.MeshStandardMaterial =>
    new THREE.MeshStandardMaterial({ color, roughness, metalness });
  return {
    sub: mat(0x767c86, 0.85),
    well: mat(0x7fb6dc, 0.7),
    nplus: mat(0x3d9950, 0.6),
    pplus: mat(0x8a63c8, 0.6),
    poly: mat(0xc2571f, 0.55),
    oxide: mat(0xdde4ea, 0.4),
    metal: mat(0xaeb8c2, 0.35, 0.6),
    glass: mat(0xcfe3ef, 0.3),
  };
}

function box(
  material: THREE.MeshStandardMaterial,
  w: number,
  h: number,
  d: number,
  x: number,
  y: number,
  z: number,
): THREE.Mesh {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), material);
  mesh.position.set(x, y, z);
  return mesh;
}

/** One FET stack (diffusions + oxide + gate + contacts) on a base layer. */
function fetStack(
  palette: LayerPalette,
  diffusion: THREE.MeshStandardMaterial,
  baseTop: number,
): THREE.Mesh[] {
  const parts: THREE.Mesh[] = [
    box(diffusion, 0.28, 0.1, 0.86, -0.36, baseTop + 0.05, 0),
    box(diffusion, 0.28, 0.1, 0.86, 0.36, baseTop + 0.05, 0),
    box(palette.oxide, 0.4, 0.02, 0.86, 0, baseTop + 0.01, 0),
    box(palette.poly, 0.14, 0.12, 1, 0, baseTop + 0.08, 0),
    box(palette.metal, 0.1, 0.1, 0.1, -0.36, baseTop + 0.15, 0),
    box(palette.metal, 0.1, 0.1, 0.1, 0.36, baseTop + 0.15, 0),
    box(palette.metal, 0.1, 0.1, 0.12, 0, baseTop + 0.19, 0),
  ];
  return parts;
}

function buildNmos(palette: LayerPalette): THREE.Group {
  const group = new THREE.Group();
  group.add(box(palette.sub, 1, 0.2, 1, 0, 0.1, 0));
  for (const mesh of fetStack(palette, palette.nplus, 0.2)) group.add(mesh);
  return group;
}

function buildPmos(palette: LayerPalette): THREE.Group {
  const group = new THREE.Group();
  group.add(box(palette.sub, 1, 0.06, 1, 0, 0.03, 0));
  group.add(box(palette.well, 1, 0.2, 1, 0, 0.16, 0));
  for (const mesh of fetStack(palette, palette.pplus, 0.26)) group.add(mesh);
  return group;
}

function buildInverter(palette: LayerPalette): THREE.Group {
  // NMOS on the left half, PMOS in a well tub on the right half,
  // one shared gate bar across both, output contact in the middle.
  const group = new THREE.Group();
  group.add(box(palette.sub, 1, 0.1, 1, 0, 0.05, 0));
  group.add(box(palette.well, 0.48, 0.16, 1, 0.26, 0.18, 0));
  const left = fetStack(palette, palette.nplus, 0.1);
  const right = fetStack(palette, palette.pplus, 0.26);
  for (const mesh of left) {
    mesh.position.x = mesh.position.x / 2 - 0.25;
    mesh.scale.x = 0.5;
    group.add(mesh);
  }
  for (const mesh of right) {
    mesh.position.x = mesh.position.x / 2 + 0.25;
    mesh.scale.x = 0.5;
    group.add(mesh);
  }
  group.add(box(palette.poly, 0.1, 0.12, 1, 0, 0.34, 0));
  group.add(box(palette.metal, 0.1, 0.1, 0.12, 0, 0.45, 0));
  return group;
}

function buildCapacitor(palette: LayerPalette): THREE.Group {
  const group = new THREE.Group();
  group.add(box(palette.metal, 1, 0.08, 1, 0, 0.04, 0));
  group.add(box(palette.glass, 0.9, 0.12, 0.9, 0, 0.14, 0));
  group.add(box(palette.metal, 1, 0.08, 1, 0, 0.24, 0));
  group.add(box(palette.metal, 0.1, 0.34, 0.3, -0.45, 0.17, 0));
  group.add(box(palette.metal, 0.1, 0.34, 0.3, 0.45, 0.17, 0));
  return group;
}

function buildResistor(palette: LayerPalette): THREE.Group {
  const group = new THREE.Group();
  group.add(box(palette.oxide, 1, 0.06, 1, 0, 0.03, 0));
  const y = 0.09;
  group.add(box(palette.poly, 0.62, 0.06, 0.14, -0.08, y, -0.3));
  group.add(box(palette.poly, 0.62, 0.06, 0.14, 0.08, y, 0));
  group.add(box(palette.poly, 0.62, 0.06, 0.14, -0.08, y, 0.3));
  group.add(box(palette.poly, 0.14, 0.06, 0.44, 0.23, y, -0.15));
  group.add(box(palette.poly, 0.14, 0.06, 0.44, -0.23, y, 0.15));
  group.add(box(palette.metal, 0.12, 0.1, 0.2, -0.44, y, -0.3));
  group.add(box(palette.metal, 0.12, 0.1, 0.2, 0.44, y, 0.3));
  return group;
}

function buildInductor(palette: LayerPalette): THREE.Group {
  const group = new THREE.Group();
  group.add(box(palette.oxide, 1, 0.06, 1, 0, 0.03, 0));
  for (const y of [0.14, 0.27, 0.4]) {
    const loop = new THREE.Mesh(
      new THREE.TorusGeometry(0.3, 0.06, 8, 24),
      palette.metal,
    );
    loop.rotation.x = Math.PI / 2;
    loop.position.set(0, y, 0);
    group.add(loop);
  }
  group.add(box(palette.metal, 0.1, 0.1, 0.1, -0.36, 0.11, 0));
  group.add(box(palette.metal, 0.1, 0.1, 0.1, 0.36, 0.37, 0));
  return group;
}

function buildGround(palette: LayerPalette): THREE.Group {
  const group = new THREE.Group();
  group.add(box(palette.metal, 0.1, 0.3, 0.1, 0, 0.15, 0));
  group.add(box(palette.metal, 0.56, 0.05, 0.56, 0, 0.325, 0));
  group.add(box(palette.metal, 0.4, 0.05, 0.4, 0, 0.375, 0));
  group.add(box(palette.metal, 0.24, 0.05, 0.24, 0, 0.425, 0));
  return group;
}

function buildMosPair(
  palette: LayerPalette,
  diffusion: THREE.MeshStandardMaterial,
  withWell: boolean,
): THREE.Group {
  // Two FET stacks side by side in one footprint: the cross-coupled
  // and differential pairs extraction reports as one part.
  const group = new THREE.Group();
  const baseTop = withWell ? 0.26 : 0.2;
  if (withWell) {
    group.add(box(palette.sub, 1, 0.06, 1, 0, 0.03, 0));
    group.add(box(palette.well, 1, 0.2, 1, 0, 0.16, 0));
  } else {
    group.add(box(palette.sub, 1, 0.2, 1, 0, 0.1, 0));
  }
  for (const [stack, offset] of [
    [fetStack(palette, diffusion, baseTop), -0.25],
    [fetStack(palette, diffusion, baseTop), 0.25],
  ] as const) {
    for (const mesh of stack) {
      mesh.position.x = mesh.position.x / 2 + offset;
      mesh.scale.x = 0.5;
      group.add(mesh);
    }
  }
  return group;
}

const BUILDERS: Record<ComponentModelKind, (palette: LayerPalette) => THREE.Group> = {
  nmos: buildNmos,
  pmos: buildPmos,
  nmosPair: (palette) => buildMosPair(palette, palette.nplus, false),
  pmosPair: (palette) => buildMosPair(palette, palette.pplus, true),
  inverter: buildInverter,
  capacitor: buildCapacitor,
  resistor: buildResistor,
  inductor: buildInductor,
  ground: buildGround,
};

/** Build the textbook structure for a kind (fresh materials each call). */
export function buildComponentModel(kind: ComponentModelKind): THREE.Group {
  return BUILDERS[kind](makePalette());
}

/** All mesh materials in a model (spotlight/hover mutate these in place). */
export function modelMaterials(model: THREE.Group): THREE.MeshStandardMaterial[] {
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
