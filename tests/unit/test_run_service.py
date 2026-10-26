"""Tests for the experiment run lifecycle service."""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from bizora.contracts.experiment import ExperimentConfig
from bizora.contracts.graph import (
    GraphEdge,
    GraphNode,
    MethodologyGraph,
    NodeKind,
)
from bizora.contracts.run import RunState
from bizora.core.errors import BizoraError, ErrorCode, ExperimentStateError
from bizora.core.run_service import ExperimentRunService
from bizora.db.base import Base
from bizora.db.repository import get_experiment_run, save_graph_revision


@pytest.fixture
def db_session() -> Iterator[Session]:
    """Create an isolated in-memory database for each test."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        yield session

    engine.dispose()


def valid_experiment_data() -> dict[str, object]:
    """Return a valid experiment configuration payload."""
    return {
        "experiment_id": "exp-1",
        "project_id": "project-1",
        "graph_id": "graph-1",
        "graph_version": 1,
        "adapter_id": "hf-vit-classification",
        "adapter_version": "0.1.0",
        "dataset_id": "cifar10-subset",
        "dataset_revision": "sha256:example",
        "seed": 42,
        "epochs": 3,
        "batch_size": 32,
        "learning_rate": 0.001,
        "split": {
            "train": 0.8,
            "validation": 0.1,
            "test": 0.1,
        },
        "code_revision": "abcdef1",
        "max_runtime_seconds": 1800,
        "max_gpu_count": 1,
    }


def persist_graph(
    db_session: Session,
    *,
    project_id: str = "project-1",
    graph_id: str = "graph-1",
    version: int = 1,
) -> None:
    """Persist a minimal graph revision matching the experiment config."""
    graph = MethodologyGraph(
        project_id=project_id,
        graph_id=graph_id,
        version=version,
        parent_version=None,
        title="Vision Transformer",
        source_ids=("paper-1",),
        nodes=(
            GraphNode(id="input", kind=NodeKind.INPUT, label="Image"),
            GraphNode(id="encoder", kind=NodeKind.MODEL, label="Encoder"),
            GraphNode(id="output", kind=NodeKind.OUTPUT, label="Predictions"),
        ),
        edges=(
            GraphEdge(id="edge-1", source="input", target="encoder"),
            GraphEdge(id="edge-2", source="encoder", target="output"),
        ),
        created_by="researcher-1",
    )
    save_graph_revision(db_session, graph)
    db_session.commit()


def make_config() -> ExperimentConfig:
    """Build a config referencing the persisted graph revision."""
    return ExperimentConfig.model_validate(valid_experiment_data())


def test_create_run_persists_pending_run(db_session: Session) -> None:
    persist_graph(db_session)
    created = datetime(2026, 1, 1, tzinfo=UTC)

    run = ExperimentRunService.create_run(
        db_session,
        make_config(),
        run_id="run-1",
        now=created,
    )

    assert run.run_id == "run-1"
    assert run.state == RunState.PENDING
    assert run.created_at == created
    assert run.config == make_config()

    loaded = ExperimentRunService.get_run(db_session, "run-1")
    assert loaded == run


def test_create_run_rejects_missing_graph_revision(
    db_session: Session,
) -> None:
    with pytest.raises(BizoraError) as exc_info:
        ExperimentRunService.create_run(
            db_session,
            make_config(),
            run_id="run-1",
        )

    assert exc_info.value.code == ErrorCode.RESOURCE_NOT_FOUND
    assert get_experiment_run(db_session, "run-1") is None


def test_create_run_rejects_wrong_graph_version(
    db_session: Session,
) -> None:
    persist_graph(db_session, version=1)
    payload = valid_experiment_data()
    payload["graph_version"] = 2
    config = ExperimentConfig.model_validate(payload)

    with pytest.raises(BizoraError) as exc_info:
        ExperimentRunService.create_run(
            db_session,
            config,
            run_id="run-1",
        )

    assert exc_info.value.code == ErrorCode.RESOURCE_NOT_FOUND


def test_create_run_rejects_duplicate_run_id(db_session: Session) -> None:
    persist_graph(db_session)
    ExperimentRunService.create_run(
        db_session, make_config(), run_id="run-1"
    )

    with pytest.raises(BizoraError) as exc_info:
        ExperimentRunService.create_run(
            db_session, make_config(), run_id="run-1"
        )

    assert exc_info.value.code == ErrorCode.RESOURCE_CONFLICT


def test_create_run_rejects_naive_timestamp(db_session: Session) -> None:
    persist_graph(db_session)

    with pytest.raises(BizoraError) as exc_info:
        ExperimentRunService.create_run(
            db_session,
            make_config(),
            run_id="run-1",
            now=datetime(2026, 1, 1),
        )

    assert exc_info.value.code == ErrorCode.INVALID_REQUEST


def test_get_run_raises_for_missing_run(db_session: Session) -> None:
    with pytest.raises(BizoraError) as exc_info:
        ExperimentRunService.get_run(db_session, "missing-run")

    assert exc_info.value.code == ErrorCode.RESOURCE_NOT_FOUND


def test_transition_through_full_lifecycle(db_session: Session) -> None:
    persist_graph(db_session)
    created = datetime(2026, 1, 1, tzinfo=UTC)
    started = datetime(2026, 1, 2, tzinfo=UTC)
    finished = datetime(2026, 1, 3, tzinfo=UTC)
    ExperimentRunService.create_run(
        db_session, make_config(), run_id="run-1", now=created
    )

    running = ExperimentRunService.transition_run(
        db_session, "run-1", to_state=RunState.RUNNING, now=started
    )
    assert running.state == RunState.RUNNING
    assert running.started_at == started
    assert running.finished_at is None

    succeeded = ExperimentRunService.transition_run(
        db_session, "run-1", to_state=RunState.SUCCEEDED, now=finished
    )
    assert succeeded.state == RunState.SUCCEEDED
    assert succeeded.started_at == started
    assert succeeded.finished_at == finished


def test_transition_rejects_invalid_jump(db_session: Session) -> None:
    persist_graph(db_session)
    ExperimentRunService.create_run(
        db_session, make_config(), run_id="run-1"
    )

    with pytest.raises(ExperimentStateError):
        ExperimentRunService.transition_run(
            db_session, "run-1", to_state=RunState.SUCCEEDED
        )

    current = ExperimentRunService.get_run(db_session, "run-1")
    assert current.state == RunState.PENDING


def test_transition_rejects_terminal_state_change(
    db_session: Session,
) -> None:
    persist_graph(db_session)
    ExperimentRunService.create_run(
        db_session, make_config(), run_id="run-1"
    )
    ExperimentRunService.transition_run(
        db_session, "run-1", to_state=RunState.RUNNING
    )
    ExperimentRunService.transition_run(
        db_session, "run-1", to_state=RunState.SUCCEEDED
    )

    with pytest.raises(ExperimentStateError):
        ExperimentRunService.transition_run(
            db_session, "run-1", to_state=RunState.FAILED
        )

    current = ExperimentRunService.get_run(db_session, "run-1")
    assert current.state == RunState.SUCCEEDED


def test_transition_raises_for_missing_run(db_session: Session) -> None:
    with pytest.raises(BizoraError) as exc_info:
        ExperimentRunService.transition_run(
            db_session, "missing-run", to_state=RunState.RUNNING
        )

    assert exc_info.value.code == ErrorCode.RESOURCE_NOT_FOUND


def test_transition_rejects_error_on_success(db_session: Session) -> None:
    persist_graph(db_session)
    ExperimentRunService.create_run(
        db_session, make_config(), run_id="run-1"
    )
    ExperimentRunService.transition_run(
        db_session, "run-1", to_state=RunState.RUNNING
    )

    with pytest.raises(ExperimentStateError):
        ExperimentRunService.transition_run(
            db_session,
            "run-1",
            to_state=RunState.SUCCEEDED,
            error="unexpected",
        )


def test_failed_transition_records_error(db_session: Session) -> None:
    persist_graph(db_session)
    ExperimentRunService.create_run(
        db_session, make_config(), run_id="run-1"
    )
    ExperimentRunService.transition_run(
        db_session, "run-1", to_state=RunState.RUNNING
    )

    failed = ExperimentRunService.transition_run(
        db_session,
        "run-1",
        to_state=RunState.FAILED,
        error="worker timeout",
    )

    assert failed.state == RunState.FAILED
    assert failed.error == "worker timeout"
    assert failed.finished_at is not None


def test_transition_reports_concurrent_modification(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persist_graph(db_session)
    ExperimentRunService.create_run(
        db_session, make_config(), run_id="run-1"
    )

    def lost_race(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        return None

    monkeypatch.setattr(
        "bizora.core.run_service.compare_and_set_run_state",
        lost_race,
    )

    with pytest.raises(BizoraError) as exc_info:
        ExperimentRunService.transition_run(
            db_session, "run-1", to_state=RunState.RUNNING
        )

    assert exc_info.value.code == ErrorCode.RESOURCE_CONFLICT
