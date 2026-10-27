
"""Provider-neutral contracts for results-table extraction."""

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from bizora.contracts.table import ExtractedTable
from bizora.providers.base import MAX_PAPER_TEXT_LENGTH


class TableExtractionRequest(BaseModel):
    """Input supplied to a results-table extraction provider."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    paper_text: str = Field(min_length=1, max_length=MAX_PAPER_TEXT_LENGTH)
    project_id: str = Field(min_length=1, max_length=128)
    graph_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1)
    created_by: str = Field(min_length=1, max_length=128)
    max_tables: int = Field(default=10, ge=1, le=20)


class TableExtractionResult(BaseModel):
    """A provider's proposed tables, not yet trusted or persisted."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    draft_tables: tuple[ExtractedTable, ...] = ()
    provider_name: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    warnings: tuple[str, ...] = ()


@runtime_checkable
class TableExtractionProvider(Protocol):
    """Interface implemented by every table extraction provider."""

    async def extract_tables(
        self,
        request: TableExtractionRequest,
    ) -> TableExtractionResult:
        """Extract proposed results tables from paper content."""
        ...
