import { useEffect, useState } from "react";
import { useRevisionDiff } from "../../app/queries.ts";
import type { GraphRevisionDiff } from "../../lib/types.ts";
import { EmptyState, ErrorState, LoadingState } from "../../components/states.tsx";
import styles from "./DiffPanel.module.css";

export function DiffPanel({
  projectId,
  graphId,
  currentVersion,
  onDiffChange,
}: {
  projectId: string;
  graphId: string;
  currentVersion: number;
  onDiffChange?: (diff: GraphRevisionDiff | null) => void;
}) {
  const [baseVersion, setBaseVersion] = useState(Math.max(1, currentVersion - 1));
  const [targetVersion, setTargetVersion] = useState(currentVersion);
  const diff = useRevisionDiff(projectId, graphId, baseVersion, targetVersion);

  useEffect(() => {
    onDiffChange?.(diff.data ?? null);
  }, [diff.data, onDiffChange]);

  return (
    <section className={styles.panel} aria-label="Revision comparison">
      <h2>Revision comparison</h2>
      <div className={styles.controls}>
        <label>
          Base
          <input
            type="number"
            min={1}
            value={baseVersion}
            onChange={(event) => setBaseVersion(Math.max(1, Number(event.target.value) || 1))}
          />
        </label>
        <label>
          Target
          <input
            type="number"
            min={1}
            value={targetVersion}
            onChange={(event) => setTargetVersion(Math.max(1, Number(event.target.value) || 1))}
          />
        </label>
      </div>
      {diff.isPending ? (
        <LoadingState label="Computing diff…" />
      ) : diff.isError ? (
        <ErrorState
          title="Could not compute the diff."
          detail={diff.error instanceof Error ? diff.error.message : undefined}
          onRetry={() => void diff.refetch()}
        />
      ) : (
        <DiffSummary
          addedNodes={diff.data.added_nodes.map((node) => node.id)}
          removedNodes={diff.data.removed_nodes.map((node) => node.id)}
          changedNodes={diff.data.changed_nodes.map((change) => change.node_id)}
          addedEdges={diff.data.added_edges.map((edge) => edge.id)}
          removedEdges={diff.data.removed_edges.map((edge) => edge.id)}
          changedEdges={diff.data.changed_edges.map((change) => change.edge_id)}
        />
      )}
    </section>
  );
}

function DiffSummary({
  addedNodes,
  removedNodes,
  changedNodes,
  addedEdges,
  removedEdges,
  changedEdges,
}: {
  addedNodes: string[];
  removedNodes: string[];
  changedNodes: string[];
  addedEdges: string[];
  removedEdges: string[];
  changedEdges: string[];
}) {
  const total =
    addedNodes.length +
    removedNodes.length +
    changedNodes.length +
    addedEdges.length +
    removedEdges.length +
    changedEdges.length;
  if (total === 0) {
    return <EmptyState title="No differences." detail="Both revisions are identical." />;
  }
  const groups: [string, string[]][] = [
    ["Added components", addedNodes],
    ["Removed components", removedNodes],
    ["Changed components", changedNodes],
    ["Added connections", addedEdges],
    ["Removed connections", removedEdges],
    ["Changed connections", changedEdges],
  ];
  return (
    <ul className={styles.groups}>
      {groups
        .filter(([, ids]) => ids.length > 0)
        .map(([label, ids]) => (
          <li key={label}>
            <span className={styles.groupLabel}>
              {label} ({ids.length})
            </span>
            <ul className={styles.ids}>
              {ids.map((id) => (
                <li key={id} className="mono">
                  {id}
                </li>
              ))}
            </ul>
          </li>
        ))}
    </ul>
  );
}
