import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { CSS2DObject, CSS2DRenderer } from "three/addons/renderers/CSS2DRenderer.js";
import { sceneToThree } from "../../diagram-engine/three-adapter.js";
import type { Scene } from "../../diagram-engine/index.js";
import { ErrorState } from "../../components/states.tsx";
import { useTheme } from "../../lib/store.ts";
import type {
  CircuitIRJson,
  DiagramBlock,
  FigureSegment,
  StructureIRJson,
} from "../../lib/types.ts";
import { useFigureSegments, useSegmentFigure } from "../../app/queries.ts";
import { renderStructureDiagram } from "./adapters.ts";
import { CircuitPicker } from "./CircuitPicker.tsx";
import { circuitToStructure } from "./circuitToStructure.ts";
import { buildCircuitWires, wireHoverThreshold } from "./circuitWires.ts";
import { buildComponentModel, modelKindForBlock } from "./componentModels.ts";
import { buildPartIdentity, shortTagLabel } from "./partIdentity.ts";
import { nestedFootprintScales, nestedGrid, nestedLabel, nestedTagLift } from "./nestedLayout.ts";
import { buildSegmentModel, matchSegmentToBlock } from "./segmentModels.ts";
import { DiagramFallback } from "./DiagramFallback.tsx";
import styles from "./DiagramView.module.css";
import canvasStyles from "./StructureCanvas.module.css";
import { ProvenanceLegend } from "./ProvenanceTag.tsx";
import type { ExplodeSnapshot } from "./structureExplode.ts";
import { WIRES_GROUP_NAME, applyExplode, snapshotExplode } from "./structureExplode.ts";
import type {
  Point3,
  Projected,
  SvgPart,
  SvgWire,
  SvgWireLeg,
} from "./structureExport.ts";
import { buildStructureSvg, structureFilename } from "./structureExport.ts";
import { countProvenance } from "./provenance.ts";
import { MESH_FALLBACK, SURFACE_FALLBACK } from "../../styles/palette.ts";
import type { DiagramSelection } from "./selection.ts";
import { findBlock, sceneIdToBlockId, structureSelection } from "./selection.ts";

const CLICK_DRIFT_PX = 6;

/** Stable empty segments: the canvas effect rebuilds on identity change. */
const NO_SEGMENTS: readonly FigureSegment[] = [];

function themeBackground(): string {
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue("--color-surface")
    .trim();
  return value === "" ? SURFACE_FALLBACK : value;
}

/** Probe context creation directly: constructing WebGLRenderer when WebGL
 *  is missing makes three.js log errors before it throws. */
function webglAvailable(): boolean {
  try {
    const probe = document.createElement("canvas");
    return probe.getContext("webgl2") !== null || probe.getContext("webgl") !== null;
  } catch {
    return false;
  }
}

function walkBlocks(root: DiagramBlock): DiagramBlock[] {
  const out: DiagramBlock[] = [root];
  for (const child of root.children) out.push(...walkBlocks(child));
  return out;
}

type StructureScene = "full" | "circuit" | "detail";

/** 3D tab: the paper's physical structure, built by the engine from
 *  the diagrams endpoint and mounted with the engine's Three.js
 *  adapter. Clicking a mesh opens the Inspector. The circuit scene is
 *  derived from the schematic circuit, so the tab shows exactly what
 *  the paper's circuit would build — with no board under it. */
