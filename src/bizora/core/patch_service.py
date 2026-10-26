
"""Safe application of explicit, auditable methodology graph patches."""

from typing import Any

from pydantic import ValidationError

from bizora.contracts.graph import (
    GraphEdge,
    GraphNode,
    MethodologyGraph,
)
from bizora.contracts.patches import GraphPatch, PatchOperation
from bizora.core.errors import BizoraError, ErrorCode, GraphValidationError
from bizora.core.graph_service import GraphService


def _patch_error(
    message: str,
    *,
    details: dict[str, Any] | None = None,
) -> BizoraError:
    """Create a stable error for an invalid graph patch."""
    return BizoraError(
        ErrorCode.INVALID_GRAPH_PATCH,
        message,
        details=details,
    )


def _require_target(patch: GraphPatch) -> str:
    """Return the required target ID or reject the patch."""
    if patch.target_id is None:
        raise _patch_error(
            "This patch operation requires target_id.",
            details={"patch_id": patch.patch_id},
        )
    return patch.target_id


def _require_payload_keys(
    patch: GraphPatch,
    expected: set[str],
) -> None:
    """Require the exact payload fields for an operation."""
    actual = set(patch.payload)
    if actual != expected:
        raise _patch_error(
            "The patch payload has unexpected or missing fields.",
            details={
                "patch_id": patch.patch_id,
                "expected_fields": sorted(expected),
                "actual_fields": sorted(actual),
            },
        )


def _parse_node(patch: GraphPatch) -> GraphNode:
    """Validate a node supplied by a patch."""
    _require_payload_keys(patch, {"node"})
    value = patch.payload["node"]

    if not isinstance(value, dict):
        raise _patch_error("The node payload must be an object.")

    try:
        return GraphNode.model_validate(value)
    except ValidationError as exc:
        raise _patch_error(
            "The supplied node does not satisfy the graph contract.",
            details={"validation_errors": exc.errors(include_input=False)},
        ) from exc


def _parse_edge(patch: GraphPatch) -> GraphEdge:
    """Validate an edge supplied by a patch."""
    _require_payload_keys(patch, {"edge"})
    value = patch.payload["edge"]

    if not isinstance(value, dict):
        raise _patch_error("The edge payload must be an object.")

    try:
        return GraphEdge.model_validate(value)
    except ValidationError as exc:
        raise _patch_error(
            "The supplied edge does not satisfy the graph contract.",
            details={"validation_errors": exc.errors(include_input=False)},
        ) from exc


class GraphPatchService:
    """Apply one patch to a specific graph snapshot without mutating it."""

    @classmethod
    def apply_patch(
        cls,
        graph: MethodologyGraph,
        patch: GraphPatch,
    ) -> MethodologyGraph:
        """Return a validated next revision or raise a domain error."""
        if patch.base_graph_id != graph.graph_id:
            raise _patch_error(
                "The patch targets a different graph.",
                details={
                    "patch_id": patch.patch_id,
                    "expected_graph_id": graph.graph_id,
                    "base_graph_id": patch.base_graph_id,
                },
            )

        if patch.base_version != graph.version:
            raise BizoraError(
                ErrorCode.RESOURCE_CONFLICT,
                "The patch base version does not match the supplied graph.",
                details={
                    "patch_id": patch.patch_id,
                    "expected_version": graph.version,
                    "base_version": patch.base_version,
                },
            )

        GraphService.validate(graph)

        nodes = list(graph.nodes)
        edges = list(graph.edges)

        if patch.operation == PatchOperation.ADD_NODE:
            node = _parse_node(patch)
            if any(existing.id == node.id for existing in nodes):
                raise _patch_error(
                    "Cannot add a node with an existing ID.",
                    details={"node_id": node.id},
                )
            nodes.append(node)

        elif patch.operation == PatchOperation.UPDATE_NODE_CONFIG:
            target_id = _require_target(patch)
            _require_payload_keys(patch, {"config"})
            updates = patch.payload["config"]

            if not isinstance(updates, dict):
                raise _patch_error("The config payload must be an object.")

            index = next(
                (
                    i
                    for i, node in enumerate(nodes)
                    if node.id == target_id
                ),
                None,
            )
            if index is None:
                raise _patch_error(
                    "Cannot update a node that does not exist.",
                    details={"node_id": target_id},
                )

            current_node = nodes[index]
            merged_config = {
                **current_node.config,
                **updates,
            }
            node_data = current_node.model_dump(mode="python")
            node_data["config"] = merged_config

            try:
                nodes[index] = GraphNode.model_validate(node_data)
            except ValidationError as exc:
                raise _patch_error(
                    "The updated node configuration is invalid.",
                    details={
                        "node_id": target_id,
                        "validation_errors": exc.errors(
                            include_input=False
                        ),
                    },
                ) from exc

        elif patch.operation == PatchOperation.REPLACE_NODE:
            target_id = _require_target(patch)
            node = _parse_node(patch)

            if node.id != target_id:
                raise _patch_error(
                    "A replacement node must retain the target ID.",
                    details={
                        "target_id": target_id,
                        "replacement_id": node.id,
                    },
                )

            index = next(
                (
                    i
                    for i, existing in enumerate(nodes)
                    if existing.id == target_id
                ),
                None,
            )
            if index is None:
                raise _patch_error(
                    "Cannot replace a node that does not exist.",
                    details={"node_id": target_id},
                )
            nodes[index] = node

        elif patch.operation == PatchOperation.ADD_EDGE:
            edge = _parse_edge(patch)
            if any(existing.id == edge.id for existing in edges):
                raise _patch_error(
                    "Cannot add an edge with an existing ID.",
                    details={"edge_id": edge.id},
                )
            edges.append(edge)

        elif patch.operation == PatchOperation.REMOVE_EDGE:
            target_id = _require_target(patch)
            _require_payload_keys(patch, set())

            index = next(
                (
                    i
                    for i, edge in enumerate(edges)
                    if edge.id == target_id
                ),
                None,
            )
            if index is None:
                raise _patch_error(
                    "Cannot remove an edge that does not exist.",
                    details={"edge_id": target_id},
                )
            edges.pop(index)

        elif patch.operation == PatchOperation.REMOVE_NODE:
            target_id = _require_target(patch)
            _require_payload_keys(patch, set())

            if not any(node.id == target_id for node in nodes):
                raise _patch_error(
                    "Cannot remove a node that does not exist.",
                    details={"node_id": target_id},
                )

            connected_edges = [
                edge.id
                for edge in edges
                if edge.source == target_id or edge.target == target_id
            ]
            if connected_edges:
                raise _patch_error(
                    "Remove connected edges before removing this node.",
                    details={
                        "node_id": target_id,
                        "connected_edge_ids": connected_edges,
                    },
                )

            nodes = [node for node in nodes if node.id != target_id]

        try:
            return GraphService.create_revision(
                graph,
                created_by=patch.requested_by,
                nodes=tuple(nodes),
                edges=tuple(edges),
            )
        except GraphValidationError as exc:
            raise _patch_error(
                "The patch would produce an invalid methodology graph.",
                details=exc.details,
            ) from exc
