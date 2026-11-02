"""Build deterministic replication plans from methodology graphs.

Steps follow dependency order (Kahn's algorithm over the graph
edges, stable by declaration order); when edges form a cycle the
plan falls back to declaration order so feedback systems still get
a usable checklist. Action verbs and verification hints are fixed
per node kind, with node descriptions and configs folded in.
"""

from collections import defaultdict, deque

from sqlalchemy.orm import Session

from bizora.contracts.graph import GraphNode, MethodologyGraph, NodeKind
from bizora.contracts.replication import ReplicationPlan, ReplicationStep
from bizora.core.errors import BizoraError, ErrorCode
from bizora.db import repository

_ACTION_VERBS: dict[NodeKind, str] = {
    NodeKind.INPUT: "Provide input",
    NodeKind.DATASET: "Prepare dataset",
    NodeKind.PREPROCESSING: "Apply preprocessing",
    NodeKind.MODEL: "Build model",
    NodeKind.COMPONENT: "Assemble component",
    NodeKind.OPERATION: "Run operation",
    NodeKind.LOSS: "Wire up loss",
    NodeKind.OPTIMIZER: "Configure optimizer",
    NodeKind.EVALUATION: "Run evaluation",
    NodeKind.OUTPUT: "Collect output",
}

_VERIFY_HINTS: dict[NodeKind, str] = {
    NodeKind.INPUT: "Confirm the input format matches the paper's description.",
    NodeKind.DATASET: "Confirm sample counts and splits match the paper.",
    NodeKind.PREPROCESSING: "Spot-check transformed samples before training.",
    NodeKind.MODEL: "Confirm parameter counts match the reported architecture.",
    NodeKind.COMPONENT: "Confirm the assembled component matches its spec.",
    NodeKind.OPERATION: "Confirm the operation's outputs look sane.",
    NodeKind.LOSS: "Confirm the loss decreases on a smoke batch.",
    NodeKind.OPTIMIZER: "Confirm hyperparameters match the paper.",
    NodeKind.EVALUATION: "Confirm metrics land near the reported values.",
    NodeKind.OUTPUT: "Confirm outputs cover every reported result.",
}


def order_nodes(graph: MethodologyGraph) -> list[GraphNode]:
    """Return nodes in dependency order, stable by declaration order."""
    by_id = {node.id: node for node in graph.nodes}
    adjacency: dict[str, list[str]] = defaultdict(list)
    indegree = {node.id: 0 for node in graph.nodes}
    for edge in graph.edges:
        if edge.source not in by_id or edge.target not in by_id:
            continue
        if edge.source == edge.target:
            continue
        adjacency[edge.source].append(edge.target)
        indegree[edge.target] += 1
    queue: deque[str] = deque(node.id for node in graph.nodes if indegree[node.id] == 0)
    ordered: list[GraphNode] = []
    while queue:
        current = queue.popleft()
        ordered.append(by_id[current])
        for neighbor in adjacency[current]:
            indegree[neighbor] -= 1
            if indegree[neighbor] == 0:
                queue.append(neighbor)
    if len(ordered) != len(graph.nodes):
        # Cyclic: declaration order is the deterministic fallback.
        return list(graph.nodes)
    return ordered


def _shape_text(shape: tuple[int | None, ...] | None) -> str | None:
    """Render an optional shape tuple, with None as '?'."""
    if shape is None:
        return None
    return "(" + ", ".join("?" if dim is None else str(dim) for dim in shape) + ")"


def step_for_node(seq: int, node: GraphNode) -> ReplicationStep:
    """Build one replication step for a node."""
    verb = _ACTION_VERBS[node.kind]
    action = f"{verb} '{node.label}' ({node.id})."
    if node.description:
        first_sentence = node.description.split(".")[0].strip()
        if first_sentence:
            action += f" {first_sentence}."
    if node.config:
        keys = ", ".join(sorted(str(key) for key in node.config))
        action += f" Settings: {keys}."
    verify = [_VERIFY_HINTS[node.kind]]
    output_shape = _shape_text(node.output_shape)
    if output_shape is not None:
        verify.append(f"Check outputs match shape {output_shape}.")
    if node.evidence:
        count = len(node.evidence)
        verify.append(f"Cross-check against {count} cited evidence ref{'s' if count != 1 else ''}.")
    if node.confidence is not None:
        verify.append(f"Extraction confidence was {node.confidence:.0%}; verify by hand.")
    return ReplicationStep(
        seq=seq,
        node_id=node.id,
        label=node.label,
        kind=node.kind.value,
        action=action,
        verify=tuple(verify),
    )


def build_replication_plan(graph: MethodologyGraph) -> ReplicationPlan:
    """Build the ordered replication plan for one graph revision."""
    steps = tuple(step_for_node(seq, node) for seq, node in enumerate(order_nodes(graph), 1))
    return ReplicationPlan(
        project_id=graph.project_id,
        graph_id=graph.graph_id,
        version=graph.version,
        steps=steps,
    )


def plan_for_latest_revision(
    session: Session, *, project_id: str, graph_id: str
) -> ReplicationPlan:
    """Build the replication plan for a graph's latest revision."""
    record = repository.get_latest_graph_revision(
        session, project_id=project_id, graph_id=graph_id
    )
    if record is None:
        raise BizoraError(ErrorCode.RESOURCE_NOT_FOUND, "Graph not found.")
    return build_replication_plan(MethodologyGraph.model_validate(record.graph_payload))
