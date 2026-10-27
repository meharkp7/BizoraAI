"""HTTP routes for the Bizora API."""

import logging
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from bizora.contracts.comparison import RunComparison
from bizora.contracts.diff import GraphRevisionDiff
from bizora.contracts.graph import MethodologyGraph
from bizora.contracts.layout import GraphLayout
from bizora.contracts.patches import GraphPatch, GraphPatchBatch
from bizora.contracts.run import (
    ArtifactRecord,
    CreateExperimentRunRequest,
    ExperimentRun,
    MetricRecord,
    TransitionExperimentRunRequest,
)
from bizora.contracts.table import (
    ExtractedTable,
    PaperExtractionResponse,
    ParsedPaper,
    SuggestedIds,
)
from bizora.core.comparison_service import ComparisonService
from bizora.core.config import get_settings
from bizora.core.diff_service import RevisionDiffService
from bizora.core.errors import BizoraError, ErrorCode
from bizora.core.execution_service import ExecutionService, WorkerConfig
from bizora.core.extraction_persistence_service import (
    ExtractionPersistenceService,
)
from bizora.core.graph_persistence_service import GraphPersistenceService
from bizora.core.layout_service import LayoutService
from bizora.core.papers import (
    DEFAULT_CREATED_BY,
    is_valid_source_id,
    split_authors,
    suggest_graph_id,
    suggest_project_id,
    suggest_source_id,
)
from bizora.core.patch_service import GraphPatchService
from bizora.core.pdf import PdfText, extract_text_from_pdf
from bizora.core.run_service import ExperimentRunService
from bizora.core.table_persistence_service import TablePersistenceService
from bizora.db.repository import (
    artifact_record_from_row,
    experiment_run_from_record,
    extracted_table_from_record,
    get_graph_revision,
    get_latest_graph_revision,
    list_artifacts_for_run,
    list_experiment_runs,
    list_extracted_tables,
    list_metrics_for_run,
    metric_record_from_row,
)
from bizora.db.session import get_db_session, get_session_factory
from bizora.providers.base import (
    MethodologyExtractionRequest,
    MethodologyProvider,
    MethodologyProviderError,
)
from bizora.providers.baseten import BasetenMethodologyProvider
from bizora.providers.fireworks import FireworksMethodologyProvider
from bizora.providers.tables import TableExtractionRequest

logger = logging.getLogger(__name__)

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


def get_baseten_provider() -> BasetenMethodologyProvider:
    """Create the configured Baseten provider or fail clearly."""

    try:
        settings = get_settings()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Baseten provider configuration is invalid.",
        ) from exc

    if not settings.enable_baseten:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Baseten provider is disabled.",
        )

    if not settings.baseten_api_key or not settings.baseten_model_name:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Baseten credentials or model configuration are missing.",
        )

    # Reasoning models on serverless infrastructure can take minutes on the
    # first large request (cold start plus long reasoning traces).
    return BasetenMethodologyProvider(
        api_key=settings.baseten_api_key.get_secret_value(),
        model_name=settings.baseten_model_name,
        base_url=settings.baseten_base_url,
        timeout=300.0,
    )


BASETEN_PROVIDER_DEPENDENCY = Depends(get_baseten_provider)

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
    provider: MethodologyProvider = BASETEN_PROVIDER_DEPENDENCY,
) -> MethodologyGraph:
    """Extract, validate, and persist an initial methodology graph."""

    try:
        return await ExtractionPersistenceService.extract_and_persist_initial(
            session,
            provider,
            extraction_request,
        )
    except MethodologyProviderError as exc:
        logger.warning("Methodology extraction provider failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Methodology extraction provider failed.",
        ) from exc


PAPER_TEXT_LIMIT = 120_000


async def _read_upload(file: UploadFile) -> tuple[bytes, PdfText]:
    """Read and parse an uploaded PDF, mapping failures to 422 errors."""
    try:
        settings = get_settings()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Provider configuration is invalid.",
        ) from exc
    max_bytes = settings.max_upload_mb * 1024 * 1024
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise BizoraError(
            ErrorCode.INVALID_REQUEST,
            f"The uploaded file exceeds the {settings.max_upload_mb} MB limit.",
        )

    try:
        pdf = extract_text_from_pdf(data, max_chars=PAPER_TEXT_LIMIT)
    except ValueError as exc:
        raise BizoraError(ErrorCode.INVALID_REQUEST, str(exc)) from exc
    return data, pdf


