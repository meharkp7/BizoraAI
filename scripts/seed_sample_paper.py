"""Seed the configured first-run sample paper into a database.

The default source is the local SRAM PUF PDF. That corpus file is intentionally
not committed, so fresh checkouts must supply an equivalent PDF with ``--pdf``;
stable identifiers are derived from the PDF exactly like an upload, and the
script prints the values to configure as ``BIZORA_SAMPLE_PAPER_*``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from bizora.core.config import get_settings
from bizora.core.errors import BizoraError
from bizora.core.extraction_persistence_service import ExtractionPersistenceService
from bizora.core.figure_service import persist_paper_figures
from bizora.core.papers import (
    is_valid_source_id,
    suggest_graph_id,
    suggest_project_id,
    suggest_source_id,
)
from bizora.core.pdf import PdfText, extract_page_texts, extract_text_from_pdf
from bizora.core.table_persistence_service import TablePersistenceService
from bizora.db.repository import get_latest_graph_revision
from bizora.db.session import get_session_factory
from bizora.providers.base import (
    MethodologyExtractionRequest,
    MethodologyProviderError,
)
from bizora.providers.baseten import BasetenMethodologyProvider
from bizora.providers.tables import TableExtractionRequest

DEFAULT_PDF_NAME = (
    "A_2_Bit_Cell_Tilting_SRAM-Based_PUF_With_a_BER_of_3.1E-10_and_an_Energy_of_21_FJ_Bit_in_65nm.pdf"
)
DEFAULT_PDF = Path(__file__).resolve().parents[1] / "research_papers" / DEFAULT_PDF_NAME
PAPER_TEXT_LIMIT = 120_000
DEFAULT_CREATED_BY_SAMPLE = "sample-seed"


@dataclass(frozen=True)
class SeedPlan:
    """Trusted identifiers and options for one sample-paper seed."""

    project_id: str
    graph_id: str
    source_id: str
    title: str | None
    created_by: str
    max_tables: int


def build_parser() -> argparse.ArgumentParser:
    """Build the seed script's command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pdf",
        type=Path,
        default=DEFAULT_PDF,
        help="Paper PDF to seed (default: local SRAM PUF corpus file).",
    )
    parser.add_argument("--project-id", default=None, help="Override the derived project ID.")
    parser.add_argument("--graph-id", default=None, help="Override the derived graph ID.")
    parser.add_argument("--source-id", default=None, help="Override the derived source ID.")
    parser.add_argument(
        "--title",
        default=None,
        help="Seed title; when omitted, the extraction provider infers it.",
    )
    parser.add_argument(
        "--created-by",
        default=DEFAULT_CREATED_BY_SAMPLE,
        help="Creator recorded on the seeded revision.",
    )
    parser.add_argument("--max-tables", type=int, default=10, help="Maximum tables to extract.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve and print identifiers without writing or calling a model.",
    )
    return parser


def _clean(value: str | None) -> str | None:
    cleaned = value.strip() if value else ""
    return cleaned or None


def resolve_seed_plan(
    pdf_bytes: bytes,
    filename: str,
    *,
    project_id: str | None = None,
    graph_id: str | None = None,
    source_id: str | None = None,
    title: str | None = None,
    created_by: str | None = DEFAULT_CREATED_BY_SAMPLE,
    max_tables: int = 10,
) -> tuple[PdfText, SeedPlan]:
    """Resolve stable seed identifiers from PDF bytes and overrides."""
    pdf = extract_text_from_pdf(pdf_bytes, max_chars=PAPER_TEXT_LIMIT)
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    if pdf.doc_title:
        stem = pdf.doc_title
    short_hash = pdf.sha256[:8]
    resolved_project = _clean(project_id) or suggest_project_id(stem, short_hash)
    resolved_graph = _clean(graph_id) or suggest_graph_id(stem, short_hash)
    resolved_source = _clean(source_id) or suggest_source_id(short_hash)
    resolved_created_by = _clean(created_by) or DEFAULT_CREATED_BY_SAMPLE
    resolved_title = _clean(title)

    if len(resolved_project) > 128 or len(resolved_graph) > 128:
        raise ValueError("Project and graph IDs must each be 128 characters or fewer.")
    if not is_valid_source_id(resolved_source):
        raise ValueError("Source IDs may contain letters, digits, and . _ : - (max 128).")
    if resolved_title is not None and len(resolved_title) > 300:
        raise ValueError("Seed titles must be 300 characters or fewer.")
    if len(resolved_created_by) > 128:
        raise ValueError("Creator names must be 128 characters or fewer.")
    if not 1 <= max_tables <= 20:
        raise ValueError("max_tables must be between 1 and 20.")

    return pdf, SeedPlan(
        project_id=resolved_project,
        graph_id=resolved_graph,
        source_id=resolved_source,
        title=resolved_title,
        created_by=resolved_created_by,
        max_tables=max_tables,
    )


