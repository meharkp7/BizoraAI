"""Measured-overlay channel: live run values per node and edge.

Every view renders from one methodology graph plus this separate
channel. The channel is empty until a real run fills it; views must
render identically with an empty overlay and decorate nodes and edges
when values arrive, with no rewrites in between.
"""

from pydantic import BaseModel, ConfigDict, Field


class OverlayValue(BaseModel):
    """One live measurement on a node or an edge."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    signal: str = Field(min_length=1, max_length=128)
    value: float = Field(description="Live measured value from the run.")
    unit: str | None = Field(default=None, max_length=32)


class MeasuredOverlay(BaseModel):
    """Live values for one graph revision, keyed by node and edge id."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str | None = Field(default=None, max_length=128)
    nodes: dict[str, tuple[OverlayValue, ...]] = Field(default_factory=dict)
    edges: dict[str, tuple[OverlayValue, ...]] = Field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        """True when no run has supplied any measurement yet."""
        return not self.nodes and not self.edges


EMPTY_OVERLAY = MeasuredOverlay()
