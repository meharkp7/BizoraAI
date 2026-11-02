import { useState } from "react";
import { useApplyPatch, useApplyPatchBatch } from "../../app/queries.ts";
import { BizoraApiError } from "../../lib/api.ts";
import type { GraphPatch } from "../../lib/types.ts";
import {
  useScenarioDrafts,
  type ScenarioDraft,
} from "./drafts.ts";
import styles from "./ScenarioDrafts.module.css";

export function ScenarioDrafts({
  projectId,
  graphId,
  currentVersion,
  currentTitle,
  onPromoted,
}: {
  projectId: string;
  graphId: string;
  currentVersion: number;
  currentTitle: string;
  onPromoted: (version: number) => void;
}) {
  const drafts = useScenarioDrafts((state) => state.drafts);
  const activeDraftId = useScenarioDrafts((state) => state.activeDraftId);
  const createDraft = useScenarioDrafts((state) => state.createDraft);
  const [name, setName] = useState("");

  const graphDrafts = drafts.filter(
    (draft) => draft.projectId === projectId && draft.graphId === graphId,
  );

  function startDraft(): void {
    const trimmed = name.trim();
    createDraft({
      name: trimmed || `Scenario ${graphDrafts.length + 1}`,
      projectId,
      graphId,
      baseVersion: currentVersion,
      baseTitle: currentTitle,
    });
    setName("");
  }

  return (
    <section className={styles.panel} aria-label="Scenario drafts">
      <h2>Scenario drafts</h2>
      <p className={styles.hint}>
        Draft a what-if as an op-list over v{currentVersion}: canvas edits stage into
        the active draft, and promoting saves them as one new revision. Drafts live
        in memory; a reload discards them.
      </p>
      <div className={styles.create}>
        <label>
          Draft name
          <input
            type="text"
            value={name}
            maxLength={80}
            placeholder={`Scenario ${graphDrafts.length + 1}`}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <button type="button" onClick={startDraft}>
          Draft from v{currentVersion}
        </button>
      </div>
      {graphDrafts.length === 0 ? (
        <p className={styles.hint}>No drafts for this graph yet.</p>
      ) : (
        <ol className={styles.list}>
          {graphDrafts.map((draft) => (
            <DraftRow
              key={draft.id}
              projectId={projectId}
              graphId={graphId}
              draft={draft}
              isActive={draft.id === activeDraftId}
              onPromoted={onPromoted}
            />
          ))}
        </ol>
      )}
    </section>
  );
}

function DraftRow({
  projectId,
  graphId,
  draft,
  isActive,
  onPromoted,
}: {
  projectId: string;
  graphId: string;
  draft: ScenarioDraft;
  isActive: boolean;
  onPromoted: (version: number) => void;
}) {
  const removePatch = useScenarioDrafts((state) => state.removePatch);
  const deleteDraft = useScenarioDrafts((state) => state.deleteDraft);
  const setActiveDraft = useScenarioDrafts((state) => state.setActiveDraft);
  const single = useApplyPatch(projectId, graphId);
  const batch = useApplyPatchBatch(projectId, graphId);
  const [confirmingDiscard, setConfirmingDiscard] = useState(false);

  const promoting = single.isPending || batch.isPending;
  const error = single.error ?? batch.error;

  function promote(): void {
    if (draft.patches.length === 0) return;
    const callbacks = {
      onSuccess: (graph: { version: number }) => {
        deleteDraft(draft.id);
        onPromoted(graph.version);
      },
    };
    if (draft.patches.length === 1) single.mutate(draft.patches[0], callbacks);
    else batch.mutate({ patches: draft.patches }, callbacks);
  }

  return (
    <li className={styles.item}>
      <div className={styles.head}>
        <span className={styles.name}>{draft.name}</span>
        {isActive ? <span className={styles.active}>staging here</span> : null}
      </div>
      <div className={styles.meta}>
        <span>
          base v{draft.baseVersion} · {draft.patches.length}{" "}
          {draft.patches.length === 1 ? "op" : "ops"}
        </span>
      </div>
      {draft.patches.length === 0 ? (
        <p className={styles.hint}>
          Empty: edit the canvas while this draft is active to stage ops.
        </p>
      ) : (
        <ul className={styles.ops}>
          {draft.patches.map((patch) => (
            <li key={patch.patch_id} className={styles.op}>
              <span className={styles.opText}>{describeOp(patch)}</span>
              <button
                type="button"
                disabled={promoting}
                onClick={() => removePatch(draft.id, patch.patch_id)}
                aria-label={`Remove ${patch.rationale}`}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className={styles.actions}>
        {isActive ? (
          <button type="button" disabled={promoting} onClick={() => setActiveDraft(null)}>
            Stop staging
          </button>
        ) : (
          <button
            type="button"
            disabled={promoting}
            onClick={() => setActiveDraft(draft.id)}
          >
            Stage here
          </button>
        )}
        <button
          type="button"
          disabled={draft.patches.length === 0 || promoting}
          onClick={promote}
        >
          {promoting ? "Promoting…" : "Promote to revision"}
        </button>
        {confirmingDiscard ? (
          <>
            <button
              type="button"
              disabled={promoting}
              onClick={() => deleteDraft(draft.id)}
            >
              Confirm discard
            </button>
            <button
              type="button"
              disabled={promoting}
              onClick={() => setConfirmingDiscard(false)}
            >
              Cancel
            </button>
          </>
        ) : (
          <button
            type="button"
            disabled={promoting}
            onClick={() => setConfirmingDiscard(true)}
          >
            Discard
          </button>
        )}
      </div>
      {error ? (
        <p className={styles.error} role="alert">
          {promoteErrorMessage(error, draft.baseVersion)}
        </p>
      ) : null}
    </li>
  );
}

function describeOp(patch: GraphPatch): string {
  return patch.target_id ? `${patch.rationale} (${patch.target_id})` : patch.rationale;
}

function promoteErrorMessage(error: unknown, baseVersion: number): string {
  if (error instanceof BizoraApiError && error.isConflict) {
    return (
      `The base v${baseVersion} is no longer the latest revision. ` +
      "Draft again from the current head to restage these ops."
    );
  }
  if (error instanceof Error) return error.message;
  return "The promote failed.";
}
