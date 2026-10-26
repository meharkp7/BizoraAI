"""Declarative, auditable graph-edit contracts; never executable code."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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
