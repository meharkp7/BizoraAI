"""Live run-telemetry streaming contracts (Phase 7, R7/R8).

Rule zero applies: nothing here enumerates domains, papers, parts, or
metric names. Event payloads carry free-text identifiers produced by packs
and adapters; this module only validates shape, bounds, and honesty
labelling (measured vs paper-reported vs illustrative).

Event flow: the execution worker publishes one :class:`TelemetryEvent`
per step, metric sample, log line, pack signal, or lifecycle transition.
The streaming router replays buffered events and then tails live ones
over Server-Sent Events. Paper-reported numbers travel in
:class:`PaperReportedMetric` and are merged with measured comparisons
only through :class:`ComparisonWithPaperReport`, which keeps the two
sources in separate fields.
"""

import math
from enum import StrEnum

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from bizora.contracts.comparison import RunComparison
from bizora.contracts.run import RunState


class TelemetryEventKind(StrEnum):
    """The payload variant carried by one telemetry event."""

    STEP = "step"
    METRIC = "metric"
    LOG = "log"
    PACK_SIGNAL = "pack_signal"
    STATE = "state"


class VisualProvenance(StrEnum):
    """Honesty label for a visual run element (R8).

    Live telemetry is always ``measured``. Placeholders and generated
    stand-ins are ``illustrative``. Values that depend on an unverified
    assumption (for example that a paper-reported number is comparable
    to a measured one) are ``assumed``.
    """

    MEASURED = "measured"
    ASSUMED = "assumed"
    ILLUSTRATIVE = "illustrative"


class TelemetryLogLevel(StrEnum):
    """Severity of one streamed log record."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class TelemetryStep(BaseModel):
    """One execution progress marker within a run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    step_index: int = Field(ge=0)
    label: str = Field(default="", max_length=200)
    total_steps: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_step_bounds(self) -> "TelemetryStep":
        """Reject a step index that exceeds its declared total."""
        if self.total_steps is not None and self.step_index >= self.total_steps:
            raise ValueError("step_index must be below total_steps.")
        return self


class TelemetryMetricSample(BaseModel):
    """One live metric value observed during a run (measured)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metric_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    value: float
    unit: str | None = Field(default=None, max_length=32)
    step_index: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_finite_value(self) -> "TelemetryMetricSample":
        """Reject non-finite live values; they cannot drive a chart."""
        if not math.isfinite(self.value):
            raise ValueError("Metric values must be finite.")
        return self


class TelemetryLogRecord(BaseModel):
    """One streamed log line from a running adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    level: TelemetryLogLevel
    message: str = Field(min_length=1, max_length=2000)
    step_index: int | None = Field(default=None, ge=0)


class PackSignalSample(BaseModel):
    """One pack-specific signal vector (voltages, activations, ...).

    The signal vocabulary is pack data, never an enum here: any pack
    may publish any signal id. Consumers render the label, unit, and
    values without interpreting the signal's physical meaning.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    signal_id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=200)
    values: tuple[float, ...] = Field(min_length=1, max_length=4096)
    unit: str | None = Field(default=None, max_length=32)
    node_ids: tuple[str, ...] = Field(default=(), max_length=256)

    @model_validator(mode="after")
    def validate_signal_values(self) -> "PackSignalSample":
        """Reject non-finite samples and blank node references."""
        for value in self.values:
            if not math.isfinite(value):
                raise ValueError("Signal values must be finite.")
        for node_id in self.node_ids:
            if not node_id or len(node_id) > 128:
                raise ValueError("Signal node ids must be 1 to 128 characters.")
        return self


class RunStatePayload(BaseModel):
    """One lifecycle transition observed for a streamed run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    state: RunState
    error: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_error_state(self) -> "RunStatePayload":
        """Allow error text only on failed or cancelled runs."""
        if self.error is not None and self.state not in (
            RunState.FAILED,
            RunState.CANCELLED,
        ):
            raise ValueError("Only failed or cancelled states may carry error text.")
        return self


