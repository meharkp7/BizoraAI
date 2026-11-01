/* Exploded view for the 3D scenes: separate the assembly so stacked
parts rise while flat layouts bloom outward. Each part's rise is
(its base height above the scene base) × t, so the lowest part
stays grounded, and each part also drifts from the scene centroid
in the ground plane by 0.6 × its offset × t, so side-by-side parts
in a flat circuit separate instead of sitting still. t = 0 restores
the build exactly. Wire endpoints track their own part's full 3D
shift via the legs metadata, so arcs stay connected while exploded.
Pure three.js object math — no rendering, no paper constants. */

import * as THREE from "three";
import type { WireLeg } from "./circuitWires.ts";

export interface Vector3Like {
  x: number;
  y: number;
  z: number;
}

export interface ExplodePart {
  object: THREE.Object3D;
  key: string;
  base: Vector3Like;
  delta: Vector3Like;
}

export interface ExplodeWires {
  geometry: THREE.BufferGeometry;
  base: Float32Array;
  legs: WireLeg[];
}

export interface ExplodeMarker {
  object: THREE.Object3D;
  base: Vector3Like;
}

export interface ExplodeSnapshot {
  minY: number;
  centerX: number;
  centerZ: number;
  parts: ExplodePart[];
  wires: ExplodeWires[];
  markers: ExplodeMarker[];
  deltas: Map<string, Vector3Like>;
}

/** Name of the rat's-nest group inside a circuit scene. */
export const WIRES_GROUP_NAME = "circuit-wires";

/** Ground-plane bloom per unit of centroid offset at full explode. */
export const BLOOM_SHARE = 0.6;

/** Translate a direct scene child into its part key, or null to skip. */
export type PartKeyOf = (child: THREE.Object3D) => string | null;

function wireLegsOf(child: THREE.Object3D): WireLeg[] {
  const legs = (child.userData as { legs?: unknown }).legs;
  if (!Array.isArray(legs)) return [];
  return legs.filter(
    (leg): leg is WireLeg =>
      typeof leg === "object" &&
      leg !== null &&
      typeof (leg as WireLeg).hub === "string" &&
      typeof (leg as WireLeg).spoke === "string",
  );
}

function pointDelta(
  x: number,
  baseY: number,
  z: number,
  snapshot: { minY: number; centerX: number; centerZ: number },
): Vector3Like {
  return {
    x: (x - snapshot.centerX) * BLOOM_SHARE,
    y: Math.max(baseY - snapshot.minY, 0),
    z: (z - snapshot.centerZ) * BLOOM_SHARE,
  };
}

/** Freeze base positions and per-part shifts for one scene group. */
export function snapshotExplode(
  group: THREE.Group,
  keyOf: PartKeyOf,
  markers: THREE.Object3D[],
): ExplodeSnapshot {
  const bounds = new THREE.Box3().setFromObject(group);
  const minY = bounds.isEmpty() ? 0 : bounds.min.y;
  const center = bounds.isEmpty() ? new THREE.Vector3() : bounds.getCenter(new THREE.Vector3());
  const frame = { minY, centerX: center.x, centerZ: center.z };
  const parts: ExplodePart[] = [];
  const wires: ExplodeWires[] = [];
  const deltas = new Map<string, Vector3Like>();
  for (const child of group.children) {
    if (child.name === WIRES_GROUP_NAME) {
      for (const entry of child.children) {
        const lines = entry as THREE.LineSegments;
        const positions = lines.geometry.getAttribute("position") as
          | THREE.BufferAttribute
          | undefined;
        if (!positions) continue;
        wires.push({
          geometry: lines.geometry,
          base: new Float32Array(positions.array as Float32Array),
          legs: wireLegsOf(entry),
        });
      }
      continue;
    }
    const key = keyOf(child);
    if (key === null) continue;
    const childBounds = new THREE.Box3().setFromObject(child);
    const baseY = childBounds.isEmpty() ? child.position.y : childBounds.min.y;
    const pivot = childBounds.isEmpty()
      ? child.position
      : childBounds.getCenter(new THREE.Vector3());
    const delta = pointDelta(pivot.x, baseY, pivot.z, frame);
    parts.push({
      object: child,
      key,
      base: { x: child.position.x, y: child.position.y, z: child.position.z },
      delta,
    });
    deltas.set(key, delta);
  }
  return {
    ...frame,
    parts,
    wires,
    markers: markers.map((object) => ({
      object,
      base: { x: object.position.x, y: object.position.y, z: object.position.z },
    })),
    deltas,
  };
}

/** Spread the snapshot to t (0 = assembled, 1 = full explode). */
export function applyExplode(snapshot: ExplodeSnapshot, t: number): void {
  for (const part of snapshot.parts) {
    part.object.position.set(
      part.base.x + part.delta.x * t,
      part.base.y + part.delta.y * t,
      part.base.z + part.delta.z * t,
    );
  }
  for (const marker of snapshot.markers) {
    const delta = pointDelta(marker.base.x, marker.base.y, marker.base.z, snapshot);
    marker.object.position.set(
      marker.base.x + delta.x * t,
      marker.base.y + delta.y * t,
      marker.base.z + delta.z * t,
    );
  }
  const zero = { x: 0, y: 0, z: 0 };
  for (const wires of snapshot.wires) {
    const positions = wires.geometry.getAttribute("position") as THREE.BufferAttribute;
    const array = positions.array as Float32Array;
    for (let leg = 0; leg < wires.legs.length; leg += 1) {
      const { hub, spoke } = wires.legs[leg];
      const hubShift = snapshot.deltas.get(hub) ?? zero;
      const spokeShift = snapshot.deltas.get(spoke) ?? zero;
      const midShift = {
        x: (hubShift.x + spokeShift.x) / 2,
        y: (hubShift.y + spokeShift.y) / 2,
        z: (hubShift.z + spokeShift.z) / 2,
      };
      // Vertex order per leg: hub, mid, mid, spoke.
      const shifts = [hubShift, midShift, midShift, spokeShift];
      for (let vertex = 0; vertex < 4; vertex += 1) {
        const base = (leg * 4 + vertex) * 3;
        if (base + 2 >= array.length) continue;
        array[base] = wires.base[base] + shifts[vertex].x * t;
        array[base + 1] = wires.base[base + 1] + shifts[vertex].y * t;
        array[base + 2] = wires.base[base + 2] + shifts[vertex].z * t;
      }
    }
    positions.needsUpdate = true;
    wires.geometry.boundingSphere = null;
  }
}
