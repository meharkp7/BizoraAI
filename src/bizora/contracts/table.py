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


class DuplicatePaper(BaseModel):
    """An already-extracted graph matching a parse's suggested identifiers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str = Field(min_length=1, max_length=128)
    graph_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=300)
    workspace_path: str = Field(min_length=1, max_length=300)


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
    duplicate_of: DuplicatePaper | None = None


class PaperExtractionResponse(BaseModel):
    """Result of extracting one uploaded paper: graph plus tables."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    graph: MethodologyGraph
    tables: list[ExtractedTable] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    page_count: int = Field(ge=1)
    truncated: bool = False


class PaperImportRequest(BaseModel):
    """A request to fetch and extract a paper from an external reference."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str = Field(min_length=1, max_length=2048)
    title: str | None = Field(default=None, max_length=300)
    max_tables: int = Field(default=10, ge=1, le=20)


class PaperImportResponse(BaseModel):
    """The fetched paper's source facts plus its extraction result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str = Field(min_length=1, max_length=2048)
    source_url: str = Field(min_length=1, max_length=2048)
    filename: str = Field(min_length=1, max_length=128)
    extraction: PaperExtractionResponse


class SamplePaper(BaseModel):
    """Configured first-run paper and whether its workspace is seeded."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str = Field(min_length=1, max_length=128)
    graph_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=300)
    workspace_path: str = Field(min_length=1, max_length=300)
    available: bool = False
