/* Pure builders for correction-loop patches.

Each decision becomes ordinary graph patches: accept/edit are
`replace_node` patches that clear the assumed marking and record the
claim as verified, reject removes connected edges first and then the
node. A submitted batch applies atomically as one new revision through
the existing patch-batch endpoint. */

import type {
  GraphNode,
  GraphPatch,
  MethodologyGraph,
  PatchOperation,
} from "../../lib/types.ts";
import {
  ASSUMED_CONFIG_KEY,
  ASSUMPTION_REASON_CONFIG_KEY,
  CORRECTION_ACTOR,
} from "./assumptions.ts";

export function makeCorrectionPatchId(): string {
  return `correction-${crypto.randomUUID()}`;
}

/** Copy a config without the assumed marking (other keys preserved). */
export function stripAssumptionKeys(
  config: Record<string, unknown>,
): Record<string, unknown> {
  const next = { ...config };
  delete next[ASSUMED_CONFIG_KEY];
  delete next[ASSUMPTION_REASON_CONFIG_KEY];
  return next;
}

function basePatch(
  graph: MethodologyGraph,
  operation: PatchOperation,
  rationale: string,
  targetId: string | null = null,
  payload: Record<string, unknown> = {},
): GraphPatch {
  return {
    patch_id: makeCorrectionPatchId(),
    base_graph_id: graph.graph_id,
    base_version: graph.version,
    operation,
    target_id: targetId,
    payload,
    rationale,
    requested_by: CORRECTION_ACTOR,
  };
}

function replacementNode(
  node: GraphNode,
  overrides: {
    label: string;
    description: string | null;
    config: Record<string, unknown>;
  },
): Record<string, unknown> {
  // The id is retained so all connections survive; evidence, shapes,
  // and kind carry over unchanged.
  return {
    id: node.id,
    kind: node.kind,
    label: overrides.label,
    description: overrides.description,
    config: stripAssumptionKeys(overrides.config),
    input_shape: node.input_shape,
    output_shape: node.output_shape,
    evidence: node.evidence,
    provenance: "verified",
    confidence: node.confidence,
  };
}

/** Accept a claim as correct: clear its assumed marking. */
export function acceptNodePatch(
  graph: MethodologyGraph,
  node: GraphNode,
): GraphPatch {
  return basePatch(
    graph,
    "replace_node",
    `Accept extracted component ${node.id} (${node.label})`,
    node.id,
    {
      node: replacementNode(node, {
        label: node.label,
        description: node.description,
        config: node.config,
      }),
    },
  );
}

export interface NodeEdit {
  label: string;
  description: string | null;
  config: Record<string, unknown>;
}

/** Correct a claim's label, description, or config; kind is retained. */
export function editNodePatch(
  graph: MethodologyGraph,
  node: GraphNode,
  edit: NodeEdit,
): GraphPatch {
  const label = edit.label.trim();
  if (label === "") {
    throw new Error("A corrected label is required.");
  }
  return basePatch(
    graph,
    "replace_node",
    `Correct extracted component ${node.id} (${node.label})`,
    node.id,
    {
      node: replacementNode(node, {
        label,
        description: edit.description,
        config: edit.config,
      }),
    },
  );
}

/**
 * Reject a claim: connected edges first (the backend refuses to remove
 * a connected node), then the node itself.
 */
export function rejectNodePatches(
  graph: MethodologyGraph,
  node: GraphNode,
): GraphPatch[] {
  const patches: GraphPatch[] = graph.edges
    .filter((edge) => edge.source === node.id || edge.target === node.id)
    .map((edge) =>
      basePatch(
        graph,
        "remove_edge",
        `Remove connection ${edge.id} of rejected component ${node.id}`,
        edge.id,
      ),
    );
  patches.push(
    basePatch(
      graph,
      "remove_node",
      `Reject extracted component ${node.id} (${node.label})`,
      node.id,
    ),
  );
  return patches;
}

export type CorrectionAction = "accept" | "edit" | "reject";

export interface CorrectionDecision {
  nodeId: string;
  action: CorrectionAction;
  edit?: NodeEdit;
}

/**
 * Build one atomic batch from review decisions. Edge removals sort
 * first so rejected nodes detach before they are removed.
 */
export function buildCorrectionBatch(
  graph: MethodologyGraph,
  decisions: CorrectionDecision[],
): GraphPatch[] {
  const byId = new Map(graph.nodes.map((node) => [node.id, node]));
  const edgeRemovals: GraphPatch[] = [];
  const nodeRemovals: GraphPatch[] = [];
  const replacements: GraphPatch[] = [];

  for (const decision of decisions) {
    const node = byId.get(decision.nodeId);
    if (!node) {
      throw new Error(`Unknown component in correction batch: ${decision.nodeId}.`);
    }
    if (decision.action === "accept") {
      replacements.push(acceptNodePatch(graph, node));
    } else if (decision.action === "reject") {
      for (const patch of rejectNodePatches(graph, node)) {
        (patch.operation === "remove_edge" ? edgeRemovals : nodeRemovals).push(patch);
      }
    } else {
      if (!decision.edit) {
        throw new Error(`Missing edit payload for component ${decision.nodeId}.`);
      }
      replacements.push(editNodePatch(graph, node, decision.edit));
    }
  }
  return [...edgeRemovals, ...nodeRemovals, ...replacements];
}
