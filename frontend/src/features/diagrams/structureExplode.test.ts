import * as THREE from "three";
import { describe, expect, it } from "vitest";
import { applyExplode, snapshotExplode } from "./structureExplode.ts";

function boxAt(x: number, y: number, id: string): THREE.Mesh {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(2, 2, 2));
  mesh.position.set(x, y, 0);
  mesh.userData = { id };
  return mesh;
}

function scene(): THREE.Group {
  const group = new THREE.Group();
  // Base plate at x=0, part stacked beside it at x=6.
  group.add(boxAt(0, 0, "plate"));
  group.add(boxAt(6, 3, "part"));
  const wires = new THREE.Group();
  wires.name = "circuit-wires";
  const geometry = new THREE.BufferGeometry();
  // One leg: hub (plate top) -> mid -> mid -> spoke (part top).
  geometry.setAttribute(
    "position",
    new THREE.BufferAttribute(new Float32Array([0, 1, 0, 3, 3, 0, 3, 3, 0, 6, 4, 0]), 3),
  );
  const lines = new THREE.LineSegments(geometry, new THREE.LineBasicMaterial());
  lines.userData = { net: "n1", legs: [{ hub: "plate", spoke: "part" }] };
  wires.add(lines);
  group.add(wires);
  return group;
}

const keyOf = (child: THREE.Object3D): string | null => {
  const id = (child.userData as { id?: unknown }).id;
  return typeof id === "string" ? id : null;
};

describe("structureExplode", () => {
  it("leaves the build untouched at t = 0", () => {
    const group = scene();
    const snapshot = snapshotExplode(group, keyOf, []);
    applyExplode(snapshot, 0);
    expect((group.children[0] as THREE.Mesh).position.toArray()).toEqual([0, 0, 0]);
    expect((group.children[1] as THREE.Mesh).position.toArray()).toEqual([6, 3, 0]);
    const wires = group.children[2].children[0] as THREE.LineSegments;
    const positions = wires.geometry.getAttribute("position") as THREE.BufferAttribute;
    expect(Array.from(positions.array as Float32Array)).toEqual([
      0, 1, 0, 3, 3, 0, 3, 3, 0, 6, 4, 0,
    ]);
  });

  it("lifts stacks while flat neighbors bloom outward", () => {
    const group = scene();
    const snapshot = snapshotExplode(group, keyOf, []);
    // Scene spans x -1..7 (center 3), base y = -1. Plate: pivot x=0
    // blooms -1.8, sits on the base (rise 0). Part: pivot x=6 blooms
    // +1.8, base y=2 rises 3.
    applyExplode(snapshot, 1);
    const plate = (group.children[0] as THREE.Mesh).position;
    const part = (group.children[1] as THREE.Mesh).position;
    expect(plate.x).toBeCloseTo(-1.8);
    expect(plate.y).toBeCloseTo(0);
    expect(part.x).toBeCloseTo(7.8);
    expect(part.y).toBeCloseTo(6);
  });

  it("keeps wire endpoints glued to their own parts", () => {
    const group = scene();
    const snapshot = snapshotExplode(group, keyOf, []);
    applyExplode(snapshot, 1);
    const wires = group.children[2].children[0] as THREE.LineSegments;
    const positions = wires.geometry.getAttribute("position") as THREE.BufferAttribute;
    const array = positions.array as Float32Array;
    // Hub tracks the plate (-1.8, +0), spoke tracks the part
    // (+1.8, +3), mids split the shift (+0, +1.5).
    expect(array[0]).toBeCloseTo(-1.8);
    expect(array[1]).toBeCloseTo(1);
    expect(array[3]).toBeCloseTo(3);
    expect(array[4]).toBeCloseTo(4.5);
    expect(array[9]).toBeCloseTo(7.8);
    expect(array[10]).toBeCloseTo(7);
  });

  it("restores the build exactly when closed again", () => {
    const group = scene();
    const snapshot = snapshotExplode(group, keyOf, []);
    applyExplode(snapshot, 1);
    applyExplode(snapshot, 0);
    expect((group.children[0] as THREE.Mesh).position.toArray()).toEqual([0, 0, 0]);
    expect((group.children[1] as THREE.Mesh).position.toArray()).toEqual([6, 3, 0]);
  });
});
