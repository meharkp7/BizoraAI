/* Rat's-nest wiring for the Circuit 3D scene: the engine lays the
schematic's parts out as individuals, so this module connects them the
way the circuit's nets do — one lifted arc per net leg, colored by net
role. Pure derivation from the circuit IR plus the dressed parts'
world anchors: no paper-specific constants. Wires answer hover
picking (each carries a net label) but clicks exclude the wires
group, so clicks pass through to the part beneath; legs metadata lets
exploded views and vector exports track each endpoint's part. Their
geometry disposes with the scene like any other child. */

import * as THREE from "three";
import type { CircuitIRJson } from "../../lib/types.ts";

/** World anchor per part id (top-center of its dressed model). */
export type PartAnchors = ReadonlyMap<string, THREE.Vector3>;

/** One star leg: hub part id to spoke part id, in vertex order. */
export interface WireLeg {
  hub: string;
  spoke: string;
}

/** Hover label naming the net and the parts it joins. */
export function wireLabel(netId: string, members: string[]): string {
  const shown = members.slice(0, 3).join(" → ");
  const rest = members.length > 3 ? ` +${members.length - 3}` : "";
  return `Net ${netId} (${shown}${rest})`;
}

/** Hover picking width for 1px wires, relative to scene size. */
export function wireHoverThreshold(sceneRadius: number): number {
  return Math.max(sceneRadius * 0.02, 0.01);
}

function roleColor(role: string): number {
  const key = role.toLowerCase();
  if (key.includes("supply") || key.includes("power") || key === "vdd") return 0xb03a2e;
  if (key.includes("ground") || key === "gnd") return 0x2e4053;
  return 0xb87333;
}

/** Arc lift as a share of the span, so short hops stay low and long
 *  ones clear the parts between them. */
const LIFT_SHARE = 0.12;

/** Connect the parts each net touches, star-shaped from the first
 *  member found. Nets with fewer than two anchored members (open pins,
 *  rails to nowhere) draw nothing: no false wire. */
export function buildCircuitWires(
  circuit: CircuitIRJson,
  anchors: PartAnchors,
): THREE.Group {
  const group = new THREE.Group();
  group.name = "circuit-wires";
  const pinNets = new Map<string, string[]>();
  for (const component of circuit.components) {
    for (const net of Object.values(component.pins)) {
      const members = pinNets.get(net) ?? [];
      members.push(component.id);
      pinNets.set(net, members);
    }
  }
  const roles = new Map(circuit.nets.map((net) => [net.id, net.role] as const));
  for (const [netId, members] of pinNets) {
    const anchored = members.filter((id) => anchors.has(id));
    if (anchored.length < 2) continue;
    const hubId = anchored[0];
    const hub = anchors.get(hubId) as THREE.Vector3;
    const positions: number[] = [];
    const legs: WireLeg[] = [];
    for (const id of anchored.slice(1)) {
      const spoke = anchors.get(id) as THREE.Vector3;
      const mid = hub
        .clone()
        .lerp(spoke, 0.5)
        .add(new THREE.Vector3(0, hub.distanceTo(spoke) * LIFT_SHARE, 0));
      positions.push(hub.x, hub.y, hub.z, mid.x, mid.y, mid.z);
      positions.push(mid.x, mid.y, mid.z, spoke.x, spoke.y, spoke.z);
      legs.push({ hub: hubId, spoke: id });
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(positions), 3));
    const wires = new THREE.LineSegments(
      geometry,
      new THREE.LineBasicMaterial({ color: roleColor(roles.get(netId) ?? "") }),
    );
    wires.userData = { net: netId, label: wireLabel(netId, anchored), legs };
    group.add(wires);
  }
  return group;
}
