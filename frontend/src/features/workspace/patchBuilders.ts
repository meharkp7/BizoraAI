/* Pure builders for canvas-driven graph patches. */

import { WORKSPACE_ACTOR } from "../../lib/constants.ts";
import type {
  GraphNode,
  GraphPatch,
  MethodologyGraph,
  NodeKind,
  PatchOperation,
} from "../../lib/types.ts";

export function makePatchId(): string {
  return `canvas-${crypto.randomUUID()}`;
}

function basePatch(
  graph: MethodologyGraph,
  operation: PatchOperation,
  rationale: string,
  targetId: string | null = null,
  payload: Record<string, unknown> = {},
): GraphPatch {
  return {
    patch_id: makePatchId(),
    base_graph_id: graph.graph_id,
    base_version: graph.version,
    operation,
    target_id: targetId,
    payload,
    rationale,
    requested_by: WORKSPACE_ACTOR,
  };
}

export function addNodePatch(
  graph: MethodologyGraph,
  spec: { id: string; kind: NodeKind; label: string },
  extras?: { description?: string | null; config?: Record<string, unknown> },
): GraphPatch {
  const node: Record<string, unknown> = {
    id: spec.id,
    kind: spec.kind,
    label: spec.label,
  };
  if (extras?.description) node.description = extras.description;
  if (extras?.config) node.config = extras.config;
  return basePatch(graph, "add_node", `Add component ${spec.id}`, null, { node });
}

const NODE_ID_PATTERN = /^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}$/;

/** Suggest a unique node ID from a label, suffixed when taken. */
export function suggestNodeId(graph: MethodologyGraph, label: string): string {
  const slug =
    label
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 120) || "node";
  const taken = new Set(graph.nodes.map((node) => node.id));
  if (!taken.has(slug)) return slug;
  let counter = 2;
  while (taken.has(`${slug}-${counter}`)) counter += 1;
  return `${slug}-${counter}`;
}

/** Explain why a node ID is unusable, or null when it is free. */
export function nodeIdProblem(graph: MethodologyGraph, id: string): string | null {
  if (!NODE_ID_PATTERN.test(id)) {
    return "IDs start with a letter or digit, then letters, digits, dots, underscores, colons, or dashes.";
  }
  if (graph.nodes.some((node) => node.id === id)) {
    return "This ID is already in the graph.";
  }
  return null;
}

export function addEdgePatch(
  graph: MethodologyGraph,
  edgeId: string,
  source: string,
  target: string,
): GraphPatch {
  return basePatch(
    graph,
    "add_edge",
    `Connect ${source} to ${target}`,
    null,
    { edge: { id: edgeId, source, target, relation: "data_flow" } },
  );
}

export function updateConfigPatch(
  graph: MethodologyGraph,
  node: GraphNode,
  config: Record<string, unknown>,
): GraphPatch {
  return basePatch(graph, "update_node_config", `Update ${node.id} configuration`, node.id, {
    config,
  });
}

export interface NodeReplacement {
  kind: NodeKind;
  label: string;
  description: string | null;
  config: Record<string, unknown>;
}

/** Swap a component in place: the ID is retained so all connections survive.
 *  Evidence, provenance, and shapes carry over from the original node. */
export function replaceNodePatch(
  graph: MethodologyGraph,
  node: GraphNode,
  replacement: NodeReplacement,
): GraphPatch {
  return basePatch(
    graph,
    "replace_node",
    `Replace ${node.id} (${node.label}) with ${replacement.label}`,
    node.id,
    {
      node: {
        id: node.id,
        kind: replacement.kind,
        label: replacement.label,
        description: replacement.description,
        config: replacement.config,
        input_shape: node.input_shape,
        output_shape: node.output_shape,
        evidence: node.evidence,
        provenance: node.provenance,
        confidence: node.confidence,
      },
    },
  );
}

/** Removal batch: edges first (explicit plus connected), then nodes. */
export function removalBatch(
  graph: MethodologyGraph,
  nodeIds: string[],
  edgeIds: string[],
): GraphPatch[] {
  const removingNodes = new Set(nodeIds);
  const connected = graph.edges
    .filter((edge) => removingNodes.has(edge.source) || removingNodes.has(edge.target))
    .map((edge) => edge.id);
  const allEdges = [...new Set([...edgeIds, ...connected])];
  const patches: GraphPatch[] = allEdges.map((edgeId) =>
    basePatch(graph, "remove_edge", `Remove connection ${edgeId}`, edgeId),
  );
  for (const nodeId of nodeIds) {
    patches.push(basePatch(graph, "remove_node", `Remove component ${nodeId}`, nodeId));
  }
  return patches;
}
