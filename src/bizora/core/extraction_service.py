
"""Orchestrate methodology extraction and graph validation."""

from bizora.contracts.assumptions import annotate_graph
from bizora.contracts.graph import MethodologyGraph
from bizora.core.errors import BizoraError, ErrorCode, GraphValidationError
from bizora.core.extraction_cache import draft_key, load_draft, rekey_draft, save_draft
from bizora.core.graph_service import GraphService
from bizora.providers.base import (
    MethodologyExtractionRequest,
    MethodologyProvider,
)


class MethodologyExtractionService:
    """Turn provider output into a validated, unpersisted graph draft."""

    @staticmethod
    async def extract_draft(
        provider: MethodologyProvider,
        request: MethodologyExtractionRequest,
        *,
        use_cache: bool = True,
    ) -> MethodologyGraph:
        """Extract a draft and validate it without persisting it."""

        key = draft_key(request.paper_text, provider)
        cached = load_draft(key) if use_cache else None
        if cached is not None:
            draft = rekey_draft(cached, request)
        else:
            result = await provider.extract_methodology(request)
            draft = result.draft_graph
            save_draft(key, draft)
        # Mark every claim without evidence as assumed (with a reason) so
        # the draft visibly distinguishes fact from inference (R2).
        graph = annotate_graph(draft)

        # Ensure the provider returned a graph for the requested resource.
        if (
            graph.project_id != request.project_id
            or graph.graph_id != request.graph_id
        ):
            raise BizoraError(
                ErrorCode.INVALID_GRAPH,
                "Provider returned a graph for a different project or graph.",
                details={
                    "requested_project_id": request.project_id,
                    "returned_project_id": graph.project_id,
                    "requested_graph_id": request.graph_id,
                    "returned_graph_id": graph.graph_id,
                },
            )

        try:
            GraphService.validate(graph)
        except GraphValidationError as exc:
            raise BizoraError(
                ErrorCode.INVALID_GRAPH,
                "Extracted methodology graph failed validation.",
                details={"validation_error": str(exc)},
            ) from exc
        return graph