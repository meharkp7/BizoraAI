"""HTTP routes for the Bizora API."""

import logging
from typing import Annotated, Any

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
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from bizora.adapters.registry import create_default_registry
from bizora.contracts.assets import NodeRenderSpec
from bizora.contracts.comparison import RunComparison
from bizora.contracts.components import (
    CompatibilityPreflight,
    ComponentDetail,
    ComponentSummary,
    CopilotRequest,
    CopilotResponse,
    PreflightRequest,
    RemovalPreflight,
)
from bizora.contracts.diff import GraphRevisionDiff
from bizora.contracts.domain import GraphEntities
from bizora.contracts.execution import AdapterSummary
from bizora.contracts.figures import PaperFigure, ResponseUsage
from bizora.contracts.graph import MethodologyGraph
from bizora.contracts.layout import GraphLayout
from bizora.contracts.packs import SimulationPreview
from bizora.contracts.patches import GraphPatch, GraphPatchBatch
from bizora.contracts.run import (
    ArtifactRecord,
    CreateExperimentRunRequest,
    ExperimentRun,
    MetricRecord,
    TransitionExperimentRunRequest,
)
from bizora.contracts.streaming import PaperReportedMetric
from bizora.contracts.table import (
    ExtractedTable,
    PaperExtractionResponse,
    ParsedPaper,
    SuggestedIds,
)
from bizora.copilot.tools import CopilotContext
from bizora.core.comparison_service import ComparisonService
from bizora.core.component_catalog import get_component, search_components
from bizora.core.component_service import preflight_removal, preflight_replacement
from bizora.core.config import get_settings
from bizora.core.copilot_service import answer_copilot_async
from bizora.core.diff_service import RevisionDiffService
from bizora.core.entity_service import preview_graph, render_specs_for_graph, resolve_graph
from bizora.core.errors import BizoraError, ErrorCode
from bizora.core.execution_service import ExecutionService, WorkerConfig
from bizora.core.extraction_persistence_service import (
    ExtractionPersistenceService,
)
from bizora.core.figure_service import ingest_paper_figures, list_graph_figures
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
from bizora.core.pdf import PdfText, extract_page_texts, extract_text_from_pdf
from bizora.core.reported_service import discover_reported_metrics, reported_metrics_for_tables
from bizora.core.run_service import ExperimentRunService
from bizora.core.table_persistence_service import TablePersistenceService
from bizora.db.repository import (
    artifact_record_from_row,
    experiment_run_from_record,
    extracted_table_from_record,
    get_graph_revision,
    get_latest_graph_revision,
    get_paper_figure,
    list_artifacts_for_run,
    list_experiment_runs,
    list_extracted_tables,
    list_metrics_for_run,
    metric_record_from_row,
)
from bizora.db.repository import (
    get_experiment_run as get_experiment_run_record,
)
from bizora.db.session import get_db_session, get_session_factory
from bizora.providers.base import (
    MethodologyExtractionRequest,
    MethodologyProvider,
    MethodologyProviderError,
)
from bizora.providers.baseten import BasetenMethodologyProvider
from bizora.providers.copilot import CopilotProvider
from bizora.providers.fireworks import FireworksMethodologyProvider
from bizora.providers.muse import MuseMethodologyProvider
from bizora.providers.muse_copilot import MuseCopilotProvider
from bizora.providers.tables import TableExtractionRequest
from bizora.streaming.bus import get_shared_bus

logger = logging.getLogger(__name__)

DB_SESSION_DEPENDENCY = Depends(get_db_session)


def get_muse_provider() -> MuseMethodologyProvider:
    """Create the Muse vision provider or fail clearly when unconfigured."""
    try:
        return MuseMethodologyProvider()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Muse credentials are missing.",
        ) from exc


