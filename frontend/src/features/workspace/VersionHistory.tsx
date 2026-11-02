import { useState } from "react";
import { useRestoreRevision, useRevisionList } from "../../app/queries.ts";
import { EmptyState, ErrorState, LoadingState } from "../../components/states.tsx";
import { BizoraApiError } from "../../lib/api.ts";
import { WORKSPACE_ACTOR } from "../../lib/constants.ts";
import type { GraphRevisionSummary } from "../../lib/types.ts";
import styles from "./VersionHistory.module.css";

export function VersionHistory({
  projectId,
  graphId,
  currentVersion,
  onSelectVersion,
  onCompare,
}: {
  projectId: string;
  graphId: string;
  currentVersion: number;
  onSelectVersion: (version: number) => void;
  onCompare: (baseVersion: number) => void;
}) {
  const list = useRevisionList(projectId, graphId);
  const restore = useRestoreRevision(projectId, graphId);
  const [confirming, setConfirming] = useState<number | null>(null);

  return (
    <section className={styles.panel} aria-label="Version history">
      <h2>Version history</h2>
      {list.isPending ? (
        <LoadingState label="Loading version history…" />
      ) : list.isError ? (
        <ErrorState
          title="Could not load the version history."
          detail={list.error instanceof Error ? list.error.message : undefined}
          onRetry={() => void list.refetch()}
        />
      ) : list.data.length === 0 ? (
        <EmptyState title="No revisions yet." />
      ) : (
        <ol className={styles.list}>
          {[...list.data].reverse().map((row) => (
            <HistoryRow
              key={row.version}
              row={row}
              isCurrent={row.version === currentVersion}
              confirming={confirming === row.version}
              restoring={restore.isPending}
              onView={() => onSelectVersion(row.version)}
              onCompare={() => onCompare(row.version)}
              onRestore={() => setConfirming(row.version)}
              onCancelRestore={() => setConfirming(null)}
              onConfirmRestore={() =>
                restore.mutate(
                  { version: row.version, requestedBy: WORKSPACE_ACTOR },
                  {
                    onSuccess: (graph) => {
                      setConfirming(null);
                      onSelectVersion(graph.version);
                    },
                  },
                )
              }
            />
          ))}
        </ol>
      )}
      {restore.isError ? (
        <p className={styles.error} role="alert">
          {restoreErrorMessage(restore.error)}
        </p>
      ) : null}
    </section>
  );
}

function HistoryRow({
  row,
  isCurrent,
  confirming,
  restoring,
  onView,
  onCompare,
  onRestore,
  onCancelRestore,
  onConfirmRestore,
}: {
  row: GraphRevisionSummary;
  isCurrent: boolean;
  confirming: boolean;
  restoring: boolean;
  onView: () => void;
  onCompare: () => void;
  onRestore: () => void;
  onCancelRestore: () => void;
  onConfirmRestore: () => void;
}) {
  return (
    <li className={styles.item}>
      <div className={styles.head}>
        <span className={styles.version}>v{row.version}</span>
        <span className={styles.title}>{row.title}</span>
        {isCurrent ? <span className={styles.current}>current</span> : null}
      </div>
      <div className={styles.meta}>
        <span className="mono">{row.created_by}</span>
        <span>{formatTimestamp(row.created_at)}</span>
      </div>
      {!isCurrent ? (
        confirming ? (
          <div className={styles.confirm}>
            <span>Restore v{row.version} as a new revision?</span>
            <button type="button" disabled={restoring} onClick={onConfirmRestore}>
              {restoring ? "Restoring…" : "Confirm restore"}
            </button>
            <button type="button" disabled={restoring} onClick={onCancelRestore}>
              Cancel
            </button>
          </div>
        ) : (
          <div className={styles.actions}>
            <button type="button" disabled={restoring} onClick={onView}>
              View
            </button>
            <button type="button" disabled={restoring} onClick={onCompare}>
              Compare
            </button>
            <button type="button" disabled={restoring} onClick={onRestore}>
              Restore
            </button>
          </div>
        )
      ) : null}
    </li>
  );
}

function formatTimestamp(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function restoreErrorMessage(error: unknown): string {
  if (error instanceof BizoraApiError && error.isConflict) {
    return "That revision is already the latest; nothing to restore.";
  }
  if (error instanceof Error) return error.message;
  return "The restore failed.";
}
