import type { CircuitIR, MethodologyIR, StructureIR, Block, ValidationResult, Issue } from './ir.js';

export const REQUIRED_PINS: Record<string, string[]> = {
  nmos: ['d', 'g', 's'], pmos: ['d', 'g', 's'], resistor: ['a', 'b'], capacitor: ['a', 'b'], inductor: ['a', 'b'],
  diode: ['a', 'k'], vsource: ['p', 'n'], isource: ['p', 'n'], ground: ['g'], inverter: ['in', 'out'], buffer: ['in', 'out'],
  amp: ['inp', 'inn', 'out'], comparator: ['inp', 'inn', 'out'],
};
export const OPTIONAL_PINS: Record<string, string[]> = { nmos: ['b'], pmos: ['b'] };

const mk = (): ValidationResult => ({ errors: [], warnings: [], stats: {} });
const err = (r: ValidationResult, code: string, message: string, ref?: string) => r.errors.push({ code, message, ref } as Issue);
const warn = (r: ValidationResult, code: string, message: string, ref?: string) => r.warnings.push({ code, message, ref } as Issue);

export function validateCircuit(ir: CircuitIR): ValidationResult {
  const r = mk();
  const compIds = new Set<string>(); const netIds = new Set<string>(ir.nets.map((n) => n.id));
  if (netIds.size !== ir.nets.length) err(r, 'dup_net', 'duplicate net ids');
  const conn = new Map<string, number>();
  let nmos = 0, pmos = 0;
  for (const c of ir.components) {
    if (compIds.has(c.id)) err(r, 'dup_component', `duplicate component id ${c.id}`, c.id);
    compIds.add(c.id);
    if (c.type === 'nmos') nmos++; if (c.type === 'pmos') pmos++;
    const req = REQUIRED_PINS[c.type];
    if (!req && c.type !== 'block') warn(r, 'unknown_type', `unknown type "${c.type}" drawn as a generic block`, c.id);
    for (const p of req ?? []) if (!(p in c.pins)) err(r, 'missing_pin', `${c.id} (${c.type}) is missing required pin ${p}`, c.id);
    const allowed = new Set([...(req ?? []), ...(OPTIONAL_PINS[c.type] ?? [])]);
    for (const [pin, net] of Object.entries(c.pins)) {
      if (!netIds.has(net)) err(r, 'bad_net_ref', `${c.id}.${pin} references unknown net "${net}"`, c.id);
      else conn.set(net, (conn.get(net) ?? 0) + 1);
      if (req && !allowed.has(pin)) warn(r, 'unknown_pin', `${c.id} has non-standard pin "${pin}" for ${c.type}`, c.id);
    }
    if ((c.confidence ?? 1) < 0.5) warn(r, 'low_confidence', `${c.id} has low confidence (${c.confidence})`, c.id);
  }
  for (const p of ir.ports ?? []) {
    if (!netIds.has(p.net)) err(r, 'bad_port_net', `port ${p.id} references unknown net ${p.net}`, p.id);
    else conn.set(p.net, (conn.get(p.net) ?? 0) + 1);
  }
  for (const n of ir.nets) {
    const k = conn.get(n.id) ?? 0;
    const isGlobal = n.global || n.role === 'supply' || n.role === 'ground';
    if (k === 0) warn(r, 'unused_net', `net ${n.id} is not connected to anything`, n.id);
    else if (k < 2 && !isGlobal) warn(r, 'dangling_net', `net ${n.id} has only one connection`, n.id);
  }
  if (!ir.nets.some((n) => n.role === 'supply' || n.role === 'ground'))
    warn(r, 'no_supply', 'no supply or ground net declared');
  r.stats = { components: ir.components.length, nets: ir.nets.length, nmos, pmos, ports: ir.ports?.length ?? 0 };
  return r;
}

export function validateMethodology(ir: MethodologyIR): ValidationResult {
  const r = mk();
  const ids = new Set<string>();
  for (const n of ir.nodes) { if (ids.has(n.id)) err(r, 'dup_node', `duplicate node id ${n.id}`, n.id); ids.add(n.id); }
  const gids = new Set((ir.groups ?? []).map((g) => g.id));
  for (const g of ir.groups ?? []) if (g.parent && !gids.has(g.parent)) err(r, 'bad_group_parent', `group ${g.id} parent ${g.parent} missing`, g.id);
  for (const n of ir.nodes) {
    if (n.group && !gids.has(n.group)) err(r, 'bad_group', `node ${n.id} references unknown group ${n.group}`, n.id);
    if (!n.evidence) warn(r, 'no_evidence', `node ${n.id} has no evidence`, n.id);
  }
  const used = new Set<string>();
  for (const e of ir.edges) {
    if (!ids.has(e.from)) err(r, 'bad_edge', `edge from unknown node ${e.from}`);
    if (!ids.has(e.to)) err(r, 'bad_edge', `edge to unknown node ${e.to}`);
    used.add(e.from); used.add(e.to);
  }
  for (const n of ir.nodes) if (!used.has(n.id) && ir.nodes.length > 1) warn(r, 'orphan', `node ${n.id} has no edges`, n.id);
  r.stats = { nodes: ir.nodes.length, edges: ir.edges.length, groups: gids.size };
  return r;
}

export function validateStructure(ir: StructureIR): ValidationResult {
  const r = mk(); let blocks = 0; const ids = new Set<string>();
  const walk = (b: Block) => {
    blocks++;
    if (ids.has(b.id)) err(r, 'dup_block', `duplicate block id ${b.id}`, b.id); ids.add(b.id);
    if (b.count !== undefined) {
      const c = typeof b.count === 'number' ? [b.count] : [b.count.rows, b.count.cols];
      if (c.some((v) => !Number.isInteger(v) || v < 1)) err(r, 'bad_count', `${b.id} has a non-positive or non-integer count`, b.id);
    }
    for (const k of ['w', 'h', 'd'] as const) { const v = b.dims?.[k]; if (v !== undefined && !(v > 0)) err(r, 'bad_dims', `${b.id}.dims.${k} must be > 0`, b.id); }
    if (b.kind === 'array' && !(b.children && b.children.length >= 1)) err(r, 'array_without_cell', `array ${b.id} needs a repeated child (the cell)`, b.id);
    (b.children ?? []).forEach(walk);
  };
  walk(ir.root);
  r.stats = { blocks };
  return r;
}
