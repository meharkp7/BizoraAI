import { useState } from "react";
import type { FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link } from "react-router";
import { useGraphRevision } from "../../app/queries.ts";
import { api, BizoraApiError } from "../../lib/api.ts";
import { CROSS_PAPER_ACTOR } from "../../lib/constants.ts";
import type { GraphSummary, TransplantResponse } from "../../lib/types.ts";
import { EmptyState, ErrorState } from "../../components/states.tsx";
import styles from "./CrossPaperPage.module.css";
import { trayKey, type TrayEntry } from "./tray.ts";

export function TransplantPanel({
  tray,
  summaries,
}: {
  tray: TrayEntry[];
  summaries: GraphSummary[];
}) {
  const [sourceKey, setSourceKey] = useState("");
  const [targetKey, setTargetKey] = useState("");
  const [picked, setPicked] = useState<string[]>([]);

  const byKey = new Map(summaries.map((s) => [trayKey(s), s]));
  const source = sourceKey ? (byKey.get(sourceKey) ?? null) : null;
  const revision = useGraphRevision(
    source?.project_id ?? "",
    source?.graph_id ?? "",
    source?.version ?? 1,
    source !== null,
  );
  const transplant = useMutation({
    mutationFn: async (): Promise<TransplantResponse> => {
      const target = targetKey ? (byKey.get(targetKey) ?? null) : null;
      if (!source || !target) throw new Error("Pick a source and a target graph.");
      return api.transplantNodes(target.project_id, target.graph_id, {
        source_project_id: source.project_id,
        source_graph_id: source.graph_id,
        source_version: source.version,
        node_ids: picked,
        created_by: CROSS_PAPER_ACTOR,
      });
    },
  });

  function chooseSource(key: string): void {
    setSourceKey(key);
    setPicked([]);
    transplant.reset();
  }

  function toggleNode(nodeId: string): void {
    setPicked((current) =>
      current.includes(nodeId)
        ? current.filter((id) => id !== nodeId)
        : [...current, nodeId],
    );
  }

  function submit(event: FormEvent): void {
    event.preventDefault();
    if (picked.length > 0 && sourceKey && targetKey && sourceKey !== targetKey) {
      transplant.mutate();
    }
  }

  if (tray.length < 2) {
    return (
      <EmptyState
        title="Add two graphs to the tray to transplant."
        detail="Copy blocks from one paper's graph into another as a new revision."
      />
    );
  }
  const options = tray.filter((entry) => byKey.has(trayKey(entry)));

  return (
    <div className={styles.arena}>
      <form className={styles.arenaForm} onSubmit={submit} aria-label="Transplant blocks">
        <label>
          Source graph
          <select value={sourceKey} onChange={(event) => chooseSource(event.target.value)}>
            <option value="">Choose a graph…</option>
            {options.map((entry) => (
              <option key={trayKey(entry)} value={trayKey(entry)}>
                {entry.title}
              </option>
            ))}
          </select>
        </label>
        <label>
          Target graph
          <select value={targetKey} onChange={(event) => setTargetKey(event.target.value)}>
            <option value="">Choose a graph…</option>
            {options
              .filter((entry) => trayKey(entry) !== sourceKey)
              .map((entry) => (
                <option key={trayKey(entry)} value={trayKey(entry)}>
                  {entry.title}
                </option>
              ))}
          </select>
        </label>
        <button
          type="submit"
          disabled={
            transplant.isPending ||
            !sourceKey ||
            !targetKey ||
            sourceKey === targetKey ||
            picked.length === 0
          }
        >
          {transplant.isPending ? "…" : "Transplant"}
        </button>
      </form>

      {source && revision.isPending ? <p className={styles.hint}>Loading source blocks…</p> : null}
      {source && revision.data ? (
        <fieldset className={styles.checks}>
          <legend>Blocks from {source.title}</legend>
          {revision.data.nodes.map((node) => (
            <label key={node.id} className={styles.check}>
              <input
                type="checkbox"
                checked={picked.includes(node.id)}
                onChange={() => toggleNode(node.id)}
              />
              {node.label} <span className={styles.meta}>({node.id})</span>
            </label>
          ))}
        </fieldset>
      ) : null}

      {transplant.isError ? (
        <ErrorState
          title="The transplant failed."
          detail={
            transplant.error instanceof BizoraApiError
              ? transplant.error.message
              : transplant.error instanceof Error
                ? transplant.error.message
                : undefined
          }
          onRetry={() => transplant.mutate()}
        />
      ) : null}
      {transplant.data ? (
        <section className={styles.card} aria-label="Transplant result">
          <h3>{transplant.data.title}</h3>
          <p className={styles.hint}>
            Moved {transplant.data.added_node_ids.length} block(s) into{" "}
            <Link to={`/g/${transplant.data.project_id}/${transplant.data.graph_id}`}>
              {transplant.data.graph_id} v{transplant.data.version}
            </Link>
            : {transplant.data.copied_edge_count} edge(s) copied,{" "}
            {transplant.data.dropped_edge_count} cut.
          </p>
          {Object.keys(transplant.data.renamed).length > 0 ? (
            <p className={styles.hint}>
              Renamed:{" "}
              {Object.entries(transplant.data.renamed)
                .map(([from, to]) => `${from} → ${to}`)
                .join(", ")}
            </p>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
