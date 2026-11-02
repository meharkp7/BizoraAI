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
  StructureIRJson,
} from "../../lib/types.ts";
import { renderStructureDiagram } from "./adapters.ts";
import { CircuitPicker } from "./CircuitPicker.tsx";
import { circuitToStructure } from "./circuitToStructure.ts";
import { buildCircuitWires, wireHoverThreshold } from "./circuitWires.ts";
import { buildPartIdentity, shortTagLabel } from "./partIdentity.ts";
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
  const activeScene = showingCircuit && circuitScene ? circuitScene.scene : showingDetail && detail ? detail : built.scene;
  const activeRoot =
    showingCircuit && circuitScene
      ? circuitScene.root
      : showingDetail && detailCell
        ? detailCell
        : structure.root;
  const counts = countProvenance(walkBlocks(activeRoot));
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
      <StructureCanvas
        scene={activeScene}
        root={activeRoot}
        circuit={showingCircuit && circuitScene ? circuitScene.circuit : null}
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
      {showingCircuit || showingDetail ? (
        <ul className={styles.layerLegend} aria-label="Part family legend">
          <li><span className={styles.swatch} data-shape="transistor" />Transistor</li>
          <li><span className={styles.swatch} data-shape="passive" />Passive</li>
          <li><span className={styles.swatch} data-shape="logic" />Logic</li>
          <li><span className={styles.swatch} data-shape="power" />Power</li>
          <li><span className={styles.swatch} data-shape="part" />Part</li>
        </ul>
      ) : (
        <ul className={styles.layerLegend} aria-label="Part shape legend">
          <li><span className={styles.swatch} data-shape="store" />Store / dataset</li>
          <li><span className={styles.swatch} data-shape="module" />Module</li>
          <li><span className={styles.swatch} data-shape="decision" />Decision</li>
          <li><span className={styles.swatch} data-shape="io" />Input / output</li>
          <li><span className={styles.swatch} data-shape="part" />Part</li>
        </ul>
      )}
      <p className={styles.counts}>
        Shapes follow the IR kind and plates name each part from the paper&apos;s own
        text — click any part for its evidence. Arrangement, not dimensions.
      </p>
    </div>
  );
}

/** Swap every engine box for its generic identity (shape by IR enum,
 *  engraved plate from IR text). The chip root keeps its box for the
 *  silicon finish below. Each part sits in an unscaled wrapper at the
 *  box's position carrying the box's id/label, so picking, hover,
 *  spotlight and disposal keep working unchanged; nested children
 *  (module members the engine never draws) lay out in a grid on top. */
function dressPartMeshes(group: THREE.Group, root: DiagramBlock): void {
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
    const model = buildPartIdentity(block, params.width / Math.max(params.depth, 1e-6));
    // Unit footprint (1x1, height 0.5) scaled onto the engine box.
    model.scale.set(params.width, params.height / 0.5, params.depth);
    wrapper.add(model);
    layoutNestedParts(wrapper, block, params.width, params.height, params.depth);
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

/** Lay a block's children in a grid on top of its dressed box. The
 *  engine draws only top-level boxes, so module members (and any other
 *  nesting) would otherwise stay invisible; this arrangement is
 *  illustrative — the caption says so — while shapes, tints and plates
 *  stay just as honest as top-level parts. Each child gets its own
 *  unscaled wrapper with its block id/label, so picking, hover and
 *  spotlight treat nested parts exactly like top-level ones. */
function layoutNestedParts(
  parent: THREE.Group,
  block: DiagramBlock,
  w: number,
  h: number,
  d: number,
): void {
  const kids = block.children;
  if (kids.length === 0) return;
  const cols = Math.ceil(Math.sqrt(kids.length));
  const rows = Math.ceil(kids.length / cols);
  const cellW = w / cols;
  const cellD = d / rows;
  const childH = Math.min(h * 0.9, Math.max(cellW, cellD) * 0.55);
  kids.forEach((kid, index) => {
    const col = index % cols;
    const row = Math.floor(index / cols);
    const wrapper = new THREE.Group();
    wrapper.position.set(
      -w / 2 + cellW * (col + 0.5),
      h,
      -d / 2 + cellD * (row + 0.5),
    );
    wrapper.userData = { id: kid.id, label: kid.label };
    const model = buildPartIdentity(kid, cellW / Math.max(cellD, 1e-6));
    model.scale.set(cellW * 0.9, childH / 0.5, cellD * 0.9);
    wrapper.add(model);
    parent.add(wrapper);
    layoutNestedParts(wrapper, kid, cellW * 0.9, childH, cellD * 0.9);
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
  spotId,
  onSelect,
  onSpot,
}: {
  scene: Scene;
  root: DiagramBlock;
  circuit: CircuitIRJson | null;
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
      dressPartMeshes(group, root);
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
    // refetched IR rebuilds it once.
  }, [scene, root, circuit, onSelect, onSpot, failed]);

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
        const open = spotLabel !== null && full === spotLabel;
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
