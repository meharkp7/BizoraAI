/* What a diagram click hands to the Inspector: the clicked element
   plus the paper evidence behind it. */

import type {
  DiagramBlock,
  DiagramComponent,
  DiagramNode,
} from "../../lib/types.ts";
import type { DiagramProvenance } from "./provenance.ts";
import { elementProvenance } from "./provenance.ts";

export type DiagramViewKind = "methodology" | "schematic" | "structure";

export interface DiagramSelectionEvidence {
  figure_id: string | null;
  page: number | null;
  quote: string | null;
  /** Normalized 0..100 figure box; circuits only, otherwise null. */
  bbox: [number, number, number, number] | null;
}

export interface DiagramSelection {
  view: DiagramViewKind;
  elementId: string;
  label: string;
  kind: string | null;
  detail: string | null;
  confidence: number | null;
  provenance: DiagramProvenance;
  evidence: DiagramSelectionEvidence | null;
  extra: { label: string; value: string }[];
}

export function methodologySelection(node: DiagramNode): DiagramSelection {
  const params = Object.entries(node.params).map(([key, value]) => ({
    label: key,
    value: typeof value === "string" || typeof value === "number" ? String(value) : JSON.stringify(value),
  }));
  return {
    view: "methodology",
    elementId: node.id,
    label: node.label,
    kind: node.kind,
    detail: node.detail,
    confidence: node.confidence,
    provenance: elementProvenance(node.evidence, node.confidence),
    evidence: node.evidence
      ? {
          figure_id: node.evidence.figure_id,
          page: node.evidence.page,
          quote: node.evidence.quote,
          bbox: null,
        }
      : null,
    extra: params,
  };
}

export function schematicSelection(
  component: DiagramComponent,
  netLabels: ReadonlyMap<string, string>,
): DiagramSelection {
  const extra: { label: string; value: string }[] = [];
  if (component.value) extra.push({ label: "Value", value: component.value });
  for (const [pin, net] of Object.entries(component.pins)) {
    extra.push({ label: `Pin ${pin}`, value: netLabels.get(net) ?? net });
  }
  return {
    view: "schematic",
    elementId: component.id,
    label: component.label,
    kind: component.type,
    detail: null,
    confidence: component.confidence,
    provenance: elementProvenance(component.evidence, component.confidence),
    evidence: component.evidence
      ? {
          figure_id: component.evidence.figure_id,
          page: null,
          quote: component.evidence.quote,
          bbox: component.evidence.bbox,
        }
      : null,
    extra,
  };
}

function blockCountLabel(block: DiagramBlock): string | null {
  if (block.count === null || block.count === undefined) return null;
  if (typeof block.count === "number") return `x${block.count}`;
  return `${block.count.rows} x ${block.count.cols}`;
}

export function structureSelection(
  block: DiagramBlock,
  instanceId: string | null = null,
): DiagramSelection {
  const extra: { label: string; value: string }[] = [];
  const count = blockCountLabel(block);
  if (count) extra.push({ label: "Count", value: count });
  if (block.dims) {
    const dims = ["w", "h", "d"]
      .map((axis) => {
        const value = block.dims?.[axis as "w" | "h" | "d"] ?? null;
        return value === null ? null : `${axis} ${value}`;
      })
      .filter((part): part is string => part !== null);
    if (dims.length > 0) {
      extra.push({
        label: "Dimensions",
        value: `${dims.join(" · ")}${block.dims.unit ? ` (${block.dims.unit})` : ""}`,
      });
    }
  }
  if (block.part) extra.push({ label: "Part", value: block.part });
  if (block.tensor_shape) extra.push({ label: "Tensor shape", value: `[${block.tensor_shape.join(" x ")}]` });
  return {
    view: "structure",
    elementId: instanceId ?? block.id,
    label: instanceId && instanceId !== block.id ? `${block.label} ${instanceId.slice(block.id.length)}` : block.label,
    kind: block.kind,
    detail: null,
    confidence: block.confidence,
    provenance: elementProvenance(block.evidence, block.confidence),
    evidence: block.evidence
      ? {
          figure_id: block.evidence.figure_id,
          page: block.evidence.page,
          quote: block.evidence.quote,
          bbox: null,
        }
      : null,
    extra,
  };
}

/** Scene mesh ids for array cells look like "arr[0,2]"; map one back
 *  to its repeated block. Returns the block id, or the id unchanged. */
export function sceneIdToBlockId(sceneId: string): string {
  const bracket = sceneId.indexOf("[");
  return bracket === -1 ? sceneId : sceneId.slice(0, bracket);
}

export function findBlock(root: DiagramBlock, blockId: string): DiagramBlock | null {
  if (root.id === blockId) return root;
  for (const child of root.children) {
    const found = findBlock(child, blockId);
    if (found) return found;
  }
  return null;
}
