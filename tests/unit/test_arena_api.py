"""Tests for the cross-graph arena comparison."""

from fastapi.testclient import TestClient
from tests.unit.test_entities_api import client, load_fixture_payload  # noqa: F401

__all__ = ["client"]

from bizora.contracts.graph import MethodologyGraph
from bizora.contracts.table import ExtractedTable
from bizora.core.arena import compare_graphs


def _graph(name: str) -> MethodologyGraph:
    return MethodologyGraph.model_validate(load_fixture_payload(name))


def _table(
    table_id: str,
    columns: tuple[str, ...],
    rows: tuple[tuple[str, ...], ...],
) -> ExtractedTable:
    return ExtractedTable(
        table_id=table_id,
        project_id="project-1",
        graph_id="graph-1",
        source_id="paper-1",
        caption="Results.",
        columns=columns,
        rows=rows,
        page=4,
        created_by="researcher-1",
    )


def test_compare_counts_structure_and_labels() -> None:
    """Structure counts and label overlap come from the revisions."""
    a_graph = _graph("sram")
    b_graph = _graph("quant")

    result = compare_graphs(a_graph, b_graph, [], [])

    assert result.a.project_id == a_graph.project_id
    assert result.structure_a.node_count == len(a_graph.nodes)
    assert result.structure_b.edge_count == len(b_graph.edges)
    assert sum(result.structure_a.kinds.values()) == len(a_graph.nodes)
    shared = {entry.label for entry in result.shared_labels}
    assert shared <= {node.label for node in a_graph.nodes}
    assert shared <= {node.label for node in b_graph.nodes}
    assert result.metrics == ()


def test_compare_matches_labels_case_insensitively() -> None:
    """'Inverter stage' and 'inverter STAGE' count as shared."""
    a_graph = _graph("sram")
    first = a_graph.nodes[0]
    renamed = first.model_copy(update={"label": first.label.upper(), "id": "other-id"})
    b_graph = _graph("sram").model_copy(
        update={
            "project_id": "other-project",
            "nodes": (renamed,),
            "edges": (),
        }
    )

    result = compare_graphs(a_graph, b_graph, [], [])

    assert [entry.label for entry in result.shared_labels] == [first.label]
    assert result.shared_labels[0].a_node_ids == (first.id,)
    assert result.shared_labels[0].b_node_ids == ("other-id",)
    assert all(entry.label != first.label for entry in result.unique_a)


def test_compare_aligns_reported_metrics_by_name() -> None:
    """Shared metric names land on one row; singles keep their side."""
    a_table = _table("t1", ("Method", "Accuracy (%)"), (("Ours", "92%"),))
    b_table = _table("t2", ("Method", "Accuracy"), (("Theirs", "0.88"),))
    c_table = _table("t3", ("Method", "Latency (ms)"), (("Theirs", "4"),))

    result = compare_graphs(_graph("sram"), _graph("quant"), [a_table], [b_table, c_table])

    by_name = {row.name: row for row in result.metrics}
    assert set(by_name) == {"Ours — Accuracy (%)", "Theirs — Latency (ms)"}
    shared = by_name["Ours — Accuracy (%)"]
    assert shared.a is not None and shared.b is not None
    assert shared.a.raw_value == "92%"
    assert shared.b.value == 0.88
    assert by_name["Theirs — Latency (ms)"].a is None
    assert by_name["Theirs — Latency (ms)"].b is not None
    assert result.metrics[0].name == "Ours — Accuracy (%)"


def test_compare_endpoint_resolves_latest_and_pinned_versions(client: TestClient) -> None:
    """The endpoint defaults to head revisions and honors pins."""
    assert (
        client.post("/api/v1/graphs", json=load_fixture_payload("sram")).status_code == 201
    )
    assert (
        client.post("/api/v1/graphs", json=load_fixture_payload("quant")).status_code == 201
    )

    latest = client.post(
        "/api/v1/graphs/compare",
        json={
            "a": {"project_id": "fixture-sram", "graph_id": "main"},
            "b": {"project_id": "fixture-quant", "graph_id": "main", "version": 1},
        },
    )

    assert latest.status_code == 200
    body = latest.json()
    assert body["a"]["version"] == 1
    assert body["b"]["version"] == 1
    assert body["structure_a"]["node_count"] > 0

    missing = client.post(
        "/api/v1/graphs/compare",
        json={
            "a": {"project_id": "nope", "graph_id": "nope"},
            "b": {"project_id": "fixture-quant", "graph_id": "main"},
        },
    )
    assert missing.status_code == 404