def _suggest_ids(filename: str, pdf: PdfText) -> SuggestedIds:
    """Derive stable identifiers from the upload, not the paper domain."""
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    if pdf.doc_title:
        stem = pdf.doc_title
    short_hash = pdf.sha256[:8]
    return SuggestedIds(
        project_id=suggest_project_id(stem, short_hash),
        graph_id=suggest_graph_id(stem, short_hash),
        source_id=suggest_source_id(short_hash),
    )


@router.post(
    "/api/v1/papers/parse",
    response_model=ParsedPaper,
    tags=["papers"],
)
async def parse_paper(file: UploadFile) -> ParsedPaper:
    """Read an uploaded PDF's metadata without calling any model."""
    _, pdf = await _read_upload(file)
    filename = file.filename or "paper.pdf"
    return ParsedPaper(
        filename=filename,
        title=pdf.doc_title,
        authors=split_authors(pdf.doc_author),
        page_count=pdf.page_count,
        chars=len(pdf.text),
        sha256=pdf.sha256,
        truncated=pdf.truncated,
        suggested=_suggest_ids(filename, pdf),
    )


@router.post(
    "/api/v1/papers/extract",
    response_model=PaperExtractionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["papers"],
)
async def extract_paper(
    file: UploadFile,
    project_id: str | None = Form(default=None, max_length=128),
    graph_id: str | None = Form(default=None, max_length=128),
    source_id: str | None = Form(default=None),
    created_by: str | None = Form(default=None, max_length=128),
    title: str | None = Form(default=None, max_length=300),
    max_tables: int = Form(default=10, ge=1, le=20),
    session: Session = DB_SESSION_DEPENDENCY,
    provider: BasetenMethodologyProvider = BASETEN_PROVIDER_DEPENDENCY,
) -> PaperExtractionResponse:
    """Extract a methodology graph and results tables from an uploaded PDF.

    Identifier fields are optional: blanks fall back to stable suggestions
    derived from the upload, so any paper works with just the file.
    """
    _, pdf = await _read_upload(file)
    filename = file.filename or "paper.pdf"
    suggested = _suggest_ids(filename, pdf)

    resolved_project = project_id.strip() if project_id and project_id.strip() else suggested.project_id
    resolved_graph = graph_id.strip() if graph_id and graph_id.strip() else suggested.graph_id
    resolved_source = source_id.strip() if source_id and source_id.strip() else suggested.source_id
    resolved_author = created_by.strip() if created_by and created_by.strip() else DEFAULT_CREATED_BY

    if not is_valid_source_id(resolved_source):
        raise BizoraError(
            ErrorCode.INVALID_REQUEST,
            "Source IDs may contain letters, digits, and . _ : - (max 128).",
            details={"source_id": resolved_source},
        )

    try:
        graph = await ExtractionPersistenceService.extract_and_persist_initial(
            session,
            provider,
            MethodologyExtractionRequest(
                paper_text=pdf.text,
                project_id=resolved_project,
                graph_id=resolved_graph,
                source_id=resolved_source,
                created_by=resolved_author,
                title=title,
            ),
        )
    except MethodologyProviderError as exc:
        logger.warning("Methodology extraction provider failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Methodology extraction provider failed.",
        ) from exc

    warnings: list[str] = []
    if pdf.truncated:
        warnings.append(
            f"Paper text was truncated to {PAPER_TEXT_LIMIT} characters."
        )

    tables: list[ExtractedTable] = []
    try:
        tables, table_warnings = await TablePersistenceService.extract_and_persist(
            session,
            provider,
            TableExtractionRequest(
                paper_text=pdf.text,
                project_id=resolved_project,
                graph_id=resolved_graph,
                source_id=resolved_source,
                created_by=resolved_author,
                max_tables=max_tables,
            ),
        )
        warnings.extend(table_warnings)
    except MethodologyProviderError:
        warnings.append(
            "Results tables could not be extracted: the provider request failed."
        )

    return PaperExtractionResponse(
        graph=graph,
        tables=tables,
        warnings=warnings,
        page_count=pdf.page_count,
        truncated=pdf.truncated,
    )


@router.get(
    "/api/v1/graphs/{project_id}/{graph_id}/tables",
    response_model=list[ExtractedTable],
    tags=["graphs"],
)
def list_graph_tables(
    project_id: str,
    graph_id: str,
    session: Session = DB_SESSION_DEPENDENCY,
) -> list[ExtractedTable]:
    """List one graph's extracted results tables."""
    latest = get_latest_graph_revision(
        session,
        project_id=project_id,
        graph_id=graph_id,
    )
    if latest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Graph revision not found.",
        )
    return [
        extracted_table_from_record(record)
        for record in list_extracted_tables(
            session,
            project_id=project_id,
            graph_id=graph_id,
        )
    ]


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

