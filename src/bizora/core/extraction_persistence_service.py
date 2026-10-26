
"""Persist validated methodology drafts as initial graph revisions."""

from sqlalchemy.orm import Session

from bizora.contracts.graph import MethodologyGraph
from bizora.core.errors import BizoraError, ErrorCode
from bizora.core.extraction_service import MethodologyExtractionService
from bizora.core.graph_persistence_service import GraphPersistenceService
from bizora.providers.base import (
    MethodologyExtractionRequest,
    MethodologyProvider,
)


class ExtractionPersistenceService:
    """Extract, validate, and persist a graph's initial revision."""

    @staticmethod
    async def extract_and_persist_initial(
        session: Session,
        provider: MethodologyProvider,
        request: MethodologyExtractionRequest,
    ) -> MethodologyGraph:
        """Persist a draft only if it is suitable as an initial revision."""

        graph = await MethodologyExtractionService.extract_draft(
            provider,
            request,
        )

        if graph.version != 1 or graph.parent_version is not None:
            raise BizoraError(
                ErrorCode.INVALID_GRAPH,
                "An extracted draft must be an initial revision.",
                details={
                    "version": graph.version,
                    "parent_version": graph.parent_version,
                },
            )

        if graph.created_by != request.created_by:
            raise BizoraError(
                ErrorCode.INVALID_GRAPH,
                "Extracted graph creator does not match the request.",
            )

        if request.source_id not in graph.source_ids:
            raise BizoraError(
                ErrorCode.INVALID_GRAPH,
                "Extracted graph must include the requested source ID.",
                details={"source_id": request.source_id},
            )

        record = GraphPersistenceService.create_initial_revision(
            session,
            graph,
        )

        return MethodologyGraph.model_validate(record.graph_payload)