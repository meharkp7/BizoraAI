"""HTTP routes for the Bizora API."""

from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    status,
)
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from bizora.contracts.graph import MethodologyGraph
from bizora.contracts.patches import GraphPatch
from bizora.contracts.run import (
    ArtifactRecord,
    CreateExperimentRunRequest,
    ExperimentRun,
    MetricRecord,
    TransitionExperimentRunRequest,
)
from bizora.core.config import get_settings
from bizora.core.errors import BizoraError, ErrorCode
from bizora.core.extraction_persistence_service import (
    ExtractionPersistenceService,
)
from bizora.core.graph_persistence_service import GraphPersistenceService
from bizora.core.patch_service import GraphPatchService
from bizora.core.run_service import ExperimentRunService
from bizora.db.repository import (
    artifact_record_from_row,
    experiment_run_from_record,
    get_graph_revision,
    list_artifacts_for_run,
    list_experiment_runs,
    list_metrics_for_run,
    metric_record_from_row,
)
from bizora.db.session import get_db_session
from bizora.providers.base import (
    MethodologyExtractionRequest,
    MethodologyProvider,
)
from bizora.providers.fireworks import (
    FireworksMethodologyProvider,
    FireworksProviderError,
)

DB_SESSION_DEPENDENCY = Depends(get_db_session)

def get_fireworks_provider() -> FireworksMethodologyProvider:
    """Create the configured Fireworks provider or fail clearly."""

    try:
        settings = get_settings()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Fireworks provider configuration is invalid.",
        ) from exc

    if not settings.enable_fireworks:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Fireworks provider is disabled.",
        )

    if not settings.fireworks_api_key or not settings.fireworks_model_name:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Fireworks credentials or model configuration are missing.",
        )

    return FireworksMethodologyProvider(
        api_key=settings.fireworks_api_key.get_secret_value(),
        model_name=settings.fireworks_model_name,
        base_url=settings.fireworks_base_url,
    )

FIREWORKS_PROVIDER_DEPENDENCY = Depends(get_fireworks_provider)

router = APIRouter()

@router.post(
    "/api/v1/graphs/extract",
    response_model=MethodologyGraph,
    status_code=status.HTTP_201_CREATED,
    tags=["graphs"],
)
async def extract_graph(
    extraction_request: MethodologyExtractionRequest,
    session: Session = DB_SESSION_DEPENDENCY,
    provider: MethodologyProvider = FIREWORKS_PROVIDER_DEPENDENCY,
) -> MethodologyGraph:
    """Extract, validate, and persist an initial methodology graph."""

    try:
        return await ExtractionPersistenceService.extract_and_persist_initial(
            session,
            provider,
            extraction_request,
        )
    except FireworksProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Methodology extraction provider failed.",
        ) from exc


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


@router.post(
    "/api/v1/experiments/runs",
    response_model=ExperimentRun,
    status_code=status.HTTP_201_CREATED,
    tags=["experiments"],
)
def create_experiment_run(
    request: CreateExperimentRunRequest,
    session: Session = DB_SESSION_DEPENDENCY,
) -> ExperimentRun:
    """Create a pending run bound to an exact persisted graph revision."""
    return ExperimentRunService.create_run(
        session,
        request.config,
        run_id=request.run_id,
    )


@router.get(
    "/api/v1/experiments/runs/{run_id}",
    response_model=ExperimentRun,
    tags=["experiments"],
)
def get_experiment_run(
    run_id: str,
    session: Session = DB_SESSION_DEPENDENCY,
) -> ExperimentRun:
    """Return one experiment run by its identifier."""
    return ExperimentRunService.get_run(session, run_id)


@router.get(
    "/api/v1/experiments/runs",
    response_model=list[ExperimentRun],
    tags=["experiments"],
)
def list_runs(
    session: Session = DB_SESSION_DEPENDENCY,
    project_id: str | None = Query(default=None, max_length=128),
    graph_id: str | None = Query(default=None, max_length=128),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ExperimentRun]:
    """List runs newest-first, optionally filtered by project and graph."""
    return [
        experiment_run_from_record(record)
        for record in list_experiment_runs(
            session,
            project_id=project_id,
            graph_id=graph_id,
            limit=limit,
        )
    ]


@router.get(
    "/api/v1/experiments/runs/{run_id}/metrics",
    response_model=list[MetricRecord],
    tags=["experiments"],
)
def list_run_metrics(
    run_id: str,
    session: Session = DB_SESSION_DEPENDENCY,
) -> list[MetricRecord]:
    """List one run's persisted metric records."""
    ExperimentRunService.get_run(session, run_id)
    return [
        metric_record_from_row(row)
        for row in list_metrics_for_run(session, run_id)
    ]


@router.get(
    "/api/v1/experiments/runs/{run_id}/artifacts",
    response_model=list[ArtifactRecord],
    tags=["experiments"],
)
def list_run_artifacts(
    run_id: str,
    session: Session = DB_SESSION_DEPENDENCY,
) -> list[ArtifactRecord]:
    """List one run's persisted artifact records."""
    ExperimentRunService.get_run(session, run_id)
    return [
        artifact_record_from_row(row)
        for row in list_artifacts_for_run(session, run_id)
    ]


@router.post(
    "/api/v1/experiments/runs/{run_id}/transitions",
    response_model=ExperimentRun,
    tags=["experiments"],
)
def transition_experiment_run(
    run_id: str,
    request: TransitionExperimentRunRequest,
    session: Session = DB_SESSION_DEPENDENCY,
) -> ExperimentRun:
    """Move an experiment run to a new lifecycle state."""
    return ExperimentRunService.transition_run(
        session,
        run_id,
        to_state=request.to_state,
        error=request.error,
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register consistent JSON responses for domain exceptions."""

    @app.exception_handler(BizoraError)
    async def handle_bizora_error(
        request: Request,
        exc: BizoraError,
    ) -> JSONResponse:
        """Convert domain errors into stable HTTP responses."""
        del request

        if exc.code == ErrorCode.RESOURCE_CONFLICT:
            status_code = status.HTTP_409_CONFLICT
        elif exc.code == ErrorCode.RESOURCE_NOT_FOUND:
            status_code = status.HTTP_404_NOT_FOUND
        else:
            status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

        return JSONResponse(
            status_code=status_code,
            content=_error_payload(exc),
        )
