"""Tests for the R9 copilot tool set (read-only tools + proposal)."""

from dataclasses import replace

import pytest

from bizora.contracts.figures import FigureKind, FigureRegion, PaperFigure
from bizora.contracts.table import ExtractedTable
from bizora.copilot.citations import (
    CopilotAnswer,
    EvidenceCitation,
    validate_citations,
)
from bizora.copilot.prompts import FINAL_ANSWER_INSTRUCTION, SYSTEM_PROMPT
from bizora.copilot.testing import (
    EVAL_GRAPH_ID,
    EVAL_PROJECT_ID,
    EVAL_SOURCE_ID,
    make_eval_context,
    make_eval_graph,
)
from bizora.copilot.tools import TOOL_SPECS, CopilotContext, execute_tool


def test_tool_specs_cover_the_r9_set() -> None:
    names = {spec.name for spec in TOOL_SPECS}

    assert names == {
        "search_library",
        "read_evidence",
        "inspect_graph",
        "diff_revisions",
        "query_runs",
        "run_preflight",
        "run_removal_preflight",
        "propose_patch",
        "read_tables",
        "read_figures",
        "quote_reported",
    }
    for spec in TOOL_SPECS:
        assert spec.description
        assert spec.parameters.get("type") == "object"


def test_unknown_tool_returns_error() -> None:
    result = execute_tool(make_eval_context(), "delete_everything", {})

    assert "error" in result


def test_search_library_finds_catalog_entries() -> None:
    result = execute_tool(
        make_eval_context(), "search_library", {"query": "NPN transistor", "limit": 3}
    )

    assert "error" not in result
    assert result["matches"][0]["component_id"] == "npn-2n3904"


def test_search_library_rejects_empty_query() -> None:
    result = execute_tool(make_eval_context(), "search_library", {"query": "  "})

    assert "error" in result


def test_read_evidence_returns_node_grounding() -> None:
    result = execute_tool(make_eval_context(), "read_evidence", {"target_id": "filter"})

    assert result["target_type"] == "node"
    assert result["target"]["label"] == "Filter stage"
    assert result["target"]["evidence"][0]["source_id"] == EVAL_SOURCE_ID
    assert result["target"]["evidence"][0]["page"] == 3


def test_read_evidence_returns_edge_grounding() -> None:
    result = execute_tool(make_eval_context(), "read_evidence", {"target_id": "e1"})

    assert result["target_type"] == "edge"
    assert result["target"]["source"] == "sensor"


def test_read_evidence_reports_unknown_target() -> None:
    result = execute_tool(make_eval_context(), "read_evidence", {"target_id": "nope"})

    assert "error" in result


def test_inspect_graph_summarizes_revision() -> None:
    result = execute_tool(make_eval_context(), "inspect_graph", {"scope": "summary"})

    assert result["project_id"] == EVAL_PROJECT_ID
    assert result["graph_id"] == EVAL_GRAPH_ID
    assert result["version"] == 2
    assert result["node_count"] == 4
    assert {node["id"] for node in result["nodes"]} == {
        "sensor",
        "filter",
        "output",
        "monitor",
    }


def test_inspect_graph_rejects_bad_scope() -> None:
    result = execute_tool(make_eval_context(), "inspect_graph", {"scope": "everything"})

    assert "error" in result


def test_diff_revisions_reports_changes() -> None:
    result = execute_tool(
        make_eval_context(), "diff_revisions", {"base_version": 1, "target_version": 2}
    )

    assert result["added_nodes"] == ["monitor"]
    assert result["removed_nodes"] == []
    assert result["changed_nodes"] == ["filter"]
    assert result["added_edges"] == ["e3"]


def test_diff_revisions_reports_missing_revision() -> None:
    result = execute_tool(
        make_eval_context(), "diff_revisions", {"base_version": 1, "target_version": 9}
    )

    assert "error" in result


def test_diff_revisions_without_loader_reports_unavailable() -> None:
    context = CopilotContext(graph=make_eval_graph(version=1))

    result = execute_tool(context, "diff_revisions", {"base_version": 1, "target_version": 2})

    assert "error" in result


