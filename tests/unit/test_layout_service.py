"""Tests for visual-only graph layout persistence."""

from collections.abc import Iterator
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from bizora.contracts.graph import (
    GraphEdge,
    GraphNode,
    MethodologyGraph,
    NodeKind,
)
from bizora.contracts.layout import GraphLayout, NodePosition, ViewportState
from bizora.core.errors import BizoraError, ErrorCode
from bizora.core.graph_persistence_service import GraphPersistenceService
from bizora.core.layout_service import LayoutService
from bizora.db.base import Base
from bizora.db.repository import get_graph_layout, get_graph_revision


@pytest.fixture
def db_session() -> Iterator[Session]:
    """Create an isolated in-memory database for each test."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        yield session

    engine.dispose()


def make_graph() -> MethodologyGraph:
    """Build a minimal persisted methodology graph."""
    return MethodologyGraph(
        project_id="project-1",
        graph_id="graph-1",
        version=1,
        title="Vision transformer",
        source_ids=("paper-1",),
        nodes=(
            GraphNode(id="input", kind=NodeKind.INPUT, label="Image"),
            GraphNode(id="encoder", kind=NodeKind.MODEL, label="Encoder"),
        ),
        edges=(GraphEdge(id="e1", source="input", target="encoder"),),
        created_by="test",
    )


def persist_graph(session: Session) -> MethodologyGraph:
    """Persist the minimal graph's initial revision."""
    graph = make_graph()
    GraphPersistenceService.create_initial_revision(session, graph)
    return graph


def make_layout(**overrides: object) -> GraphLayout:
    """Build a minimal layout for the persisted graph revision."""
    values: dict[str, object] = {
        "project_id": "project-1",
        "graph_id": "graph-1",
        "version": 1,
        "positions": (
            NodePosition(node_id="input", x=10.0, y=20.0),
            NodePosition(node_id="encoder", x=30.0, y=40.0),
        ),
        "viewport": ViewportState(x=0.0, y=0.0, zoom=1.0),
        "updated_by": "test",
    }
    values.update(overrides)
    return GraphLayout(**values)


def test_save_and_retrieve_layout_round_trip(db_session: Session) -> None:
    persist_graph(db_session)
    saved = LayoutService.save_layout(db_session, make_layout())

    assert saved.positions[0].node_id == "input"
    assert saved.viewport is not None
    assert saved.viewport.zoom == 1.0

    retrieved = LayoutService.get_layout(
        db_session, project_id="project-1", graph_id="graph-1", version=1
    )
    assert retrieved == saved


def test_save_layout_replaces_prior_layout(db_session: Session) -> None:
    persist_graph(db_session)
    LayoutService.save_layout(db_session, make_layout())
    updated = LayoutService.save_layout(
        db_session,
        make_layout(
            positions=(NodePosition(node_id="input", x=99.0, y=99.0),),
            updated_by="editor-2",
        ),
    )

    assert updated.updated_by == "editor-2"
    assert updated.positions[0].x == 99.0
    retrieved = LayoutService.get_layout(
        db_session, project_id="project-1", graph_id="graph-1", version=1
    )
    assert retrieved == updated


def test_partial_positions_allowed(db_session: Session) -> None:
    persist_graph(db_session)
    saved = LayoutService.save_layout(
        db_session,
        make_layout(positions=(NodePosition(node_id="input", x=1.0, y=2.0),)),
    )
    assert len(saved.positions) == 1


def test_unknown_node_position_rejected(db_session: Session) -> None:
    persist_graph(db_session)
    with pytest.raises(BizoraError) as exc_info:
        LayoutService.save_layout(
            db_session,
            make_layout(
                positions=(NodePosition(node_id="ghost", x=1.0, y=2.0),)
            ),
        )

    assert exc_info.value.code == ErrorCode.INVALID_REQUEST
    assert exc_info.value.details["unknown_node_ids"] == ["ghost"]
    assert (
        get_graph_layout(
            db_session, project_id="project-1", graph_id="graph-1", version=1
        )
        is None
    )


def test_missing_revision_rejected(db_session: Session) -> None:
    with pytest.raises(BizoraError) as exc_info:
        LayoutService.save_layout(db_session, make_layout())

    assert exc_info.value.code == ErrorCode.RESOURCE_NOT_FOUND


def test_missing_layout_retrieval_rejected(db_session: Session) -> None:
    persist_graph(db_session)
    with pytest.raises(BizoraError) as exc_info:
        LayoutService.get_layout(
            db_session, project_id="project-1", graph_id="graph-1", version=1
        )

    assert exc_info.value.code == ErrorCode.RESOURCE_NOT_FOUND


def test_naive_timestamp_rejected(db_session: Session) -> None:
    persist_graph(db_session)
    with pytest.raises(BizoraError) as exc_info:
        LayoutService.save_layout(
            db_session, make_layout(), now=datetime(2026, 1, 1)
        )

    assert exc_info.value.code == ErrorCode.INVALID_REQUEST


def test_layout_save_leaves_graph_semantics_untouched(
    db_session: Session,
) -> None:
    persist_graph(db_session)
    before = get_graph_revision(
        db_session, project_id="project-1", graph_id="graph-1", version=1
    )
    assert before is not None
    payload_before = dict(before.graph_payload)
    hash_before = before.snapshot_sha256

    LayoutService.save_layout(db_session, make_layout())
    LayoutService.save_layout(
        db_session, make_layout(updated_by="editor-2", viewport=None)
    )

    after = get_graph_revision(
        db_session, project_id="project-1", graph_id="graph-1", version=1
    )
    assert after is not None
    assert after.graph_payload == payload_before
    assert after.snapshot_sha256 == hash_before
    assert after.version == 1
    assert after.parent_version is None
