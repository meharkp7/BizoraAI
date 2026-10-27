from bizora.contracts.diff import GraphRevisionDiff
from bizora.contracts.graph import GraphEdge, GraphNode, NodeKind


def test_empty_diff_reports_no_changes() -> None:
    diff = GraphRevisionDiff(
        project_id="p", graph_id="g", base_version=1, target_version=1
    )
    assert diff.is_empty()
    assert diff.summary() == {
        "added_nodes": 0,
        "removed_nodes": 0,
        "changed_nodes": 0,
        "added_edges": 0,
        "removed_edges": 0,
        "changed_edges": 0,
    }


def test_non_empty_diff_reports_counts() -> None:
    diff = GraphRevisionDiff(
        project_id="p",
        graph_id="g",
        base_version=1,
        target_version=2,
        added_nodes=(
            GraphNode(id="n", kind=NodeKind.INPUT, label="N"),
        ),
        added_edges=(GraphEdge(id="e", source="n", target="n2"),),
    )
    assert not diff.is_empty()
    assert diff.summary()["added_nodes"] == 1
    assert diff.summary()["added_edges"] == 1
    assert diff.summary()["removed_nodes"] == 0
