import { useParams, useSearchParams } from "react-router";
import { WorkspacePage } from "../features/workspace/WorkspacePage.tsx";
import { RunDetailPage, RunsPage } from "../features/runs/RunsPage.tsx";

function useGraphParams(): { projectId: string; graphId: string } {
  const { projectId, graphId } = useParams();
  if (!projectId || !graphId) throw new Error("Missing graph route parameters.");
  return { projectId, graphId };
}

export function WorkspaceRoute() {
  const { projectId, graphId } = useGraphParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const parsed = Number(searchParams.get("v") ?? "1");
  const version = Number.isInteger(parsed) && parsed >= 1 ? parsed : 1;

  return (
    <WorkspacePage
      projectId={projectId}
      graphId={graphId}
      version={version}
      onVersionChange={(next) => {
        void setSearchParams(next === 1 ? {} : { v: String(next) });
      }}
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
