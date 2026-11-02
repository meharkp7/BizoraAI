
"""Aggregate committed eval reports into the quality-dashboard summary.

Diagram evals come from one `eval-report.json` per paper directory (written
by `scripts/eval_diagrams.py`); the copilot numbers come from the harness's
last-run file. Reports carry no timestamps, so each summary's `recorded_at`
is the report file's modification time — the dashboard shows exactly how
fresh every number is. Missing reports mean "not run yet", never an error;
unparseable reports are skipped with a warning, never silently trusted.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from bizora.contracts.quality import (
    CopilotEvalSummary,
    DiagramEvalSummary,
    QualitySummary,
)

logger = logging.getLogger(__name__)


def _recorded_at(path: Path) -> datetime:
    """Return a report file's modification time as an aware datetime."""
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def _count_list_entries(section: Any, key: str) -> int:
    """Count entries in `section[key]`, tolerating missing shapes."""
    if not isinstance(section, dict):
        return 0
    entries = section.get(key)
    return len(entries) if isinstance(entries, list) else 0


def _as_int(value: Any) -> int | None:
    """Return an int for bool-free int/float values, else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _as_float(value: Any) -> float | None:
    """Return a float for bool-free numeric values, else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def summarize_diagram_eval(path: Path) -> DiagramEvalSummary | None:
    """Reduce one `eval-report.json` to dashboard numbers, or skip it."""
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Skipping unreadable diagram eval report %s: %s", path, exc)
        return None
    if not isinstance(report, dict):
        logger.warning("Skipping malformed diagram eval report %s: not an object", path)
        return None

    usage = report.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    figure_validation = report.get("figure_validation")
    text = report.get("text")
    text = text if isinstance(text, dict) else {}
    gold = report.get("gold")
    gold = gold if isinstance(gold, dict) else {}
    classification = report.get("classification")
    classification = classification if isinstance(classification, dict) else {}

    pass_rate = _as_float(report.get("validator_pass_rate"))
    paper_id = report.get("paper_id")
    if not isinstance(paper_id, str) or not paper_id or pass_rate is None:
        logger.warning("Skipping diagram eval report %s: missing paper_id or pass rate", path)
        return None

    payload = {
        "paper_id": paper_id,
        "recorded_at": _recorded_at(path),
        "validator_pass_rate": pass_rate,
        "error_count": (
            _count_list_entries(figure_validation, "errors")
            + _count_list_entries(text.get("methodology"), "errors")
            + _count_list_entries(text.get("structure"), "errors")
        ),
        "warning_count": (
            _count_list_entries(figure_validation, "warnings")
            + _count_list_entries(text.get("methodology"), "warnings")
            + _count_list_entries(text.get("structure"), "warnings")
        ),
        "input_tokens": _as_int(usage.get("input_tokens")) or 0,
        "output_tokens": _as_int(usage.get("output_tokens")) or 0,
        "provider_calls": _as_int(usage.get("calls")) or 0,
        "gold_present": gold.get("present") is True,
        "classification_kind": (
            classification.get("kind") if isinstance(classification.get("kind"), str) else None
        ),
    }
    try:
        return DiagramEvalSummary.model_validate(payload)
    except ValidationError as exc:
        logger.warning("Skipping invalid diagram eval report %s: %s", path, exc)
        return None


def summarize_diagram_evals(directory: Path) -> list[DiagramEvalSummary]:
    """Summarize every paper report in a directory, sorted by paper."""
    if not directory.is_dir():
        return []
    summaries: list[DiagramEvalSummary] = []
    for path in sorted(directory.glob("*/eval-report.json")):
        summary = summarize_diagram_eval(path)
        if summary is not None:
            summaries.append(summary)
    return sorted(summaries, key=lambda summary: summary.paper_id)


def summarize_copilot_eval(path: Path) -> CopilotEvalSummary | None:
    """Reduce the copilot harness's last-run file, or return None."""
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Skipping unreadable copilot eval report %s: %s", path, exc)
        return None
    if not isinstance(report, dict):
        logger.warning("Skipping malformed copilot eval report %s: not an object", path)
        return None

    payload = {
        "total": _as_int(report.get("total")),
        "passed": _as_int(report.get("passed")),
        "citation_accuracy": _as_float(report.get("citation_accuracy")),
        "citation_recall": _as_float(report.get("citation_recall")),
        "writes_detected": report.get("writes_detected") is True,
        "input_tokens": _as_int(report.get("input_tokens")) or 0,
        "output_tokens": _as_int(report.get("output_tokens")) or 0,
        "recorded_at": _recorded_at(path),
    }
    if any(
        payload[key] is None
        for key in ("total", "passed", "citation_accuracy", "citation_recall")
    ):
        logger.warning("Skipping copilot eval report %s: missing core scores", path)
        return None
    try:
        return CopilotEvalSummary.model_validate(payload)
    except ValidationError as exc:
        logger.warning("Skipping invalid copilot eval report %s: %s", path, exc)
        return None


def build_quality_summary(
    *, diagram_eval_dir: str, copilot_eval_results: str
) -> QualitySummary:
    """Build the dashboard summary from the configured report locations."""
    return QualitySummary(
        generated_at=datetime.now(tz=UTC),
        diagram_evals=summarize_diagram_evals(Path(diagram_eval_dir)),
        copilot_eval=summarize_copilot_eval(Path(copilot_eval_results)),
    )
