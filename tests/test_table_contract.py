"""Tests for results-table contracts."""

import pytest
from pydantic import ValidationError

from bizora.contracts.table import ExtractedTable


def valid_table_data() -> dict[str, object]:
    """Return a valid extracted-table payload."""
    return {
        "table_id": "table-1",
        "project_id": "project-1",
        "graph_id": "graph-1",
        "source_id": "paper-1",
        "caption": "CASP14 results.",
        "columns": ["Method", "TM-score"],
        "rows": [["AlphaFold2", "0.92"], ["Baseline", "0.71"]],
        "created_by": "test-user",
    }


def test_valid_table_round_trip() -> None:
    table = ExtractedTable.model_validate(valid_table_data())

    assert table.table_id == "table-1"
    assert table.columns == ("Method", "TM-score")
    assert table.rows == (("AlphaFold2", "0.92"), ("Baseline", "0.71"))


def test_empty_rows_allowed() -> None:
    data = valid_table_data()
    data["rows"] = []

    table = ExtractedTable.model_validate(data)

    assert table.rows == ()


def test_ragged_row_rejected() -> None:
    data = valid_table_data()
    data["rows"] = [["AlphaFold2"]]

    with pytest.raises(ValidationError, match="Row 0"):
        ExtractedTable.model_validate(data)


def test_missing_columns_rejected() -> None:
    data = valid_table_data()
    data["columns"] = []

    with pytest.raises(ValidationError):
        ExtractedTable.model_validate(data)
