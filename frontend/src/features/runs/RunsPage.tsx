import { Link } from "react-router";
import { useExecuteRun, useRun, useRunArtifacts, useRunMetrics, useRuns } from "../../app/queries.ts";
import { BizoraApiError } from "../../lib/api.ts";
import type { RunState } from "../../lib/types.ts";
import { EmptyState, ErrorState, LoadingState } from "../../components/states.tsx";
import styles from "./RunsPage.module.css";

function StateBadge({ state }: { state: RunState }) {
  return (
    <span className={`${styles.badge} ${styles[state]}`} aria-label={`state: ${state}`}>
      {state}
    </span>
  );
}

export function RunsPage({ projectId, graphId }: { projectId: string; graphId: string }) {
  const runs = useRuns({ project_id: projectId, graph_id: graphId });
  const executeRun = useExecuteRun();

  if (runs.isPending) return <LoadingState label="Loading runs…" />;
  if (runs.isError) {
    return (
      <ErrorState
        title="Could not load runs."
        detail={runs.error instanceof Error ? runs.error.message : undefined}
        onRetry={() => void runs.refetch()}
      />
    );
  }
  if (runs.data.length === 0) {
    return (
      <EmptyState
        title="No runs yet."
        detail="Run the current revision from the workspace to see measured results here."
      />
    );
  }

  return (
    <div className={styles.page}>
      <h1>Runs</h1>
      <ul className={styles.list}>
        {runs.data.map((run) => (
          <li key={run.run_id} className={styles.card}>
            <div className={styles.head}>
              <Link
                to={`/g/${encodeURIComponent(projectId)}/${encodeURIComponent(graphId)}/runs/${encodeURIComponent(run.run_id)}`}
                className={`mono ${styles.runLink}`}
              >
                {run.run_id}
              </Link>
              <StateBadge state={run.state} />
              {run.state === "pending" || run.state === "failed" ? (
                <button
                  type="button"
                  disabled={executeRun.isPending}
                  onClick={() => executeRun.mutate(run.run_id)}
                >
                  {executeRun.isPending && executeRun.variables === run.run_id
                    ? "Executing…"
                    : "Execute"}
                </button>
              ) : null}
            </div>
            <dl className={styles.facts}>
              <dt>Experiment</dt>
              <dd className="mono">{run.config.experiment_id}</dd>
              <dt>Graph</dt>
              <dd>
                <span className="mono">{run.config.graph_id}</span> v{run.config.graph_version}
              </dd>
              <dt>Adapter</dt>
              <dd className="mono">
                {run.config.adapter_id} {run.config.adapter_version}
              </dd>
              <dt>Seed</dt>
              <dd className="mono">{run.config.seed}</dd>
            </dl>
            {run.error ? <p className={styles.runError}>{run.error}</p> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function RunDetailPage({ runId }: { runId: string }) {
  const run = useRun(runId);
  const metrics = useRunMetrics(runId, run.data?.state === "succeeded");
  const artifacts = useRunArtifacts(runId, run.data?.state === "succeeded");
  const executeRun = useExecuteRun();

  if (run.isPending) return <LoadingState label="Loading run…" />;
  if (run.isError) {
    const notFound = run.error instanceof BizoraApiError && run.error.isNotFound;
    return (
      <ErrorState
        title={notFound ? "Run not found." : "Could not load the run."}
        detail={notFound ? undefined : run.error instanceof Error ? run.error.message : undefined}
        onRetry={() => void run.refetch()}
      />
    );
  }

  const data = run.data;
  return (
    <div className={styles.page}>
      <div className={styles.detailHead}>
        <h1 className="mono">{data.run_id}</h1>
        <StateBadge state={data.state} />
        {data.state === "pending" || data.state === "failed" ? (
          <button
            type="button"
            disabled={executeRun.isPending}
            onClick={() => executeRun.mutate(data.run_id)}
          >
            {executeRun.isPending ? "Executing…" : "Execute"}
          </button>
        ) : null}
      </div>
      {data.error ? (
        <div className={styles.alert} role="alert">
          {data.error}
        </div>
      ) : null}

      <section className={styles.section} aria-label="Run record">
        <h2>Run record</h2>
        <dl className={styles.facts}>
          <dt>Experiment</dt>
          <dd className="mono">{data.config.experiment_id}</dd>
          <dt>Graph</dt>
          <dd>
            <span className="mono">{data.config.graph_id}</span> v{data.config.graph_version}
          </dd>
          <dt>Adapter</dt>
          <dd className="mono">
            {data.config.adapter_id} {data.config.adapter_version}
          </dd>
          <dt>Seed</dt>
          <dd className="mono">{data.config.seed}</dd>
          <dt>Dataset</dt>
          <dd className="mono">
            {data.config.dataset_id} {data.config.dataset_revision}
          </dd>
          <dt>Code revision</dt>
          <dd className="mono">{data.config.code_revision}</dd>
          <dt>Created</dt>
          <dd className="mono">{data.created_at}</dd>
          <dt>Started</dt>
          <dd className="mono">{data.started_at ?? "—"}</dd>
          <dt>Finished</dt>
          <dd className="mono">{data.finished_at ?? "—"}</dd>
        </dl>
      </section>

      <section className={styles.section} aria-label="Metrics">
        <h2>Metrics</h2>
        {metrics.isPending ? (
          <LoadingState label="Loading metrics…" />
        ) : metrics.isError ? (
          <ErrorState
            title="Could not load metrics."
            detail={metrics.error instanceof Error ? metrics.error.message : undefined}
            onRetry={() => void metrics.refetch()}
          />
        ) : metrics.data.length === 0 ? (
          <EmptyState
            title="No metrics recorded."
            detail={
              data.state === "succeeded"
                ? "The adapter reported no metrics for this run."
                : "Metrics appear once the run succeeds."
            }
          />
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Metric</th>
                <th scope="col">Value</th>
                <th scope="col">Kind</th>
              </tr>
            </thead>
            <tbody>
              {metrics.data.map((metric) => (
                <tr key={metric.metric_id}>
                  <td className="mono">{metric.name}</td>
                  <td className="mono">{metric.value}</td>
                  <td>{metric.result_kind}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className={styles.section} aria-label="Artifacts">
        <h2>Artifacts</h2>
        {artifacts.isPending ? (
          <LoadingState label="Loading artifacts…" />
        ) : artifacts.isError ? (
          <ErrorState
            title="Could not load artifacts."
            detail={artifacts.error instanceof Error ? artifacts.error.message : undefined}
            onRetry={() => void artifacts.refetch()}
          />
        ) : artifacts.data.length === 0 ? (
          <EmptyState title="No artifacts recorded." />
        ) : (
          <ul className={styles.artifactList}>
            {artifacts.data.map((artifact) => (
              <li key={artifact.artifact_id}>
                <span className="mono">{artifact.artifact_id}</span> · {artifact.kind} ·{" "}
                <span className="mono">{artifact.uri}</span>
                {artifact.sha256 ? (
                  <span className={styles.sha}> sha256:{artifact.sha256.slice(0, 12)}…</span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
