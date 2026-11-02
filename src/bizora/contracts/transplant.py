"""Cross-graph transplant contracts.

A transplant copies nodes (plus the edges between them) from one graph
revision into another graph as a new head revision. Node ids that
collide are renamed with a numeric suffix; edges to nodes left behind
are cut and counted, never silently kept.
"""

from pydantic import BaseModel, ConfigDict, Field


class TransplantRequest(BaseModel):
    """Copy nodes from a source revision into this graph."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_project_id: str = Field(min_length=1, max_length=128)
    source_graph_id: str = Field(min_length=1, max_length=128)
    source_version: int | None = Field(default=None, ge=1)
    node_ids: list[str] = Field(min_length=1, max_length=20)
    created_by: str = Field(min_length=1, max_length=128)


class TransplantResponse(BaseModel):
    """The new head revision plus exactly what moved over."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str = Field(min_length=1, max_length=128)
    graph_id: str = Field(min_length=1, max_length=128)
    version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=300)
    added_node_ids: tuple[str, ...] = ()
    renamed: dict[str, str] = Field(default_factory=dict)
    copied_edge_count: int = Field(ge=0)
    dropped_edge_count: int = Field(ge=0)
