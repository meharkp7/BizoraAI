
"""Append-only ledger for model and execution spend, plus cap enforcement.

Every provider call that can cost money appends one row at its call site;
calls whose provider reports no usage still append a row with null tokens
so dashboards show them as unmetered instead of pretending they were free.
Costs are estimates from the configured per-token rates — every consumer
labels them estimated — and caps compare against estimated spend only.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bizora.contracts.usage import (
    RunUsage,
    UsageCaps,
    UsageDay,
    UsageSummary,
    UsageTotals,
)
from bizora.core.config import Settings
from bizora.core.errors import BizoraError, ErrorCode
from bizora.db.models import ExperimentRunRecord, UsageRecordRow


def utc_midnight(now: datetime) -> datetime:
    """Return midnight UTC on the day containing `now`."""
    return now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def _as_utc(value: datetime) -> datetime:
    """Return an aware UTC timestamp, assuming UTC when naive (sqlite)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def estimate_cost(
    input_tokens: int | None,
    output_tokens: int | None,
    *,
    usd_per_1k_input: float,
    usd_per_1k_output: float,
) -> float | None:
    """Estimate one call's cost, or None when both counts are unknown."""
    if input_tokens is None and output_tokens is None:
        return None
    return (input_tokens or 0) / 1000 * usd_per_1k_input + (
        output_tokens or 0
    ) / 1000 * usd_per_1k_output


def record_usage(
    session: Session,
    *,
    kind: str,
    provider: str,
    model: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cost_usd_estimated: float | None = None,
    run_id: str | None = None,
    project_id: str | None = None,
    graph_id: str | None = None,
) -> UsageRecordRow:
    """Append one usage row and commit it: the call happened and may bill."""
    row = UsageRecordRow(
        kind=kind,
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd_estimated=cost_usd_estimated,
        run_id=run_id,
        project_id=project_id,
        graph_id=graph_id,
    )
    session.add(row)
    session.commit()
    return row


def record_provider_usage(
    session: Session,
    settings: Settings,
    *,
    kind: str,
    provider: Any,
    run_id: str | None = None,
    project_id: str | None = None,
    graph_id: str | None = None,
) -> UsageRecordRow:
    """Record one provider call from its `last_usage`, metered or not."""
    usage = getattr(provider, "last_usage", None)
    provider_name = str(getattr(provider, "provider_name", type(provider).__name__))
    input_tokens = getattr(usage, "input_tokens", None) if usage is not None else None
    output_tokens = getattr(usage, "output_tokens", None) if usage is not None else None
    model = getattr(usage, "model", None) if usage is not None else None
    return record_usage(
        session,
        kind=kind,
        provider=provider_name,
        model=str(model) if model is not None else None,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd_estimated=estimate_cost(
            input_tokens,
            output_tokens,
            usd_per_1k_input=settings.usd_per_1k_input,
            usd_per_1k_output=settings.usd_per_1k_output,
        ),
        run_id=run_id,
        project_id=project_id,
        graph_id=graph_id,
    )


def spend_since(session: Session, since: datetime) -> tuple[float, int, int]:
    """Return (estimated spend, calls, unmetered calls) at or after `since`."""
    rows = session.scalars(
        select(UsageRecordRow).where(UsageRecordRow.created_at >= since)
    ).all()
    total = sum(row.cost_usd_estimated or 0.0 for row in rows)
    unmetered = sum(1 for row in rows if row.cost_usd_estimated is None)
    return total, len(rows), unmetered


def spend_for_run(session: Session, run_id: str) -> float | None:
    """Return one run's estimated spend, or None when nothing is metered."""
    rows = session.scalars(
        select(UsageRecordRow).where(UsageRecordRow.run_id == run_id)
    ).all()
    metered = [row.cost_usd_estimated for row in rows if row.cost_usd_estimated is not None]
    if not rows or not metered:
        return None
    return sum(metered)


def runs_started_since(session: Session, since: datetime) -> int:
    """Count experiment runs created at or after `since`."""
    result = session.execute(
        select(func.count(ExperimentRunRecord.id)).where(
            ExperimentRunRecord.created_at >= since
        )
    )
    return int(result.scalar() or 0)


def check_spend_caps(session: Session, settings: Settings, *, now: datetime) -> None:
    """Block metered model calls once the estimated daily cap is reached."""
    if settings.daily_spend_cap_usd <= 0:
        return
    total, _, _ = spend_since(session, utc_midnight(now))
    if total >= settings.daily_spend_cap_usd:
        raise BizoraError(
            ErrorCode.SPEND_LIMIT_EXCEEDED,
            f"Estimated daily spend reached the ${settings.daily_spend_cap_usd:.2f} cap.",
            details={"estimated_spend_usd": round(total, 4)},
        )


