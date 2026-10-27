
"""Validate and persist extracted results tables."""

from sqlalchemy.orm import Session

from bizora.contracts.table import ExtractedTable
from bizora.core.errors import BizoraError, ErrorCode
from bizora.db.repository import save_extracted_table
from bizora.providers.tables import (
    TableExtractionProvider,
    TableExtractionRequest,
    TableExtractionResult,
)


class TablePersistenceService:
    """Extract tables, verify their binding, and persist them."""

    @staticmethod
    async def extract_and_persist(
        session: Session,
        provider: TableExtractionProvider,
        request: TableExtractionRequest,
    ) -> tuple[list[ExtractedTable], list[str]]:
        """Persist provider tables, skipping duplicates with warnings."""
        result = await provider.extract_tables(request)

        try:
            persisted, warnings = TablePersistenceService._persist_drafts(
                session, request, result
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        return persisted, warnings

    @staticmethod
    def _persist_drafts(
        session: Session,
        request: TableExtractionRequest,
        result: TableExtractionResult,
    ) -> tuple[list[ExtractedTable], list[str]]:
        """Validate bindings and stage drafts without committing."""
        warnings = list(result.warnings)
        persisted: list[ExtractedTable] = []
        seen: set[str] = set()
        for table in result.draft_tables:
            if (
                table.project_id != request.project_id
                or table.graph_id != request.graph_id
                or table.source_id != request.source_id
                or table.created_by != request.created_by
            ):
                raise BizoraError(
                    ErrorCode.INVALID_REQUEST,
                    "Provider returned a table for a different request.",
                    details={"table_id": table.table_id},
                )
            if table.table_id in seen:
                warnings.append(
                    f"Table {table.table_id} was skipped: duplicate table id."
                )
                continue
            seen.add(table.table_id)
            save_extracted_table(session, table)
            persisted.append(table)

        return persisted, warnings