MUSE_PROVIDER_DEPENDENCY = Depends(get_muse_provider)


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

    resolved_project = (
        project_id.strip() if project_id and project_id.strip() else suggested.project_id
    )
    resolved_graph = graph_id.strip() if graph_id and graph_id.strip() else suggested.graph_id
    resolved_source = source_id.strip() if source_id and source_id.strip() else suggested.source_id
    resolved_author = (
        created_by.strip() if created_by and created_by.strip() else DEFAULT_CREATED_BY
    )

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
        warnings.append(f"Paper text was truncated to {PAPER_TEXT_LIMIT} characters.")

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
        warnings.append("Results tables could not be extracted: the provider request failed.")

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

    base_graph = MethodologyGraph.model_validate(base_record.graph_payload)

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

    base_graph = MethodologyGraph.model_validate(base_record.graph_payload)

    patched_graph = GraphPatchService.apply_patches(base_graph, batch.patches)

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


@router.get(
    "/api/v1/graphs/{project_id}/{graph_id}/revisions/{version}/entities",
    response_model=GraphEntities,
    tags=["graphs"],
)
def get_graph_entities(
    project_id: str,
    graph_id: str,
    version: int,
    session: Session = DB_SESSION_DEPENDENCY,
) -> GraphEntities:
    """Return domain classification plus per-node entity resolutions."""
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

    graph = MethodologyGraph.model_validate(record.graph_payload)
    return resolve_graph(graph)


@router.get(
    "/api/v1/graphs/{project_id}/{graph_id}/revisions/{version}/simulation-preview",
    response_model=SimulationPreview | None,
    tags=["graphs"],
)
def get_simulation_preview(
    project_id: str,
    graph_id: str,
    version: int,
    session: Session = DB_SESSION_DEPENDENCY,
) -> SimulationPreview | None:
    """Return the routed pack's simulation preview, or null when absent.

    A missing preview is a normal state (most graphs have none), so it
    returns 200 null instead of 404 noise; unknown revisions still 404.
    """
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

    graph = MethodologyGraph.model_validate(record.graph_payload)
    return preview_graph(graph)


@router.get(
    "/api/v1/graphs/{project_id}/{graph_id}/revisions/{version}/render-specs",
    response_model=list[NodeRenderSpec],
    tags=["graphs"],
)
def get_render_specs(
    project_id: str,
    graph_id: str,
    version: int,
    session: Session = DB_SESSION_DEPENDENCY,
) -> tuple[NodeRenderSpec, ...]:
    """Return per-node 3D visuals; nodes without one are omitted."""
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

    graph = MethodologyGraph.model_validate(record.graph_payload)
    return render_specs_for_graph(graph)


@router.get(
    "/api/v1/components",
    response_model=list[ComponentSummary],
    tags=["components"],
)
def list_components(
    q: str = Query(default=""),
    domain: str | None = Query(default=None),
    category: str | None = Query(default=None),
    generic: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> tuple[ComponentSummary, ...]:
    """Search the component library with optional filters."""
    return search_components(q, domain=domain, category=category, generic=generic, limit=limit)


@router.get(
    "/api/v1/components/{component_id}",
    response_model=ComponentDetail,
    tags=["components"],
)
def get_component_detail(component_id: str) -> ComponentDetail:
    """Return one component library entry with specs and configuration."""
    detail = get_component(component_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Component not found.",
        )
    return detail


def _revision_or_404(
    session: Session, project_id: str, graph_id: str, version: int
) -> MethodologyGraph:
    """Load one persisted revision or raise the standard HTTP errors."""
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
    "/api/v1/graphs/{project_id}/{graph_id}/revisions/{version}/nodes/{node_id}/preflight",
    response_model=CompatibilityPreflight,
    tags=["graphs"],
)
def preflight_node_replacement(
    project_id: str,
    graph_id: str,
    version: int,
    node_id: str,
    request: PreflightRequest,
    session: Session = DB_SESSION_DEPENDENCY,
) -> CompatibilityPreflight:
    """Validate a catalog replacement against one node without writing."""
    graph = _revision_or_404(session, project_id, graph_id, version)
    return preflight_replacement(graph, node_id, request.component_id, request.config)


@router.post(
    "/api/v1/graphs/{project_id}/{graph_id}/revisions/{version}/nodes/{node_id}/removal-preflight",
    response_model=RemovalPreflight,
    tags=["graphs"],
)
def preflight_node_removal(
    project_id: str,
    graph_id: str,
    version: int,
    node_id: str,
    session: Session = DB_SESSION_DEPENDENCY,
) -> RemovalPreflight:
    """Preview removing one node: neighbors, dropped edges, paper claims."""
    graph = _revision_or_404(session, project_id, graph_id, version)
    return preflight_removal(graph, node_id)


