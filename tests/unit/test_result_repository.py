"""Tests for metric and artifact record persistence."""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from bizora.contracts.experiment import ResultKind
from bizora.contracts.run import ArtifactRecord, MetricRecord
from bizora.core.errors import BizoraError, ErrorCode
from bizora.db.base import Base
from bizora.db.repository import (
    artifact_record_from_row,
    get_artifact_record,
    get_metric_record,
    list_artifacts_for_run,
    list_metrics_for_run,
    metric_record_from_row,
    save_artifact_record,
    save_metric_record,
)


@pytest.fixture
def db_session() -> Iterator[Session]:
    """Create an isolated in-memory database for each test."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        yield session

    engine.dispose()


def make_metric(
    *,
    run_id: str = "run-1",
    metric_id: str = "metric-1",
    name: str = "accuracy",
    value: float = 0.92,
) -> MetricRecord:
    """Build a minimal metric record."""
    return MetricRecord(
        metric_id=metric_id,
        run_id=run_id,
        name=name,
        value=value,
        result_kind=ResultKind.MEASURED,
    )


def make_artifact(
    *,
    run_id: str = "run-1",
    artifact_id: str = "artifact-1",
) -> ArtifactRecord:
    """Build a minimal artifact record."""
    return ArtifactRecord(
        artifact_id=artifact_id,
        run_id=run_id,
        kind="checkpoint",
        uri="file:///tmp/checkpoint",
        sha256="a" * 64,
        result_kind=ResultKind.MEASURED,
    )


def test_save_and_retrieve_metric_record(db_session: Session) -> None:
    row = save_metric_record(db_session, make_metric())
    db_session.commit()

    assert row.id is not None

    loaded = get_metric_record(
        db_session, run_id="run-1", metric_id="metric-1"
    )
    assert loaded is not None
    assert metric_record_from_row(loaded) == make_metric()


def test_duplicate_metric_is_rejected(db_session: Session) -> None:
    save_metric_record(db_session, make_metric())
    db_session.commit()

    with pytest.raises(BizoraError) as exc_info:
        save_metric_record(db_session, make_metric())

    assert exc_info.value.code == ErrorCode.RESOURCE_CONFLICT
    assert exc_info.value.details == {
        "run_id": "run-1",
        "metric_id": "metric-1",
    }


def test_same_metric_id_allowed_for_other_runs(db_session: Session) -> None:
    save_metric_record(db_session, make_metric(run_id="run-1"))
    save_metric_record(db_session, make_metric(run_id="run-2"))
    db_session.commit()

    loaded = get_metric_record(
        db_session, run_id="run-2", metric_id="metric-1"
    )

    assert loaded is not None
    assert loaded.run_id == "run-2"


def test_list_metrics_returns_run_ordered_by_name(
    db_session: Session,
) -> None:
    save_metric_record(db_session, make_metric(name="loss", metric_id="m-loss"))
    save_metric_record(
        db_session, make_metric(name="accuracy", metric_id="m-accuracy")
    )
    save_metric_record(
        db_session, make_metric(run_id="run-2", name="accuracy")
    )
    db_session.commit()

    rows = list_metrics_for_run(db_session, "run-1")

    assert [row.name for row in rows] == ["accuracy", "loss"]


def test_missing_metric_returns_none(db_session: Session) -> None:
    assert (
        get_metric_record(db_session, run_id="run-1", metric_id="absent")
        is None
    )
    assert list_metrics_for_run(db_session, "run-1") == []


def test_save_and_retrieve_artifact_record(db_session: Session) -> None:
    row = save_artifact_record(db_session, make_artifact())
    db_session.commit()

    assert row.id is not None

    loaded = get_artifact_record(
        db_session, run_id="run-1", artifact_id="artifact-1"
    )
    assert loaded is not None
    restored = artifact_record_from_row(loaded)
    assert restored == make_artifact()
    assert restored.sha256 == "a" * 64


def test_duplicate_artifact_is_rejected(db_session: Session) -> None:
    save_artifact_record(db_session, make_artifact())
    db_session.commit()

    with pytest.raises(BizoraError) as exc_info:
        save_artifact_record(db_session, make_artifact())

    assert exc_info.value.code == ErrorCode.RESOURCE_CONFLICT
    assert exc_info.value.details == {
        "run_id": "run-1",
        "artifact_id": "artifact-1",
    }


def test_list_artifacts_returns_run_ordered_by_id(
    db_session: Session,
) -> None:
    save_artifact_record(db_session, make_artifact(artifact_id="b-second"))
    save_artifact_record(db_session, make_artifact(artifact_id="a-first"))
    save_artifact_record(
        db_session, make_artifact(run_id="run-2", artifact_id="a-first")
    )
    db_session.commit()

    rows = list_artifacts_for_run(db_session, "run-1")

    assert [row.artifact_id for row in rows] == ["a-first", "b-second"]


def test_missing_artifact_returns_none(db_session: Session) -> None:
    assert (
        get_artifact_record(db_session, run_id="run-1", artifact_id="absent")
        is None
    )
    assert list_artifacts_for_run(db_session, "run-1") == []
