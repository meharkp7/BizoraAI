"""HTTP routes for the Bizora API."""

from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    HTTPException,
    Request,
    status,
)
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from bizora.contracts.graph import MethodologyGraph
from bizora.contracts.patches import GraphPatch
from bizora.core.errors import BizoraError, ErrorCode
from bizora.core.graph_persistence_service import GraphPersistenceService
from bizora.core.patch_service import GraphPatchService
from bizora.db.repository import get_graph_revision
from bizora.db.session import get_db_session

DB_SESSION_DEPENDENCY = Depends(get_db_session)
router = APIRouter()

def _error_payload(exc: BizoraError) -> dict[str, Any]:
    """Convert a domain exception into a stable JSON error body."""
    code = getattr(exc.code, "value", str(exc.code))
    details = getattr(exc, "details", {})

    return {
        "error": {
            "code": code,
            "message": str(exc),
            "details": details,
        }
    }


@router.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    """Report that the HTTP application is responding."""
    return {"status": "ok"}


@router.post(
    "/api/v1/graphs",
    response_model=MethodologyGraph,
    status_code=status.HTTP_201_CREATED,
    tags=["graphs"],
)
def create_graph(
    graph: MethodologyGraph,
    session: Session = DB_SESSION_DEPENDENCY,
) -> MethodologyGraph:
    """Validate and persist a graph's initial revision."""
    GraphPersistenceService.create_initial_revision(session, graph)
    return graph

@router.post(
    "/api/v1/graphs/{project_id}/{graph_id}/revisions",
    response_model=MethodologyGraph,
    status_code=status.HTTP_201_CREATED,
    tags=["graphs"],
)
def create_graph_revision(
    project_id: str,
    graph_id: str,
    graph: MethodologyGraph,
    session: Session = DB_SESSION_DEPENDENCY,
) -> MethodologyGraph:
    """Create a new revision from the exact current persisted snapshot."""
    if graph.project_id != project_id or graph.graph_id != graph_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Path identifiers must match the graph payload.",
        )

    record = GraphPersistenceService.create_revision(
        session,
        graph,
        created_by=graph.created_by,
    )
    return MethodologyGraph.model_validate(record.graph_payload)


@router.post(
    "/api/v1/graphs/{project_id}/{graph_id}/patches",
    response_model=MethodologyGraph,
    status_code=status.HTTP_201_CREATED,
    tags=["graphs"],
)
def apply_graph_patch(
    project_id: str,
    graph_id: str,
    patch: GraphPatch,
    session: Session = DB_SESSION_DEPENDENCY,
) -> MethodologyGraph:
    """Apply a validated patch and persist the resulting graph revision."""
    if patch.base_graph_id != graph_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Path graph_id must match patch.base_graph_id.",
        )

    base_record = get_graph_revision(
        session,
        project_id=project_id,
        graph_id=graph_id,
        version=patch.base_version,
    )

    if base_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Base graph revision not found.",
        )

    base_graph = MethodologyGraph.model_validate(
        base_record.graph_payload
    )

    patched_graph = GraphPatchService.apply_patch(base_graph, patch)

    # Re-check the latest persisted snapshot transactionally before saving.
    record = GraphPersistenceService.create_revision(
        session,
        base_graph,
        created_by=patched_graph.created_by,
        nodes=patched_graph.nodes,
        edges=patched_graph.edges,
        source_ids=patched_graph.source_ids,
        title=patched_graph.title,
    )

    return MethodologyGraph.model_validate(record.graph_payload)

@router.get(
    "/api/v1/graphs/{project_id}/{graph_id}/revisions/{version}",
    response_model=MethodologyGraph,
    tags=["graphs"],
)
def get_graph(
    project_id: str,
    graph_id: str,
    version: int,
    session: Session = DB_SESSION_DEPENDENCY,
) -> MethodologyGraph:
    """Return an exact persisted graph revision."""
    if version < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Version must be a positive integer.",
        )

    record = get_graph_revision(
        session,
        project_id=project_id,
        graph_id=graph_id,
        version=version,
    )

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Graph revision not found.",
        )

    return MethodologyGraph.model_validate(record.graph_payload)



def register_error_handlers(app: FastAPI) -> None:
    """Register consistent JSON responses for domain exceptions."""

    @app.exception_handler(BizoraError)
    async def handle_bizora_error(
        request: Request,
        exc: BizoraError,
    ) -> JSONResponse:
        """Convert domain errors into stable HTTP responses."""
        del request

        status_code = (
            status.HTTP_409_CONFLICT
            if exc.code == ErrorCode.RESOURCE_CONFLICT
            else status.HTTP_422_UNPROCESSABLE_CONTENT
        )

        return JSONResponse(
            status_code=status_code,
            content=_error_payload(exc),
        )
