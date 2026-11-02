"""Tests for the usage ledger, spend caps, and usage endpoints."""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from tests.unit.test_papers_api import FakePaperProvider, make_pdf_bytes
from tests.unit.test_run_api import (  # noqa: F401
    client_with_db,
    create_run,
    make_config_payload,
    make_graph_payload,
)
from tests.unit.test_run_repository import make_run

__all__ = ["client_with_db"]

from bizora import api
from bizora.api import get_baseten_provider
from bizora.core.config import Settings
from bizora.core.errors import BizoraError, ErrorCode
from bizora.core.usage_ledger import (
    check_run_caps,
    check_spend_caps,
    estimate_cost,
    record_usage,
    spend_for_run,
    spend_since,
    summarize_run_usage,
    summarize_usage,
    utc_midnight,
)
from bizora.db.base import Base
from bizora.db.models import UsageRecordRow
from bizora.db.repository import save_experiment_run
from bizora.main import app


@pytest.fixture
def db_session() -> Iterator[Session]:
    """Create an isolated in-memory database for each test."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        yield session

    engine.dispose()


def _settings(**overrides: object) -> Settings:
    """Build settings with cap overrides and no .env file."""
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


def test_estimate_cost_returns_none_when_unmetered() -> None:
    assert (
        estimate_cost(None, None, usd_per_1k_input=0.003, usd_per_1k_output=0.015)
        is None
    )
    assert estimate_cost(
        1000, 1000, usd_per_1k_input=0.003, usd_per_1k_output=0.015
    ) == pytest.approx(0.018)


def test_spend_since_counts_unmetered_calls(db_session: Session) -> None:
    record_usage(db_session, kind="extraction", provider="muse", cost_usd_estimated=1.5)
    record_usage(db_session, kind="extraction", provider="baseten")

    total, calls, unmetered = spend_since(db_session, utc_midnight(datetime.now(UTC)))

    assert total == pytest.approx(1.5)
    assert calls == 2
    assert unmetered == 1


def test_spend_for_run_needs_metered_rows(db_session: Session) -> None:
    assert spend_for_run(db_session, "run-absent") is None

    record_usage(db_session, kind="run", provider="adapter", run_id="run-1")
    assert spend_for_run(db_session, "run-1") is None

    record_usage(
        db_session,
        kind="run",
        provider="adapter",
        run_id="run-1",
        cost_usd_estimated=0.5,
    )
    assert spend_for_run(db_session, "run-1") == pytest.approx(0.5)


def test_check_spend_caps_blocks_past_cap(db_session: Session) -> None:
    settings = _settings(BIZORA_DAILY_SPEND_CAP_USD=1.0)
    record_usage(db_session, kind="extraction", provider="muse", cost_usd_estimated=1.0)

    with pytest.raises(BizoraError) as exc_info:
        check_spend_caps(db_session, settings, now=datetime.now(UTC))

    assert exc_info.value.code == ErrorCode.SPEND_LIMIT_EXCEEDED


def test_check_spend_caps_allows_disabled_cap(db_session: Session) -> None:
    settings = _settings(BIZORA_DAILY_SPEND_CAP_USD=0.0)
    record_usage(db_session, kind="extraction", provider="muse", cost_usd_estimated=100.0)

    check_spend_caps(db_session, settings, now=datetime.now(UTC))


def test_check_run_caps_blocks_past_daily_count(db_session: Session) -> None:
    settings = _settings(BIZORA_MAX_RUNS_PER_DAY=1)
    save_experiment_run(
        db_session, make_run(run_id="run-1", created_at=datetime.now(UTC))
    )
    db_session.commit()

    with pytest.raises(BizoraError) as exc_info:
        check_run_caps(db_session, settings, now=datetime.now(UTC), run_id="run-2")

    assert exc_info.value.code == ErrorCode.EXPERIMENT_LIMIT_EXCEEDED


def test_check_run_caps_ignores_unmetered_run_spend(db_session: Session) -> None:
    settings = _settings(BIZORA_RUN_SPEND_CAP_USD=0.01, BIZORA_MAX_RUNS_PER_DAY=0)
    record_usage(db_session, kind="run", provider="adapter", run_id="run-1")

    check_run_caps(db_session, settings, now=datetime.now(UTC), run_id="run-1")


def test_summarize_usage_buckets_days(db_session: Session) -> None:
    now = datetime.now(UTC)
    record_usage(db_session, kind="extraction", provider="muse", cost_usd_estimated=2.0)
    record_usage(db_session, kind="tables", provider="baseten")
    settings = _settings()

    summary = summarize_usage(db_session, settings, days=7, now=now)

    assert len(summary.days) == 7
    assert summary.totals.calls == 2
    assert summary.totals.cost_usd_estimated == pytest.approx(2.0)
    assert summary.totals.unmetered_calls == 1
    assert summary.days[-1].date == utc_midnight(now).date().isoformat()
    assert summary.days[-1].calls == 2
    assert summary.caps.daily_cap_usd == settings.daily_spend_cap_usd
    assert summary.estimated is True
    assert summary.currency == "USD"


def test_summarize_run_usage_orders_by_recency(db_session: Session) -> None:
    record_usage(
        db_session,
        kind="run",
        provider="adapter",
        run_id="run-old",
        cost_usd_estimated=1.0,
        project_id="project-1",
        graph_id="graph-1",
    )
    record_usage(db_session, kind="run", provider="adapter", run_id="run-new")

    summaries = summarize_run_usage(db_session, limit=10)

    assert [summary.run_id for summary in summaries] == ["run-new", "run-old"]
    assert summaries[0].unmetered is True
    assert summaries[0].cost_usd_estimated is None
    assert summaries[1].cost_usd_estimated == pytest.approx(1.0)
    assert summaries[1].project_id == "project-1"


def test_old_usage_does_not_count_today(db_session: Session) -> None:
    record_usage(db_session, kind="extraction", provider="muse", cost_usd_estimated=5.0)
    row = db_session.scalars(select(UsageRecordRow)).one()
    row.created_at = datetime.now(UTC) - timedelta(days=2)
    db_session.commit()

    total, calls, _ = spend_since(db_session, utc_midnight(datetime.now(UTC)))

    assert total == 0.0
    assert calls == 0


def test_usage_summary_endpoint_reports_zeros_when_empty(
    client_with_db: tuple[TestClient, Callable[[], Session]],
) -> None:
    client, _ = client_with_db

    response = client.get("/api/v1/usage/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["totals"] == {
        "calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd_estimated": 0.0,
        "unmetered_calls": 0,
    }
    assert len(body["days"]) == 7
    assert body["estimated"] is True


def test_usage_endpoints_report_seeded_rows(
    client_with_db: tuple[TestClient, Callable[[], Session]],
) -> None:
    client, make_session = client_with_db
    with make_session() as session:
        record_usage(
            session,
            kind="extraction",
            provider="muse",
            model="spark",
            input_tokens=1000,
            output_tokens=500,
            cost_usd_estimated=0.0105,
            project_id="project-1",
            graph_id="graph-1",
        )
        record_usage(
            session,
            kind="run",
            provider="adapter",
            run_id="run-1",
            project_id="project-1",
            graph_id="graph-1",
        )

    summary = client.get("/api/v1/usage/summary?days=1")
    assert summary.status_code == 200
    assert summary.json()["totals"]["calls"] == 2
    assert summary.json()["totals"]["cost_usd_estimated"] == pytest.approx(0.0105)

    runs = client.get("/api/v1/usage/runs")
    assert runs.status_code == 200
    assert runs.json() == [
        {
            "run_id": "run-1",
            "project_id": "project-1",
            "graph_id": "graph-1",
            "calls": 1,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd_estimated": None,
            "unmetered": True,
            "last_used_at": runs.json()[0]["last_used_at"],
        }
    ]


def test_extract_is_blocked_past_daily_spend_cap(
    client_with_db: tuple[TestClient, Callable[[], Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, make_session = client_with_db
    with make_session() as session:
        record_usage(session, kind="extraction", provider="muse", cost_usd_estimated=10.0)
    monkeypatch.setattr(api, "get_settings", lambda: _settings(BIZORA_DAILY_SPEND_CAP_USD=0.01))
    app.dependency_overrides[get_baseten_provider] = lambda: FakePaperProvider()
    try:
        response = client.post(
            "/api/v1/papers/extract",
            files={"file": ("capped.pdf", make_pdf_bytes("Capped body."), "application/pdf")},
        )
    finally:
        app.dependency_overrides.pop(get_baseten_provider, None)

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "SPEND_LIMIT_EXCEEDED"


def test_extract_records_unmetered_provider_calls(
    client_with_db: tuple[TestClient, Callable[[], Session]],
) -> None:
    client, _ = client_with_db
    app.dependency_overrides[get_baseten_provider] = lambda: FakePaperProvider()
    try:
        response = client.post(
            "/api/v1/papers/extract",
            files={"file": ("metered.pdf", make_pdf_bytes("Metered body."), "application/pdf")},
        )
    finally:
        app.dependency_overrides.pop(get_baseten_provider, None)

    assert response.status_code == 201
    summary = client.get("/api/v1/usage/summary?days=1")
    assert summary.json()["totals"]["calls"] == 2
    assert summary.json()["totals"]["unmetered_calls"] == 2


def test_execute_is_blocked_past_daily_run_count(
    client_with_db: tuple[TestClient, Callable[[], Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = client_with_db
    graph = client.post("/api/v1/graphs", json=make_graph_payload())
    assert graph.status_code == 201
    created = create_run(client, config=make_config_payload())
    assert created.status_code == 201
    monkeypatch.setattr(api, "get_settings", lambda: _settings(BIZORA_MAX_RUNS_PER_DAY=1))

    response = client.post("/api/v1/experiments/runs/run-api-1/execute")

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "EXPERIMENT_LIMIT_EXCEEDED"


def test_copilot_fast_path_records_no_usage(
    client_with_db: tuple[TestClient, Callable[[], Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = client_with_db
    graph = client.post("/api/v1/graphs", json=make_graph_payload())
    assert graph.status_code == 201
    monkeypatch.setattr(api, "_copilot_provider_or_none", lambda: None)

    response = client.post(
        "/api/v1/graphs/project-api/graph-api/revisions/1/copilot",
        json={"message": "hello"},
    )

    assert response.status_code == 200
    summary = client.get("/api/v1/usage/summary?days=1")
    assert summary.json()["totals"]["calls"] == 0
