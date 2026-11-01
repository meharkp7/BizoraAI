/* A 3D circuit scene derived from a schematic circuit IR: every component
   becomes a clickable part carrying its own figure evidence, so the
   3D tab shows exactly what the schematic would build. Pure
   derivation from endpoint data — no paper-specific constants. The
   root is a cell (not a chip/board), so the engine draws the parts
   with no plate beneath them. */

import type {
  CircuitIRJson,
  StructureIRJson,
} from "../../lib/types.ts";

export function circuitToStructure(circuit: CircuitIRJson): StructureIRJson {
  return {
    version: 1,
    title: circuit.title,
    root: {
      id: `schematic-${circuit.source.figure_id}`,
      label: circuit.title,
      kind: "cell",
      count: null,
      dims: null,
      pos: null,
      part: null,
      tensor_shape: null,
      children: circuit.components.map((component) => ({
        id: component.id,
        label: component.label,
        kind: "part",
        count: null,
        dims: null,
        pos: null,
        // The Inspector shows this as the part's component type.
        part: component.type,
        tensor_shape: null,
        children: [],
        confidence: component.confidence,
        evidence: component.evidence
          ? {
              page: null,
              figure_id: component.evidence.figure_id,
              quote: component.evidence.quote,
            }
          : null,
      })),
      // The grouping adds no uncertainty beyond the parts themselves.
      confidence: 1,
      evidence: {
        page: circuit.source.page,
        figure_id: circuit.source.figure_id,
        quote: null,
      },
    },
  };
}
