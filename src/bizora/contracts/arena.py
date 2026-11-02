"""Cross-graph arena comparison contracts.

The arena lines up two graph revisions head-to-head: structure counts,
shared entity labels, and the papers' reported numbers side by side.
Every figure comes from stored revisions and tables; nothing is
inferred or generated.
"""

from pydantic import BaseModel, ConfigDict, Field


class ArenaSideRef(BaseModel):
    """One side of the arena: a graph at an optional pinned version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str = Field(min_length=1, max_length=128)
    graph_id: str = Field(min_length=1, max_length=128)
    version: int | None = Field(default=None, ge=1)


class ArenaCompareRequest(BaseModel):
    """Compare two graph revisions head-to-head."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    a: ArenaSideRef
    b: ArenaSideRef


class ArenaSideSummary(BaseModel):
    """Which revision actually anchored one side of the arena."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str = Field(min_length=1, max_length=128)
    graph_id: str = Field(min_length=1, max_length=128)
    version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=300)


class ArenaStructureSide(BaseModel):
    """Node/edge counts for one side, totals plus by-kind."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    kinds: dict[str, int] = Field(default_factory=dict)


class ArenaLabelOverlap(BaseModel):
    """One entity label both sides share, with its node ids per side."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str = Field(min_length=1, max_length=300)
    a_node_ids: tuple[str, ...] = ()
    b_node_ids: tuple[str, ...] = ()


class ArenaUniqueLabel(BaseModel):
    """One entity label only one side has."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str = Field(min_length=1, max_length=300)
    node_ids: tuple[str, ...] = ()


class ArenaMetricValue(BaseModel):
    """One side's quoted value for a shared-or-single metric name."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    raw_value: str = Field(min_length=1, max_length=128)
    value: float | None = None
    unit: str | None = Field(default=None, max_length=32)


class ArenaMetricRow(BaseModel):
    """One metric name with both sides' quoted values (either may miss)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=128)
    a: ArenaMetricValue | None = None
    b: ArenaMetricValue | None = None


class ArenaComparison(BaseModel):
    """The full head-to-head result for two graph revisions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    a: ArenaSideSummary
    b: ArenaSideSummary
    structure_a: ArenaStructureSide
    structure_b: ArenaStructureSide
    shared_labels: tuple[ArenaLabelOverlap, ...] = ()
    unique_a: tuple[ArenaUniqueLabel, ...] = ()
    unique_b: tuple[ArenaUniqueLabel, ...] = ()
    metrics: tuple[ArenaMetricRow, ...] = ()
