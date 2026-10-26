
"""Tests for transactional graph persistence workflows."""

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
from bizora.core.errors import BizoraError, ErrorCode, GraphValidationError
from bizora.core.graph_persistence_service import GraphPersistenceService
from bizora.db.base import Base
from bizora.db.repository import get_graph_revision, get_latest_graph_revision


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
    """Build a minimal valid methodology graph."""
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


def test_create_initial_revision_persists_and_commits(
    db_session: Session,
) -> None:
    graph = make_graph()

    record = GraphPersistenceService.create_initial_revision(db_session, graph)

    assert record.id is not None
    assert record.version == 1
    assert record.parent_version is None

    loaded = get_graph_revision(
        db_session,
        project_id=graph.project_id,
        graph_id=graph.graph_id,
        version=1,
    )
    assert loaded is not None
    assert loaded.graph_payload == graph.model_dump(mode="json")


def test_create_revision_increments_version_and_preserves_parent(
    db_session: Session,
) -> None:
    graph = make_graph()
    GraphPersistenceService.create_initial_revision(db_session, graph)

    updated = GraphPersistenceService.create_revision(
        db_session,
        graph,
        created_by="researcher-2",
        title="Updated Vision Transformer",
    )

    assert updated.version == 2
    assert updated.parent_version == 1
    assert updated.title == "Updated Vision Transformer"
    assert updated.created_by == "researcher-2"

    latest = get_latest_graph_revision(
        db_session,
        project_id=graph.project_id,
        graph_id=graph.graph_id,
    )
    assert latest is not None
    assert latest.version == 2


def test_create_revision_rejects_stale_snapshot(
    db_session: Session,
) -> None:
    original = make_graph()
    GraphPersistenceService.create_initial_revision(db_session, original)

    GraphPersistenceService.create_revision(
        db_session,
        original,
        created_by="researcher-2",
        title="Updated Vision Transformer",
    )

    with pytest.raises(BizoraError) as exc_info:
        GraphPersistenceService.create_revision(
            db_session,
            original,
            created_by="researcher-3",
            title="Stale update",
        )

    assert exc_info.value.code == ErrorCode.RESOURCE_CONFLICT

    latest = get_latest_graph_revision(
        db_session,
        project_id=original.project_id,
        graph_id=original.graph_id,
    )
    assert latest is not None
    assert latest.version == 2
    assert latest.title == "Updated Vision Transformer"


def test_create_initial_revision_rejects_duplicate(
    db_session: Session,
) -> None:
    graph = make_graph()
    GraphPersistenceService.create_initial_revision(db_session, graph)

    with pytest.raises(BizoraError) as exc_info:
        GraphPersistenceService.create_initial_revision(db_session, graph)

    assert exc_info.value.code == ErrorCode.RESOURCE_CONFLICT


def test_create_revision_requires_existing_graph(
    db_session: Session,
) -> None:
    with pytest.raises(BizoraError) as exc_info:
        GraphPersistenceService.create_revision(
            db_session,
            make_graph(),
            created_by="researcher-2",
        )

    assert exc_info.value.code == ErrorCode.RESOURCE_CONFLICT


def test_initial_revision_rejects_invalid_graph(
    db_session: Session,
) -> None:
    graph = make_graph()
    invalid_graph = graph.model_copy(
        update={
            "edges": (
                GraphEdge(
                    id="invalid-edge",
                    source="missing-node",
                    target="encoder",
                ),
            )
        }
    )

    with pytest.raises(GraphValidationError):
        GraphPersistenceService.create_initial_revision(
            db_session,
            invalid_graph,
        )

    assert (
        get_latest_graph_revision(
            db_session,
            project_id=graph.project_id,
            graph_id=graph.graph_id,
        )
        is None
    )