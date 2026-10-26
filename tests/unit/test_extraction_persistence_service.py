"""Tests for extraction-to-persistence orchestration."""

import asyncio
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from bizora.contracts.graph import MethodologyGraph
from bizora.core.errors import BizoraError, ErrorCode
from bizora.core.extraction_persistence_service import (
    ExtractionPersistenceService,
)
from bizora.db.base import Base
from bizora.providers.base import (
    MethodologyExtractionRequest,
    MethodologyExtractionResult,
)


class FakeMethodologyProvider:
    def __init__(self, graph: MethodologyGraph) -> None:
        self.graph = graph

    async def extract_methodology(
        self,
        request: MethodologyExtractionRequest,
    ) -> MethodologyExtractionResult:
        return MethodologyExtractionResult(
            draft_graph=self.graph,
            provider_name="fake",
            model_name="test-model",
        )


def make_request() -> MethodologyExtractionRequest:
    return MethodologyExtractionRequest(
        paper_text="The authors describe their methodology.",
        project_id="project-persist",
        graph_id="graph-persist",
        source_id="paper-persist",
        created_by="test-user",
        title="Persistence test",
    )


def make_graph(
    *,
    version: int = 1,
    parent_version: int | None = None,
    created_by: str = "test-user",
    source_ids: tuple[str, ...] = ("paper-persist",),
) -> MethodologyGraph:
    return MethodologyGraph(
        schema_version="1.0",
        project_id="project-persist",
        graph_id="graph-persist",
        version=version,
        title="Persistence test",
        source_ids=source_ids,
        nodes=(),
        edges=(),
        created_by=created_by,
        parent_version=parent_version,
    )


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    try:
        with Session(engine) as db_session:
            yield db_session
    finally:
        engine.dispose()


def test_extract_and_persist_initial_revision(session: Session) -> None:
    async def run_test() -> None:
        request = make_request()
        provider = FakeMethodologyProvider(make_graph())

        persisted = (
            await ExtractionPersistenceService.extract_and_persist_initial(
                session,
                provider,
                request,
            )
        )

        assert persisted.project_id == request.project_id
        assert persisted.graph_id == request.graph_id
        assert persisted.version == 1
        assert persisted.parent_version is None
        assert persisted.source_ids == (request.source_id,)

    asyncio.run(run_test())


def test_extract_and_persist_rejects_duplicate_initial_revision(
    session: Session,
) -> None:
    async def run_test() -> None:
        request = make_request()
        provider = FakeMethodologyProvider(make_graph())

        await ExtractionPersistenceService.extract_and_persist_initial(
            session,
            provider,
            request,
        )

        with pytest.raises(BizoraError) as exc_info:
            await ExtractionPersistenceService.extract_and_persist_initial(
                session,
                provider,
                request,
            )

        assert exc_info.value.code == ErrorCode.RESOURCE_CONFLICT

    asyncio.run(run_test())


def test_extract_and_persist_rejects_missing_source_id(
    session: Session,
) -> None:
    async def run_test() -> None:
        request = make_request()
        provider = FakeMethodologyProvider(
            make_graph(source_ids=("another-paper",))
        )

        with pytest.raises(BizoraError) as exc_info:
            await ExtractionPersistenceService.extract_and_persist_initial(
                session,
                provider,
                request,
            )

        assert exc_info.value.code == ErrorCode.INVALID_GRAPH

    asyncio.run(run_test())


def test_extract_and_persist_rejects_non_initial_revision(
    session: Session,
) -> None:
    async def run_test() -> None:
        request = make_request()
        provider = FakeMethodologyProvider(
            make_graph(version=2, parent_version=1)
        )

        with pytest.raises(BizoraError) as exc_info:
            await ExtractionPersistenceService.extract_and_persist_initial(
                session,
                provider,
                request,
            )

        assert exc_info.value.code == ErrorCode.INVALID_GRAPH

    asyncio.run(run_test())


def test_extract_and_persist_rejects_creator_mismatch(
    session: Session,
) -> None:
    async def run_test() -> None:
        request = make_request()
        provider = FakeMethodologyProvider(
            make_graph(created_by="different-user")
        )

        with pytest.raises(BizoraError) as exc_info:
            await ExtractionPersistenceService.extract_and_persist_initial(
                session,
                provider,
                request,
            )

        assert exc_info.value.code == ErrorCode.INVALID_GRAPH
    asyncio.run(run_test())