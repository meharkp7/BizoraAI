import { useState } from "react";
import { NODE_KINDS } from "../../lib/constants.ts";
import type { GraphPatch, MethodologyGraph, NodeKind } from "../../lib/types.ts";
import {
  addEdgePatch,
  addNodePatch,
  nodeIdProblem,
  suggestNodeId,
} from "./patchBuilders.ts";
import styles from "./AddStep.module.css";

function isNodeKind(value: string): value is NodeKind {
  return (NODE_KINDS as readonly string[]).includes(value);
}

/** Suggest a unique edge id for one new connection. */
function suggestEdgeId(
  graph: MethodologyGraph,
  source: string,
  target: string,
): string {
  const base = `e-${source}-${target}`.slice(0, 120);
  const taken = new Set(graph.edges.map((edge) => edge.id));
  if (!taken.has(base)) return base;
  let counter = 2;
  while (taken.has(`${base}-${counter}`)) counter += 1;
  return `${base}-${counter}`;
}

/**
 * Append one step to the workspace graph: a node plus, unless the
 * step stands alone, an edge from its predecessor. The submitter
 * writes a new revision through the usual patch flow.
 */
export function AddStepForm({
  graph,
  disabled,
  insertAfter,
  onSubmit,
  onCancel,
}: {
  graph: MethodologyGraph;
  disabled: boolean;
  insertAfter: string | null;
  onSubmit: (patches: GraphPatch[]) => void;
  onCancel: () => void;
}) {
  const knownIds = new Set(graph.nodes.map((node) => node.id));
  const fallbackAfter = graph.nodes[graph.nodes.length - 1]?.id ?? "";
  const [label, setLabel] = useState("");
  const [id, setId] = useState("");
  const [idTouched, setIdTouched] = useState(false);
  const [kind, setKind] = useState<NodeKind>("operation");
  const [description, setDescription] = useState("");
  const [after, setAfter] = useState(
    insertAfter && knownIds.has(insertAfter) ? insertAfter : fallbackAfter,
  );

  const effectiveId = idTouched ? id : suggestNodeId(graph, label.trim() || "step");
  const problem =
    label.trim() === "" ? "Name the step." : nodeIdProblem(graph, effectiveId);

  function submit(): void {
    if (disabled || problem !== null) return;
    const cleanLabel = label.trim();
    const patches: GraphPatch[] = [
      addNodePatch(
        graph,
        { id: effectiveId, kind, label: cleanLabel },
        { description: description.trim() === "" ? null : description.trim() },
      ),
    ];
    if (after !== "") {
      patches.push(addEdgePatch(graph, suggestEdgeId(graph, after, effectiveId), after, effectiveId));
    }
    onSubmit(patches);
  }

  return (
    <form
      className={styles.form}
      aria-label="Add a step"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <label>
        Step label
        <input
          value={label}
          onChange={(event) => setLabel(event.target.value)}
          placeholder="Quantize weights"
          autoComplete="off"
          spellCheck={false}
        />
      </label>
      <label>
        Step ID
        <input
          value={effectiveId}
          onChange={(event) => {
            setIdTouched(true);
            setId(event.target.value);
          }}
          autoComplete="off"
          spellCheck={false}
        />
      </label>
      <label>
        Kind
        <select
          value={kind}
          onChange={(event) => {
            if (isNodeKind(event.target.value)) setKind(event.target.value);
          }}
        >
          {NODE_KINDS.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>
      <label>
        Description
        <input
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          placeholder="Optional: what this step does"
          autoComplete="off"
          spellCheck={false}
        />
      </label>
      <label>
        Insert after
        <select value={after} onChange={(event) => setAfter(event.target.value)}>
          <option value="">Standalone (no connection)</option>
          {graph.nodes.map((node) => (
            <option key={node.id} value={node.id}>
              {node.label} ({node.id})
            </option>
          ))}
        </select>
      </label>
      {problem !== null && label.trim() !== "" ? (
        <p className={styles.error} role="alert">
          {problem}
        </p>
      ) : null}
      <div className={styles.actions}>
        <button type="submit" disabled={disabled || problem !== null}>
          Add step
        </button>
        <button type="button" className={styles.secondary} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
