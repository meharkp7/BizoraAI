/* True 3D structures for typed IR parts: a transistor builds as a
 * transistor (diffusions, poly gate, well tub), a database as a
 * banded canister, a converter as quantization steps — never a
 * labeled box. Keyed ONLY by the IR's typed `part`/`kind` enums
 * first, then by whole device words from a closed dictionary in the
 * paper's own label (structure extraction reports "NMOS pair N1-N2",
 * not a type). No substring matching anywhere: unknown parts return
 * null and keep the honest labeled fallback. Unit footprint: x/z in
 * [-0.5, 0.5], base at y = 0, height at most 0.5; the canvas scales
 * the group onto the engine box. Illustrative dimensions throughout
 * (the caption says so); identity always comes from the IR.
 *
 * Every build mints fresh materials (never shared): the spotlight
 * dims and glows meshes in place, so shared instances would leak
 * highlight state across parts. */

import * as THREE from "three";

export type ComponentModelKind =
  | "nmos"
  | "pmos"
  | "nmosPair"
  | "pmosPair"
  | "inverter"
  | "buffer"
  | "capacitor"
  | "resistor"
  | "inductor"
  | "diode"
  | "ground"
  | "vsource"
  | "isource"
  | "amp"
  | "comparator"
  | "adc"
  | "dac"
  | "sensor"
  | "database"
  | "layerStack"
  | "modelStack"
  | "inputPort"
  | "outputPort"
  | "decision"
  | "moduleSlab";

/** Map an IR component type (or methodology kind) to a model kind, or
 *  null to keep the fallback. Exact, case-folded match only. */
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
    case "inv":
      return "inverter";
    case "buffer":
    case "buf":
      return "buffer";
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
    case "diode":
      return "diode";
    case "ground":
    case "gnd":
      return "ground";
    case "vsource":
      return "vsource";
    case "isource":
      return "isource";
    case "amp":
    case "amplifier":
    case "opamp":
      return "amp";
    case "comparator":
    case "comp":
      return "comparator";
    case "adc":
      return "adc";
    case "dac":
      return "dac";
    case "sensor":
      return "sensor";
    case "store":
    case "dataset":
    case "database":
      return "database";
    case "model":
      return "modelStack";
    case "input":
      return "inputPort";
    case "output":
      return "outputPort";
    case "decision":
      return "decision";
    default:
      return null;
  }
}

/** Map a structure block kind to a model kind. Layers read as weight
 *  stacks and modules as dark slabs however they are labeled. */
export function modelKindForKind(kind: string): ComponentModelKind | null {
  switch (kind.toLowerCase()) {
    case "layer":
      return "layerStack";
    case "module":
      return "moduleSlab";
    default:
      return null;
  }
}

const PAIR_WORDS = new Set(["pair", "pairs", "coupled"]);

/** Whole device words in the paper's own label. Closed dictionary,
 *  whole words only — "transistor" alone stays unmapped (NMOS and
 *  PMOS look different, so guessing would lie). */
function modelKindForLabelWords(words: Set<string>): ComponentModelKind | null {
  const pair = [...PAIR_WORDS].some((word) => words.has(word));
  if (words.has("nmos") || words.has("nmosfet") || words.has("nfet")) {
    return pair ? "nmosPair" : "nmos";
  }
  if (words.has("pmos") || words.has("pmosfet") || words.has("pfet")) {
    return pair ? "pmosPair" : "pmos";
  }
  if (words.has("inverter") || words.has("inv")) return "inverter";
  if (words.has("buffer") || words.has("buf")) return "buffer";
  if (words.has("capacitor") || words.has("cap") || words.has("mom")) return "capacitor";
  if (words.has("resistor") || words.has("res")) return "resistor";
  if (words.has("inductor") || words.has("ind") || words.has("coil")) return "inductor";
  if (words.has("diode")) return "diode";
  if (words.has("ground") || words.has("gnd")) return "ground";
  if (words.has("comparator") || words.has("comp")) return "comparator";
  if (words.has("amplifier") || words.has("opamp") || words.has("op-amp")) return "amp";
  if (words.has("adc") || words.has("sar")) return "adc";
  if (words.has("dac")) return "dac";
  if (words.has("sensor")) return "sensor";
  if (words.has("database") || words.has("datastore")) return "database";
  return null;
}

