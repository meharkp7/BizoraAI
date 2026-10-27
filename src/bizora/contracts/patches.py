"""Declarative, auditable graph-edit contracts; never executable code."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PatchOperation(StrEnum):
    ADD_NODE = "add_node"
    UPDATE_NODE_CONFIG = "update_node_config"
    REPLACE_NODE = "replace_node"
    ADD_EDGE = "add_edge"
    REMOVE_EDGE = "remove_edge"
    REMOVE_NODE = "remove_node"


class GraphPatch(BaseModel):
    """A requested change to a specific graph revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    patch_id: str = Field(min_length=1, max_length=128)
    base_graph_id: str = Field(min_length=1, max_length=128)
    base_version: int = Field(ge=1)
    operation: PatchOperation
    target_id: str | None = Field(default=None, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)
    rationale: str = Field(min_length=1, max_length=2000)
    requested_by: str = Field(min_length=1, max_length=128)


class GraphPatchBatch(BaseModel):
    """A set of patches applied atomically as one graph revision.

    All patches must target the same base revision and actor so the
    resulting revision keeps a single unambiguous parent and author.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    patches: tuple[GraphPatch, ...] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_uniform_base(self) -> "GraphPatchBatch":
        base_ids = {patch.base_graph_id for patch in self.patches}
        base_versions = {patch.base_version for patch in self.patches}
        actors = {patch.requested_by for patch in self.patches}
        if len(base_ids) != 1 or len(base_versions) != 1:
            raise ValueError(
                "all patches in a batch must target the same base revision"
            )
        if len(actors) != 1:
            raise ValueError(
                "all patches in a batch must share one requested_by actor"
            )
        return self
