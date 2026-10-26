
"""Tests for graph revision persistence."""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from bizora.contracts.graph import (
    GraphEdge,
    GraphNode,
    MethodologyGraph,
    NodeKind,
)
from bizora.core.errors import BizoraError, ErrorCode
from bizora.db.base import Base
from bizora.db.repository import (
    get_graph_revision,
    get_latest_graph_revision,
    save_graph_revision,
)


@pytest.fixture
def db_session() -> Iterator[Session]:
    """Create an isolated in-memory database for each test."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        yield session

    engine.dispose()


def make_graph(
    *,
    version: int = 1,
    parent_version: int | None = None,
    title: str = "Vision Transformer",
) -> MethodologyGraph:
    """Build a minimal valid graph snapshot."""
    return MethodologyGraph(
        project_id="project-1",
        graph_id="graph-1",
        version=version,
        parent_version=parent_version,
        title=title,
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


def test_save_and_retrieve_graph_revision(db_session: Session) -> None:
    graph = make_graph()

    record = save_graph_revision(db_session, graph)
    db_session.commit()

    loaded = get_graph_revision(
        db_session,
        project_id="project-1",
        graph_id="graph-1",
        version=1,
    )

    assert loaded is not None
    assert record.id is not None
    assert loaded.graph_payload["title"] == "Vision Transformer"
    assert loaded.graph_payload["version"] == 1
    assert len(loaded.snapshot_sha256) == 64


def test_duplicate_graph_version_is_rejected(db_session: Session) -> None:
    save_graph_revision(db_session, make_graph())
    db_session.commit()

    with pytest.raises(BizoraError) as exc_info:
        save_graph_revision(db_session, make_graph())

    assert exc_info.value.code == ErrorCode.RESOURCE_CONFLICT


def test_latest_revision_returns_highest_version(db_session: Session) -> None:
    save_graph_revision(db_session, make_graph(version=1))
    save_graph_revision(
        db_session,
        make_graph(version=2, parent_version=1, title="Updated Transformer"),
    )
    db_session.commit()

    latest = get_latest_graph_revision(
        db_session,
        project_id="project-1",
        graph_id="graph-1",
    )

    assert latest is not None
    assert latest.version == 2
    assert latest.parent_version == 1
    assert latest.title == "Updated Transformer"


def test_missing_revision_returns_none(db_session: Session) -> None:
    result = get_graph_revision(
        db_session,
        project_id="project-1",
        graph_id="graph-1",
        version=99,
    )

    assert result is None


def test_snapshot_hash_changes_when_graph_changes(db_session: Session) -> None:
    first = save_graph_revision(db_session, make_graph())
    second = save_graph_revision(
        db_session,
        make_graph(version=2, parent_version=1, title="Updated Transformer"),
    )

    assert first.snapshot_sha256 != second.snapshot_sha256


def test_snapshot_payload_round_trips_evidence_free_graph(db_session: Session) -> None:
    graph = make_graph()
    save_graph_revision(db_session, graph)
    db_session.commit()

    loaded = get_graph_revision(
        db_session,
        project_id=graph.project_id,
        graph_id=graph.graph_id,
        version=graph.version,
    )

    assert loaded is not None
    restored = MethodologyGraph.model_validate(loaded.graph_payload)
    assert restored == graph