/** Map a structure block to a model kind: the typed `part` field
 *  first, then the block kind (layers/modules), else — only when the
 *  part is untyped — whole-word device words in the paper's own
 *  label. A typed non-device part ("block", "process", ...) is
 *  respected: a methodology step that merely mentions NMOS keeps the
 *  honest labeled fallback instead of dressing as a transistor.
 *  Null keeps the honest labeled fallback. */
export function modelKindForBlock(block: {
  kind: string;
  part: string | null;
  label: string;
}): ComponentModelKind | null {
  const typed = modelKindForType(block.part);
  if (typed) return typed;
  const kinded = modelKindForKind(block.kind);
  if (kinded) return kinded;
  if (block.part !== null && block.part !== "") return null;
  return modelKindForLabelWords(
    new Set(block.label.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean)),
  );
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
  dark: THREE.MeshStandardMaterial;
  slab: THREE.MeshStandardMaterial;
  steel: THREE.MeshStandardMaterial;
  slabA: THREE.MeshStandardMaterial;
  slabB: THREE.MeshStandardMaterial;
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
    dark: mat(0x2b3138, 0.55),
    slab: mat(0x3a4250, 0.6),
    steel: mat(0x9aa4ae, 0.35, 0.65),
    slabA: mat(0x7f9fd0, 0.6),
    slabB: mat(0x5a7ab0, 0.6),
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
    const loop = new THREE.Mesh(new THREE.TorusGeometry(0.3, 0.06, 8, 24), palette.metal);
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

/** Axial diode: glass body, cathode band, wire leads both ends. */
function buildDiode(palette: LayerPalette): THREE.Group {
  const group = new THREE.Group();
  const body = new THREE.Mesh(new THREE.CylinderGeometry(0.13, 0.13, 0.44, 20), palette.glass);
  body.rotation.z = Math.PI / 2;
  body.position.set(0, 0.2, 0);
  group.add(body);
  const band = new THREE.Mesh(new THREE.CylinderGeometry(0.135, 0.135, 0.07, 20), palette.dark);
  band.rotation.z = Math.PI / 2;
  band.position.set(0.15, 0.2, 0);
  group.add(band);
  for (const x of [-0.34, 0.34]) {
    const lead = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.3, 8), palette.metal);
    lead.rotation.z = Math.PI / 2;
    lead.position.set(x, 0.2, 0);
    group.add(lead);
  }
  group.add(box(palette.oxide, 1, 0.05, 0.5, 0, 0.025, 0));
  return group;
}

/** Voltage source: battery can with a top nub and base ring. */
function buildVsource(palette: LayerPalette): THREE.Group {
  const group = new THREE.Group();
  const can = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.3, 0.32, 24), palette.metal);
  can.position.set(0, 0.16, 0);
  group.add(can);
  const nub = new THREE.Mesh(new THREE.CylinderGeometry(0.1, 0.1, 0.08, 16), palette.dark);
  nub.position.set(0, 0.36, 0);
  group.add(nub);
  const ring = new THREE.Mesh(new THREE.TorusGeometry(0.3, 0.025, 8, 24), palette.dark);
  ring.rotation.x = Math.PI / 2;
  ring.position.set(0, 0.32, 0);
  group.add(ring);
  return group;
}

