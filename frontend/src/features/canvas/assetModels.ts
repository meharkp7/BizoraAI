/* Asset-model layer for the 3D explorer: GLB load requests, procedural
   fallback geometry, and the measured-vs-illustrative indicator. Field
   names mirror backend RenderSpec JSON verbatim. No renderer imports
   here beyond three.js scene-graph classes, so vitest never needs
   WebGL: BufferGeometry construction and the loader stub run headless. */

import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

export type AssetProvenance = "measured" | "illustrative";

/** One node's render spec, mirroring backend RenderSpec JSON. */
export interface NodeAssetSpec {
  nodeId: string;
  label: string;
  assetUri: string | null;
  fallbackPackage: string | null;
  illustrative: boolean;
}

/** One generated solid, mirroring backend MeshPart JSON. */
export interface ProceduralPartData {
  name: string;
  vertices: [number, number, number][];
  faces: [number, number, number][];
}

/** Generated fallback mesh, mirroring backend ProceduralMesh JSON. */
export interface ProceduralMeshData {
  parts: ProceduralPartData[];
}

export interface AssetSummary {
  measured: number;
  illustrative: number;
  total: number;
}

export interface GlbLoadRequest {
  nodeId: string;
  url: string;
}

/** Provenance of one node visual: a real model or a stand-in. */
export function provenanceOf(spec: NodeAssetSpec): AssetProvenance {
  return spec.illustrative ? "illustrative" : "measured";
}

export function provenanceLabel(provenance: AssetProvenance): string {
  return provenance === "measured" ? "Measured model" : "Illustrative stand-in";
}

/** Count measured vs illustrative visuals for the explorer indicator. */
export function summarizeProvenance(specs: readonly NodeAssetSpec[] | null | undefined): AssetSummary {
  let measured = 0;
  let illustrative = 0;
  for (const spec of specs ?? []) {
    if (provenanceOf(spec) === "measured") measured += 1;
    else illustrative += 1;
  }
  return { measured, illustrative, total: measured + illustrative };
}

/** GLB fetch list: measured specs with a URI, deduplicated by node. */
export function loadRequests(specs: readonly NodeAssetSpec[] | null | undefined): GlbLoadRequest[] {
  const seen = new Set<string>();
  const requests: GlbLoadRequest[] = [];
  for (const spec of specs ?? []) {
    if (spec.assetUri === null || spec.assetUri === "" || seen.has(spec.nodeId)) continue;
    seen.add(spec.nodeId);
    requests.push({ nodeId: spec.nodeId, url: spec.assetUri });
  }
  return requests;
}

export function specsByNodeId(
  specs: readonly NodeAssetSpec[] | null | undefined,
): Map<string, NodeAssetSpec> {
  const index = new Map<string, NodeAssetSpec>();
  for (const spec of specs ?? []) {
    if (!index.has(spec.nodeId)) index.set(spec.nodeId, spec);
  }
  return index;
}

/** Minimal loader surface so tests can stub GLB fetching. */
export interface GlbLoader {
  loadAsync(url: string): Promise<{ scene: THREE.Group }>;
}

/** Fetch one GLB model; the caller owns caching, scaling, and disposal. */
export async function loadGlbModel(url: string, loader: GlbLoader = new GLTFLoader()): Promise<THREE.Group> {
  const gltf = await loader.loadAsync(url);
  return gltf.scene;
}

/** Build one BufferGeometry per part from generated mesh data. Vertices
 *  are real fallback solids from the backend, not decoration: faces
 *  index them directly and normals are computed from the triangles. */
export function buildProceduralGeometries(mesh: ProceduralMeshData): THREE.BufferGeometry[] {
  return mesh.parts.map((part) => {
    const positions = new Float32Array(part.vertices.length * 3);
    part.vertices.forEach(([x, y, z], index) => {
      positions[index * 3] = x;
      positions[index * 3 + 1] = y;
      positions[index * 3 + 2] = z;
    });
    const indices: number[] = [];
    for (const [a, b, c] of part.faces) indices.push(a, b, c);
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geometry.setIndex(indices);
    geometry.computeVertexNormals();
    return geometry;
  });
}