class TelemetryEvent(BaseModel):
    """One sequenced envelope in a run's telemetry stream."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1, max_length=128)
    seq: int = Field(ge=0)
    emitted_at: AwareDatetime
    kind: TelemetryEventKind
    provenance: VisualProvenance = VisualProvenance.MEASURED
    step: TelemetryStep | None = None
    metric: TelemetryMetricSample | None = None
    log: TelemetryLogRecord | None = None
    pack_signal: PackSignalSample | None = None
    state: RunStatePayload | None = None

    @model_validator(mode="after")
    def validate_kind_payload(self) -> "TelemetryEvent":
        """Require exactly the payload matching the event kind."""
        payloads = {
            TelemetryEventKind.STEP: self.step,
            TelemetryEventKind.METRIC: self.metric,
            TelemetryEventKind.LOG: self.log,
            TelemetryEventKind.PACK_SIGNAL: self.pack_signal,
            TelemetryEventKind.STATE: self.state,
        }
        for kind, payload in payloads.items():
            expected = kind == self.kind
            if expected and payload is None:
                raise ValueError(f"A '{kind.value}' event requires its payload.")
            if not expected and payload is not None:
                raise ValueError(f"A '{self.kind.value}' event must not carry '{kind.value}' data.")
        return self


class PaperReportedMetric(BaseModel):
    """One number quoted from the paper, kept separate from measured data.

    ``raw_value`` preserves the printed text; ``value`` holds a parsed
    numeric form only when parsing is unambiguous. At least one
    grounding pointer (table, page, quote, or locator) is required so a
    reported number is never shown without its evidence.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=128)
    raw_value: str = Field(min_length=1, max_length=128)
    value: float | None = None
    unit: str | None = Field(default=None, max_length=32)
    source_id: str = Field(min_length=1, max_length=128)
    table_id: str | None = Field(default=None, min_length=1, max_length=128)
    page: int | None = Field(default=None, ge=1)
    quote: str | None = Field(default=None, max_length=2000)
    locator: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def validate_reported_grounding(self) -> "PaperReportedMetric":
        """Require evidence and a finite parsed value when present."""
        if self.value is not None and not math.isfinite(self.value):
            raise ValueError("Parsed reported values must be finite.")
        if (
            self.table_id is None
            and self.page is None
            and self.quote is None
            and self.locator is None
        ):
            raise ValueError("A paper-reported metric requires a table, page, quote, or locator.")
        return self


class ReportedComparisonRow(BaseModel):
    """One metric row joining measured values with paper-reported ones.

    Measured values (ours, from real runs) and reported values (theirs,
    quoted from the paper) live in separate fields and must be rendered
    in separate columns; comparability between them is an assumption
    the UI must label, never a fact.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=128)
    baseline_measured: float | None = None
    variant_measured: float | None = None
    reported: tuple[PaperReportedMetric, ...] = ()

    @model_validator(mode="after")
    def validate_row_values(self) -> "ReportedComparisonRow":
        """Reject non-finite measured values and misfiled reports."""
        for label, candidate in (
            ("baseline_measured", self.baseline_measured),
            ("variant_measured", self.variant_measured),
        ):
            if candidate is not None and not math.isfinite(candidate):
                raise ValueError(f"{label} must be finite when present.")
        for entry in self.reported:
            if entry.name != self.name:
                raise ValueError("Reported entries must match their row's metric name.")
        return self


class ComparisonWithPaperReport(BaseModel):
    """A measured run comparison plus separately-kept paper numbers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    comparison: RunComparison
    reported: tuple[PaperReportedMetric, ...] = ()
    rows: tuple[ReportedComparisonRow, ...] = ()

    @model_validator(mode="after")
    def validate_row_coverage(self) -> "ComparisonWithPaperReport":
        """Require rows to cover exactly the union of metric names."""
        expected = {metric.name for metric in self.comparison.metrics}
        expected.update(entry.name for entry in self.reported)
        actual = [row.name for row in self.rows]
        if len(actual) != len(set(actual)):
            raise ValueError("Comparison rows must not repeat a metric name.")
        if set(actual) != expected:
            raise ValueError("Comparison rows must cover every measured and reported name.")
        return self
