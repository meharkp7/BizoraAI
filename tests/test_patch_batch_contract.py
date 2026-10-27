import pytest
from pydantic import ValidationError

from bizora.contracts.patches import (
    GraphPatch,
    GraphPatchBatch,
    PatchOperation,
)


def make_patch(
    operation: PatchOperation,
    *,
    patch_id: str = "patch-1",
    base_graph_id: str = "graph-1",
    base_version: int = 1,
    requested_by: str = "test-user",
) -> GraphPatch:
    """Create a patch for batch-contract tests."""
    return GraphPatch(
        patch_id=patch_id,
        base_graph_id=base_graph_id,
        base_version=base_version,
        operation=operation,
        rationale="Test batch edit",
        requested_by=requested_by,
    )


def test_uniform_batch_passes() -> None:
    batch = GraphPatchBatch(
        patches=(
            make_patch(PatchOperation.REMOVE_EDGE, patch_id="p1"),
            make_patch(PatchOperation.REMOVE_NODE, patch_id="p2"),
        )
    )
    assert len(batch.patches) == 2


def test_empty_batch_rejected() -> None:
    with pytest.raises(ValidationError):
        GraphPatchBatch(patches=())


def test_oversized_batch_rejected() -> None:
    with pytest.raises(ValidationError):
        GraphPatchBatch(
            patches=tuple(
                make_patch(PatchOperation.REMOVE_EDGE, patch_id=f"p{i}")
                for i in range(51)
            )
        )


def test_mixed_base_graph_rejected() -> None:
    with pytest.raises(ValidationError, match="same base revision"):
        GraphPatchBatch(
            patches=(
                make_patch(PatchOperation.REMOVE_EDGE, patch_id="p1"),
                make_patch(
                    PatchOperation.REMOVE_EDGE,
                    patch_id="p2",
                    base_graph_id="other",
                ),
            )
        )


def test_mixed_base_version_rejected() -> None:
    with pytest.raises(ValidationError, match="same base revision"):
        GraphPatchBatch(
            patches=(
                make_patch(PatchOperation.REMOVE_EDGE, patch_id="p1"),
                make_patch(
                    PatchOperation.REMOVE_EDGE,
                    patch_id="p2",
                    base_version=2,
                ),
            )
        )


def test_mixed_actor_rejected() -> None:
    with pytest.raises(ValidationError, match="one requested_by actor"):
        GraphPatchBatch(
            patches=(
                make_patch(PatchOperation.REMOVE_EDGE, patch_id="p1"),
                make_patch(
                    PatchOperation.REMOVE_EDGE,
                    patch_id="p2",
                    requested_by="someone-else",
                ),
            )
        )