export function StructureDiagramView({
  structure,
  circuits,
  sourceFigureId,
  warnings,
  projectId,
  graphId,
  nodeLabels,
  onSelect,
}: {
  structure: StructureIRJson | null;
  circuits: CircuitIRJson[];
  sourceFigureId: string | null;
  warnings: string[];
  projectId: string;
  graphId: string;
  nodeLabels: Map<string, string>;
  onSelect: (selection: DiagramSelection) => void;
}) {
  const built = useMemo(
    () => (structure === null ? null : renderStructureDiagram(structure)),
    [structure],
  );
  const [activeCircuit, setActiveCircuit] = useState(0);
  const circuitScene = useMemo(() => {
    const circuit = circuits[Math.min(activeCircuit, circuits.length - 1)] ?? null;
    if (!circuit) return null;
    const derived = circuitToStructure(circuit);
    const result = renderStructureDiagram(derived);
    if (!result.ok) return null;
    return { circuit, root: derived.root, scene: result.scene };
  }, [circuits, activeCircuit]);
  // No explicit pick yet: open on the circuit build (one part per
  // schematic component) when there is one, else the full structure.
  const [scene, setScene] = useState<StructureScene | null>(null);
  const effective = scene ?? (circuitScene ? "circuit" : "full");
  const [spotId, setSpotId] = useState<string | null>(null);
  const [showTraced, setShowTraced] = useState(true);
  // Trace prompts name the visible parts (scene-independent, so the
  // hooks below stay above the early returns); matching by label
  // applies outlines to whichever scene is active.
  const tracePrompts = useMemo(() => {
    if (structure === null) return [];
    const labels = new Set<string>();
    for (const block of walkBlocks(structure.root).slice(1)) {
      if (block.kind === "chip" || block.kind === "array") continue;
      // Concept prompts name the part family ("nmos N1"): bare
      // instance names ("N1") segment nothing.
      const family = block.part && block.part !== "block" ? `${block.part} ` : "";
      labels.add(`${family}${block.label}`);
    }
    for (const circuit of circuits) {
      for (const component of circuit.components) {
        const family =
          component.type && component.type !== "block" ? `${component.type} ` : "";
        labels.add(`${family}${component.label}`);
      }
    }
    return [...labels].slice(0, 12);
  }, [structure, circuits]);
  const tracedOutlines = useFigureSegments(
    projectId,
    graphId,
    sourceFigureId,
    tracePrompts,
  );
  const traceMutation = useSegmentFigure(projectId, graphId, sourceFigureId ?? "");

  if (structure === null) {
    return (
      <DiagramFallback
        viewLabel="Structure"
        reason="the paper's figures yielded nothing suitable."
        sourceFigureId={sourceFigureId}
        projectId={projectId}
        graphId={graphId}
        nodeLabels={nodeLabels}
        warnings={warnings}
      />
    );
  }
  if (built === null || !built.ok) {
    return (
      <DiagramFallback
        viewLabel="Structure"
        reason={built === null ? "the diagram could not be rendered." : built.reason}
        sourceFigureId={sourceFigureId}
        projectId={projectId}
        graphId={graphId}
        nodeLabels={nodeLabels}
        warnings={warnings}
      />
    );
  }

  // The engine builds a second scene for the cell interior when the
  // repeated cell carries parts; offer it instead of hiding it.
  const detail = built.scene.detail ?? null;
  // The engine builds the detail scene from the first array's repeated
  // cell, so the parts list and picking root follow the same rule.
  const detailCell =
    detail !== null
      ? (structure.root.children.find((child) => child.kind === "array")?.children[0] ?? null)
      : null;
  const showingCircuit = effective === "circuit" && circuitScene !== null;
  const showingDetail = effective === "detail" && detail !== null;
  // Methodology-derived system blocks are pipeline stages, gauges and
  // stores — not devices — so they get the step caption and the shape
  // legend instead of the transistor/passive/power families.
  const showingDerivedCircuit =
    showingCircuit &&
    (circuitScene?.circuit.source.figure_id.startsWith("derived-") ?? false);
  const showFamilyLegend = (showingCircuit && !showingDerivedCircuit) || showingDetail;
  const activeScene = showingCircuit && circuitScene ? circuitScene.scene : showingDetail && detail ? detail : built.scene;
  const activeRoot =
    showingCircuit && circuitScene
      ? circuitScene.root
      : showingDetail && detailCell
        ? detailCell
        : structure.root;
  const counts = countProvenance(walkBlocks(activeRoot));
  const cachedSegments = tracedOutlines.data?.segments ?? NO_SEGMENTS;
  // Traced outlines stay on once they arrive; the toggle below lets the
  // viewer flip back to procedural models for comparison.
  const segments = showTraced ? cachedSegments : NO_SEGMENTS;
  const tracedCount = walkBlocks(activeRoot).filter(
    (block) => matchSegmentToBlock(block, segments) !== null,
  ).length;
  const title = showingCircuit && circuitScene ? circuitScene.circuit.title : structure.title;
  return (
    <div className={styles.view}>
      <div className={styles.head}>
        <h3>{title}</h3>
        <p className={styles.counts}>
          {counts.fromPaper} from paper · {counts.assumed} assumed
        </p>
      </div>
      <ProvenanceLegend />
      {!showingCircuit && warnings.length > 0 ? (
        <ul className={styles.warnings} aria-label="Extraction warnings">
          {warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}
      {circuitScene || detail ? (
        <div className={styles.picker} role="group" aria-label="Structure scene">
          <button
            type="button"
            aria-pressed={!showingCircuit && !showingDetail}
            onClick={() => {
              setSpotId(null);
              setScene("full");
            }}
          >
            Full structure
          </button>
          {circuitScene ? (
            <button
              type="button"
              aria-pressed={showingCircuit}
              onClick={() => {
                setSpotId(null);
                setScene("circuit");
              }}
            >
              Circuit 3D
            </button>
          ) : null}
          {detail ? (
            <button
              type="button"
              aria-pressed={showingDetail}
              onClick={() => {
                setSpotId(null);
                setScene("detail");
              }}
            >
              Cell interior
            </button>
          ) : null}
        </div>
      ) : null}
      {showingCircuit ? (
        <CircuitPicker
          circuits={circuits}
          active={activeCircuit}
          onPick={(index) => {
            setSpotId(null);
            setActiveCircuit(index);
          }}
        />
      ) : null}
      {sourceFigureId !== null && tracePrompts.length > 0 ? (
        <div className={styles.picker} role="group" aria-label="Figure tracing">
          {cachedSegments.length === 0 ? (
            <button
              type="button"
              disabled={
                traceMutation.isPending || tracedOutlines.data?.available === false
              }
              title={
                tracedOutlines.data?.available === false
                  ? (tracedOutlines.data.reason ?? "Segmentation unavailable.")
                  : "Outline these parts from the source figure (SAM 3.1)"
              }
              onClick={() => traceMutation.mutate(tracePrompts)}
            >
              {traceMutation.isPending ? "Tracing…" : "Trace true shapes"}
            </button>
          ) : (
            <button
              type="button"
              aria-pressed={showTraced}
              title={
                showTraced
                  ? "Outlines from the source figure are on; flip to procedural models"
                  : "Procedural models are on; flip to the traced outlines"
              }
              onClick={() => setShowTraced((value) => !value)}
            >
              {showTraced ? "✓ Traced outlines" : "Show procedural"}
            </button>
          )}
          {tracedCount > 0 ? (
            <p className={styles.counts} role="status">
              {tracedCount} {tracedCount === 1 ? "part" : "parts"} traced from the figure.
            </p>
          ) : null}
        </div>
      ) : null}
      {traceMutation.isError ? (
        <ul className={styles.warnings} aria-label="Tracing errors">
          <li>
            {traceMutation.error instanceof Error
              ? traceMutation.error.message
              : "Tracing failed."}
          </li>
        </ul>
      ) : null}
      <StructureCanvas
        scene={activeScene}
        root={activeRoot}
        circuit={showingCircuit && circuitScene ? circuitScene.circuit : null}
        segments={segments}
        spotId={spotId}
        onSelect={onSelect}
        onSpot={setSpotId}
      />
      {walkBlocks(activeRoot).length > 1 ? (
        <div className={styles.picker} role="group" aria-label="Parts in this scene">
          {walkBlocks(activeRoot).slice(1).map((child) => (
            <button
              key={child.id}
              type="button"
              aria-pressed={spotId === child.id}
              title={child.kind}
              onClick={() => {
                setSpotId(child.id);
                onSelect(structureSelection(child));
              }}
            >
              {child.label}
            </button>
          ))}
        </div>
      ) : null}
      {activeScene.notes.length > 0 ? (
        <ul className={styles.notes} aria-label="Structure notes">
          {activeScene.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      ) : null}
      {showFamilyLegend ? (
        <ul className={styles.layerLegend} aria-label="Part family legend">
          <li><span className={styles.swatch} data-shape="transistor" />Transistor</li>
          <li><span className={styles.swatch} data-shape="passive" />Passive</li>
          <li><span className={styles.swatch} data-shape="logic" />Logic</li>
          <li><span className={styles.swatch} data-shape="power" />Power</li>
          <li><span className={styles.swatch} data-shape="part" />Part</li>
        </ul>
      ) : (
        <ul className={styles.layerLegend} aria-label="Part shape legend">
          <li><span className={styles.swatch} data-shape="logic" />Process stage</li>
          <li><span className={styles.swatch} data-shape="decision" />Decision / evaluation</li>
          <li><span className={styles.swatch} data-shape="store" />Store / dataset</li>
          <li><span className={styles.swatch} data-shape="module" />Module</li>
          <li><span className={styles.swatch} data-shape="io" />Input / output</li>
          <li><span className={styles.swatch} data-shape="part" />Part</li>
        </ul>
      )}
      <p className={styles.counts}>
        {showFamilyLegend
          ? "Each part builds as its typed device from the paper's own IR — transistors, passives, converters, stores — click any part for its evidence. Unrecognized parts keep a labeled plate. Arrangement, not dimensions."
          : showingDerivedCircuit
            ? "Each step builds as its typed shape from the paper's own methodology — pipeline stages, evaluation gauges, stores, ports — click any part for its evidence. Unrecognized steps keep a labeled plate. Arrangement, not dimensions."
            : "Each block builds from the paper's own structure — arrays, modules, and weight matrices sized by their stated dims — click any block for its evidence. Floating tags name nested blocks. Arrangement, not dimensions."}
        {tracedCount > 0
          ? ` ${tracedCount} ${tracedCount === 1 ? "part is" : "parts are"} traced from the source figure's own outlines.`
          : ""}
      </p>
    </div>
  );
}

/** Swap every engine box for its true structure (a transistor builds
 *  as a transistor, a store as a canister) or, for unrecognized
 *  parts, the honest labeled fallback. The chip root keeps its box
 *  for the silicon finish below. Each part sits in an unscaled
 *  wrapper at the box's position carrying the box's id/label, so
 *  picking, hover, spotlight and disposal keep working unchanged;
 *  nested children (module members the engine never draws) lay out
 *  in a grid on top. */
/** Dress one block: a traced figure outline when SAM matched it,
 *  else its typed procedural model, else the honest labeled plate. */
function dressBlockModel(
  block: DiagramBlock,
  width: number,
  height: number,
  depth: number,
  segments: readonly FigureSegment[],
): THREE.Group {
  const segment = matchSegmentToBlock(block, segments);
  const traced = segment ? buildSegmentModel(segment.polygon, block.part) : null;
  const kind = traced ? null : modelKindForBlock(block);
  const model = traced ?? (kind
    ? buildComponentModel(kind)
    : buildPartIdentity(block, width / Math.max(depth, 1e-6)));
  // Unit footprint (1x1, height 0.5) scaled onto the engine box.
  model.scale.set(width, height / 0.5, depth);
  return model;
}

function dressPartMeshes(
  group: THREE.Group,
  root: DiagramBlock,
  segments: readonly FigureSegment[],
  tags: NestedTag[],
): void {
  // Blocks the engine already drew as top-level boxes (arrays, side
  // strips): nested layout must not lay them again as members, or
  // the scene shows every container twice — once placed, once nested.
  const drawn = new Set<string>();
  for (const child of group.children) {
    if (!(child instanceof THREE.Mesh)) continue;
    const rawId = (child.userData as { id?: unknown }).id;
    if (typeof rawId === "string") drawn.add(sceneIdToBlockId(rawId));
  }
  for (const child of [...group.children]) {
    if (!(child instanceof THREE.Mesh)) continue;
    const rawId = (child.userData as { id?: unknown }).id;
    if (typeof rawId !== "string") continue;
    const block = findBlock(root, sceneIdToBlockId(rawId));
    // The chip root keeps its silicon finish; array instances keep the
    // engine box (the array annotation names them once — sixteen
    // identical plates would be noise; interiors live in the detail
    // scene). Everything else gets its generic identity.
    if (!block || block.kind === "chip" || block.kind === "array") continue;
    const params = (child.geometry as THREE.BoxGeometry).parameters;
    if (!params) continue;
    const wrapper = new THREE.Group();
    wrapper.position.set(
      child.position.x,
      child.position.y - params.height / 2,
      child.position.z,
    );
    wrapper.userData = { ...child.userData };
    const model = dressBlockModel(block, params.width, params.height, params.depth, segments);
    wrapper.add(model);
    layoutNestedParts(wrapper, block, params.width, params.height, params.depth, segments, tags, drawn);
    group.add(wrapper);
    group.remove(child);
    child.geometry.dispose();
    const material = child.material as THREE.Material | THREE.Material[] | undefined;
    if (Array.isArray(material)) {
      for (const entry of material) entry.dispose();
    } else if (material) {
      material.dispose();
    }
    for (const edge of child.children) {
      const line = edge as THREE.LineSegments;
      // Edge geometry is per-mesh; its material is shared by the
      // adapter and must never be disposed here.
      if (line.geometry) line.geometry.dispose();
    }
  }
}

/** One nested part awaiting its floating tag: the wrapper it rides
 *  on (so explode carries the tag with the part), the full tag text,
 *  the model's top in wrapper units, and the sibling slot that
 *  staggers dense tags across heights. */
interface NestedTag {
  wrapper: THREE.Group;
  full: string;
  top: number;
  slot: number;
}

/** Lay a block's children in a grid on top of its dressed box. The
 *  engine draws only top-level boxes, so module members (and any other
 *  nesting) would otherwise stay invisible; this arrangement is
 *  illustrative — the caption says so — while true structures and the
 *  labeled fallback stay just as honest as top-level parts. Each
 *  child gets its own unscaled wrapper with its block id/label, so
 *  picking, hover and spotlight treat nested parts exactly like
 *  top-level ones. Siblings stating tensor dims size their footprints
 *  from them (a 14336-wide matrix reads larger than a 1024-wide one);
 *  every nested child reports a tag so the scene names it in 3D.
 *  Members the engine already drew as top-level boxes are skipped —
 *  they own their own wrapper, tags, and evidence already. */
function layoutNestedParts(
  parent: THREE.Group,
  block: DiagramBlock,
  w: number,
  h: number,
  d: number,
  segments: readonly FigureSegment[],
  tags: NestedTag[],
  drawn: ReadonlySet<string>,
): void {
  const kids = block.children.filter((kid) => !drawn.has(kid.id));
  if (kids.length === 0) return;
  const { cols, rows } = nestedGrid(kids.length, w, d);
  const cellW = w / cols;
  const cellD = d / rows;
  const childH = Math.min(h * 0.9, Math.max(cellW, cellD) * 0.55);
  const scales = nestedFootprintScales(kids.map((kid) => kid.dims));
  kids.forEach((kid, index) => {
    const col = index % cols;
    const row = Math.floor(index / cols);
    const scale = scales[index] ?? 1;
    const footW = cellW * 0.9 * scale;
    const footD = cellD * 0.9 * scale;
    const wrapper = new THREE.Group();
    wrapper.position.set(
      -w / 2 + cellW * (col + 0.5),
      h,
      -d / 2 + cellD * (row + 0.5),
    );
    wrapper.userData = { id: kid.id, label: kid.label };
    const model = dressBlockModel(kid, footW, childH, footD, segments);
    wrapper.add(model);
    parent.add(wrapper);
    tags.push({ wrapper, full: nestedLabel(kid.label, kid.dims), top: childH, slot: index % 3 });
    layoutNestedParts(wrapper, kid, footW, childH, footD, segments, tags, drawn);
  });
}

/** First paintable color under a part, for the SVG snapshot. */
function partColor(child: THREE.Object3D): string {
  let found: string | null = null;
  child.traverse((node) => {
    if (found) return;
    const material = (node as THREE.Mesh).material as
      | { color?: THREE.Color }
      | { color?: THREE.Color }[]
      | undefined;
    const first = Array.isArray(material) ? material[0] : material;
    if (first?.color) found = `#${first.color.getHexString()}`;
  });
  return found ?? MESH_FALLBACK;
}

function downloadHref(filename: string, href: string): void {
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
}

const SVG_WIDTH = 800;
const SVG_HEIGHT = 600;

/** Restyle the die plate as silicon: the engine draws the chip root
 *  as a plain slab, which reads as a PCB; the block says chip, so a
 *  dark silicon finish states what it is. Geometry and edges stay the
 *  engine's; only the finish is app-layer, generic over any chip. */
function dressChipPlate(group: THREE.Group, root: DiagramBlock): void {
  for (const child of group.children) {
    if (!(child instanceof THREE.Mesh)) continue;
    const rawId = (child.userData as { id?: unknown }).id;
    if (typeof rawId !== "string") continue;
    const block = findBlock(root, sceneIdToBlockId(rawId));
    if (block?.kind !== "chip") continue;
    const old = child.material as THREE.Material | THREE.Material[] | undefined;
    child.material = new THREE.MeshStandardMaterial({
      color: 0x3a4450,
      roughness: 0.45,
      metalness: 0.55,
    });
    if (Array.isArray(old)) {
      for (const entry of old) entry.dispose();
    } else if (old) {
      old.dispose();
    }
  }
}

function StructureCanvas({
  scene,
  root,
  circuit,
  segments,
  spotId,
  onSelect,
  onSpot,
}: {
  scene: Scene;
  root: DiagramBlock;
  circuit: CircuitIRJson | null;
  segments: readonly FigureSegment[];
  spotId: string | null;
  onSelect: (selection: DiagramSelection) => void;
  onSpot: (blockId: string | null) => void;
}) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const groupRef = useRef<THREE.Group | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const snapshotRef = useRef<ExplodeSnapshot | null>(null);
  const [hover, setHover] = useState<{ x: number; y: number; label: string } | null>(null);
  const [explode, setExplodeState] = useState(0);
  const explodeRef = useRef(0);
  const setExplode = (value: number): void => {
    explodeRef.current = value;
    setExplodeState(value);
  };
  // Decided during render so the effect never flips state synchronously.
  const [failed, setFailed] = useState<boolean>(
    () => typeof document !== "undefined" && !webglAvailable(),
  );

  useEffect(() => {
    const host = hostRef.current;
    if (!host || failed) return;
    let renderer: THREE.WebGLRenderer | null = null;
    let labelRenderer: CSS2DRenderer | null = null;
    const disposables: { dispose: () => void }[] = [];
    const onDispose: (() => void)[] = [];
    try {
      const background = new THREE.Color(themeBackground());
      const scene3 = new THREE.Scene();
      scene3.background = background;

      const group = sceneToThree(scene);
      const nestedTags: NestedTag[] = [];
      dressPartMeshes(group, root, segments, nestedTags);
      dressChipPlate(group, root);
      if (circuit) {
        // Wire anchor: the top-center of each dressed part, so the
        // rat's-nest lands on the structures, not the old boxes.
        const anchors = new Map<string, THREE.Vector3>();
        for (const child of group.children) {
          const rawId = (child.userData as { id?: unknown }).id;
          if (typeof rawId !== "string") continue;
          const bounds = new THREE.Box3().setFromObject(child);
          if (bounds.isEmpty()) continue;
          const center = bounds.getCenter(new THREE.Vector3());
          anchors.set(sceneIdToBlockId(rawId), new THREE.Vector3(center.x, bounds.max.y, center.z));
        }
        group.add(buildCircuitWires(circuit, anchors));
      }
      groupRef.current = group;
      scene3.add(group);
      onDispose.push(() => {
        groupRef.current = null;
        scene3.remove(group);
        group.traverse((child) => {
          const mesh = child as THREE.Mesh;
          if (mesh.geometry) mesh.geometry.dispose();
          const material = mesh.material as THREE.Material | THREE.Material[] | undefined;
          const disposeEntry = (entry: THREE.Material): void => {
            const mapped = (entry as THREE.MeshStandardMaterial).map;
            if (mapped) mapped.dispose();
            entry.dispose();
          };
          if (Array.isArray(material)) material.forEach(disposeEntry);
          else if (material) disposeEntry(material);
        });
      });

      const box = new THREE.Box3().setFromObject(group);
      const center = box.getCenter(new THREE.Vector3());
      const size = box.getSize(new THREE.Vector3());
      const radius = Math.max(size.length() / 2, 1);

      const camera = new THREE.PerspectiveCamera(45, 1, 0.1, radius * 50);
      const aspect =
        host.clientWidth > 0 && host.clientHeight > 0
          ? host.clientWidth / host.clientHeight
          : 1;
      camera.aspect = aspect;
      camera.updateProjectionMatrix();
      const distance = (radius / Math.sin((camera.fov * Math.PI) / 360)) * 1.15;
      const direction = new THREE.Vector3(1, 0.8, 1).normalize();
      camera.position.set(
        center.x + direction.x * distance,
        center.y + direction.y * distance,
        center.z + direction.z * distance,
      );

      const created = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
      renderer = created;
      rendererRef.current = created;
      cameraRef.current = camera;
      onDispose.push(() => {
        rendererRef.current = null;
        cameraRef.current = null;
        snapshotRef.current = null;
      });
      created.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      host.appendChild(created.domElement);
      const createdLabels = new CSS2DRenderer();
      labelRenderer = createdLabels;
      createdLabels.domElement.className = canvasStyles.labels;
      host.appendChild(createdLabels.domElement);

      // Paper labels from the scene float above their boxes, kept
      // short so neighbors stay readable; the full text rides along in
      // dataset.full and returns when its part is clicked (see the
      // spotlight effect below).
      const markers: THREE.Object3D[] = [];
      for (const annotation of scene.annotations) {
        const tag = document.createElement("div");
        tag.className = canvasStyles.tagInner;
        tag.textContent = shortTagLabel(annotation.text);
        tag.dataset.full = annotation.text;
        const marker = new CSS2DObject(tag);
        marker.position.set(annotation.x, annotation.z, annotation.y);
        scene3.add(marker);
        markers.push(marker);
        onDispose.push(() => {
          scene3.remove(marker);
        });
      }
      // Nested module members get the same tags, riding their own
      // wrapper just above the model: they state name and dims
      // ("Up · 14336×4096"), and explode carries them with the part,
      // so they stay out of the snapshot's marker list.
      for (const nested of nestedTags) {
        const tag = document.createElement("div");
        tag.className = canvasStyles.tagInner;
        tag.textContent = shortTagLabel(nested.full);
        tag.dataset.full = nested.full;
        const marker = new CSS2DObject(tag);
        marker.position.set(0, nested.top + nestedTagLift(nested.slot), 0);
        nested.wrapper.add(marker);
        onDispose.push(() => {
          nested.wrapper.remove(marker);
        });
      }
      snapshotRef.current = snapshotExplode(
        group,
        (child) => {
          const rawId = (child.userData as { id?: unknown }).id;
          return typeof rawId === "string" ? sceneIdToBlockId(rawId) : null;
        },
        markers,
      );
      applyExplode(snapshotRef.current, explodeRef.current / 100);

      scene3.add(new THREE.HemisphereLight(0xfffdf6, 0x8b8471, 1.3));
      const key = new THREE.DirectionalLight(0xffffff, 1.0);
      key.position.set(center.x + distance, center.y + distance, center.z + distance);
      scene3.add(key);
      const fill = new THREE.DirectionalLight(0xf0e1cf, 0.4);
      fill.position.set(center.x - distance, center.y + distance * 0.5, center.z - distance);
      scene3.add(fill);

      const unsubscribeTheme = useTheme.subscribe(() => {
        (scene3.background as THREE.Color).set(themeBackground());
      });
      onDispose.push(unsubscribeTheme);

      const controls = new OrbitControls(camera, created.domElement);
      controls.target.copy(center);
      controls.enableDamping = true;
      controls.dampingFactor = 0.08;
      controls.minDistance = radius * 0.4;
      controls.maxDistance = radius * 8;
      onDispose.push(() => controls.dispose());

      const raycaster = new THREE.Raycaster();
      raycaster.params.Line.threshold = wireHoverThreshold(radius);
      const pointer = new THREE.Vector2();
      // Clicks pass through the rat's-nest to the part beneath; hover
      // answers on wires too, so it keeps the full child list.
      const pickables = group.children.filter((child) => child.name !== WIRES_GROUP_NAME);
      let downAt: { x: number; y: number } | null = null;
      const resolveId = (target: THREE.Object3D): string | null => {
        let current: THREE.Object3D | null = target;
        while (current) {
          const id = (current.userData as { id?: unknown }).id;
          if (typeof id === "string") return id;
          current = current.parent;
        }
        return null;
      };
      const onPointerDown = (event: PointerEvent): void => {
        downAt = { x: event.clientX, y: event.clientY };
      };
      const onPointerUp = (event: PointerEvent): void => {
        if (!downAt) return;
        const drift = Math.hypot(event.clientX - downAt.x, event.clientY - downAt.y);
        downAt = null;
        if (drift > CLICK_DRIFT_PX) return;
        const rect = created.domElement.getBoundingClientRect();
        pointer.set(
          ((event.clientX - rect.left) / rect.width) * 2 - 1,
          -((event.clientY - rect.top) / rect.height) * 2 + 1,
        );
        raycaster.setFromCamera(pointer, camera);
        const hit = raycaster.intersectObjects(pickables, true)[0];
        const sceneId = hit ? resolveId(hit.object) : null;
        if (!sceneId) {
          onSpot(null);
          return;
        }
        onSpot(sceneIdToBlockId(sceneId));
        const block = findBlock(root, sceneIdToBlockId(sceneId));
        if (block) onSelect(structureSelection(block, sceneId));
      };
      // Hover names the part under the cursor. Throttled: a tooltip at
      // 20fps is plenty, and the scene stays cheap to raycast.
      let lastHoverAt = 0;
      const onPointerMove = (event: PointerEvent): void => {
        const now = Date.now();
        if (now - lastHoverAt < 50) return;
        lastHoverAt = now;
        const rect = created.domElement.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return;
        pointer.set(
          ((event.clientX - rect.left) / rect.width) * 2 - 1,
          -((event.clientY - rect.top) / rect.height) * 2 + 1,
        );
        raycaster.setFromCamera(pointer, camera);
        const hit = raycaster.intersectObjects(group.children, true)[0];
        let node: THREE.Object3D | null = hit ? hit.object : null;
        let label: string | null = null;
        while (node) {
          const text = (node.userData as { label?: unknown }).label;
          if (typeof text === "string") {
            label = text;
            break;
          }
          node = node.parent;
        }
        created.domElement.style.cursor = label ? "pointer" : "";
        setHover(
          label
            ? { x: event.clientX - rect.left, y: event.clientY - rect.top, label }
            : null,
        );
      };
      const onPointerLeave = (): void => {
        created.domElement.style.cursor = "";
        setHover(null);
      };
      created.domElement.addEventListener("pointerdown", onPointerDown);
      created.domElement.addEventListener("pointerup", onPointerUp);
      created.domElement.addEventListener("pointermove", onPointerMove);
      created.domElement.addEventListener("pointerleave", onPointerLeave);
      onDispose.push(() => {
        created.domElement.removeEventListener("pointerdown", onPointerDown);
        created.domElement.removeEventListener("pointerup", onPointerUp);
        created.domElement.removeEventListener("pointermove", onPointerMove);
        created.domElement.removeEventListener("pointerleave", onPointerLeave);
      });

      const resize = (): void => {
        if (host.clientWidth === 0 || host.clientHeight === 0) return;
        camera.aspect = host.clientWidth / host.clientHeight;
        camera.updateProjectionMatrix();
        created.setSize(host.clientWidth, host.clientHeight);
        createdLabels.setSize(host.clientWidth, host.clientHeight);
      };
      resize();
      const observer =
        typeof ResizeObserver === "function" ? new ResizeObserver(resize) : null;
      observer?.observe(host);
      onDispose.push(() => observer?.disconnect());

      let frame = 0;
      let stopped = false;
      onDispose.push(() => {
        stopped = true;
      });
      const loop = (): void => {
        if (stopped) return;
        frame = requestAnimationFrame(loop);
        controls.update();
        created.render(scene3, camera);
        createdLabels.render(scene3, camera);
      };
      loop();
      onDispose.push(() => cancelAnimationFrame(frame));
    } catch {
      setFailed(true);
    }
    return () => {
      for (const dispose of onDispose) dispose();
      for (const disposable of disposables) disposable.dispose();
      renderer?.dispose();
      labelRenderer?.domElement.remove();
      renderer?.domElement.remove();
    };
    // The scene, root, circuit, and handlers are stable per IR (the
    // select handler is memoized at the workspace, the spot handler is
    // a setState), so parent re-renders never rebuild the canvas; a
    // refetched IR — or newly traced outlines — rebuilds it once.
  }, [scene, root, circuit, segments, onSelect, onSpot, failed]);

  // The slider only rewrites three.js transforms from the snapshot —
  // no state, no rebuild, so it glides at input speed.
  useEffect(() => {
    if (snapshotRef.current) applyExplode(snapshotRef.current, explode / 100);
  }, [explode]);

  function exportPng(): void {
    const canvas = rendererRef.current?.domElement;
    if (!canvas) return;
    downloadHref(structureFilename(scene.title, "png"), canvas.toDataURL("image/png"));
  }

  function exportSvg(): void {
    const group = groupRef.current;
    const camera = cameraRef.current;
    if (!group || !camera) return;
    group.updateMatrixWorld(true);
    camera.updateMatrixWorld();
    const project = (point: Point3): Projected | null => {
      const cameraSpace = new THREE.Vector3(point[0], point[1], point[2]).applyMatrix4(
        camera.matrixWorldInverse,
      );
      if (cameraSpace.z > 0) return null;
      const ndc = new THREE.Vector3(point[0], point[1], point[2]).project(camera);
      return {
        x: (ndc.x * 0.5 + 0.5) * SVG_WIDTH,
        y: (1 - (ndc.y * 0.5 + 0.5)) * SVG_HEIGHT,
        z: ndc.z,
      };
    };
    const parts: SvgPart[] = [];
    const wires: SvgWire[] = [];
    for (const child of group.children) {
      if (child.name === WIRES_GROUP_NAME) {
        for (const lines of child.children) {
          const segments = lines as THREE.LineSegments;
          const positions = segments.geometry.getAttribute("position") as
            | THREE.BufferAttribute
            | undefined;
          const net = (segments.userData as { net?: unknown }).net;
          if (!positions || typeof net !== "string") continue;
          const array = positions.array as Float32Array;
          const legs: SvgWireLeg[] = [];
          for (let vertex = 0; vertex + 3 < positions.count; vertex += 4) {
            const at = (offset: number): Point3 => {
              const base = (vertex + offset) * 3;
              return [array[base], array[base + 1], array[base + 2]];
            };
            legs.push({ hub: at(0), mid: at(1), spoke: at(3) });
          }
          const material = segments.material as THREE.LineBasicMaterial | undefined;
          wires.push({ net, color: `#${material?.color.getHexString() ?? "999999"}`, legs });
        }
        continue;
      }
      const rawId = (child.userData as { id?: unknown }).id;
      if (typeof rawId !== "string") continue;
      const label = (child.userData as { label?: unknown }).label;
      const bounds = new THREE.Box3().setFromObject(child);
      if (bounds.isEmpty()) continue;
      const corners: Point3[] = [];
      for (const x of [bounds.min.x, bounds.max.x]) {
        for (const y of [bounds.min.y, bounds.max.y]) {
          for (const z of [bounds.min.z, bounds.max.z]) {
            corners.push([x, y, z]);
          }
        }
      }
      parts.push({
        label: typeof label === "string" ? label : sceneIdToBlockId(rawId),
        color: partColor(child),
        corners,
      });
    }
    const svg = buildStructureSvg({
      title: scene.title,
      caption: "Projected vector snapshot — arrangement, not dimensions.",
      width: SVG_WIDTH,
      height: SVG_HEIGHT,
      background: themeBackground(),
      parts,
      wires,
      project,
    });
    const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
    downloadHref(structureFilename(scene.title, "svg"), url);
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  // Spotlight: the picked part glows while the rest of the scene dims
  // to ghosts, so one part is always pointable among many. Originals
  // are stashed per mesh because the engine varies base colors by kind.
  useEffect(() => {
    const group = groupRef.current;
    if (!group || failed) return;
    // The picked part's floating tag expands to its full label; every
    // other tag stays short so the scene keeps breathing room.
    const host = hostRef.current;
    const spotLabel = spotId ? (findBlock(root, spotId)?.label ?? null) : null;
    if (host) {
      for (const el of host.querySelectorAll(`.${canvasStyles.tagInner}`)) {
        const tag = el as HTMLDivElement;
        const full = tag.dataset.full ?? tag.textContent ?? "";
        // Nested tags carry dims ("Up · 14336×4096"); they still open
        // for their own block.
        const open =
          spotLabel !== null && (full === spotLabel || full.startsWith(`${spotLabel} · `));
        tag.textContent = open ? full : shortTagLabel(full);
        tag.classList.toggle(canvasStyles.tagOpen, open);
      }
    }
    group.traverse((child) => {
      if (!(child instanceof THREE.Mesh)) return;
      const raw = child.material as THREE.Material | THREE.Material[] | undefined;
      const mats = Array.isArray(raw) ? raw : raw ? [raw] : [];
      // Model sub-meshes carry no id; the dressed group above them does.
      let node: THREE.Object3D | null = child;
      let id: string | null = null;
      while (node) {
        const raw = (node.userData as { id?: unknown }).id;
        if (typeof raw === "string") {
          id = sceneIdToBlockId(raw);
          break;
        }
        node = node.parent;
      }
      const userData = child.userData as {
        spot?: { e: number; ei: number; o: number; t: boolean };
      };
      const lit = spotId !== null && id === spotId;
      for (const mat of mats) {
        if (!(mat instanceof THREE.MeshStandardMaterial)) continue;
        userData.spot ??= {
          e: mat.emissive.getHex(),
          ei: mat.emissiveIntensity,
          o: mat.opacity,
          t: mat.transparent,
        };
        const orig = userData.spot;
        if (spotId === null) {
          mat.emissive.setHex(orig.e);
          mat.emissiveIntensity = orig.ei;
          mat.opacity = orig.o;
          mat.transparent = orig.t;
        } else if (lit) {
          mat.emissive.setHex(0xffffff);
          mat.emissiveIntensity = 0.45;
          mat.opacity = orig.o;
          mat.transparent = orig.t;
        } else {
          mat.emissive.setHex(0x000000);
          mat.emissiveIntensity = orig.ei;
          mat.opacity = 0.22;
          mat.transparent = true;
        }
        mat.needsUpdate = true;
      }
    });
  }, [spotId, scene, root, failed]);

  if (failed) {
    return (
      <ErrorState
        title="3D needs WebGL, which this browser does not offer."
        detail="No structure is drawn instead of a degraded one; the paper's figures and the other views stay available."
      />
    );
  }
  return (
    <>
      <div className={canvasStyles.toolbar} role="group" aria-label="3D view tools">
        <label className={canvasStyles.explode}>
          Explode
          <input
            type="range"
            min={0}
            max={100}
            step={1}
            value={explode}
            onChange={(event) => setExplode(Number(event.target.value))}
            aria-label="Explode layers"
          />
        </label>
        <button type="button" onClick={exportPng}>
          Export PNG
        </button>
        <button type="button" onClick={exportSvg}>
          Export SVG
        </button>
      </div>
      <div
        ref={hostRef}
        className={canvasStyles.stage}
        role="application"
        aria-label={`3D structure: ${scene.title}`}
      >
        <p className={canvasStyles.hint}>Drag to orbit · scroll to zoom · hover parts and wires · click to inspect</p>
        {hover ? (
          <div
            className={canvasStyles.hoverTip}
            style={{ left: hover.x, top: hover.y }}
            aria-hidden="true"
            data-testid="structure-hover"
          >
            {hover.label}
          </div>
        ) : null}
      </div>
    </>
  );
}
