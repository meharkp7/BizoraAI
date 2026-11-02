import type { CanvasView } from "../../app/routeElements.tsx";
import type {
  CopilotDiagramElement,
  DiagramBlock,
  PaperDiagramsResponse,
} from "../../lib/types.ts";

const ROSTER_LIMIT = 40;

function flattenBlocks(root: DiagramBlock): DiagramBlock[] {
  const out: DiagramBlock[] = [];
  const visit = (block: DiagramBlock): void => {
    out.push(block);
    for (const child of block.children) visit(child);
  };
  visit(root);
  return out;
}

/**
 * List the current tab's diagram elements for the copilot roster.
 * Capped so the request stays small; order matches the IR order.
 */
export function rosterFromDiagrams(
  diagrams: PaperDiagramsResponse | undefined,
  view: CanvasView,
): CopilotDiagramElement[] {
  if (!diagrams) return [];
  if (view === "methodology") {
    return (diagrams.methodology?.nodes ?? []).slice(0, ROSTER_LIMIT).map((node) => ({
      view: "methodology" as const,
      element_id: node.id,
      label: node.label,
      kind: node.kind,
      detail: node.detail,
    }));
  }
  if (view === "schematic") {
    const components = diagrams.circuits.flatMap((circuit) => circuit.components);
    return components.slice(0, ROSTER_LIMIT).map((component) => ({
      view: "schematic" as const,
      element_id: component.id,
      label: component.label,
      kind: component.type,
      detail: component.value,
    }));
  }
  if (!diagrams.structure) return [];
  return flattenBlocks(diagrams.structure.root)
    .slice(0, ROSTER_LIMIT)
    .map((block) => ({
      view: "structure" as const,
      element_id: block.id,
      label: block.label,
      kind: block.kind,
      detail: block.part,
    }));
}
