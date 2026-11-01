import type { CircuitIR, MethodologyIR, StructureIR, ValidationResult } from './ir.js';
import { validateCircuit, validateMethodology, validateStructure } from './validate.js';
import { renderSchematic, type SchematicOptions } from './schematic.js';
import { renderMethodology, type MethodologyOptions } from './methodology.js';
import { renderStructureIso, buildStructureScene, type Scene } from './structure.js';

export * from './ir.js';
export * from './validate.js';
export { renderSchematic, renderMethodology, renderStructureIso, buildStructureScene };
export type { Scene };
export { dark, light } from './theme.js';

/** "Safe" entry points: the engine never invents content. If the IR is invalid or too thin to be a real diagram,
 *  it returns ok:false and the app must show the paper's own figure (with overlays) instead of a made-up picture. */
export type Safe<T> = { ok: true; validation: ValidationResult } & T | { ok: false; reason: string; validation: ValidationResult };

export function renderCircuitSafe(ir: CircuitIR, o?: SchematicOptions): Safe<{ svg: string }> {
  const v = validateCircuit(ir);
  if (v.errors.length) return { ok: false, reason: `circuit IR invalid: ${v.errors[0].message}`, validation: v };
  if (ir.components.length < 2) return { ok: false, reason: 'too few components to draw a schematic', validation: v };
  return { ok: true, validation: v, svg: renderSchematic(ir, o).svg };
}
export function renderMethodologySafe(ir: MethodologyIR, o?: MethodologyOptions): Safe<{ svg: string }> {
  const v = validateMethodology(ir);
  if (v.errors.length) return { ok: false, reason: `methodology IR invalid: ${v.errors[0].message}`, validation: v };
  if (ir.nodes.length < 3 || ir.edges.length < 2) return { ok: false, reason: 'too little structure to draw a flow diagram', validation: v };
  return { ok: true, validation: v, svg: renderMethodology(ir, o).svg };
}
export function buildStructureSafe(ir: StructureIR): Safe<{ scene: Scene }> {
  const v = validateStructure(ir);
  if (v.errors.length) return { ok: false, reason: `structure IR invalid: ${v.errors[0].message}`, validation: v };
  const scene = buildStructureScene(ir);
  if (scene.boxes.length < 2) return { ok: false, reason: 'no physical structure could be built from this IR', validation: v };
  return { ok: true, validation: v, scene };
}
