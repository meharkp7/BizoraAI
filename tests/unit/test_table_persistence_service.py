"""Tests for results-table persistence."""

import asyncio
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from bizora.contracts.table import ExtractedTable
from bizora.core.errors import BizoraError, ErrorCode
from bizora.core.table_persistence_service import TablePersistenceService
from bizora.db.base import Base
from bizora.db.repository import list_extracted_tables
from bizora.providers.tables import (
    TableExtractionRequest,
    TableExtractionResult,
)


@pytest.fixture
def db_session() -> Iterator[Session]:
    """Create an isolated in-memory database for each test."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        yield session

    engine.dispose()


def make_table(table_id: str = "table-1") -> ExtractedTable:
    return ExtractedTable(
        table_id=table_id,
        project_id="project-1",
        graph_id="graph-1",
        source_id="paper-1",
        caption="CASP14 results.",
        columns=("Method", "TM-score"),
        rows=(("AlphaFold2", "0.92"),),
        created_by="test-user",
    )


def make_request() -> TableExtractionRequest:
    return TableExtractionRequest(
        paper_text="AlphaFold2 achieves 0.92 TM-score on CASP14.",
        project_id="project-1",
        graph_id="graph-1",
        source_id="paper-1",
        created_by="test-user",
    )


class FakeTableProvider:
    """Fake table provider returning canned drafts and warnings."""

    def __init__(
        self,
        tables: tuple[ExtractedTable, ...],
        warnings: tuple[str, ...] = (),
    ) -> None:
        self.tables = tables
        self.warnings = warnings

    async def extract_tables(
        self, request: TableExtractionRequest
    ) -> TableExtractionResult:
        del request
        return TableExtractionResult(
            draft_tables=self.tables,
            provider_name="fake",
            model_name="test-model",
            warnings=self.warnings,
        )


def test_persists_tables_and_returns_warnings(db_session: Session) -> None:
    async def run_test() -> None:
        provider = FakeTableProvider(
            (make_table("table-1"), make_table("table-2")),
            warnings=("Provider note.",),
        )
        tables, warnings = await TablePersistenceService.extract_and_persist(
            db_session, provider, make_request()
        )

        assert [table.table_id for table in tables] == ["table-1", "table-2"]
        assert warnings == ["Provider note."]
        stored = list_extracted_tables(
            db_session, project_id="project-1", graph_id="graph-1"
        )
        assert [row.table_id for row in stored] == ["table-1", "table-2"]

    asyncio.run(run_test())


def test_duplicate_table_ids_skipped_with_warning(db_session: Session) -> None:
    async def run_test() -> None:
        provider = FakeTableProvider((make_table("table-1"), make_table("table-1")))
        tables, warnings = await TablePersistenceService.extract_and_persist(
            db_session, provider, make_request()
        )

        assert [table.table_id for table in tables] == ["table-1"]
        assert warnings == ["Table table-1 was skipped: duplicate table id."]

    asyncio.run(run_test())


def test_misbound_table_rejected(db_session: Session) -> None:
    async def run_test() -> None:
        other = make_table("table-1").model_copy(
            update={"project_id": "other-project"}
        )
        provider = FakeTableProvider((other,))

        with pytest.raises(BizoraError) as exc_info:
            await TablePersistenceService.extract_and_persist(
                db_session, provider, make_request()
            )

        assert exc_info.value.code == ErrorCode.INVALID_REQUEST

    asyncio.run(run_test())
