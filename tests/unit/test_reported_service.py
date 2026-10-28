"""Tests for deriving paper-reported metrics from extracted tables."""

from bizora.contracts.streaming import PaperReportedMetric
from bizora.contracts.table import ExtractedTable
from bizora.core.reported_service import reported_metrics_for_tables


def _table(
    table_id: str,
    columns: tuple[str, ...],
    rows: tuple[tuple[str, ...], ...],
    *,
    page: int | None = 4,
) -> ExtractedTable:
    """Build one extracted results table."""
    return ExtractedTable(
        table_id=table_id,
        project_id="project-1",
        graph_id="graph-1",
        source_id="paper-1",
        caption="Results.",
        columns=columns,
        rows=rows,
        page=page,
        created_by="researcher-1",
    )


def _column_table() -> ExtractedTable:
    """Build a column-header table: methods as rows, metric as a column."""
    return _table(
        "table-1",
        ("Method", "Accuracy"),
        (("Ours", "0.92"), ("Baseline", "0.71")),
    )


def test_column_header_match_returns_one_entry_per_cell() -> None:
    entries = reported_metrics_for_tables([_column_table()], ["accuracy"])

    assert [(entry.raw_value, entry.value) for entry in entries] == [
        ("0.92", 0.92),
        ("0.71", 0.71),
    ]
    for entry in entries:
        assert entry.name == "accuracy"
        assert entry.source_id == "paper-1"
        assert entry.table_id == "table-1"
        assert entry.page == 4
        assert entry.quote
        assert entry.locator


def test_header_match_ignores_case_and_unit_parenthetical() -> None:
    table = _table("table-1", ("Method", "Accuracy (%)"), (("Ours", "92%"),))

    entries = reported_metrics_for_tables([table], ["accuracy"])

    assert len(entries) == 1
    assert entries[0].value == 92.0
    assert entries[0].unit == "%"


def test_row_label_match_returns_values_beside_the_label() -> None:
    table = _table("table-1", ("Metric", "Ours"), (("Accuracy", "0.92"),))

    entries = reported_metrics_for_tables([table], ["accuracy"])

    assert [(entry.raw_value, entry.value) for entry in entries] == [("0.92", 0.92)]


def test_leading_value_survives_plus_minus_ranges() -> None:
    table = _table("table-1", ("Method", "Loss"), (("Ours", "0.23 ± 0.01"),))

    entries = reported_metrics_for_tables([table], ["loss"])

    assert len(entries) == 1
    assert entries[0].raw_value == "0.23 ± 0.01"
    assert entries[0].value == 0.23


def test_non_numeric_cells_are_quoted_verbatim_without_a_value() -> None:
    table = _table("table-1", ("Method", "Loss"), (("Ours", "0.23"), ("Ablated", "N/A")))

    entries = reported_metrics_for_tables([table], ["loss"])

    assert [(entry.raw_value, entry.value) for entry in entries] == [
        ("0.23", 0.23),
        ("N/A", None),
    ]


def test_match_without_any_numeric_cell_yields_nothing() -> None:
    table = _table("table-1", ("Method", "Setting"), (("Ours", "Adam"),))

    assert reported_metrics_for_tables([table], ["setting"]) == ()


def test_unknown_names_and_blank_cells_yield_nothing() -> None:
    table = _table("table-1", ("Method", "Accuracy"), (("Ours", ""),))

    assert reported_metrics_for_tables([table], ["perplexity"]) == ()
    assert reported_metrics_for_tables([table], ["accuracy"]) == ()
    assert reported_metrics_for_tables([table], ["  "]) == ()
    assert reported_metrics_for_tables([], ["accuracy"]) == ()


def test_multiple_tables_accumulate_without_duplicates() -> None:
    entries = reported_metrics_for_tables(
        [_column_table(), _column_table()], ["accuracy"]
    )

    assert len(entries) == 2
    assert all(isinstance(entry, PaperReportedMetric) for entry in entries)