async def seed_sample_paper(
    session: Session,
    provider: BasetenMethodologyProvider,
    *,
    pdf_bytes: bytes,
    filename: str,
    plan: SeedPlan,
) -> dict[str, object]:
    """Seed one paper, returning a JSON-serializable status report."""
    latest = get_latest_graph_revision(
        session,
        project_id=plan.project_id,
        graph_id=plan.graph_id,
    )
    if latest is not None:
        return {
            "status": "exists",
            "filename": filename,
            "project_id": plan.project_id,
            "graph_id": plan.graph_id,
            "source_id": plan.source_id,
            "title": latest.title,
            "workspace_path": f"/g/{plan.project_id}/{plan.graph_id}",
        }

    pdf = extract_text_from_pdf(pdf_bytes, max_chars=PAPER_TEXT_LIMIT)
    persist_paper_figures(
        session,
        project_id=plan.project_id,
        graph_id=plan.graph_id,
        pdf_bytes=pdf_bytes,
        page_texts=extract_page_texts(pdf_bytes),
        source_id=plan.source_id,
        created_by=plan.created_by,
    )
    graph = await ExtractionPersistenceService.extract_and_persist_initial(
        session,
        provider,
        MethodologyExtractionRequest(
            paper_text=pdf.text,
            project_id=plan.project_id,
            graph_id=plan.graph_id,
            source_id=plan.source_id,
            created_by=plan.created_by,
            title=plan.title,
        ),
    )

    warnings: list[str] = []
    if pdf.truncated:
        warnings.append(f"Paper text was truncated to {PAPER_TEXT_LIMIT} characters.")
    table_count = 0
    try:
        tables, table_warnings = await TablePersistenceService.extract_and_persist(
            session,
            provider,
            TableExtractionRequest(
                paper_text=pdf.text,
                project_id=plan.project_id,
                graph_id=plan.graph_id,
                source_id=plan.source_id,
                created_by=plan.created_by,
                max_tables=plan.max_tables,
            ),
        )
        table_count = len(tables)
        warnings.extend(table_warnings)
    except MethodologyProviderError:
        warnings.append("Results tables could not be extracted: the provider request failed.")

    return {
        "status": "created",
        "filename": filename,
        "project_id": plan.project_id,
        "graph_id": plan.graph_id,
        "source_id": plan.source_id,
        "title": graph.title,
        "version": graph.version,
        "tables": table_count,
        "warnings": warnings,
        "workspace_path": f"/g/{plan.project_id}/{plan.graph_id}",
    }


def main(argv: list[str] | None = None) -> int:
    """Seed the sample paper from command-line arguments."""
    load_dotenv()
    args = build_parser().parse_args(argv)
    pdf_path = Path(args.pdf)
    try:
        pdf_bytes = pdf_path.read_bytes()
    except OSError:
        print(f"Sample PDF not found: {pdf_path}", file=sys.stderr)
        print("Supply an equivalent paper with --pdf.", file=sys.stderr)
        return 2

    try:
        _, plan = resolve_seed_plan(
            pdf_bytes,
            pdf_path.name,
            project_id=args.project_id,
            graph_id=args.graph_id,
            source_id=args.source_id,
            title=args.title,
            created_by=args.created_by,
            max_tables=args.max_tables,
        )
    except ValueError as exc:
        print(f"Invalid seed request: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "planned",
                    "filename": pdf_path.name,
                    "project_id": plan.project_id,
                    "graph_id": plan.graph_id,
                    "source_id": plan.source_id,
                    "title": plan.title,
                    "workspace_path": f"/g/{plan.project_id}/{plan.graph_id}",
                },
                indent=2,
            )
        )
        return 0

    try:
        settings = get_settings()
    except ValueError as exc:
        print(f"Invalid sample configuration: {exc}", file=sys.stderr)
        return 2
    if not settings.enable_baseten:
        print("Baseten is disabled; set BIZORA_ENABLE_BASETEN=true to seed.", file=sys.stderr)
        return 2
    if not settings.baseten_api_key or not settings.baseten_model_name:
        print("Baseten credentials or model configuration are missing.", file=sys.stderr)
        return 2

    provider = BasetenMethodologyProvider(
        api_key=settings.baseten_api_key.get_secret_value(),
        model_name=settings.baseten_model_name,
        base_url=settings.baseten_base_url,
        timeout=300.0,
    )
    session = get_session_factory()()
    try:
        report = asyncio.run(
            seed_sample_paper(
                session,
                provider,
                pdf_bytes=pdf_bytes,
                filename=pdf_path.name,
                plan=plan,
            )
        )
    except (BizoraError, MethodologyProviderError) as exc:
        print(f"Sample seeding failed: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
