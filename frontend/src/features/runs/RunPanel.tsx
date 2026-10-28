import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router";
import { useAdapters, useCreateRun, useExecuteRun } from "../../app/queries.ts";
import type { ExperimentConfig, MethodologyGraph } from "../../lib/types.ts";
import styles from "./RunPanel.module.css";

const DEFAULT_ADAPTER_ID = "bizora.deterministic-test";
const DEFAULT_ADAPTER_VERSION = "0.1.0";

function suggestRunId(experimentId: string, version: number): string {
  const stamp = Date.now().toString(36);
  return `run-${experimentId}-v${version}-${stamp}`.slice(0, 128);
}

export function RunPanel({
  projectId,
  graph,
}: {
  projectId: string;
  graph: MethodologyGraph;
}) {
  const [experimentId, setExperimentId] = useState(`exp-${graph.graph_id}-v${graph.version}`);
  const [seed, setSeed] = useState("42");
  const [adapterId, setAdapterId] = useState(DEFAULT_ADAPTER_ID);
  const [failure, setFailure] = useState<string | null>(null);
  const [finishedRunId, setFinishedRunId] = useState<string | null>(null);
  const createRun = useCreateRun();
  const executeRun = useExecuteRun();
  const adapters = useAdapters();
  const busy = createRun.isPending || executeRun.isPending;
  const options = adapters.data ?? [];
  const selected = options.find((adapter) => adapter.adapter_id === adapterId) ?? null;
  const adapterVersion = selected?.adapter_version ?? DEFAULT_ADAPTER_VERSION;

  function submit(event: FormEvent): void {
    event.preventDefault();
    const name = experimentId.trim();
    const seedValue = Number(seed);
    if (!name || !Number.isInteger(seedValue) || seedValue < 0) return;
    setFailure(null);
    setFinishedRunId(null);
    const config: ExperimentConfig = {
      experiment_id: name,
      project_id: projectId,
      graph_id: graph.graph_id,
      graph_version: graph.version,
      adapter_id: adapterId,
      adapter_version: adapterVersion,
      dataset_id: graph.graph_id,
      dataset_revision: `v${graph.version}`,
      seed: seedValue,
      epochs: 1,
      batch_size: 1,
      learning_rate: 0.001,
      split: { train: 0.8, validation: 0.1, test: 0.1 },
      code_revision: "workspace",
      max_runtime_seconds: 300,
      max_gpu_count: 0,
      network_access: false,
    };
    const runId = suggestRunId(name, graph.version);
    createRun.mutate(
      { runId, config },
      {
        onSuccess: (run) => {
          executeRun.mutate(run.run_id, {
            onSuccess: (finished) => setFinishedRunId(finished.run_id),
            onError: (error) =>
              setFailure(error instanceof Error ? error.message : "Execution failed."),
          });
        },
        onError: (error) =>
          setFailure(error instanceof Error ? error.message : "Run creation failed."),
      },
    );
  }

  return (
    <section className={styles.panel} aria-label="Run revision">
      <h2>Run revision</h2>
      <p className={styles.hint}>
        Run v{graph.version} with the selected adapter and inspect the persisted
        run.
      </p>
      <p className={styles.hint}>
        Connected adapters:{" "}
        {adapters.data
          ? adapters.data.map((adapter) => adapter.adapter_id).join(", ")
          : "loading…"}
      </p>
      {selected ? <p className={styles.hint}>{selected.description}</p> : null}
      <p className={styles.hint}>
        Hardware-in-the-loop, ML training, and LLM inference are not connected.
      </p>
      <form className={styles.form} onSubmit={submit}>
        <label>
          Adapter
          <select
            value={adapterId}
            onChange={(event) => setAdapterId(event.target.value)}
            disabled={options.length === 0}
          >
            {options.map((adapter) => (
              <option key={adapter.adapter_id} value={adapter.adapter_id}>
                {adapter.adapter_id} ({adapter.adapter_version})
              </option>
            ))}
            {options.length === 0 ? (
              <option value={adapterId}>{adapterId}</option>
            ) : null}
          </select>
        </label>
        <label>
          Experiment ID
          <input
            value={experimentId}
            onChange={(event) => setExperimentId(event.target.value)}
            autoComplete="off"
            spellCheck={false}
            maxLength={90}
          />
        </label>
        <label>
          Seed
          <input
            value={seed}
            onChange={(event) => setSeed(event.target.value)}
            inputMode="numeric"
            autoComplete="off"
          />
        </label>
        <button type="submit" disabled={busy || !experimentId.trim()}>
          {busy ? "Running…" : `Run v${graph.version}`}
        </button>
      </form>
      {failure ? (
        <p className={styles.error} role="alert">
          {failure}
        </p>
      ) : null}
      {finishedRunId ? (
        <p className={styles.done}>
          Run finished:{" "}
          <Link
            to={`/g/${encodeURIComponent(projectId)}/${encodeURIComponent(graph.graph_id)}/runs/${encodeURIComponent(finishedRunId)}`}
            className="mono"
          >
            {finishedRunId}
          </Link>
        </p>
      ) : null}
    </section>
  );
}
