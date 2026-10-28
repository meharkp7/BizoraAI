"""Builders for validated telemetry events.

The execution worker (owner wiring) calls :meth:`TelemetryBus.next_seq`
and then one builder per observation. Builders take plain arguments and
return a validated :class:`TelemetryEvent`; invalid input raises a
pydantic ``ValidationError`` instead of publishing a malformed event.
"""

from collections.abc import Sequence
from datetime import UTC, datetime

from bizora.contracts.run import RunState
from bizora.contracts.streaming import (
    PackSignalSample,
    RunStatePayload,
    TelemetryEvent,
    TelemetryEventKind,
    TelemetryLogLevel,
    TelemetryLogRecord,
    TelemetryMetricSample,
    TelemetryStep,
    VisualProvenance,
)


def utcnow() -> datetime:
    """Return the current timezone-aware UTC time."""
    return datetime.now(UTC)


def make_step_event(
    run_id: str,
    seq: int,
    step_index: int,
    *,
    label: str = "",
    total_steps: int | None = None,
    emitted_at: datetime | None = None,
    provenance: VisualProvenance = VisualProvenance.MEASURED,
) -> TelemetryEvent:
    """Build one validated execution-progress event."""
    return TelemetryEvent(
        run_id=run_id,
        seq=seq,
        emitted_at=emitted_at or utcnow(),
        kind=TelemetryEventKind.STEP,
        provenance=provenance,
        step=TelemetryStep(
            step_index=step_index,
            label=label,
            total_steps=total_steps,
        ),
    )


def make_metric_event(
    run_id: str,
    seq: int,
    metric_id: str,
    name: str,
    value: float,
    *,
    unit: str | None = None,
    step_index: int | None = None,
    emitted_at: datetime | None = None,
    provenance: VisualProvenance = VisualProvenance.MEASURED,
) -> TelemetryEvent:
    """Build one validated live-metric event."""
    return TelemetryEvent(
        run_id=run_id,
        seq=seq,
        emitted_at=emitted_at or utcnow(),
        kind=TelemetryEventKind.METRIC,
        provenance=provenance,
        metric=TelemetryMetricSample(
            metric_id=metric_id,
            name=name,
            value=value,
            unit=unit,
            step_index=step_index,
        ),
    )


def make_log_event(
    run_id: str,
    seq: int,
    level: TelemetryLogLevel,
    message: str,
    *,
    step_index: int | None = None,
    emitted_at: datetime | None = None,
    provenance: VisualProvenance = VisualProvenance.MEASURED,
) -> TelemetryEvent:
    """Build one validated streamed-log event."""
    return TelemetryEvent(
        run_id=run_id,
        seq=seq,
        emitted_at=emitted_at or utcnow(),
        kind=TelemetryEventKind.LOG,
        provenance=provenance,
        log=TelemetryLogRecord(
            level=level,
            message=message,
            step_index=step_index,
        ),
    )


def make_pack_signal_event(
    run_id: str,
    seq: int,
    signal_id: str,
    label: str,
    values: Sequence[float],
    *,
    unit: str | None = None,
    node_ids: Sequence[str] = (),
    emitted_at: datetime | None = None,
    provenance: VisualProvenance = VisualProvenance.MEASURED,
) -> TelemetryEvent:
    """Build one validated pack-signal event.

    ``signal_id`` and ``label`` are free pack vocabulary; nothing here
    interprets their physical meaning.
    """
    return TelemetryEvent(
        run_id=run_id,
        seq=seq,
        emitted_at=emitted_at or utcnow(),
        kind=TelemetryEventKind.PACK_SIGNAL,
        provenance=provenance,
        pack_signal=PackSignalSample(
            signal_id=signal_id,
            label=label,
            values=tuple(values),
            unit=unit,
            node_ids=tuple(node_ids),
        ),
    )


def make_state_event(
    run_id: str,
    seq: int,
    state: RunState,
    *,
    error: str | None = None,
    emitted_at: datetime | None = None,
    provenance: VisualProvenance = VisualProvenance.MEASURED,
) -> TelemetryEvent:
    """Build one validated lifecycle-transition event."""
    return TelemetryEvent(
        run_id=run_id,
        seq=seq,
        emitted_at=emitted_at or utcnow(),
        kind=TelemetryEventKind.STATE,
        provenance=provenance,
        state=RunStatePayload(state=state, error=error),
    )
