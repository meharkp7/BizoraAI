"""Tests for the gold-set evaluation harness."""

import asyncio
import json
from pathlib import Path

import pytest

from bizora.contracts.gold import GoldManifest, GoldPaper, GoldPaperResult
from bizora.contracts.graph import MethodologyGraph
from bizora.eval_gold import (
    BaselineEmptyProvider,
    domain_matches,
    evaluate_paper,
    format_report,
    run_eval,
    score_components,
    summarize,
    terms_match,
)


def make_paper(**overrides: object) -> GoldPaper:
    base: dict[str, object] = {
        "paper_id": "demo-paper",
        "pdf_path": "tests/gold/papers/demo-paper.pdf",
        "domain_tags": ["Embedded IoT"],
        "components": [
            {"name": "ESP32 DevKit", "aliases": ["ESP32"]},
            {"name": "Soil sensor"},
        ],
    }
    base.update(overrides)
    return GoldPaper.model_validate(base)


def make_minimal_pdf_bytes(text: str) -> bytes:
    """Assemble a minimal one-page PDF with computed xref offsets."""
    safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({safe}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length "
        + str(len(stream)).encode("latin-1")
        + b" >>\nstream\n"
        + stream
        + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode("latin-1") + body + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode("latin-1")
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n"
    ).encode("latin-1")
    return out


def test_domain_matches_is_case_insensitive() -> None:
    assert domain_matches("generic", ("Generic",)) is True
    assert domain_matches("generic", ("embedded IoT",)) is False


def test_score_components_matches_aliases() -> None:
    paper = make_paper()

    matched_expected, matched_predicted = score_components(("esp32", "Other part"), paper)

    assert matched_expected == 1
    assert matched_predicted == 1


def test_score_components_empty_prediction() -> None:
    paper = make_paper()

    assert score_components((), paper) == (0, 0)


def test_terms_match_containment_both_directions() -> None:
    assert terms_match("LoRA", "LoRA rank decomposition matrices A and B") is True
    assert terms_match("LoRA rank decomposition matrices A and B", "LoRA") is True
    assert terms_match("ESP32 DevKit", "esp32 devkit") is True
    assert terms_match("LoRA", "Vision Transformer") is False
    assert terms_match("", "LoRA") is False
    assert terms_match("LoRA", "") is False


def test_score_components_matches_descriptive_labels() -> None:
    paper = make_paper()

    matched_expected, matched_predicted = score_components(
        ("ESP32 DevKit board revision C", "Unrelated widget"), paper
    )

    assert matched_expected == 1
    assert matched_predicted == 1


def test_evaluate_missing_pdf_reports_missing(tmp_path: Path) -> None:
    paper = make_paper()

    result = asyncio.run(
        evaluate_paper(paper, repo_root=tmp_path, provider=BaselineEmptyProvider())
    )

    assert result.status == "missing"
    assert result.detail == f"pdf: {paper.pdf_path}"


def test_evaluate_ok_path_uses_pipeline_entry_points(tmp_path: Path) -> None:
    pdf_dir = tmp_path / "tests" / "gold" / "papers"
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "demo-paper.pdf").write_bytes(make_minimal_pdf_bytes("ESP32 soil monitor"))
    paper = make_paper()

    result = asyncio.run(
        evaluate_paper(paper, repo_root=tmp_path, provider=BaselineEmptyProvider())
    )

    assert result.status == "ok"
    assert result.predicted_domain is not None
    assert result.predicted_components == 0
    assert result.matched_expected == 0


def test_evaluate_bad_pdf_reports_error(tmp_path: Path) -> None:
    pdf_dir = tmp_path / "tests" / "gold" / "papers"
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "demo-paper.pdf").write_bytes(b"%PDF-1.4 not a real pdf")
    paper = make_paper()

    result = asyncio.run(
        evaluate_paper(paper, repo_root=tmp_path, provider=BaselineEmptyProvider())
    )

    assert result.status == "error"


def test_zero_papers_report_has_honest_zeros() -> None:
    manifest = GoldManifest.model_validate({"version": 1, "papers": []})
    report = summarize(manifest, (), provider_name="gold-baseline")

    assert report.domain_accuracy == 0.0
    assert report.component_precision == 0.0
    assert report.component_recall == 0.0
    text = format_report(report, manifest_path=Path("tests/gold/manifest.json"))
    assert "awaiting gold papers" in text


def test_run_eval_mixed_statuses(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "papers": [
                    make_paper().model_dump(),
                    make_paper(
                        paper_id="absent", pdf_path="tests/gold/papers/absent.pdf"
                    ).model_dump(),
                ],
            }
        ),
        encoding="utf-8",
    )
    pdf_dir = tmp_path / "tests" / "gold" / "papers"
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "demo-paper.pdf").write_bytes(make_minimal_pdf_bytes("ESP32 soil monitor"))

    report = asyncio.run(
        run_eval(
            manifest_path,
            provider=BaselineEmptyProvider(),
            provider_name="gold-baseline",
            repo_root=tmp_path,
        )
    )

    assert report.papers_total == 2
    assert report.evaluated == 1
    assert report.missing == 1
    assert report.errors == 0


