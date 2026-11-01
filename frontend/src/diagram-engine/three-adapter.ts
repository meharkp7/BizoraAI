// Optional adapter: turns a Scene (renderer-agnostic boxes) into a Three.js group for the app's 3D canvas.
// Scene axes: x = east, y = south, z = up.  Three.js axes: x = east, y = up, z = south.
import * as THREE from 'three';
import type { Scene, Box3D } from './structure.js';

export function sceneToThree(scene: Scene): THREE.Group {
  const group = new THREE.Group(); group.name = scene.title;
  const edge = new THREE.LineBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.35 });
  const make = (b: Box3D) => {
    const geo = new THREE.BoxGeometry(b.w, b.h, b.d);
    const mesh = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: b.color, roughness: 0.65, metalness: 0.05 }));
    mesh.position.set(b.x + b.w / 2, b.z + b.h / 2, b.y + b.d / 2);
    mesh.userData = { id: b.id, label: b.label, kind: b.kind, part: b.part }; // for picking -> inspector/evidence
    const lines = new THREE.LineSegments(new THREE.EdgesGeometry(geo), edge); mesh.add(lines);
    return mesh;
  };
  scene.boxes.forEach((b) => group.add(make(b)));
  return group;
}