def test_query_runs_lists_status_and_metrics() -> None:
    result = execute_tool(make_eval_context(), "query_runs", {})

    assert [run["run_id"] for run in result["runs"]] == ["run-eval-1", "run-eval-2"]
    assert result["runs"][0]["state"] == "succeeded"
    assert result["runs"][1]["state"] == "failed"
    assert "diverged" in result["runs"][1]["error"]
    assert {"loss", "accuracy"} == {metric["name"] for metric in result["runs"][0]["metrics"]}


def test_query_runs_inspects_one_run() -> None:
    result = execute_tool(make_eval_context(), "query_runs", {"run_id": "run-eval-1"})

    assert len(result["runs"]) == 1
    assert result["runs"][0]["metrics"][0]["result_kind"] == "measured"


def test_query_runs_reports_unknown_run() -> None:
    result = execute_tool(make_eval_context(), "query_runs", {"run_id": "run-nope"})

    assert "error" in result


def test_query_runs_empty_without_run_source() -> None:
    context = CopilotContext(graph=make_eval_graph(version=1))

    result = execute_tool(context, "query_runs", {})

    assert result == {"runs": []}


def test_run_preflight_validates_without_writing() -> None:
    context = make_eval_context()
    before = context.graph.model_dump_json()

    result = execute_tool(
        context,
        "run_preflight",
        {"node_id": "sensor", "component_id": "npn-2n3904"},
    )

    assert result["compatible"] is False
    assert result["candidate_label"] == "2N3904 NPN transistor"
    assert result["missing_interfaces"][0]["kind"] == "analog"
    assert context.graph.model_dump_json() == before


def test_run_preflight_reports_unknown_component() -> None:
    result = execute_tool(
        make_eval_context(),
        "run_preflight",
        {"node_id": "sensor", "component_id": "part-nope"},
    )

    assert "error" in result


def test_run_removal_preflight_reports_blast_radius() -> None:
    context = make_eval_context()
    before = context.graph.model_dump_json()

    result = execute_tool(context, "run_removal_preflight", {"node_id": "filter"})

    assert result["target_node_id"] == "filter"
    assert result["neighbor_node_ids"] == ["sensor", "output", "monitor"]
    assert result["dropped_edge_ids"] == ["e1", "e2", "e3"]
    quotes = [ref["quote"] for ref in result["evidence"]]
    assert quotes == [
        "a second-order section with a 4 kHz corner",
        "front-end feeds the filter",
    ]
    assert context.graph.model_dump_json() == before


def test_run_removal_preflight_reports_unknown_node() -> None:
    result = execute_tool(make_eval_context(), "run_removal_preflight", {"node_id": "nope"})

    assert "error" in result


def test_propose_patch_returns_pending_proposal() -> None:
    context = make_eval_context()
    before = context.graph.model_dump_json()

    result = execute_tool(
        context,
        "propose_patch",
        {
            "node_id": "filter",
            "config": {"corner_hz": 8000},
            "rationale": "Widen the corner for the experiment.",
        },
    )

    assert result["status"] == "pending_approval"
    assert result["proposal"]["node_id"] == "filter"
    assert result["proposal"]["config"]["corner_hz"] == 8000
    assert context.graph.model_dump_json() == before


def test_propose_patch_replacement_keeps_node_identity() -> None:
    result = execute_tool(
        make_eval_context(),
        "propose_patch",
        {
            "node_id": "sensor",
            "component_id": "npn-2n3904",
            "rationale": "Try the catalog transistor here.",
        },
    )

    assert result["status"] == "pending_approval"
    assert result["proposal"]["component_id"] == "npn-2n3904"
    assert result["proposal"]["node_id"] == "sensor"


def test_propose_patch_requires_rationale() -> None:
    result = execute_tool(
        make_eval_context(), "propose_patch", {"node_id": "sensor", "rationale": " "}
    )

    assert "error" in result


@pytest.mark.parametrize("tool", sorted(name for name in ("search_library", "read_evidence")))
def test_tool_arguments_must_be_well_formed(tool: str) -> None:
    result = execute_tool(make_eval_context(), tool, {"limit": "many"})

    assert "error" in result


