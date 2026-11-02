import { useEffect, useState } from "react";
import { Link } from "react-router";
import { useGraphs } from "../../app/queries.ts";
import { EmptyState, ErrorState, LoadingState } from "../../components/states.tsx";
import type { GraphSummary } from "../../lib/types.ts";
import { ArenaPanel } from "./ArenaPanel.tsx";
import { MemoryPanel } from "./MemoryPanel.tsx";
import { SharePanel } from "./SharePanel.tsx";
import { TransplantPanel } from "./TransplantPanel.tsx";
import styles from "./CrossPaperPage.module.css";
import { loadTray, saveTray, trayKey, type TrayEntry } from "./tray.ts";

function entryOf(summary: GraphSummary): TrayEntry {
  return {
    project_id: summary.project_id,
    graph_id: summary.graph_id,
    title: summary.title,
  };
}

export function CrossPaperPage() {
  const graphs = useGraphs();
  const [tray, setTray] = useState<TrayEntry[]>(() => loadTray());
  const [tab, setTab] = useState<"tray" | "arena" | "transplant" | "memory" | "share">(
    "tray",
  );

  useEffect(() => {
    saveTray(tray);
  }, [tray]);

  if (graphs.isPending) {
    return <LoadingState label="Loading graphs…" />;
  }
  if (graphs.isError || !graphs.data) {
    return (
      <ErrorState
        title="Could not load graphs."
        detail={graphs.error instanceof Error ? graphs.error.message : undefined}
        onRetry={() => void graphs.refetch()}
      />
    );
  }

  const inTray = new Set(tray.map(trayKey));
  function add(summary: GraphSummary): void {
    const entry = entryOf(summary);
    if (inTray.has(trayKey(entry))) return;
    setTray((current) => [...current, entry]);
  }
  function remove(entry: TrayEntry): void {
    const key = trayKey(entry);
    setTray((current) => current.filter((candidate) => trayKey(candidate) !== key));
  }

  return (
    <div className={styles.page}>
      <h1>Cross-paper workspace</h1>
      <p className={styles.hint}>
        Collect graphs from different papers into a tray, then compare or combine them.
      </p>

      <div className={styles.tabs} role="tablist" aria-label="Cross-paper views">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "tray"}
          onClick={() => setTab("tray")}
        >
          Tray
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "arena"}
          onClick={() => setTab("arena")}
        >
          Arena
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "transplant"}
          onClick={() => setTab("transplant")}
        >
          Transplant
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "memory"}
          onClick={() => setTab("memory")}
        >
          Memory
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "share"}
          onClick={() => setTab("share")}
        >
          Share
        </button>
      </div>

      {tab === "arena" ? (
        <ArenaPanel tray={tray} />
      ) : tab === "transplant" ? (
        <TransplantPanel tray={tray} summaries={graphs.data} />
      ) : tab === "memory" ? (
        <MemoryPanel tray={tray} />
      ) : tab === "share" ? (
        <SharePanel tray={tray} />
      ) : (
        <>
          <section className={styles.card} aria-label="Tray">
        <h2>Tray ({tray.length})</h2>
        {tray.length === 0 ? (
          <EmptyState
            title="The tray is empty."
            detail="Add graphs below to line them up for comparison."
          />
        ) : (
          <ul className={styles.tray}>
            {tray.map((entry) => (
              <li key={trayKey(entry)} className={styles.trayItem}>
                <Link to={`/g/${entry.project_id}/${entry.graph_id}`}>
                  {entry.title}
                </Link>
                <span className={styles.meta}>
                  {entry.project_id} / {entry.graph_id}
                </span>
                <button type="button" onClick={() => remove(entry)}>
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className={styles.card} aria-label="Graphs">
        <h2>Graphs</h2>
        {graphs.data.length === 0 ? (
          <EmptyState
            title="No graphs yet."
            detail="Extract a paper to grow its first graph."
          />
        ) : (
          <ul className={styles.graphs}>
            {graphs.data.map((summary) => {
              const added = inTray.has(
                trayKey({ project_id: summary.project_id, graph_id: summary.graph_id }),
              );
              return (
                <li key={`${summary.project_id}::${summary.graph_id}`} className={styles.row}>
                  <div>
                    <Link to={`/g/${summary.project_id}/${summary.graph_id}`}>
                      {summary.title}
                    </Link>
                    <p className={styles.meta}>
                      v{summary.version} · {summary.node_count} nodes ·{" "}
                      {summary.edge_count} edges · {summary.source_ids.join(", ") || "no paper"}
                    </p>
                  </div>
                  <button type="button" disabled={added} onClick={() => add(summary)}>
                    {added ? "In tray" : "Add to tray"}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>
        </>
      )}
    </div>
  );
}
