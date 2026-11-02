import { useParams, useSearchParams } from "react-router";
import { CorrectionPage } from "../features/correction/CorrectionPage.tsx";
import { NotebookPage } from "../features/notebook/NotebookPage.tsx";
import { WorkspacePage } from "../features/workspace/WorkspacePage.tsx";
import { RunDetailPage, RunsPage } from "../features/runs/RunsPage.tsx";
import { TablesPage } from "../features/tables/TablesPage.tsx";

function useGraphParams(): { projectId: string; graphId: string } {
  const { projectId, graphId } = useParams();
  if (!projectId || !graphId) throw new Error("Missing graph route parameters.");
  return { projectId, graphId };
}

export type CanvasView = "methodology" | "schematic" | "3d";

/** Retired view ids and their diagram-engine equivalents. The old
 *  structure/flow editor views map to the methodology flow; floorplan
 *  was physical geometry, now covered by the 3D structure tab. */
const LEGACY_VIEWS: Record<string, CanvasView> = {
  "2d": "methodology",
  process: "methodology",
  structure: "methodology",
  flow: "methodology",
  floorplan: "3d",
};

const CANVAS_VIEWS: ReadonlySet<string> = new Set(["methodology", "schematic", "3d"]);

export function WorkspaceRoute() {
  const { projectId, graphId } = useGraphParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const parsed = Number(searchParams.get("v") ?? "1");
  const version = Number.isInteger(parsed) && parsed >= 1 ? parsed : 1;
  const requested = searchParams.get("view");
  const view: CanvasView =
    requested && CANVAS_VIEWS.has(requested)
      ? (requested as CanvasView)
      : requested && requested in LEGACY_VIEWS
        ? LEGACY_VIEWS[requested]
        : "methodology";

  function updateParams(next: { version?: number; view?: CanvasView }): void {
    const params = new URLSearchParams(searchParams);
    const versionValue = next.version ?? version;
    if (versionValue === 1) {
      params.delete("v");
    } else {
      params.set("v", String(versionValue));
    }
    const viewValue = next.view ?? view;
    if (viewValue === "methodology") {
      params.delete("view");
    } else {
      params.set("view", viewValue);
    }
    void setSearchParams(params);
  }

  return (
    <WorkspacePage
      projectId={projectId}
      graphId={graphId}
      version={version}
      view={view}
      onVersionChange={(nextVersion) => updateParams({ version: nextVersion })}
      onViewChange={(nextView) => updateParams({ view: nextView })}
    />
  );
}

export function RunsRoute() {
  const { projectId, graphId } = useGraphParams();
  return <RunsPage projectId={projectId} graphId={graphId} />;
}

export function NotebookRoute() {
  const { projectId, graphId } = useGraphParams();
  return <NotebookPage projectId={projectId} graphId={graphId} />;
}

export function RunDetailRoute() {
  const { runId } = useParams();
  if (!runId) throw new Error("Missing run route parameter.");
  return <RunDetailPage runId={runId} />;
}

export function TablesRoute() {
  const { projectId, graphId } = useGraphParams();
  return <TablesPage projectId={projectId} graphId={graphId} />;
}

export function CorrectionRoute() {
  const { projectId, graphId } = useGraphParams();
  const [searchParams] = useSearchParams();
  const parsed = Number(searchParams.get("v") ?? "1");
  const version = Number.isInteger(parsed) && parsed >= 1 ? parsed : 1;
  return <CorrectionPage projectId={projectId} graphId={graphId} version={version} />;
}
