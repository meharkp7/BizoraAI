import { useEffect } from "react";
import { useMatch, useParams } from "react-router";
import { useGraphRevision, useRevisionList } from "../../app/queries.ts";
import { CopilotBot } from "./CopilotBot.tsx";

const STORAGE_KEY = "bizora.siteAgent.graph";

interface GraphRef {
  projectId: string;
  graphId: string;
}

function loadGraphRef(): GraphRef | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (
      typeof parsed === "object" &&
      parsed !== null &&
      typeof (parsed as GraphRef).projectId === "string" &&
      typeof (parsed as GraphRef).graphId === "string"
    ) {
      return {
        projectId: (parsed as GraphRef).projectId,
        graphId: (parsed as GraphRef).graphId,
      };
    }
  } catch {
    // Corrupt or unavailable storage: no recent graph.
  }
  return null;
}

/**
 * The site-wide agent: the same floating bot on every page except the
 * workspace canvas, which mounts its own with live diagram context.
 * On graph sub-pages (runs, tables, notebook) it chats about that
 * graph; elsewhere it keeps the most recent graph. Proposals stay
 * visible but apply from the workspace.
 */
export function SiteAgent() {
  const { projectId, graphId } = useParams();
  const onWorkspace = useMatch("g/:projectId/:graphId");
  const onLogin = useMatch("login");

  useEffect(() => {
    if (!projectId || !graphId) return;
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ projectId, graphId }));
    } catch {
      // Private mode: the graph just doesn't persist.
    }
  }, [projectId, graphId]);

  // The fallback reads straight from storage every render: visits persist
  // through the effect above, so this is current without render-effect
  // state ping-pong, within and across sessions.
  const live = projectId && graphId ? { projectId, graphId } : null;
  const target = live ?? loadGraphRef();
  const history = useRevisionList(
    target?.projectId ?? "",
    target?.graphId ?? "",
    target !== null,
  );
  const latest = (history.data ?? []).reduce(
    (max, entry) => Math.max(max, entry.version),
    0,
  );
  const revision = useGraphRevision(
    target?.projectId ?? "",
    target?.graphId ?? "",
    latest,
    target !== null && latest > 0,
  );

  if (onWorkspace || onLogin || !target || !revision.data) return null;
  return (
    <CopilotBot
      key={`${target.projectId}::${target.graphId}`}
      projectId={target.projectId}
      graph={revision.data}
      disabled
      view="methodology"
      selection={null}
      onSubmit={() => {}}
      detached
    />
  );
}