def _copilot_provider_or_none() -> CopilotProvider | None:
    """Return the LLM copilot provider, or None when no key is configured.

    Without a provider the route stays on the deterministic fast path;
    the key itself is never logged or returned.
    """
    try:
        return MuseCopilotProvider()
    except ValueError:
        logger.info("Copilot LLM provider unavailable; using deterministic fast path.")
        return None


@router.post(
    "/api/v1/graphs/{project_id}/{graph_id}/revisions/{version}/copilot",
    response_model=CopilotResponse,
    tags=["graphs"],
)
async def ask_copilot(
    project_id: str,
    graph_id: str,
    version: int,
    request: CopilotRequest,
    session: Session = DB_SESSION_DEPENDENCY,
) -> CopilotResponse:
    """Answer one copilot message against the catalog and graph state."""
    graph = _revision_or_404(session, project_id, graph_id, version)

    def load_revision(target: int) -> MethodologyGraph | None:
        record = get_graph_revision(
            session, project_id=project_id, graph_id=graph_id, version=target
        )
        if record is None:
            return None
        return MethodologyGraph.model_validate(record.graph_payload)

    def list_runs() -> list[ExperimentRun]:
        return [
            experiment_run_from_record(record)
            for record in list_experiment_runs(session, project_id=project_id, graph_id=graph_id)
        ]

    def get_run(run_id: str) -> ExperimentRun | None:
        record = get_experiment_run_record(session, run_id)
        if record is None:
            return None
        return experiment_run_from_record(record)

    def list_metrics(run_id: str) -> list[MetricRecord]:
        return [metric_record_from_row(row) for row in list_metrics_for_run(session, run_id)]

    def list_tables() -> list[ExtractedTable]:
        return [
            extracted_table_from_record(record)
            for record in list_extracted_tables(
                session, project_id=project_id, graph_id=graph_id
            )
        ]

    def list_figures() -> list[PaperFigure]:
        return list(list_graph_figures(session, project_id=project_id, graph_id=graph_id))

    context = CopilotContext(
        graph=graph,
        selected_node_id=request.selected_node_id,
        load_revision=load_revision,
        list_runs=list_runs,
        get_run=get_run,
        list_metrics=list_metrics,
        list_tables=list_tables,
        list_figures=list_figures,
    )
    return await answer_copilot_async(
        graph,
        request.message,
        request.selected_node_id,
        provider=_copilot_provider_or_none(),
        context=context,
        mode="auto",
    )


@router.get(
    "/api/v1/experiments/adapters",
    response_model=list[AdapterSummary],
    tags=["experiments"],
)
def list_adapters() -> list[AdapterSummary]:
    """Return the registered execution adapters the UI may offer."""
    registry = create_default_registry()
    summaries = []
    for adapter_id, adapter_version in registry.available():
        adapter = registry.resolve(adapter_id, adapter_version)
        summaries.append(
            AdapterSummary(
                adapter_id=adapter_id,
                adapter_version=adapter_version,
                description=type(adapter).__doc__ or "Registered execution adapter.",
            )
        )
    return summaries


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
    if layout.project_id != project_id or layout.graph_id != graph_id or layout.version != version:
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


class FigureIngestResponse(BaseModel):
    """Outcome of one figure-overlay ingest, served to the UI."""

    figures: list[PaperFigure] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    truncated: bool = False
    skipped: int = 0
    usage: list[ResponseUsage] = Field(default_factory=list)


