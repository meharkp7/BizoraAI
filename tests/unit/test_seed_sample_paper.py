"""Tests for the sample-paper seed script's pure identifier helpers."""

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest
from tests.unit.test_papers_api import make_pdf_bytes


def load_script():  # type: ignore[no-untyped-def]
    path = Path(__file__).resolve().parents[2] / "scripts" / "seed_sample_paper.py"
    spec = importlib.util.spec_from_file_location("seed_sample_paper", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_seed_plan_derives_stable_upload_identifiers() -> None:
    seed = load_script()
    pdf_bytes = make_pdf_bytes("Sample methods.")
    short_hash = hashlib.sha256(pdf_bytes).hexdigest()[:8]

    _, plan = seed.resolve_seed_plan(pdf_bytes, "Sample Paper.pdf")

    assert plan.project_id == f"sample-paper-{short_hash}"
    assert plan.graph_id == f"sample-paper-graph-{short_hash}"
    assert plan.source_id == f"paper-{short_hash}"
    assert plan.title is None
    assert plan.created_by == "sample-seed"
    assert plan.max_tables == 10


def test_seed_plan_prefers_explicit_identifiers_and_title() -> None:
    seed = load_script()
    pdf_bytes = make_pdf_bytes("Sample methods.")

    _, plan = seed.resolve_seed_plan(
        pdf_bytes,
        "Sample Paper.pdf",
        project_id=" custom-project ",
        graph_id="custom-graph",
        source_id="paper-custom",
        title=" Custom title ",
        created_by=" docs ",
        max_tables=3,
    )

    assert plan.project_id == "custom-project"
    assert plan.graph_id == "custom-graph"
    assert plan.source_id == "paper-custom"
    assert plan.title == "Custom title"
    assert plan.created_by == "docs"
    assert plan.max_tables == 3


def test_seed_plan_rejects_invalid_seed_options() -> None:
    seed = load_script()
    pdf_bytes = make_pdf_bytes("Sample methods.")

    with pytest.raises(ValueError, match="Source IDs"):
        seed.resolve_seed_plan(pdf_bytes, "Sample Paper.pdf", source_id="has spaces")
    with pytest.raises(ValueError, match="max_tables"):
        seed.resolve_seed_plan(pdf_bytes, "Sample Paper.pdf", max_tables=21)
    with pytest.raises(ValueError, match="300 characters"):
        seed.resolve_seed_plan(pdf_bytes, "Sample Paper.pdf", title="x" * 301)


def test_seed_parser_defaults_to_local_sram_corpus_file() -> None:
    seed = load_script()

    args = seed.build_parser().parse_args([])

    assert args.pdf.name == seed.DEFAULT_PDF_NAME
    assert args.pdf == seed.DEFAULT_PDF
    assert args.dry_run is False