def check_run_caps(
    session: Session, settings: Settings, *, now: datetime, run_id: str
) -> None:
    """Block run execution past the daily count or known run-spend cap."""
    if settings.max_runs_per_day > 0:
        started = runs_started_since(session, utc_midnight(now))
        if started >= settings.max_runs_per_day:
            raise BizoraError(
                ErrorCode.EXPERIMENT_LIMIT_EXCEEDED,
                f"Started runs reached the daily limit of {settings.max_runs_per_day}.",
                details={"runs_started_today": started},
            )
    if settings.run_spend_cap_usd > 0:
        spent = spend_for_run(session, run_id)
        if spent is not None and spent >= settings.run_spend_cap_usd:
            raise BizoraError(
                ErrorCode.SPEND_LIMIT_EXCEEDED,
                f"Estimated run spend reached the ${settings.run_spend_cap_usd:.2f} cap.",
                details={"estimated_spend_usd": round(spent, 4)},
            )


def summarize_usage(
    session: Session, settings: Settings, *, days: int, now: datetime
) -> UsageSummary:
    """Bucket the last `days` UTC days of usage plus window totals."""
    start = utc_midnight(now) - timedelta(days=days - 1)
    rows = session.scalars(
        select(UsageRecordRow)
        .where(UsageRecordRow.created_at >= start)
        .order_by(UsageRecordRow.created_at.asc())
    ).all()
    buckets: dict[str, UsageDay] = {}
    for offset in range(days):
        day = (start + timedelta(days=offset)).date().isoformat()
        buckets[day] = UsageDay(
            date=day,
            calls=0,
            input_tokens=0,
            output_tokens=0,
            cost_usd_estimated=0.0,
            unmetered_calls=0,
        )
    for row in rows:
        day = _as_utc(row.created_at).date().isoformat()
        bucket = buckets.get(day)
        if bucket is None:
            continue
        buckets[day] = UsageDay(
            date=day,
            calls=bucket.calls + 1,
            input_tokens=bucket.input_tokens + (row.input_tokens or 0),
            output_tokens=bucket.output_tokens + (row.output_tokens or 0),
            cost_usd_estimated=bucket.cost_usd_estimated + (row.cost_usd_estimated or 0.0),
            unmetered_calls=bucket.unmetered_calls + (1 if row.cost_usd_estimated is None else 0),
        )
    ordered = [buckets[day] for day in sorted(buckets)]
    totals = UsageTotals(
        calls=sum(day.calls for day in ordered),
        input_tokens=sum(day.input_tokens for day in ordered),
        output_tokens=sum(day.output_tokens for day in ordered),
        cost_usd_estimated=sum(day.cost_usd_estimated for day in ordered),
        unmetered_calls=sum(day.unmetered_calls for day in ordered),
    )
    return UsageSummary(
        generated_at=now.astimezone(UTC),
        days=ordered,
        totals=totals,
        caps=UsageCaps(
            daily_cap_usd=settings.daily_spend_cap_usd,
            run_cap_usd=settings.run_spend_cap_usd,
            max_runs_per_day=settings.max_runs_per_day,
        ),
    )


def summarize_run_usage(session: Session, *, limit: int) -> list[RunUsage]:
    """Aggregate usage by run, most recently used first."""
    rows = session.scalars(
        select(UsageRecordRow)
        .where(UsageRecordRow.run_id.is_not(None))
        .order_by(UsageRecordRow.created_at.desc())
    ).all()
    aggregates: dict[str, dict[str, Any]] = {}
    for row in rows:
        assert row.run_id is not None
        entry = aggregates.setdefault(
            row.run_id,
            {
                "project_id": row.project_id,
                "graph_id": row.graph_id,
                "calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost": 0.0,
                "metered": False,
                "last_used_at": None,
            },
        )
        entry["calls"] += 1
        entry["input_tokens"] += row.input_tokens or 0
        entry["output_tokens"] += row.output_tokens or 0
        if row.cost_usd_estimated is not None:
            entry["cost"] += row.cost_usd_estimated
            entry["metered"] = True
        if entry["last_used_at"] is None:
            entry["last_used_at"] = _as_utc(row.created_at)
        if entry["project_id"] is None:
            entry["project_id"] = row.project_id
        if entry["graph_id"] is None:
            entry["graph_id"] = row.graph_id
    summaries: list[RunUsage] = []
    for run_id, entry in aggregates.items():
        metered = bool(entry["metered"])
        summaries.append(
            RunUsage(
                run_id=run_id,
                project_id=entry["project_id"],
                graph_id=entry["graph_id"],
                calls=int(entry["calls"]),
                input_tokens=int(entry["input_tokens"]),
                output_tokens=int(entry["output_tokens"]),
                cost_usd_estimated=float(entry["cost"]) if metered else None,
                unmetered=not metered,
                last_used_at=entry["last_used_at"],
            )
        )
    summaries.sort(
        key=lambda summary: summary.last_used_at or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    return summaries[:limit]
