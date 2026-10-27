
"""Provider-neutral contracts for methodology extraction."""

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from bizora.contracts.graph import MethodologyGraph

MAX_PAPER_TEXT_LENGTH = 500_000


class MethodologyExtractionRequest(BaseModel):
    """Input supplied to a methodology extraction provider."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    paper_text: str = Field(min_length=1, max_length=MAX_PAPER_TEXT_LENGTH)
    project_id: str = Field(min_length=1, max_length=128)
    graph_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1)
    created_by: str = Field(min_length=1, max_length=128)
    title: str | None = Field(default=None, max_length=300)


class MethodologyExtractionResult(BaseModel):
    """A provider's proposed graph, not yet trusted or persisted."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    draft_graph: MethodologyGraph
    provider_name: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    warnings: tuple[str, ...] = ()


@runtime_checkable
class MethodologyProvider(Protocol):
    """Interface implemented by every methodology extraction provider."""

    async def extract_methodology(
        self,
        request: MethodologyExtractionRequest,
    ) -> MethodologyExtractionResult:
        """Extract a proposed methodology graph from paper content."""
        ...