import { useState } from "react";
import type { FormEvent } from "react";
import type { CanvasView } from "../../app/routeElements.tsx";
import { NODE_KINDS } from "../../lib/constants.ts";
import type { NodeKind } from "../../lib/types.ts";
import { isValidNodeId, suggestNodeId } from "./ids.ts";
import styles from "./CanvasToolbar.module.css";

const KINDS: readonly NodeKind[] = NODE_KINDS;

export interface NewNodeSpec {
  id: string;
  kind: NodeKind;
  label: string;
}

export type LayoutSaveStatus = "idle" | "saving" | "saved" | "error";

const LAYOUT_STATUS_TEXT: Record<LayoutSaveStatus, string | null> = {
  idle: null,
  saving: "Saving layout…",
  saved: "Layout saved",
  error: "Layout save failed",
};

export function CanvasToolbar({
  takenIds,
  canUndo,
  canRedo,
  onUndo,
  onRedo,
  onAddNode,
  disabled,
  layoutStatus,
  onResetLayout,
  view,
  onViewChange,
}: {
  takenIds: Set<string>;
  canUndo: boolean;
  canRedo: boolean;
  onUndo: () => void;
  onRedo: () => void;
  onAddNode: (spec: NewNodeSpec) => void;
  disabled: boolean;
  layoutStatus: LayoutSaveStatus;
  onResetLayout: () => void;
  view: CanvasView;
  onViewChange: (view: CanvasView) => void;
}) {
  const [id, setId] = useState("");
  const [kind, setKind] = useState<NodeKind>("model");
  const [label, setLabel] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  function submit(event: FormEvent): void {
    event.preventDefault();
    const trimmedLabel = label.trim();
    if (!trimmedLabel) {
      setFormError("A label is required.");
      return;
    }
    const nodeId = id.trim() === "" ? suggestNodeId(takenIds) : id.trim();
    if (!isValidNodeId(nodeId)) {
      setFormError("Use letters, digits, and . _ : - (max 128).");
      return;
    }
    if (takenIds.has(nodeId)) {
      setFormError(`"${nodeId}" is already used.`);
      return;
    }
    setFormError(null);
    setId("");
    setLabel("");
    onAddNode({ id: nodeId, kind, label: trimmedLabel });
  }

  return (
    <div className={styles.toolbar}>
      <div className={styles.history} role="group" aria-label="Revision history">
        <button type="button" onClick={onUndo} disabled={disabled || !canUndo} title="Undo (Ctrl+Z)">
          Undo
        </button>
        <button
          type="button"
          onClick={onRedo}
          disabled={disabled || !canRedo}
          title="Redo (Ctrl+Shift+Z)"
        >
          Redo
        </button>
      </div>
      <form className={styles.addForm} onSubmit={submit} aria-label="Add component">
        <input
          value={id}
          onChange={(event) => setId(event.target.value)}
          placeholder="id (optional)"
          aria-label="Node id"
          autoComplete="off"
          spellCheck={false}
          disabled={disabled}
        />
        <select
          value={kind}
          onChange={(event) => setKind(event.target.value as NodeKind)}
          aria-label="Node kind"
          disabled={disabled}
        >
          {KINDS.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
        <input
          value={label}
          onChange={(event) => setLabel(event.target.value)}
          placeholder="Label"
          aria-label="Node label"
          autoComplete="off"
          disabled={disabled}
        />
        <button type="submit" disabled={disabled}>
          Add
        </button>
      </form>
      {formError ? (
        <p className={styles.formError} role="alert">
          {formError}
        </p>
      ) : null}
      {LAYOUT_STATUS_TEXT[layoutStatus] ? (
        <span className={`${styles.layoutStatus} ${styles[layoutStatus]}`} role="status">
          {LAYOUT_STATUS_TEXT[layoutStatus]}
        </span>
      ) : null}
      <button
        type="button"
        className={styles.toolButton}
        onClick={onResetLayout}
        disabled={disabled}
        title="Reset node positions to the automatic layered layout"
      >
        Reset layout
      </button>
      <div className={styles.viewToggle} role="group" aria-label="Canvas view">
        <button
          type="button"
          onClick={() => onViewChange("structure")}
          disabled={disabled}
          aria-pressed={view === "structure"}
          title="Structure: the paper's architecture as a block diagram"
        >
          Structure
        </button>
        <button
          type="button"
          onClick={() => onViewChange("flow")}
          disabled={disabled}
          aria-pressed={view === "flow"}
          title="Flow: step-by-step walkthrough of the method"
        >
          Flow
        </button>
        <button
          type="button"
          onClick={() => onViewChange("3d")}
          disabled={disabled}
          aria-pressed={view === "3d"}
          title="3D structure: physical parts only"
        >
          3D
        </button>
      </div>
    </div>
  );
}