def _eval_table() -> ExtractedTable:
    return ExtractedTable(
        table_id="table-eval",
        project_id=EVAL_PROJECT_ID,
        graph_id=EVAL_GRAPH_ID,
        source_id=EVAL_SOURCE_ID,
        caption="Filter results.",
        columns=("Method", "Accuracy"),
        rows=(("Ours", "0.92"), ("Baseline", "0.71")),
        page=4,
        quote="Table 1 reports accuracy.",
        created_by="researcher-1",
    )


def _eval_figure() -> PaperFigure:
    return PaperFigure(
        figure_id="fig-eval",
        project_id=EVAL_PROJECT_ID,
        graph_id=EVAL_GRAPH_ID,
        source_id=EVAL_SOURCE_ID,
        created_by="researcher-1",
        page=2,
        label="Figure 1",
        caption="Filter stage overview.",
        kind=FigureKind.DIAGRAM,
        regions=(
            FigureRegion(
                region_id="fig-eval-r1",
                figure_id="fig-eval",
                bbox=(0.1, 0.1, 0.4, 0.4),
                node_id="filter",
                label="filter stage",
                confidence=0.9,
            ),
        ),
    )


def _grounded_context() -> CopilotContext:
    base = make_eval_context()
    return replace(
        base,
        list_tables=lambda: [_eval_table()],
        list_figures=lambda: [_eval_figure()],
    )


def test_read_tables_returns_tables_with_citable_evidence() -> None:
    result = execute_tool(_grounded_context(), "read_tables", {})

    assert result["tables"][0]["table_id"] == "table-eval"
    assert result["tables"][0]["rows"][0] == ["Ours", "0.92"]
    ref = result["target"]["evidence"][0]
    assert ref["source_id"] == EVAL_SOURCE_ID
    assert ref["page"] == 4
    assert "Filter results." in ref["quote"]

    missing = execute_tool(_grounded_context(), "read_tables", {"table_id": "nope"})
    assert "error" in missing

    empty = execute_tool(make_eval_context(), "read_tables", {})
    assert empty["tables"] == []
    assert "note" in empty


def test_read_figures_returns_regions_with_figure_citations() -> None:
    result = execute_tool(_grounded_context(), "read_figures", {})

    assert result["figures"][0]["label"] == "Figure 1"
    assert result["figures"][0]["regions"][0]["node_id"] == "filter"
    ref = result["target"]["evidence"][0]
    assert ref["figure_label"] == "Figure 1"
    assert ref["page"] == 2

    missing = execute_tool(_grounded_context(), "read_figures", {"figure_id": "nope"})
    assert "error" in missing


def test_quote_reported_quotes_table_numbers() -> None:
    result = execute_tool(
        _grounded_context(), "quote_reported", {"names": ["Accuracy"]}
    )

    assert [entry["raw_value"] for entry in result["entries"]] == ["0.92", "0.71"]
    assert result["target"]["evidence"][0]["source_id"] == EVAL_SOURCE_ID

    bad = execute_tool(_grounded_context(), "quote_reported", {"names": []})
    assert "error" in bad


def test_table_and_figure_citations_validate() -> None:
    context = _grounded_context()
    results = [
        execute_tool(context, "read_tables", {}),
        execute_tool(context, "read_figures", {}),
    ]
    answer = CopilotAnswer(
        reply="Accuracy is 0.92 (Figure 1).",
        citations=(
            EvidenceCitation(
                source_id=EVAL_SOURCE_ID, page=4, quote="Filter results."
            ),
            EvidenceCitation(source_id=EVAL_SOURCE_ID, figure_label="Figure 1"),
            EvidenceCitation(source_id=EVAL_SOURCE_ID, page=99, quote="invented"),
        ),
    )

    report = validate_citations(answer, results, context)

    assert len(report.valid) == 2
    assert len(report.invalid) == 1


def test_prompts_require_tools_and_honest_abstention() -> None:
    for tool in ("read_tables", "read_figures", "quote_reported", "run_removal_preflight"):
        assert tool in SYSTEM_PROMPT
    assert "the paper does not state this" in SYSTEM_PROMPT
    assert "the paper does not state this" in FINAL_ANSWER_INSTRUCTION
