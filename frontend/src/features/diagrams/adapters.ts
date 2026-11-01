/* Backend diagram JSON -> engine IR normalization plus the Safe
   render entry points used by the canvas views. The engine is never
   fed fixtures or invented content: every IR here arrives from
   GET /papers/{paper_id}/diagrams. */

import {
  buildStructureSafe,
  dark,
  renderCircuitSafe,
  renderMethodologySafe,
} from "../../diagram-engine/index.js";
import type {
  Block,
  CircuitIR,
  MethodologyIR,
  Side,
  StructureIR,
} from "../../diagram-engine/index.js";
import type { MethodologyOptions } from "../../diagram-engine/methodology.js";
import type { SchematicOptions } from "../../diagram-engine/schematic.js";
import type {
  CircuitIRJson,
  DiagramBlock,
  DiagramComponent,
  DiagramNode,
  DiagramTextEvidence,
  MethodologyIRJson,
  StructureIRJson,
} from "../../lib/types.ts";
import { fitMethodologySvg, markWhatIfNodes } from "./methodologySvg.ts";

function defined<T>(value: T | null | undefined): T | undefined {
  return value ?? undefined;
}

function normalizeParams(params: Record<string, unknown>): Record<string, string | number> {
  const out: Record<string, string | number> = {};
  for (const [key, value] of Object.entries(params)) {
    if (typeof value === "string" || typeof value === "number") {
      out[key] = value;
    } else if (typeof value === "boolean") {
      out[key] = value ? "true" : "false";
    } else if (value === null || value === undefined) {
      out[key] = "null";
    } else {
      out[key] = JSON.stringify(value);
    }
  }
  return out;
}

function normalizeTextEvidence(
  evidence: DiagramTextEvidence | null,
): MethodologyIR["nodes"][number]["evidence"] {
  if (!evidence) return undefined;
  const out = {
    page: defined(evidence.page),
    figure_id: defined(evidence.figure_id),
    quote: defined(evidence.quote),
  };
  return out.page === undefined && out.figure_id === undefined && out.quote === undefined
    ? undefined
    : out;
}

export function normalizeMethodologyIR(ir: MethodologyIRJson): MethodologyIR {
  return {
    version: 1,
    title: ir.title,
    groups: ir.groups.map((group) => ({
      id: group.id,
      label: group.label,
      parent: defined(group.parent),
    })),
    nodes: ir.nodes.map(
      (node: DiagramNode): MethodologyIR["nodes"][number] => ({
        id: node.id,
        label: node.label,
        kind: node.kind,
        group: defined(node.group),
        detail: defined(node.detail),
        params: normalizeParams(node.params),
        confidence: node.confidence,
        evidence: normalizeTextEvidence(node.evidence),
      }),
    ),
    edges: ir.edges.map((edge) => ({
      from: edge.from,
      to: edge.to,
      label: defined(edge.label),
      kind: edge.kind as MethodologyIR["edges"][number]["kind"],
    })),
  };
}

export function normalizeCircuitIR(ir: CircuitIRJson): CircuitIR {
  return {
    version: 1,
    title: ir.title,
    source: { figure_id: ir.source.figure_id, page: ir.source.page },
    components: ir.components.map(
      (component: DiagramComponent): CircuitIR["components"][number] => ({
        id: component.id,
        type: component.type,
        label: component.label,
        value: defined(component.value),
        pins: { ...component.pins },
        placement: component.placement
          ? {
              x: component.placement.x,
              y: component.placement.y,
              rot: component.placement.rot,
              mirror: component.placement.mirror,
              flip: component.placement.flip,
            }
          : undefined,
        pin_sides: (component.pin_sides ?? undefined) as
          | Record<string, Side>
          | undefined,
        confidence: component.confidence,
        evidence: component.evidence
          ? {
              figure_id: component.evidence.figure_id,
              bbox: component.evidence.bbox ? [...component.evidence.bbox] as [number, number, number, number] : undefined,
              quote: defined(component.evidence.quote),
            }
          : undefined,
      }),
    ),
    nets: ir.nets.map((net) => ({
      id: net.id,
      label: net.label,
      role: net.role as CircuitIR["nets"][number]["role"],
      global: net.global,
    })),
    ports: ir.ports.map((port) => ({
      id: port.id,
      net: port.net,
      label: port.label,
      dir: port.dir as CircuitIR["ports"] extends (infer P)[] | undefined ? P extends { dir?: infer D } ? D : never : never,
      side: port.side as CircuitIR["ports"] extends (infer P)[] | undefined ? P extends { side?: infer S } ? S : never : never,
      placement: port.placement ? { x: port.placement.x, y: port.placement.y } : undefined,
    })),
    subcircuits: ir.subcircuits.map((sub) => ({
      id: sub.id,
      label: sub.label,
      component_ids: [...sub.component_ids],
    })),
    layout: ir.layout ? { unit: defined(ir.layout.unit) } : undefined,
  };
}

function normalizeBlock(block: DiagramBlock): Block {
  return {
    id: block.id,
    label: block.label,
    kind: block.kind,
    count: (block.count ?? undefined) as Block["count"],
    dims: block.dims
      ? {
          w: defined(block.dims.w),
          h: defined(block.dims.h),
          d: defined(block.dims.d),
          unit: defined(block.dims.unit),
        }
      : undefined,
    pos: (block.pos ?? undefined) as Block["pos"],
    part: defined(block.part),
    tensor_shape: block.tensor_shape ? [...block.tensor_shape] : undefined,
    children: block.children.map(normalizeBlock),
    confidence: block.confidence,
    evidence: normalizeTextEvidence(block.evidence),
  };
}

export function normalizeStructureIR(ir: StructureIRJson): StructureIR {
  return { version: 1, title: ir.title, root: normalizeBlock(ir.root) };
}

/** True when every component carries paper placement, so the engine
 *  keeps the paper's own layout instead of its weaker auto-layout. */
export function circuitHasPaperLayout(ir: CircuitIRJson): boolean {
  return ir.components.length > 0 && ir.components.every((c) => c.placement !== null);
}

export function renderMethodologyDiagram(
  ir: MethodologyIRJson,
  options?: MethodologyOptions,
) {
  const result = renderMethodologySafe(normalizeMethodologyIR(ir), options);
  if (!result.ok) return result;
  return {
    ...result,
    svg: markWhatIfNodes(fitMethodologySvg(result.svg, ir.nodes), ir.nodes),
  };
}

export function renderCircuitDiagram(ir: CircuitIRJson, options?: SchematicOptions) {
  const result = renderCircuitSafe(normalizeCircuitIR(ir), options);
  if (!result.ok) return result;
  // Net labels sit on wires: outline every label with the background
  // so nets, pins, and ports stay readable (the engine files stay
  // untouched; this presentation rule lives in the app layer).
  const bg = options?.theme?.bg ?? dark.bg;
  const halo =
    `<style>.net,.lbl,.pin,.port-lbl{paint-order:stroke;stroke:${bg};` +
    `stroke-width:3.2px;stroke-linejoin:round}.net{font-size:11px}</style>`;
  return { ...result, svg: result.svg.replace("</svg>", `${halo}</svg>`) };
}

export function renderStructureDiagram(ir: StructureIRJson) {
  return buildStructureSafe(normalizeStructureIR(ir));
}