@router.post(
    "/api/v1/graphs/{project_id}/{graph_id}/patch-batches",
    response_model=MethodologyGraph,
    status_code=status.HTTP_201_CREATED,
    tags=["graphs"],
)
def apply_graph_patch_batch(
    project_id: str,
    graph_id: str,
    batch: GraphPatchBatch,
    session: Session = DB_SESSION_DEPENDENCY,
) -> MethodologyGraph:
    """Apply a validated patch batch and persist one resulting revision."""
    first = batch.patches[0]
    if first.base_graph_id != graph_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Path graph_id must match the batch base_graph_id.",
        )

    base_record = get_graph_revision(
        session,
        project_id=project_id,
        graph_id=graph_id,
        version=first.base_version,
    )

    if base_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Base graph revision not found.",
        )

    base_graph = MethodologyGraph.model_validate(
        base_record.graph_payload
    )

    patched_graph = GraphPatchService.apply_patches(
        base_graph, batch.patches
    )

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


@router.put(
    "/api/v1/graphs/{project_id}/{graph_id}/revisions/{version}/layout",
    response_model=GraphLayout,
    tags=["graphs"],
)
def save_graph_layout(
    project_id: str,
    graph_id: str,
    version: int,
    layout: GraphLayout,
    session: Session = DB_SESSION_DEPENDENCY,
) -> GraphLayout:
    """Save a visual-only layout without altering the graph revision."""
    if (
        layout.project_id != project_id
        or layout.graph_id != graph_id
        or layout.version != version
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Path identifiers must match the layout payload.",
        )

    return LayoutService.save_layout(session, layout)


@router.get(
    "/api/v1/graphs/{project_id}/{graph_id}/revisions/{version}/layout",
    response_model=GraphLayout,
    tags=["graphs"],
)
def get_saved_graph_layout(
    project_id: str,
    graph_id: str,
    version: int,
    session: Session = DB_SESSION_DEPENDENCY,
) -> GraphLayout:
    """Return one revision's saved visual-only layout."""
    return LayoutService.get_layout(
        session,
        project_id=project_id,
        graph_id=graph_id,
        version=version,
    )


@router.get(
    "/api/v1/graphs/{project_id}/{graph_id}/diff",
    response_model=GraphRevisionDiff,
    tags=["graphs"],
)
def diff_graph_revisions(
    project_id: str,
    graph_id: str,
    session: Session = DB_SESSION_DEPENDENCY,
    base_version: int = Query(ge=1),
    target_version: int = Query(ge=1),
) -> GraphRevisionDiff:
    """Return the deterministic diff between two persisted revisions."""
    base_record = get_graph_revision(
        session,
        project_id=project_id,
        graph_id=graph_id,
        version=base_version,
    )
    target_record = get_graph_revision(
        session,
        project_id=project_id,
        graph_id=graph_id,
        version=target_version,
    )

    if base_record is None or target_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Graph revision not found.",
        )

    return RevisionDiffService.diff(
        MethodologyGraph.model_validate(base_record.graph_payload),
        MethodologyGraph.model_validate(target_record.graph_payload),
    )


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


def get_execution_service() -> ExecutionService:
    """Build the API-driven local execution worker.

    Separated for tests: endpoint tests substitute a stub instead of
    spawning the real supervised child process.
    """
    return ExecutionService(
        get_session_factory(),
        WorkerConfig(worker_id="api-executor", max_runtime_seconds=600),
    )


@router.post(
    "/api/v1/experiments/runs/{run_id}/execute",
    response_model=ExperimentRun,
    tags=["experiments"],
)
def execute_experiment_run(run_id: str) -> ExperimentRun:
    """Claim a run and supervise its adapter through completion."""
    return get_execution_service().execute_run(run_id)


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


@router.get(
    "/api/v1/experiments/comparisons",
    response_model=RunComparison,
    tags=["experiments"],
)
def compare_experiment_runs(
    session: Session = DB_SESSION_DEPENDENCY,
    baseline_run_id: str = Query(min_length=1, max_length=128),
    variant_run_id: str = Query(min_length=1, max_length=128),
) -> RunComparison:
    """Compare a variant run against a baseline run."""
    return ComparisonService.compare_runs(
        session,
        baseline_run_id=baseline_run_id,
        variant_run_id=variant_run_id,
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
