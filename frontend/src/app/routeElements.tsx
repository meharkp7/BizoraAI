import { useParams, useSearchParams } from "react-router";
import { WorkspacePage } from "../features/workspace/WorkspacePage.tsx";
import { RunDetailPage, RunsPage } from "../features/runs/RunsPage.tsx";
import { TablesPage } from "../features/tables/TablesPage.tsx";

function useGraphParams(): { projectId: string; graphId: string } {
  const { projectId, graphId } = useParams();
  if (!projectId || !graphId) throw new Error("Missing graph route parameters.");
  return { projectId, graphId };
}

export type CanvasView = "2d" | "3d";

export function WorkspaceRoute() {
  const { projectId, graphId } = useGraphParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const parsed = Number(searchParams.get("v") ?? "1");
  const version = Number.isInteger(parsed) && parsed >= 1 ? parsed : 1;
  const view: CanvasView = searchParams.get("view") === "3d" ? "3d" : "2d";

  function updateParams(next: { version?: number; view?: CanvasView }): void {
    const params = new URLSearchParams(searchParams);
    const versionValue = next.version ?? version;
    if (versionValue === 1) {
      params.delete("v");
    } else {
      params.set("v", String(versionValue));
    }
    const viewValue = next.view ?? view;
    if (viewValue === "2d") {
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

export function RunDetailRoute() {
  const { runId } = useParams();
  if (!runId) throw new Error("Missing run route parameter.");
  return <RunDetailPage runId={runId} />;
}

export function TablesRoute() {
  const { projectId, graphId } = useGraphParams();
  return <TablesPage projectId={projectId} graphId={graphId} />;
}
