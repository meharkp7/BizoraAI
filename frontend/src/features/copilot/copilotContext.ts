import type { CanvasView } from "../../app/routeElements.tsx";
import type { DiagramSelection } from "../diagrams/selection.ts";

export function tabName(view: CanvasView): string {
  return view === "3d" ? "3D" : view;
}

/** One short line telling the model which tab and selection the user sees. */
export function diagramContextFor(
  view: CanvasView,
  selection: DiagramSelection | null,
  graphSelection: { id: string; label: string } | null,
): string {
  const viewing = `viewing ${tabName(view)} tab`;
  if (selection) {
    return `${viewing}; diagram selection ${selection.elementId} (${selection.label})`;
  }
  if (graphSelection) {
    return `${viewing}; graph selection ${graphSelection.id} (${graphSelection.label})`;
  }
  return viewing;
}