/** Current source: flat ring with a bar across its middle. */
function buildIsource(palette: LayerPalette): THREE.Group {
  const group = new THREE.Group();
  group.add(box(palette.oxide, 1, 0.05, 1, 0, 0.025, 0));
  const ring = new THREE.Mesh(new THREE.TorusGeometry(0.3, 0.07, 10, 28), palette.metal);
  ring.rotation.x = Math.PI / 2;
  ring.position.set(0, 0.2, 0);
  group.add(ring);
  group.add(box(palette.dark, 0.5, 0.06, 0.09, 0, 0.2, 0));
  const head = new THREE.Mesh(new THREE.ConeGeometry(0.08, 0.14, 4), palette.dark);
  head.rotation.z = -Math.PI / 2;
  head.position.set(0.32, 0.2, 0);
  group.add(head);
  return group;
}

/** Buffer: low slab with a triangular gate prism and lead bars. */
function buildBuffer(palette: LayerPalette): THREE.Group {
  const group = new THREE.Group();
  group.add(box(palette.sub, 0.9, 0.1, 0.9, 0, 0.05, 0));
  const prism = new THREE.Mesh(new THREE.CylinderGeometry(0.32, 0.32, 0.24, 3), palette.poly);
  prism.rotation.y = Math.PI / 2;
  prism.position.set(0, 0.22, 0);
  group.add(prism);
  group.add(box(palette.metal, 0.24, 0.08, 0.12, -0.38, 0.1, 0));
  group.add(box(palette.metal, 0.24, 0.08, 0.12, 0.38, 0.1, 0));
  return group;
}

/** Packaged IC (amp, comparator): dark body, pins, pin-1 dot. */
function buildQfp(palette: LayerPalette): THREE.Group {
  const group = new THREE.Group();
  group.add(box(palette.dark, 0.6, 0.16, 0.6, 0, 0.14, 0));
  for (const offset of [-0.2, 0, 0.2]) {
    group.add(box(palette.metal, 0.2, 0.06, 0.08, -0.4, 0.08, offset));
    group.add(box(palette.metal, 0.2, 0.06, 0.08, 0.4, 0.08, offset));
    group.add(box(palette.metal, 0.08, 0.06, 0.2, offset, 0.08, -0.4));
    group.add(box(palette.metal, 0.08, 0.06, 0.2, offset, 0.08, 0.4));
  }
  const dot = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.03, 12), palette.oxide);
  dot.position.set(-0.2, 0.23, -0.2);
  group.add(dot);
  return group;
}

/** Data converter: ascending quantization steps with input fins. */
function buildConverter(palette: LayerPalette, flip: boolean): THREE.Group {
  const group = new THREE.Group();
  const heights = flip ? [0.36, 0.24, 0.12] : [0.12, 0.24, 0.36];
  heights.forEach((h, index) => {
    group.add(box(index % 2 === 0 ? palette.slabA : palette.slabB, 0.3, h, 0.8, -0.32 + index * 0.32, h / 2, 0));
  });
  for (const z of [-0.3, 0, 0.3]) {
    group.add(box(palette.metal, 0.08, 0.3, 0.08, -0.46, 0.15, z));
  }
  return group;
}

/** Thermal/sensor device: finned can with a sense nub on top. */
function buildSensor(palette: LayerPalette): THREE.Group {
  const group = new THREE.Group();
  const can = new THREE.Mesh(new THREE.CylinderGeometry(0.24, 0.24, 0.26, 20), palette.steel);
  can.position.set(0, 0.13, 0);
  group.add(can);
  for (const angle of [0, Math.PI / 4, Math.PI / 2, (3 * Math.PI) / 4]) {
    const fin = box(palette.steel, 0.56, 0.2, 0.04, 0, 0.12, 0);
    const holder = new THREE.Group();
    holder.rotation.y = angle;
    holder.add(fin);
    group.add(holder);
  }
  const nub = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.1, 0.1, 12), palette.dark);
  nub.position.set(0, 0.31, 0);
  group.add(nub);
  return group;
}

