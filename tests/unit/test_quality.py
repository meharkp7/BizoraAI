"""Tests for the quality-dashboard aggregation and endpoint."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.unit.test_api import app

from bizora import api
from bizora.core.config import Settings
from bizora.core.quality import (
    build_quality_summary,
    summarize_copilot_eval,
    summarize_diagram_evals,
)


@pytest.fixture()
def quality_reports(tmp_path: Path) -> dict[str, Path]:
    """Write one diagram report plus one copilot last-run file."""
    paper_dir = tmp_path / "evals" / "sram-puf-tilting"
    paper_dir.mkdir(parents=True)
    diagram_report = paper_dir / "eval-report.json"
    diagram_report.write_text(
        json.dumps(
            {
                "paper_id": "sram-puf-tilting",
                "classification": {"kind": "circuit", "confidence": 0.99},
                "figure_validation": {"errors": ["bad net"], "warnings": []},
                "text": {
                    "methodology": {"errors": [], "warnings": ["orphan node"]},
                    "structure": {"errors": [], "warnings": []},
                },
                "validator_pass_rate": 0.75,
                "usage": {"input_tokens": 100, "output_tokens": 50, "calls": 2},
                "gold": {"present": True},
            }
        ),
        encoding="utf-8",
    )
    copilot_report = tmp_path / "latest.json"
    copilot_report.write_text(
        json.dumps(
            {
                "total": 30,
                "passed": 29,
                "citation_accuracy": 0.97,
                "citation_recall": 1.0,
                "writes_detected": False,
                "input_tokens": 10,
                "output_tokens": 5,
            }
        ),
        encoding="utf-8",
    )
    return {"diagram_dir": tmp_path / "evals", "copilot": copilot_report}


def test_diagram_evals_aggregate_counts(quality_reports: dict[str, Path]) -> None:
    summaries = summarize_diagram_evals(quality_reports["diagram_dir"])

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.paper_id == "sram-puf-tilting"
    assert summary.validator_pass_rate == 0.75
    assert summary.error_count == 1
    assert summary.warning_count == 1
    assert summary.input_tokens == 100
    assert summary.output_tokens == 50
    assert summary.provider_calls == 2
    assert summary.gold_present is True
    assert summary.classification_kind == "circuit"
    assert summary.recorded_at.tzinfo is not None


def test_malformed_diagram_report_is_skipped(tmp_path: Path) -> None:
    paper_dir = tmp_path / "broken-paper"
    paper_dir.mkdir()
    (paper_dir / "eval-report.json").write_text("{not json", encoding="utf-8")

    assert summarize_diagram_evals(tmp_path) == []


def test_missing_diagram_dir_is_empty(tmp_path: Path) -> None:
    assert summarize_diagram_evals(tmp_path / "absent") == []


def test_copilot_eval_reduces_last_run(quality_reports: dict[str, Path]) -> None:
    summary = summarize_copilot_eval(quality_reports["copilot"])

    assert summary is not None
    assert summary.total == 30
    assert summary.passed == 29
    assert summary.citation_accuracy == 0.97
    assert summary.writes_detected is False
    assert summary.recorded_at.tzinfo is not None


def test_missing_copilot_eval_is_none(tmp_path: Path) -> None:
    assert summarize_copilot_eval(tmp_path / "absent.json") is None


def test_quality_summary_endpoint_aggregates_reports(
    quality_reports: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(
        _env_file=None,
        BIZORA_DIAGRAM_EVAL_DIR=str(quality_reports["diagram_dir"]),
        BIZORA_COPILOT_EVAL_RESULTS=str(quality_reports["copilot"]),
    )
    monkeypatch.setattr(api, "get_settings", lambda: settings)
    client = TestClient(app)

    response = client.get("/api/v1/quality/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["copilot_eval"]["passed"] == 29
    assert len(body["diagram_evals"]) == 1
    assert body["diagram_evals"][0]["paper_id"] == "sram-puf-tilting"
    assert "generated_at" in body


def test_quality_summary_endpoint_reports_missing_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(
        _env_file=None,
        BIZORA_DIAGRAM_EVAL_DIR=str(tmp_path / "absent"),
        BIZORA_COPILOT_EVAL_RESULTS=str(tmp_path / "absent.json"),
    )
    monkeypatch.setattr(api, "get_settings", lambda: settings)
    client = TestClient(app)

    response = client.get("/api/v1/quality/summary")

    assert response.status_code == 200
    assert response.json()["diagram_evals"] == []
    assert response.json()["copilot_eval"] is None


def test_build_quality_summary_marks_generation_time(
    quality_reports: dict[str, Path],
) -> None:
    summary = build_quality_summary(
        diagram_eval_dir=str(quality_reports["diagram_dir"]),
        copilot_eval_results=str(quality_reports["copilot"]),
    )

    assert summary.generated_at.tzinfo is not None
    assert summary.copilot_eval is not None
