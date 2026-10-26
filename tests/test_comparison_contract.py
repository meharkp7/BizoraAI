"""Tests for baseline comparison contracts."""

import pytest
from pydantic import ValidationError

from bizora.contracts.comparison import (
    ComparisonVerdict,
    MetricComparison,
    RunComparison,
)


def valid_graph_pair() -> dict[str, object]:
    """Return a graph pair payload."""
    return {
        "baseline_graph_id": "graph-1",
        "baseline_graph_version": 1,
        "variant_graph_id": "graph-1",
        "variant_graph_version": 2,
    }


def valid_metric_comparison() -> dict[str, object]:
    """Return a metric comparison payload."""
    return {
        "name": "accuracy",
        "baseline_value": 0.8,
        "variant_value": 0.9,
        "absolute_change": 0.1,
        "relative_change": 0.125,
    }


def test_metric_comparison_accepts_defined_change() -> None:
    comparison = MetricComparison.model_validate(valid_metric_comparison())

    assert comparison.relative_change == 0.125
    assert comparison.relative_undefined_reason is None


def test_metric_comparison_requires_reason_when_undefined() -> None:
    with pytest.raises(ValidationError, match="undefined reason"):
        MetricComparison.model_validate(
            {
                "name": "accuracy",
                "baseline_value": 0.0,
                "variant_value": 0.1,
                "absolute_change": 0.1,
                "relative_change": None,
            }
        )


def test_metric_comparison_rejects_reason_with_defined_change() -> None:
    payload = valid_metric_comparison()
    payload["relative_undefined_reason"] = "spurious"

    with pytest.raises(ValidationError, match="must not carry"):
        MetricComparison.model_validate(payload)


def test_valid_comparison_carries_metric_changes() -> None:
    comparison = RunComparison.model_validate(
        {
            "baseline_run_id": "run-baseline",
            "variant_run_id": "run-variant",
            "verdict": ComparisonVerdict.VALID.value,
            "reasons": [],
            "graph": valid_graph_pair(),
            "metrics": [valid_metric_comparison()],
        }
    )

    assert comparison.verdict == ComparisonVerdict.VALID
    assert comparison.metrics[0].name == "accuracy"


def test_valid_comparison_rejects_reasons() -> None:
    with pytest.raises(ValidationError, match="must not carry"):
        RunComparison.model_validate(
            {
                "baseline_run_id": "run-baseline",
                "variant_run_id": "run-variant",
                "verdict": ComparisonVerdict.VALID.value,
                "reasons": ["spurious caveat"],
                "graph": valid_graph_pair(),
            }
        )


def test_confounded_comparison_requires_reasons() -> None:
    with pytest.raises(ValidationError, match="requires reasons"):
        RunComparison.model_validate(
            {
                "baseline_run_id": "run-baseline",
                "variant_run_id": "run-variant",
                "verdict": ComparisonVerdict.CONFOUNDED.value,
                "reasons": [],
                "graph": valid_graph_pair(),
                "metrics": [valid_metric_comparison()],
            }
        )


def test_invalid_comparison_reports_no_metric_changes() -> None:
    with pytest.raises(ValidationError, match="must not report"):
        RunComparison.model_validate(
            {
                "baseline_run_id": "run-baseline",
                "variant_run_id": "run-variant",
                "verdict": ComparisonVerdict.INVALID.value,
                "reasons": ["Runs share no measured metrics."],
                "graph": valid_graph_pair(),
                "metrics": [valid_metric_comparison()],
            }
        )


def test_comparison_is_immutable() -> None:
    comparison = RunComparison.model_validate(
        {
            "baseline_run_id": "run-baseline",
            "variant_run_id": "run-variant",
            "verdict": ComparisonVerdict.VALID.value,
            "reasons": [],
            "graph": valid_graph_pair(),
        }
    )

    with pytest.raises(ValidationError):
        comparison.__setattr__("verdict", ComparisonVerdict.INVALID)


def test_comparison_rejects_unexpected_fields() -> None:
    payload = valid_metric_comparison()
    payload["unreviewed"] = True

    with pytest.raises(ValidationError):
        MetricComparison.model_validate(payload)