/** Database/store: steel canister with two band rings. */
function buildDatabase(palette: LayerPalette): THREE.Group {
  const group = new THREE.Group();
  const can = new THREE.Mesh(new THREE.CylinderGeometry(0.44, 0.44, 0.38, 28), palette.steel);
  can.position.set(0, 0.19, 0);
  group.add(can);
  for (const y of [0.13, 0.25]) {
    const band = new THREE.Mesh(new THREE.TorusGeometry(0.44, 0.025, 8, 32), palette.metal);
    band.rotation.x = Math.PI / 2;
    band.position.set(0, y, 0);
    group.add(band);
  }
  return group;
}

/** Weight/layer stack: thin slabs with gaps, slightly offset — the
 *  depth reads as stacked weight layers, not one block. */
function buildLayerStack(palette: LayerPalette): THREE.Group {
  const group = new THREE.Group();
  const slabs: Array<[number, number]> = [
    [0, 0],
    [0.04, -0.03],
    [-0.03, 0.04],
    [0.02, 0.02],
  ];
  slabs.forEach(([dx, dz], index) => {
    group.add(
      box(
        index % 2 === 0 ? palette.slabA : palette.slabB,
        0.88,
        0.07,
        0.88,
        dx,
        0.055 + index * 0.115,
        dz,
      ),
    );
  });
  return group;
}

function buildPort(palette: LayerPalette, flip: boolean): THREE.Group {
  // Tapered funnel: inputs narrow downward (into the flow),
  // outputs narrow upward (out of it).
  const group = new THREE.Group();
  const funnel = new THREE.Mesh(
    new THREE.CylinderGeometry(flip ? 0.4 : 0.12, flip ? 0.12 : 0.4, 0.38, 24),
    palette.steel,
  );
  funnel.position.set(0, 0.19, 0);
  group.add(funnel);
  group.add(box(palette.dark, 0.5, 0.05, 0.5, 0, 0.025, 0));
  return group;
}

/** Decision: a squashed diamond octahedron on a base plate. */
function buildDecision(palette: LayerPalette): THREE.Group {
  const group = new THREE.Group();
  group.add(box(palette.sub, 0.9, 0.06, 0.9, 0, 0.03, 0));
  const gem = new THREE.Mesh(new THREE.OctahedronGeometry(0.36), palette.slabA);
  gem.scale.set(1, 0.5, 1);
  gem.position.set(0, 0.24, 0);
  group.add(gem);
  return group;
}

/** Module slab: graphite containment block with crisp edges. */
function buildModuleSlab(palette: LayerPalette): THREE.Group {
  const group = new THREE.Group();
  const geometry = new THREE.BoxGeometry(1, 0.5, 1);
  const mesh = new THREE.Mesh(geometry, palette.slab);
  mesh.position.y = 0.25;
  group.add(mesh);
  const edges = new THREE.LineSegments(
    new THREE.EdgesGeometry(geometry),
    new THREE.LineBasicMaterial({ color: 0x14181d, transparent: true, opacity: 0.55 }),
  );
  edges.position.y = 0.25;
  group.add(edges);
  return group;
}

const BUILDERS: Record<ComponentModelKind, (palette: LayerPalette) => THREE.Group> = {
  nmos: buildNmos,
  pmos: buildPmos,
  nmosPair: (palette) => buildMosPair(palette, palette.nplus, false),
  pmosPair: (palette) => buildMosPair(palette, palette.pplus, true),
  inverter: buildInverter,
  buffer: buildBuffer,
  capacitor: buildCapacitor,
  resistor: buildResistor,
  inductor: buildInductor,
  diode: buildDiode,
  ground: buildGround,
  vsource: buildVsource,
  isource: buildIsource,
  amp: buildQfp,
  comparator: buildQfp,
  adc: (palette) => buildConverter(palette, false),
  dac: (palette) => buildConverter(palette, true),
  sensor: buildSensor,
  database: buildDatabase,
  layerStack: buildLayerStack,
  modelStack: buildLayerStack,
  inputPort: (palette) => buildPort(palette, false),
  outputPort: (palette) => buildPort(palette, true),
  decision: buildDecision,
  moduleSlab: buildModuleSlab,
};

/** Build the true structure for a kind (fresh materials each call). */
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
