import { useMemo, useState } from "react";
import type { GraphPatch, MethodologyGraph } from "../../lib/types.ts";
import { EmptyState } from "../../components/states.tsx";
import { needsReview } from "./assumptions.ts";
import {
  buildCorrectionBatch,
  type CorrectionAction,
  type CorrectionDecision,
  type NodeEdit,
} from "./correctionPatches.ts";
import { CorrectionCard } from "./CorrectionCard.tsx";
import styles from "./CorrectionReview.module.css";

interface DecisionState {
  action: CorrectionAction;
  edit?: NodeEdit;
}

/**
 * Review every extracted component: accept, edit, or reject each claim
 * with its evidence shown. Submitting sends one atomic patch batch,
 * which the backend persists as a single new revision.
 */
export function CorrectionReview({
  graph,
  pending,
  error,
  savedVersion,
  onSubmit,
}: {
  graph: MethodologyGraph;
  pending: boolean;
  error: string | null;
  savedVersion: number | null;
  onSubmit: (patches: GraphPatch[]) => void;
}) {
  const [decisions, setDecisions] = useState<Record<string, DecisionState>>({});
  const [buildError, setBuildError] = useState<string | null>(null);

  const ordered = useMemo(
    () =>
      [...graph.nodes].sort((a, b) => Number(needsReview(b)) - Number(needsReview(a))),
    [graph],
  );
  const reviewCount = useMemo(
    () => graph.nodes.filter(needsReview).length,
    [graph],
  );
  const decidedCount = Object.keys(decisions).length;

  function setDecision(nodeId: string, state: DecisionState): void {
    setDecisions((current) => ({ ...current, [nodeId]: state }));
  }

  function clearDecision(nodeId: string): void {
    setDecisions((current) => {
      const next = { ...current };
      delete next[nodeId];
      return next;
    });
  }

  function handleSubmit(): void {
    const batch: CorrectionDecision[] = Object.entries(decisions).map(
      ([nodeId, state]) => ({ nodeId, action: state.action, edit: state.edit }),
    );
    try {
      onSubmit(buildCorrectionBatch(graph, batch));
      setBuildError(null);
    } catch (cause) {
      setBuildError(cause instanceof Error ? cause.message : "Could not build the correction batch.");
    }
  }

  if (graph.nodes.length === 0) {
    return <EmptyState title="No components in this revision." />;
  }

  return (
    <div className={styles.review}>
      <div className={styles.summary} role="status">
        <span>
          {decidedCount} of {graph.nodes.length} components decided · {reviewCount} need
          review
        </span>
        <button
          type="button"
          onClick={handleSubmit}
          disabled={pending || decidedCount === 0}
        >
          {pending ? "Saving…" : "Submit corrections"}
        </button>
      </div>

      {savedVersion !== null ? (
        <p className={styles.saved} role="status">
          Corrections saved as revision {savedVersion}.
        </p>
      ) : null}
      {error ? <p className={styles.failed} role="alert">{error}</p> : null}
      {buildError ? <p className={styles.failed} role="alert">{buildError}</p> : null}

      <div className={styles.cards}>
        {ordered.map((node) => (
          <CorrectionCard
            key={node.id}
            node={node}
            decision={decisions[node.id]?.action ?? null}
            disabled={pending}
            onAccept={() => setDecision(node.id, { action: "accept" })}
            onReject={() => setDecision(node.id, { action: "reject" })}
            onEdit={(edit) => setDecision(node.id, { action: "edit", edit })}
            onClear={() => clearDecision(node.id)}
          />
        ))}
      </div>
    </div>
  );
}