def test_summarize_micro_averages_only_ok_papers() -> None:
    manifest = GoldManifest.model_validate({"version": 1, "papers": []})
    results = (
        GoldPaperResult(
            paper_id="a",
            status="ok",
            predicted_domain="generic",
            domain_match=True,
            expected_components=2,
            predicted_components=2,
            matched_expected=1,
            matched_predicted=1,
        ),
        GoldPaperResult(
            paper_id="b",
            status="missing",
            expected_components=4,
            predicted_components=0,
            matched_expected=0,
            matched_predicted=0,
        ),
    )
    report = summarize(manifest, results, provider_name="gold-baseline")

    assert report.domain_accuracy == 1.0
    assert report.component_precision == 0.5
    assert report.component_recall == 0.5


def test_baseline_provider_returns_empty_graph() -> None:
    from bizora.providers.base import MethodologyExtractionRequest

    request = MethodologyExtractionRequest(
        paper_text="Some paper text.",
        project_id="p-1",
        graph_id="g-1",
        source_id="paper-1",
        created_by="gold-eval",
    )
    result = asyncio.run(BaselineEmptyProvider().extract_methodology(request))

    assert isinstance(result.draft_graph, MethodologyGraph)
    assert result.draft_graph.nodes == ()
    assert result.provider_name == "gold-baseline"


def _write_demo_pdf(root: Path) -> None:
    pdf_dir = root / "tests" / "gold" / "papers"
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "demo-paper.pdf").write_bytes(make_minimal_pdf_bytes("ESP32 soil monitor"))


def test_cache_hit_skips_provider_call(tmp_path: Path) -> None:
    from bizora.eval_gold import build_provider

    _write_demo_pdf(tmp_path)
    cache_dir = tmp_path / "cache"
    paper = make_paper()

    first = asyncio.run(
        evaluate_paper(
            paper,
            repo_root=tmp_path,
            provider=BaselineEmptyProvider(),
            provider_name="gold-baseline",
            cache_dir=cache_dir,
        )
    )
    assert first.status == "ok"
    assert list(cache_dir.iterdir()) != []

    class ExplodingProvider(BaselineEmptyProvider):
        async def extract_methodology(self, request):  # type: ignore[override]
            raise AssertionError("provider must not be called on a cache hit")

    second = asyncio.run(
        evaluate_paper(
            paper,
            repo_root=tmp_path,
            provider=ExplodingProvider(),
            provider_name="gold-baseline",
            cache_dir=cache_dir,
        )
    )
    assert second.status == "ok"
    assert build_provider("baseline").provider_name == "gold-baseline"


def test_refresh_bypasses_cache(tmp_path: Path) -> None:
    _write_demo_pdf(tmp_path)
    cache_dir = tmp_path / "cache"
    paper = make_paper()
    asyncio.run(
        evaluate_paper(
            paper,
            repo_root=tmp_path,
            provider=BaselineEmptyProvider(),
            provider_name="gold-baseline",
            cache_dir=cache_dir,
        )
    )

    class ExplodingProvider(BaselineEmptyProvider):
        async def extract_methodology(self, request):  # type: ignore[override]
            raise RuntimeError("live call attempted")

    result = asyncio.run(
        evaluate_paper(
            paper,
            repo_root=tmp_path,
            provider=ExplodingProvider(),
            provider_name="gold-baseline",
            cache_dir=cache_dir,
            refresh=True,
        )
    )
    assert result.status == "error"


def test_run_eval_split_filters_held_out(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "papers": [
                    make_paper().model_dump(),
                    make_paper(
                        paper_id="held",
                        pdf_path="tests/gold/papers/absent.pdf",
                        held_out=True,
                    ).model_dump(),
                ],
            }
        ),
        encoding="utf-8",
    )
    _write_demo_pdf(tmp_path)

    dev = asyncio.run(
        run_eval(
            manifest_path,
            provider=BaselineEmptyProvider(),
            provider_name="gold-baseline",
            repo_root=tmp_path,
            split="dev",
        )
    )
    assert dev.papers_total == 1
    held = asyncio.run(
        run_eval(
            manifest_path,
            provider=BaselineEmptyProvider(),
            provider_name="gold-baseline",
            repo_root=tmp_path,
            split="heldout",
        )
    )
    assert held.papers_total == 1
    assert held.missing == 1


def test_format_report_includes_usage_line() -> None:
    manifest = GoldManifest.model_validate({"version": 1, "papers": []})
    report = summarize(manifest, (), provider_name="muse")

    text = format_report(
        report,
        manifest_path=Path("tests/gold/manifest.json"),
        usage={"live_calls": 2, "input_tokens": 10, "output_tokens": 5},
    )
    assert "tokens_input=10 tokens_output=5 live_calls=2" in text
    plain = format_report(report, manifest_path=Path("tests/gold/manifest.json"))
    assert "tokens_input" not in plain


def test_build_provider_muse_requires_key(monkeypatch) -> None:
    from bizora.eval_gold import build_provider
    from bizora.providers.muse import MuseMethodologyProvider

    monkeypatch.setenv("MUSE_API_KEY", "")
    with pytest.raises(ValueError, match="Muse provider unavailable"):
        build_provider("muse")
    monkeypatch.setenv("MUSE_API_KEY", "fake-test-key")
    assert isinstance(build_provider("muse"), MuseMethodologyProvider)
