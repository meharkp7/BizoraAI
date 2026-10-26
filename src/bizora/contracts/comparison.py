"""Baseline comparison contracts with explicit compatibility rules."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ComparisonVerdict(StrEnum):
    VALID = "valid"
    CONFOUNDED = "confounded"
    INVALID = "invalid"


class MetricComparison(BaseModel):
    """One shared measured metric compared across two runs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=128)
    baseline_value: float
    variant_value: float
    absolute_change: float
    relative_change: float | None = None
    relative_undefined_reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_change_consistency(self) -> "MetricComparison":
        if self.relative_change is None and self.relative_undefined_reason is None:
            raise ValueError(
                "A missing relative change requires an undefined reason."
            )
        if (
            self.relative_change is not None
            and self.relative_undefined_reason is not None
        ):
            raise ValueError(
                "A defined relative change must not carry an undefined reason."
            )
        return self


class SkippedMetric(BaseModel):
    """A metric name excluded from comparison, with its reason."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=500)


class ConfigDifference(BaseModel):
    """One differing configuration field between two runs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str = Field(min_length=1, max_length=128)
    baseline: Any
    variant: Any


class GraphPair(BaseModel):
    """The exact graph revisions behind a comparison."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    baseline_graph_id: str = Field(min_length=1, max_length=128)
    baseline_graph_version: int = Field(ge=1)
    variant_graph_id: str = Field(min_length=1, max_length=128)
    variant_graph_version: int = Field(ge=1)


class RunComparison(BaseModel):
    """Baseline-to-variant comparison with its validity assessment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    baseline_run_id: str = Field(min_length=1, max_length=128)
    variant_run_id: str = Field(min_length=1, max_length=128)
    verdict: ComparisonVerdict
    reasons: tuple[str, ...] = ()
    graph: GraphPair
    metrics: tuple[MetricComparison, ...] = ()
    skipped_metrics: tuple[SkippedMetric, ...] = ()
    config_differences: tuple[ConfigDifference, ...] = ()

    @model_validator(mode="after")
    def validate_verdict_consistency(self) -> "RunComparison":
        if self.verdict == ComparisonVerdict.VALID and self.reasons:
            raise ValueError("A valid comparison must not carry caveat reasons.")
        if self.verdict in (
            ComparisonVerdict.CONFOUNDED,
            ComparisonVerdict.INVALID,
        ) and not self.reasons:
            raise ValueError(
                "A confounded or invalid comparison requires reasons."
            )
        if self.verdict == ComparisonVerdict.INVALID and self.metrics:
            raise ValueError("An invalid comparison must not report metric changes.")
        return self
