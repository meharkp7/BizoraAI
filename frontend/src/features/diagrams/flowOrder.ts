/* Signal-flow order for the schematic walkthrough. Steps follow the
   paper's own connectivity: breadth-first from the input side over
   shared signal nets, so the pulse travels the way the circuit
   actually flows. Deterministic for one IR. */

import type { CircuitIRJson } from "../../lib/types.ts";

/** Nets that carry the walk: globals (supply/ground) would connect
 *  everything to everything, so only signal nets steer the order. */
function walkableNetRoles(): Set<string> {
  return new Set(["signal", "clock", "input", "output"]);
}

/** First net shared by two components: a walkable signal net when one
 *  exists, else any shared net (supply/ground stubs still share copper).
 *  Null when the pair has nothing in common. Powers the walkthrough
 *  tag's "via X" line. */
export function sharedNet(
  circuit: CircuitIRJson,
  fromId: string,
  toId: string,
): string | null {
  const from = circuit.components.find((entry) => entry.id === fromId);
  const to = circuit.components.find((entry) => entry.id === toId);
  if (!from || !to) return null;
  const roleByNet = new Map(circuit.nets.map((net) => [net.id, net.role]));
  const walkable = walkableNetRoles();
  const toNets = new Set(Object.values(to.pins));
  let fallback: string | null = null;
  for (const net of Object.values(from.pins)) {
    if (!toNets.has(net)) continue;
    const role = roleByNet.get(net);
    if (role === undefined || walkable.has(role)) return net;
    fallback ??= net;
  }
  return fallback;
}

export function deriveCircuitSteps(circuit: CircuitIRJson): string[] {
  const roleByNet = new Map(circuit.nets.map((net) => [net.id, net.role]));
  const walkable = walkableNetRoles();
  const isWalkable = (netId: string): boolean => {
    const role = roleByNet.get(netId);
    return role === undefined || walkable.has(role);
  };

  const netsByComponent = new Map<string, string[]>();
  const componentsByNet = new Map<string, string[]>();
  for (const component of circuit.components) {
    const nets = Object.values(component.pins).filter(isWalkable);
    netsByComponent.set(component.id, nets);
    for (const net of nets) {
      const list = componentsByNet.get(net) ?? [];
      list.push(component.id);
      componentsByNet.set(net, list);
    }
  }

  // Seeds: components touching an input net or an input port's net,
  // in IR order. Nothing input-like: start from the first component.
  const inputNets = new Set(
    circuit.nets.filter((net) => net.role === "input").map((net) => net.id),
  );
  for (const port of circuit.ports) {
    if (port.dir === "in") inputNets.add(port.net);
  }
  let seeds = circuit.components
    .filter((component) =>
      Object.values(component.pins).some((net) => inputNets.has(net)),
    )
    .map((component) => component.id);
  if (seeds.length === 0 && circuit.components.length > 0) {
    seeds = [circuit.components[0].id];
  }

  // Breadth-first over shared nets; anything unreachable (supply-only
  // parts, strays) appends in IR order so every step stays clickable.
  const seen = new Set<string>();
  const order: string[] = [];
  const queue = [...seeds];
  while (queue.length > 0) {
    const id = queue.shift();
    if (id === undefined || seen.has(id)) continue;
    seen.add(id);
    order.push(id);
    for (const net of netsByComponent.get(id) ?? []) {
      for (const next of componentsByNet.get(net) ?? []) {
        if (!seen.has(next)) queue.push(next);
      }
    }
  }
  for (const component of circuit.components) {
    if (!seen.has(component.id)) {
      seen.add(component.id);
      order.push(component.id);
    }
  }
  return order;
}
