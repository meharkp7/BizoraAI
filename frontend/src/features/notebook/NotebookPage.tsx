import { useMemo } from "react";
import { Link } from "react-router";
import {
  useGraphRevision,
  usePaperNotes,
  useRevisionList,
  useRunMetrics,
  useRuns,
} from "../../app/queries.ts";
import { EmptyState, ErrorState, LoadingState } from "../../components/states.tsx";
import type { ExperimentRun, PaperNote } from "../../lib/types.ts";
import styles from "./NotebookPage.module.css";

/** Experiment notebook: one graph's revisions, runs with metrics, and paper notes. */
export function NotebookPage({
  projectId,
  graphId,
}: {
  projectId: string;
  graphId: string;
}) {
  const revisions = useRevisionList(projectId, graphId);
  const runs = useRuns({ project_id: projectId, graph_id: graphId, limit: 100 });
  const latestVersion = revisions.data?.at(-1)?.version;
  const head = useGraphRevision(projectId, graphId, latestVersion ?? 0, revisions.isSuccess);
  const paperId = head.data?.source_ids[0] ?? null;
  const notes = usePaperNotes(paperId, head.isSuccess);

  const markdown = useMemo(
    () =>
      buildMarkdown({
        projectId,
        graphId,
        title: revisions.data?.at(-1)?.title ?? graphId,
        revisions: revisions.data ?? [],
        runs: runs.data ?? [],
        notes: notes.data ?? [],
      }),
    [projectId, graphId, revisions.data, runs.data, notes.data],
  );

  if (revisions.isPending || runs.isPending) {
    return <LoadingState label="Loading notebook…" />;
  }
  if (revisions.isError) {
    return (
      <ErrorState
        title="Could not load the notebook."
        detail={revisions.error instanceof Error ? revisions.error.message : undefined}
        onRetry={() => void revisions.refetch()}
      />
    );
  }
  if (runs.isError) {
    return (
      <ErrorState
        title="Could not load the notebook runs."
        detail={runs.error instanceof Error ? runs.error.message : undefined}
        onRetry={() => void runs.refetch()}
      />
    );
  }

  function download(): void {
    const blob = new Blob([markdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `notebook-${graphId}.md`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className={`bz-enter ${styles.page}`}>
      <div className={styles.head}>
        <div>
          <h1>Notebook</h1>
          <p className={styles.sub}>
            {revisions.data.at(-1)?.title ?? graphId} · {revisions.data.length}{" "}
            {revisions.data.length === 1 ? "revision" : "revisions"} · {runs.data.length}{" "}
            {runs.data.length === 1 ? "run" : "runs"}
          </p>
        </div>
        <button type="button" onClick={download}>
          Export Markdown
        </button>
      </div>

      <section className={styles.section} aria-label="Revision history">
        <h2>Revisions</h2>
        {revisions.data.length === 0 ? (
          <EmptyState title="No revisions yet." />
        ) : (
          <ol className={styles.list}>
            {[...revisions.data].reverse().map((row) => (
              <li key={row.version}>
                <span className={styles.version}>v{row.version}</span>{" "}
                <span>{row.title}</span>{" "}
                <span className={styles.meta}>
                  <span className="mono">{row.created_by}</span> ·{" "}
                  {formatTimestamp(row.created_at)}
                </span>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section className={styles.section} aria-label="Experiment runs">
        <h2>Runs</h2>
        {runs.data.length === 0 ? (
          <EmptyState
            title="No runs yet."
            detail="Run the current revision from the workspace to verify estimates with measured results."
          />
        ) : (
          <ol className={styles.list}>
            {runs.data.map((run) => (
              <RunRow key={run.run_id} projectId={projectId} graphId={graphId} run={run} />
            ))}
          </ol>
        )}
      </section>

      <section className={styles.section} aria-label="Paper notes">
        <h2>Notes</h2>
        {notes.isPending ? (
          <LoadingState label="Loading notes…" />
        ) : notes.isError || paperId === null ? (
          <EmptyState
            title="No notes linked."
            detail="This graph is not linked to a paper with notes."
          />
        ) : notes.data.length === 0 ? (
          <EmptyState title="No notes yet." />
        ) : (
          <ol className={styles.list}>
            {notes.data.map((note) => (
              <li key={note.id}>
                <p className={styles.note}>{note.body}</p>
                <span className={styles.meta}>{formatTimestamp(note.updated_at)}</span>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}

function RunRow({
  projectId,
  graphId,
  run,
}: {
  projectId: string;
  graphId: string;
  run: ExperimentRun;
}) {
  const metrics = useRunMetrics(run.run_id, run.state === "succeeded");
  return (
    <li>
      <div className={styles.runHead}>
        <Link
          to={`/g/${encodeURIComponent(projectId)}/${encodeURIComponent(graphId)}/runs/${encodeURIComponent(run.run_id)}`}
          className="mono"
        >
          {run.run_id}
        </Link>
        <span className={styles.meta}>
          {run.config.adapter_id} · {run.state}
        </span>
      </div>
      {run.state === "succeeded" ? (
        metrics.isPending ? (
          <span className={styles.meta}>Loading metrics…</span>
        ) : metrics.isError || (metrics.data ?? []).length === 0 ? (
          <span className={styles.meta}>No metrics recorded.</span>
        ) : (
          <ul className={styles.metrics}>
            {(metrics.data ?? []).map((metric) => (
              <li key={metric.metric_id}>
                <span className="mono">
                  {metric.name} = {metric.value}
                </span>{" "}
                <span className={styles.meta}>({metric.result_kind})</span>
              </li>
            ))}
          </ul>
        )
      ) : run.error ? (
        <span className={styles.meta}>{run.error}</span>
      ) : null}
    </li>
  );
}

function formatTimestamp(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

export function buildMarkdown({
  projectId,
  graphId,
  title,
  revisions,
  runs,
  notes,
}: {
  projectId: string;
  graphId: string;
  title: string;
  revisions: { version: number; title: string; created_by: string; created_at: string }[];
  runs: ExperimentRun[];
  notes: PaperNote[];
}): string {
  const lines = [
    `# Notebook: ${title}`,
    "",
    `Project ${projectId}, graph ${graphId}.`,
    "",
    "## Revisions",
    "",
  ];
  if (revisions.length === 0) {
    lines.push("No revisions yet.", "");
  } else {
    for (const row of [...revisions].reverse()) {
      lines.push(`- v${row.version} ${row.title} (${row.created_by}, ${row.created_at})`);
    }
    lines.push("");
  }
  lines.push("## Runs", "");
  if (runs.length === 0) {
    lines.push("No runs yet.", "");
  } else {
    for (const run of runs) {
      lines.push(`- ${run.run_id}: ${run.config.adapter_id}, ${run.state}`);
    }
    lines.push("");
  }
  lines.push("## Notes", "");
  if (notes.length === 0) {
    lines.push("No notes yet.", "");
  } else {
    for (const note of notes) {
      lines.push(`- ${note.body} (${note.updated_at})`);
    }
    lines.push("");
  }
  return lines.join("\n");
}
