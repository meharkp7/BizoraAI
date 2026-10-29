import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { CSS2DObject, CSS2DRenderer } from "three/addons/renderers/CSS2DRenderer.js";
import { EmptyState, ErrorState } from "../../components/states.tsx";
import { useTheme, useWorkspaceSelection } from "../../lib/store.ts";
import type {
  GraphEntities,
  GraphLayout,
  MeasuredOverlay,
  MethodologyGraph,
} from "../../lib/types.ts";
import { EMPTY_OVERLAY } from "../../lib/types.ts";
import {
  buildProceduralGroup,
  loadGlbModel,
  loadRequests,
  meshSpecs,
  partLegendEntries,
  provenanceLabel,
  provenanceOf,
  specsByNodeId,
  summarizeProvenance,
} from "./assetModels.ts";
import type { NodeAssetSpec, ProceduralPartRole } from "./assetModels.ts";
import { PartLegend } from "./EntityLegend.tsx";
import {
  EDGE_COLOR,
  SELECT_COLOR,
  boundingSphere,
  fitDistance,
  resolutionsByNodeId,
  toWorldPositions,
} from "./graph3d.ts";
import styles from "./GraphCanvas3D.module.css";

const NODE_RADIUS = 1.1;
const SELECT_SCALE = 1.3;
const CLICK_DRIFT_PX = 6;

