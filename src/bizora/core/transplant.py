"""Pure transplant planner: merge source nodes into a target graph.

The planner never touches the database: it takes two validated graphs
and returns the merged node/edge tuples plus the move report. Id
collisions rename with a `-tN` suffix; edges with one endpoint left
behind are cut and counted.
"""

from dataclasses import dataclass

from bizora.contracts.graph import GraphEdge, GraphNode, MethodologyGraph


@dataclass(frozen=True)
class TransplantPlan:
    """Merged content plus the honest move report."""

    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    source_ids: tuple[str, ...]
    title: str
    added_node_ids: tuple[str, ...]
    renamed: dict[str, str]
    copied_edge_count: int
    dropped_edge_count: int


def _fresh_id(wanted: str, taken: set[str]) -> str:
    """Return `wanted`, or the first `-tN` suffix not yet taken."""
    if wanted not in taken:
        return wanted
    suffix = 1
    while f"{wanted}-t{suffix}" in taken:
        suffix += 1
    return f"{wanted}-t{suffix}"


def plan_transplant(
    source_graph: MethodologyGraph,
    target_graph: MethodologyGraph,
    node_ids: list[str],
) -> TransplantPlan:
    """Plan copying `node_ids` from source into target.

    Raises KeyError with the missing ids when the source lacks any.
    """
    wanted = list(dict.fromkeys(node_ids))
    by_id = {node.id: node for node in source_graph.nodes}
    missing = [node_id for node_id in wanted if node_id not in by_id]
    if missing:
        raise KeyError(missing)

    taken_nodes = {node.id for node in target_graph.nodes}
    taken_edges = {edge.id for edge in target_graph.edges}
    id_map: dict[str, str] = {}
    renamed: dict[str, str] = {}
    new_nodes: list[GraphNode] = []
    for node_id in wanted:
        fresh = _fresh_id(node_id, taken_nodes)
        taken_nodes.add(fresh)
        id_map[node_id] = fresh
        if fresh != node_id:
            renamed[node_id] = fresh
        new_nodes.append(by_id[node_id].model_copy(update={"id": fresh}))

    moving = set(wanted)
    new_edges: list[GraphEdge] = []
    dropped = 0
    for edge in source_graph.edges:
        inside = [endpoint in moving for endpoint in (edge.source, edge.target)]
        if all(inside):
            fresh_edge = _fresh_id(edge.id, taken_edges)
            taken_edges.add(fresh_edge)
            new_edges.append(
                edge.model_copy(
                    update={
                        "id": fresh_edge,
                        "source": id_map[edge.source],
                        "target": id_map[edge.target],
                    }
                )
            )
        elif any(inside):
            dropped += 1

    merged_sources = list(target_graph.source_ids)
    for source_id in source_graph.source_ids:
        if source_id not in merged_sources:
            merged_sources.append(source_id)

    count = len(wanted)
    title = (
        f"Transplant {count} block{'s' if count != 1 else ''} "
        f"from {source_graph.graph_id}"
    )
    return TransplantPlan(
        nodes=tuple(target_graph.nodes) + tuple(new_nodes),
        edges=tuple(target_graph.edges) + tuple(new_edges),
        source_ids=tuple(merged_sources),
        title=title,
        added_node_ids=tuple(id_map[node_id] for node_id in wanted),
        renamed=renamed,
        copied_edge_count=len(new_edges),
        dropped_edge_count=dropped,
    )