@router.post(
    "/api/v1/graphs/{project_id}/{graph_id}/revisions/{version}/figures",
    response_model=FigureIngestResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["graphs"],
)
async def ingest_graph_figures(
    project_id: str,
    graph_id: str,
    version: int,
    file: UploadFile,
    source_id: str | None = Form(default=None),
    created_by: str | None = Form(default=None, max_length=128),
    session: Session = DB_SESSION_DEPENDENCY,
    provider: MuseMethodologyProvider = MUSE_PROVIDER_DEPENDENCY,
) -> FigureIngestResponse:
    """Ingest one PDF's figures for a revision: describe, localize, persist.

    The source paper travels with the request because figure bytes are
    never stored elsewhere. A PDF with no embedded images yields an
    empty figure list, never invented figures.
    """
    graph = _revision_or_404(session, project_id, graph_id, version)
    data, _ = await _read_upload(file)
    resolved_source = (
        source_id.strip() if source_id and source_id.strip() else graph.source_ids[0]
    )
    resolved_author = (
        created_by.strip() if created_by and created_by.strip() else DEFAULT_CREATED_BY
    )
    try:
        report = await ingest_paper_figures(
            session,
            graph=graph,
            pdf_bytes=data,
            page_texts=extract_page_texts(data),
            source_id=resolved_source,
            created_by=resolved_author,
            provider=provider,
        )
    except MethodologyProviderError as exc:
        logger.warning("Figure vision provider failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Figure vision provider failed.",
        ) from exc
    return FigureIngestResponse(
        figures=list(report.figures),
        warnings=list(report.warnings),
        truncated=report.truncated,
        skipped=report.skipped,
        usage=list(report.usage),
    )


@router.get(
    "/api/v1/graphs/{project_id}/{graph_id}/figures",
    response_model=list[PaperFigure],
    tags=["graphs"],
)
def list_revision_figures(
    project_id: str,
    graph_id: str,
    session: Session = DB_SESSION_DEPENDENCY,
) -> list[PaperFigure]:
    """List one graph's persisted figures with their regions."""
    return list(
        list_graph_figures(session, project_id=project_id, graph_id=graph_id)
    )


@router.get(
    "/api/v1/graphs/{project_id}/{graph_id}/figures/{figure_id}/image",
    tags=["graphs"],
)
def get_figure_image(
    project_id: str,
    graph_id: str,
    figure_id: str,
    session: Session = DB_SESSION_DEPENDENCY,
) -> Response:
    """Serve one persisted figure's image bytes."""
    record = get_paper_figure(
        session, project_id=project_id, graph_id=graph_id, figure_id=figure_id
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Figure not found.",
        )
    return Response(content=record.image_bytes, media_type=record.mime_type or "image/png")


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
        telemetry_bus=get_shared_bus(),
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
    return [metric_record_from_row(row) for row in list_metrics_for_run(session, run_id)]


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
    return [artifact_record_from_row(row) for row in list_artifacts_for_run(session, run_id)]


@router.get(
    "/api/v1/experiments/runs/{run_id}/reported-metrics",
    response_model=list[PaperReportedMetric],
    tags=["experiments"],
)
def list_run_reported_metrics(
    run_id: str,
    session: Session = DB_SESSION_DEPENDENCY,
    names: Annotated[list[str] | None, Query()] = None,
) -> list[PaperReportedMetric]:
    """Quote the named metrics from the run's graph tables, with evidence."""
    run = ExperimentRunService.get_run(session, run_id)
    tables = [
        extracted_table_from_record(record)
        for record in list_extracted_tables(
            session,
            project_id=run.config.project_id,
            graph_id=run.config.graph_id,
        )
    ]
    return list(reported_metrics_for_tables(tables, names or []))


@router.get(
    "/api/v1/graphs/{project_id}/{graph_id}/reported-metrics",
    response_model=list[PaperReportedMetric],
    tags=["graphs"],
)
def list_graph_reported_metrics(
    project_id: str,
    graph_id: str,
    session: Session = DB_SESSION_DEPENDENCY,
    names: Annotated[list[str] | None, Query()] = None,
) -> list[PaperReportedMetric]:
    """Quote the paper's reported numbers from the graph's tables.

    With names, quotes exactly those metrics; without, discovers
    every numeric header. Every entry is labelled by the caller as
    reported by the paper — the baseline Stage 2 compares against.
    """
    tables = [
        extracted_table_from_record(record)
        for record in list_extracted_tables(
            session, project_id=project_id, graph_id=graph_id
        )
    ]
    if names:
        return list(reported_metrics_for_tables(tables, names))
    return list(discover_reported_metrics(tables))


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