function themeBackground(): string {
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue("--color-surface")
    .trim();
  return value === "" ? "#faf7ec" : value;
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

export function GraphCanvas3D({
  graph,
  layout,
  entities,
  entitiesPending = false,
  entitiesError = null,
  assetSpecs = null,
  overlay = EMPTY_OVERLAY,
}: {
  graph: MethodologyGraph;
  layout: GraphLayout | null;
  entities: GraphEntities | null;
  entitiesPending?: boolean;
  entitiesError?: string | null;
  assetSpecs?: NodeAssetSpec[] | null;
  overlay?: MeasuredOverlay;
}) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [failed, setFailed] = useState(false);
  const assetSummary = useMemo(() => summarizeProvenance(assetSpecs), [assetSpecs]);
  // Parts-only scene: a node renders if and only if the backend serves a
  // part model for it. Everything else stays in the 2D views, counted
  // honestly in the legend instead of faked with a generic solid.
  const parts = useMemo(
    () => partLegendEntries(assetSpecs, graph.nodes, resolutionsByNodeId(entities)),
    [assetSpecs, graph, entities],
  );
  const modeledIds = useMemo(() => {
    const ids = new Set(graph.nodes.map((node) => node.id));
    return new Set(parts.map((part) => part.nodeId).filter((id) => ids.has(id)));
  }, [parts, graph]);
  const unmodeled = graph.nodes.length - modeledIds.size;
  const [coarsePointer] = useState(
    () =>
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(pointer: coarse)").matches,
  );

  useEffect(() => {
    const host = hostRef.current;
    if (!host || failed) return;
    if (!webglAvailable()) {
      setFailed(true);
      return;
    }
    let renderer: THREE.WebGLRenderer | null = null;
    let labelRenderer: CSS2DRenderer | null = null;
    const disposables: { dispose: () => void }[] = [];
    const onDispose: (() => void)[] = [];
    try {
      const positions = toWorldPositions(graph, layout);
      // The camera fits the rendered models, not the unmodeled nodes that
      // stay in the 2D views: fitting ghosts would shrink real parts.
      const rendered = new Map(
        [...positions.entries()].filter(([id]) => modeledIds.has(id)),
      );
      const { center, radius } = boundingSphere(rendered);
      const background = new THREE.Color(themeBackground());

      const scene = new THREE.Scene();
      scene.background = background;
      scene.fog = new THREE.Fog(background.clone(), radius * 3, radius * 7);

      const camera = new THREE.PerspectiveCamera(45, 1, 0.1, radius * 50);
      const aspect =
        host.clientWidth > 0 && host.clientHeight > 0
          ? host.clientWidth / host.clientHeight
          : 1;
      const aim = { x: 1, y: 0.85, z: 1 };
      // Exact rotation-invariant fit: neither diagonal views nor orbiting
      // can clip corners; the margin covers the sphere bodies.
      const distance = fitDistance(rendered, aim, camera.fov, aspect, NODE_RADIUS, 1.1);
      const direction = new THREE.Vector3(aim.x, aim.y, aim.z).normalize();
      camera.position.set(
        center.x + direction.x * distance,
        center.y + direction.y * distance,
        center.z + direction.z * distance,
      );

      const created = new THREE.WebGLRenderer({ antialias: true });
      renderer = created;
      created.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      host.appendChild(created.domElement);
      const createdLabels = new CSS2DRenderer();
      labelRenderer = createdLabels;
      createdLabels.domElement.className = styles.labels;
      host.appendChild(createdLabels.domElement);

      scene.add(new THREE.HemisphereLight(0xfffdf6, 0x8b8471, 1.3));
      const key = new THREE.DirectionalLight(0xffffff, 1.0);
      key.position.set(center.x + distance, center.y + distance, center.z + distance);
      scene.add(key);
      const fill = new THREE.DirectionalLight(0xf0e1cf, 0.4);
      fill.position.set(center.x - distance, center.y + distance * 0.5, center.z - distance);
      scene.add(fill);

      const modelGroups = new Map<string, THREE.Group>();
      const pickRoots: THREE.Object3D[] = [];
      const nodeTags = new Map<string, { element: HTMLDivElement; marker: CSS2DObject }>();
      const specs = specsByNodeId(assetSpecs);
      // Label markers exist for every modeled node, floating at the node
      // position until their model group arrives to parent them.
      for (const node of graph.nodes) {
        if (!modeledIds.has(node.id)) continue;
        const point = positions.get(node.id) ?? { x: 0, y: 0, z: 0 };
        const tag = document.createElement("div");
        tag.className = `${styles.tag} ${styles.tagHidden}`;
        const inner = document.createElement("div");
        inner.className = styles.tagInner;
        const name = document.createElement("div");
        name.textContent = node.label;
        inner.appendChild(name);
        const spec = specs.get(node.id);
        if (spec) {
          // Per-node measured-vs-illustrative marker inside the lifted
          // label block, so it floats above the node instead of sitting
          // centered on the body where the mesh hides it.
          const badge = document.createElement("span");
          const provenance = provenanceOf(spec);
          badge.textContent = provenanceLabel(provenance);
          badge.dataset.provenance = provenance;
          badge.style.display = "block";
          badge.style.fontSize = "11px";
          badge.style.opacity = "0.8";
          inner.appendChild(badge);
        }
        tag.appendChild(inner);
        const marker = new CSS2DObject(tag);
        marker.visible = false;
        marker.position.set(point.x, point.y, point.z);
        scene.add(marker);
        nodeTags.set(node.id, { element: tag, marker });
      }

      // Generated package solids render synchronously, normalized to the
      // node size. Specs with a model URI skip this path: the GLB loader
      // below owns them instead. Nodes without a spec render nothing.
      const bodyMaterial = new THREE.MeshStandardMaterial({
        color: "#4a4a55",
        roughness: 0.42,
        metalness: 0.3,
      });
      const leadMaterial = new THREE.MeshStandardMaterial({
        color: "#c9ced6",
        roughness: 0.3,
        metalness: 0.9,
      });
      disposables.push(bodyMaterial, leadMaterial);
      const proceduralMaterial = (role: ProceduralPartRole): THREE.Material =>
        role === "body" ? bodyMaterial : leadMaterial;
      for (const spec of meshSpecs(assetSpecs)) {
        if (spec.asset_uri || spec.mesh === null) continue;
        if (!modeledIds.has(spec.node_id)) continue;
        const point = positions.get(spec.node_id);
        if (!point) continue;
        const group = buildProceduralGroup(spec.mesh, proceduralMaterial);
        const box = new THREE.Box3().setFromObject(group);
        const size = box.getSize(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z) || 1;
        const scale = (NODE_RADIUS * 2) / maxDim;
        group.scale.setScalar(scale);
        const center = box.getCenter(new THREE.Vector3());
        group.position.set(
          point.x - center.x * scale,
          point.y - center.y * scale,
          point.z - center.z * scale,
        );
        group.userData.nodeId = spec.node_id;
        group.userData.baseScale = scale;
        const swappedTag = nodeTags.get(spec.node_id);
        if (swappedTag) {
          // The marker reparents to the model so the label tracks it;
          // without a model the marker stays floating at the position.
          group.add(swappedTag.marker);
          swappedTag.marker.position.set(center.x * scale, center.y * scale, center.z * scale);
        }
        scene.add(group);
        modelGroups.set(spec.node_id, group);
        pickRoots.push(group);
        disposables.push({
          dispose: () => {
            scene.remove(group);
            group.traverse((child) => {
              const childMesh = child as THREE.Mesh;
              if (childMesh.geometry) childMesh.geometry.dispose();
            });
          },
        });
      }

      // GLB models load asynchronously, normalized to the node size. A
      // missing or failing URL leaves the node out of the scene: no
      // model, no marker.
      let cancelled = false;
      const pendingLoads = new Map<string, Promise<THREE.Group>>();
      const loadCached = (url: string): Promise<THREE.Group> => {
        const pending = pendingLoads.get(url);
        if (pending) return pending;
        const started = loadGlbModel(url);
        pendingLoads.set(url, started);
        return started;
      };
      for (const request of loadRequests(assetSpecs)) {
        if (!modeledIds.has(request.nodeId)) continue;
        const point = positions.get(request.nodeId);
        if (!point) continue;
        void loadCached(request.url).then(
          (group) => {
            if (cancelled) return;
            const box = new THREE.Box3().setFromObject(group);
            const size = box.getSize(new THREE.Vector3());
            const maxDim = Math.max(size.x, size.y, size.z) || 1;
            const scale = (NODE_RADIUS * 2) / maxDim;
            group.scale.setScalar(scale);
            const center = box.getCenter(new THREE.Vector3());
            group.position.set(
              point.x - center.x * scale,
              point.y - center.y * scale,
              point.z - center.z * scale,
            );
            group.userData.nodeId = request.nodeId;
            group.userData.baseScale = scale;
            const swappedTag = nodeTags.get(request.nodeId);
            if (swappedTag) {
              group.add(swappedTag.marker);
              swappedTag.marker.position.set(
                center.x * scale,
                center.y * scale,
                center.z * scale,
              );
            }
            scene.add(group);
            modelGroups.set(request.nodeId, group);
            pickRoots.push(group);
            disposables.push({
              dispose: () => {
                scene.remove(group);
                group.traverse((child) => {
                  const childMesh = child as THREE.Mesh;
                  if (childMesh.geometry) childMesh.geometry.dispose();
                  const material = childMesh.material as
                    | THREE.Material
                    | THREE.Material[]
                    | undefined;
                  if (Array.isArray(material)) material.forEach((entry) => entry.dispose());
                  else if (material) material.dispose();
                });
              },
            });
          },
          () => {
            // Leave the node out: no model, no silent stand-in.
          },
        );
      }
      onDispose.push(() => {
        cancelled = true;
      });

      const edgeLines = new Map<string, THREE.Line>();
      const edgeTags = new Map<string, { element: HTMLDivElement; marker: CSS2DObject }>();
      for (const edge of graph.edges) {
        if (!modeledIds.has(edge.source) || !modeledIds.has(edge.target)) continue;
        const from = positions.get(edge.source);
        const to = positions.get(edge.target);
        if (!from || !to) continue;
        const start = new THREE.Vector3(from.x, from.y, from.z);
        const end = new THREE.Vector3(to.x, to.y, to.z);
        const geometry = new THREE.BufferGeometry().setFromPoints([start, end]);
        disposables.push(geometry);
        const material = new THREE.LineBasicMaterial({
          color: EDGE_COLOR,
          transparent: true,
          opacity: 0.75,
        });
        disposables.push(material);
        const line = new THREE.Line(geometry, material);
        line.userData.edgeId = edge.id;
        scene.add(line);
        edgeLines.set(edge.id, line);
        const tag = document.createElement("div");
        tag.className = `${styles.tag} ${styles.tagHidden}`;
        const inner = document.createElement("div");
        inner.className = `${styles.tagInner} ${styles.edgeTag}`;
        inner.textContent = edge.label ?? `${edge.source} → ${edge.target}`;
        tag.appendChild(inner);
        const marker = new CSS2DObject(tag);
        marker.visible = false;
        marker.position.copy(start).lerp(end, 0.5);
        scene.add(marker);
        edgeTags.set(edge.id, { element: tag, marker });
      }

      let hoveredId: string | null = null;
      const showTag = (
        tags: Map<string, { element: HTMLDivElement; marker: CSS2DObject }>,
        id: string,
        show: boolean,
      ): void => {
        const tag = tags.get(id);
        if (!tag) return;
        // Both: the label renderer manages inline display per frame, so the
        // marker flag and a stacking class carry the hidden state together.
        tag.marker.visible = show;
        tag.element.classList.toggle(styles.tagHidden, !show);
      };
      const showNodeTag = (id: string, show: boolean): void => showTag(nodeTags, id, show);
      const showEdgeTag = (id: string, show: boolean): void => showTag(edgeTags, id, show);
      const resolveNodeId = (target: THREE.Object3D): string | null => {
        let current: THREE.Object3D | null = target;
        while (current) {
          const id = current.userData.nodeId;
          if (typeof id === "string") return id;
          current = current.parent;
        }
        return null;
      };
      const applySelection = (nodeIds: readonly string[], edgeIds: readonly string[]): void => {
        const nodes = new Set(nodeIds);
        const edges = new Set(edgeIds);
        for (const id of modeledIds) {
          const selected = nodes.has(id);
          const group = modelGroups.get(id);
          if (group) {
            const base = group.userData.baseScale as number;
            group.scale.setScalar(base * (selected ? SELECT_SCALE : 1));
          }
          if (id !== hoveredId) showNodeTag(id, selected);
        }
        for (const [id, line] of edgeLines) {
          const selected = edges.has(id);
          const material = line.material as THREE.LineBasicMaterial;
          material.color.set(selected ? SELECT_COLOR : EDGE_COLOR);
          material.opacity = selected ? 1 : 0.75;
          showEdgeTag(id, selected);
        }
      };

      const store = useWorkspaceSelection.getState();
      applySelection(store.selectedNodeIds, store.selectedEdgeIds);
      const unsubscribe = useWorkspaceSelection.subscribe((state) => {
        applySelection(state.selectedNodeIds, state.selectedEdgeIds);
      });
      onDispose.push(unsubscribe);
      const unsubscribeTheme = useTheme.subscribe(() => {
        const color = new THREE.Color(themeBackground());
        (scene.background as THREE.Color).copy(color);
        (scene.fog as THREE.Fog).color.copy(color);
      });
      onDispose.push(unsubscribeTheme);

      const controls = new OrbitControls(camera, created.domElement);
      controls.target.set(center.x, center.y, center.z);
      controls.enableDamping = true;
      controls.dampingFactor = 0.08;
      controls.minDistance = radius * 0.4;
      controls.maxDistance = radius * 8;
      onDispose.push(() => controls.dispose());
      const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      controls.autoRotate = !reduceMotion;
      controls.autoRotateSpeed = 0.7;
      const stopSpin = (): void => {
        controls.autoRotate = false;
      };
      controls.addEventListener("start", stopSpin);
      onDispose.push(() => controls.removeEventListener("start", stopSpin));

      const raycaster = new THREE.Raycaster();
      raycaster.params.Line.threshold = 0.6;
      const pointer = new THREE.Vector2();
      let downAt: { x: number; y: number } | null = null;
      const pick = (event: PointerEvent): void => {
        const rect = created.domElement.getBoundingClientRect();
        pointer.set(
          ((event.clientX - rect.left) / rect.width) * 2 - 1,
          -((event.clientY - rect.top) / rect.height) * 2 + 1,
        );
        raycaster.setFromCamera(pointer, camera);
        const live = useWorkspaceSelection.getState();
        const nodeHit = raycaster.intersectObjects(pickRoots, true)[0];
        const nodeId = nodeHit ? resolveNodeId(nodeHit.object) : null;
        if (nodeHit && nodeId) {
          live.selectNodes([nodeId]);
          return;
        }
        const edgeHit = raycaster.intersectObjects([...edgeLines.values()], false)[0];
        if (edgeHit) {
          live.selectEdges([edgeHit.object.userData.edgeId as string]);
          return;
        }
        live.selectNodes([]);
      };
      const onPointerDown = (event: PointerEvent): void => {
        downAt = { x: event.clientX, y: event.clientY };
      };
      const onPointerUp = (event: PointerEvent): void => {
        if (!downAt) return;
        const drift = Math.hypot(event.clientX - downAt.x, event.clientY - downAt.y);
        downAt = null;
        if (drift <= CLICK_DRIFT_PX) pick(event);
      };
      created.domElement.addEventListener("pointerdown", onPointerDown);
      created.domElement.addEventListener("pointerup", onPointerUp);
      let lastHover = 0;
      const onPointerMove = (event: PointerEvent): void => {
        if (downAt !== null) return;
        const now = Date.now();
        if (now - lastHover < 60) return;
        lastHover = now;
        const rect = created.domElement.getBoundingClientRect();
        pointer.set(
          ((event.clientX - rect.left) / rect.width) * 2 - 1,
          -((event.clientY - rect.top) / rect.height) * 2 + 1,
        );
        raycaster.setFromCamera(pointer, camera);
        const hit = raycaster.intersectObjects(pickRoots, true)[0];
        const id = hit ? resolveNodeId(hit.object) : null;
        if (id === hoveredId) return;
        const store = useWorkspaceSelection.getState();
        if (hoveredId !== null && !store.selectedNodeIds.includes(hoveredId)) {
          showNodeTag(hoveredId, false);
        }
        hoveredId = id;
        if (id !== null) showNodeTag(id, true);
        created.domElement.style.cursor = id !== null ? "pointer" : "";
      };
      const onPointerLeave = (): void => {
        const store = useWorkspaceSelection.getState();
        if (hoveredId !== null && !store.selectedNodeIds.includes(hoveredId)) {
          showNodeTag(hoveredId, false);
        }
        hoveredId = null;
        created.domElement.style.cursor = "";
      };
      created.domElement.addEventListener("pointermove", onPointerMove);
      created.domElement.addEventListener("pointerleave", onPointerLeave);
      onDispose.push(() => {
        created.domElement.removeEventListener("pointerdown", onPointerDown);
        created.domElement.removeEventListener("pointerup", onPointerUp);
        created.domElement.removeEventListener("pointermove", onPointerMove);
        created.domElement.removeEventListener("pointerleave", onPointerLeave);
      });

      const resize = (): void => {
        const width = host.clientWidth;
        const height = host.clientHeight;
        if (width === 0 || height === 0) return;
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
        created.setSize(width, height);
        createdLabels.setSize(width, height);
      };
      resize();
      const observer = new ResizeObserver(resize);
      observer.observe(host);
      onDispose.push(() => observer.disconnect());

      created.setAnimationLoop(() => {
        controls.update();
        created.render(scene, camera);
        createdLabels.render(scene, camera);
      });
    } catch {
      setFailed(true);
    }
    return () => {
      for (const cleanup of onDispose) cleanup();
      for (const disposable of disposables) disposable.dispose();
      renderer?.setAnimationLoop(null);
      renderer?.dispose();
      renderer?.domElement.remove();
      labelRenderer?.domElement.remove();
    };
    // Scene lifetime: rebuild per graph object; selection syncs via the store.
  }, [graph, layout, entities, assetSpecs, failed, modeledIds]);

  if (failed) {
    return (
      <ErrorState
        title="3D view is unavailable."
        detail="WebGL could not start in this browser. The 2D canvas still works."
      />
    );
  }
  if (modeledIds.size === 0) {
    return (
      <EmptyState
        title="No part models in this view."
        detail={
          graph.nodes.length === 0
            ? "There is nothing to show in 3D."
            : "Nothing here resolves to a catalog part model yet; the 2D views show every component."
        }
      />
    );
  }
  return (
    <div
      ref={hostRef}
      className={styles.stage}
      role="application"
      aria-label={`3D methodology graph: ${modeledIds.size} part models. Drag to orbit, scroll to zoom, click a component to inspect it.`}
    >
      <p className={styles.hint}>
        {coarsePointer
          ? "Drag to orbit · Pinch to zoom · Two-finger drag to pan"
          : "Drag to orbit · Scroll to zoom · Right-drag to pan"}
      </p>
      {entitiesError ? (
        <p className={styles.entitiesWarning} role="alert">
          Component identities unavailable ({entitiesError}); showing part models without
          identity labels.
        </p>
      ) : entitiesPending ? (
        <p className={styles.entitiesNote} role="status">
          Resolving component identities…
        </p>
      ) : null}
      <PartLegend
        entities={entities}
        parts={parts}
        assetSummary={assetSummary}
        unmodeled={unmodeled}
        overlay={overlay}
      />
    </div>
  );
}
