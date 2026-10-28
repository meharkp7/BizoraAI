import { useState } from "react";
import type { EvidenceRef, GraphNode } from "../../lib/types.ts";
import { assumptionReason, hasEvidence, isAssumed } from "./assumptions.ts";
import {
  stripAssumptionKeys,
  type CorrectionAction,
  type NodeEdit,
} from "./correctionPatches.ts";
import styles from "./CorrectionCard.module.css";

function locatorSummary(ref: EvidenceRef): string {
  const parts: string[] = [];
  if (ref.page !== null) parts.push(`p. ${ref.page}`);
  if (ref.figure_label) parts.push(ref.figure_label);
  if (ref.locator) parts.push(ref.locator);
  return parts.join(" · ") || "cited source";
}

function decisionLabel(action: CorrectionAction): string {
  if (action === "accept") return "Accepted";
  if (action === "edit") return "Edited";
  return "Rejected";
}

function EvidenceList({ node }: { node: GraphNode }) {
  if (!hasEvidence(node)) {
    return (
      <p className={styles.hint}>
        No source references recorded for this component. Treat its details as
        unverified.
      </p>
    );
  }
  return (
    <ul className={styles.evidenceList}>
      {node.evidence.map((ref, index) => (
        <li key={`${ref.source_id}-${index}`} className={styles.evidenceItem}>
          <div className={styles.evidenceHead}>
            <span className="mono">{ref.source_id}</span>
            <span className={styles.evidenceStatus}>{ref.status}</span>
          </div>
          <div className={styles.locator}>{locatorSummary(ref)}</div>
          {ref.quote ? (
            <blockquote className={styles.quote}>{ref.quote}</blockquote>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

export function CorrectionCard({
  node,
  decision,
  disabled,
  onAccept,
  onReject,
  onEdit,
  onClear,
}: {
  node: GraphNode;
  decision: CorrectionAction | null;
  disabled: boolean;
  onAccept: () => void;
  onReject: () => void;
  onEdit: (edit: NodeEdit) => void;
  onClear: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [label, setLabel] = useState(node.label);
  const [description, setDescription] = useState(node.description ?? "");
  const [configText, setConfigText] = useState(() =>
    JSON.stringify(stripAssumptionKeys(node.config), null, 2),
  );
  const [formError, setFormError] = useState<string | null>(null);

  const assumed = isAssumed(node);
  const reason = assumptionReason(node);
  const grounded = hasEvidence(node);
  const headingId = `correction-${node.id}`;

  function handleSaveEdit(): void {
    if (label.trim() === "") {
      setFormError("A corrected label is required.");
      return;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(configText) as unknown;
    } catch {
      setFormError("Configuration must be valid JSON.");
      return;
    }
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      setFormError("Configuration must be a JSON object.");
      return;
    }
    setFormError(null);
    setEditing(false);
    onEdit({
      label: label.trim(),
      description: description.trim() === "" ? null : description.trim(),
      config: parsed as Record<string, unknown>,
    });
  }

  return (
    <article className={styles.card} aria-labelledby={headingId}>
      <div className={styles.head}>
        <div>
          <h3 id={headingId} className={styles.title}>
            {node.label}
          </h3>
          <p className={styles.meta}>
            {node.kind} · <span className="mono">{node.id}</span>
            {node.confidence !== null ? ` · confidence ${node.confidence}` : null}
          </p>
        </div>
        {assumed ? (
          <span className={`${styles.badge} ${styles.assumed}`}>Assumed</span>
        ) : grounded ? (
          <span className={`${styles.badge} ${styles.grounded}`}>Evidence-backed</span>
        ) : (
          <span className={`${styles.badge} ${styles.ungrounded}`}>No evidence</span>
        )}
      </div>

      {reason ? <p className={styles.reason}>{reason}</p> : null}
      {node.description ? <p className={styles.description}>{node.description}</p> : null}

      <EvidenceList node={node} />

      {decision ? (
        <div className={styles.decisionRow}>
          <span className={styles.decision}>Decision: {decisionLabel(decision)}</span>
          <button type="button" onClick={onClear} disabled={disabled}>
            Clear decision
          </button>
        </div>
      ) : (
        <div className={styles.actions}>
          <button type="button" onClick={onAccept} disabled={disabled}>
            Accept
          </button>
          <button
            type="button"
            onClick={() => {
              setFormError(null);
              setEditing((value) => !value);
            }}
            disabled={disabled}
          >
            Edit
          </button>
          <button type="button" onClick={onReject} disabled={disabled}>
            Reject
          </button>
        </div>
      )}

      {editing && !decision ? (
        <form
          className={styles.form}
          onSubmit={(event) => {
            event.preventDefault();
            handleSaveEdit();
          }}
        >
          <label className={styles.field}>
            Label
            <input
              type="text"
              value={label}
              onChange={(event) => setLabel(event.target.value)}
              disabled={disabled}
            />
          </label>
          <label className={styles.field}>
            Description
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              disabled={disabled}
              rows={3}
            />
          </label>
          <label className={styles.field}>
            Configuration JSON
            <textarea
              value={configText}
              onChange={(event) => setConfigText(event.target.value)}
              disabled={disabled}
              rows={5}
              className="mono"
            />
          </label>
          {formError ? <p className={styles.error} role="alert">{formError}</p> : null}
          <div className={styles.actions}>
            <button type="submit" disabled={disabled}>
              Save correction
            </button>
            <button
              type="button"
              onClick={() => {
                setEditing(false);
                setFormError(null);
              }}
              disabled={disabled}
            >
              Cancel
            </button>
          </div>
        </form>
      ) : null}
    </article>
  );
}
