"""Tests for citation validation against observed tool output."""

from bizora.copilot.citations import (
    ComponentCitation,
    CopilotAnswer,
    EvidenceCitation,
    RunCitation,
    collect_observed_grounding,
    validate_citations,
)
from bizora.copilot.testing import EVAL_SOURCE_ID, make_eval_context
from bizora.copilot.tools import execute_tool


def _gathered_results() -> list[dict[str, object]]:
    context = make_eval_context()
    return [
        execute_tool(context, "read_evidence", {"target_id": "filter"}),
        execute_tool(context, "query_runs", {"run_id": "run-eval-1"}),
        execute_tool(context, "search_library", {"query": "NPN transistor", "limit": 2}),
    ]


def test_collect_observed_grounding() -> None:
    observed = collect_observed_grounding(_gathered_results())

    assert observed["evidence"][0]["source_id"] == EVAL_SOURCE_ID
    assert "run-eval-1" in observed["run_ids"]
    assert "accuracy" in observed["metric_names"]["run-eval-1"]
    assert "npn-2n3904" in observed["component_ids"]


def test_valid_citations_pass() -> None:
    context = make_eval_context()
    answer = CopilotAnswer(
        reply="Grounded reply.",
        citations=(
            EvidenceCitation(source_id=EVAL_SOURCE_ID, page=3, target_id="filter"),
            EvidenceCitation(
                source_id=EVAL_SOURCE_ID,
                quote="a second-order section with a 4 kHz corner",
            ),
            RunCitation(run_id="run-eval-1", metric_name="accuracy"),
            ComponentCitation(component_id="npn-2n3904"),
        ),
    )

    report = validate_citations(answer, _gathered_results(), context)

    assert report.all_valid
    assert len(report.valid) == 4


def test_fabricated_evidence_page_fails() -> None:
    context = make_eval_context()
    answer = CopilotAnswer(
        reply="Reply.",
        citations=(EvidenceCitation(source_id=EVAL_SOURCE_ID, page=99),),
    )

    report = validate_citations(answer, _gathered_results(), context)

    assert not report.all_valid
    assert len(report.valid) == 0
    assert "eval-paper-1" in report.invalid[0].reason


def test_fabricated_quote_fails() -> None:
    context = make_eval_context()
    answer = CopilotAnswer(
        reply="Reply.",
        citations=(
            EvidenceCitation(source_id=EVAL_SOURCE_ID, quote="words never printed anywhere"),
        ),
    )

    report = validate_citations(answer, _gathered_results(), context)

    assert not report.all_valid


def test_evidence_citation_needs_a_locator() -> None:
    context = make_eval_context()
    answer = CopilotAnswer(reply="Reply.", citations=(EvidenceCitation(source_id=EVAL_SOURCE_ID),))

    report = validate_citations(answer, _gathered_results(), context)

    assert not report.all_valid
    assert "page, quote" in report.invalid[0].reason


def test_unobserved_run_fails() -> None:
    context = make_eval_context()
    answer = CopilotAnswer(reply="Reply.", citations=(RunCitation(run_id="run-nope"),))

    report = validate_citations(answer, _gathered_results(), context)

    assert not report.all_valid


def test_unobserved_metric_fails() -> None:
    context = make_eval_context()
    answer = CopilotAnswer(
        reply="Reply.", citations=(RunCitation(run_id="run-eval-1", metric_name="f1"),)
    )

    report = validate_citations(answer, _gathered_results(), context)

    assert not report.all_valid


def test_unobserved_component_fails() -> None:
    context = make_eval_context()
    answer = CopilotAnswer(
        reply="Reply.", citations=(ComponentCitation(component_id="npn-2n3904"),)
    )

    report = validate_citations(answer, [], context)

    assert not report.all_valid
