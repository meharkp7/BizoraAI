"""Contracts for results tables extracted from papers."""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bizora.contracts.graph import MethodologyGraph


class ExtractedTable(BaseModel):
    """One results table extracted from a paper, bound to a graph."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    table_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)
    graph_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1)
    caption: str = Field(default="", max_length=2000)
    columns: tuple[str, ...] = Field(min_length=1)
    rows: tuple[tuple[str, ...], ...] = ()
    page: int | None = Field(default=None, ge=1)
    quote: str | None = Field(default=None, max_length=2000)
    created_by: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_row_widths(self) -> "ExtractedTable":
        """Require every row to match the column count."""
        width = len(self.columns)
        for index, row in enumerate(self.rows):
            if len(row) != width:
                raise ValueError(
                    f"Row {index} has {len(row)} cells for {width} columns."
                )
        return self


class SuggestedIds(BaseModel):
    """Stable identifier suggestions derived from an upload, not a paper."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str = Field(min_length=1, max_length=128)
    graph_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)


class ParsedPaper(BaseModel):
    """Metadata read from an uploaded PDF without any model call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    filename: str = Field(min_length=1)
    title: str | None = None
    authors: tuple[str, ...] = ()
    page_count: int = Field(ge=1)
    chars: int = Field(ge=1)
    sha256: str = Field(min_length=64, max_length=64)
    truncated: bool = False
    suggested: SuggestedIds


class PaperExtractionResponse(BaseModel):
    """Result of extracting one uploaded paper: graph plus tables."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    graph: MethodologyGraph
    tables: list[ExtractedTable] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    page_count: int = Field(ge=1)
    truncated: bool = False
