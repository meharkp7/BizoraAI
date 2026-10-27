"""Tests for paper-agnostic upload helpers."""

from bizora.core.papers import (
    is_valid_source_id,
    slugify,
    split_authors,
    suggest_graph_id,
    suggest_project_id,
    suggest_source_id,
)


def test_slugify_reduces_free_text() -> None:
    assert slugify("Highly Accurate SRAM Study!") == "highly-accurate-sram-study"
    assert slugify("  a/b  c  ") == "a-b-c"
    assert slugify("!!!") == "paper"


def test_slugify_truncates_long_titles() -> None:
    assert len(slugify("x" * 200)) <= 40


def test_split_authors_only_splits_unambiguous_separators() -> None:
    assert split_authors(None) == ()
    assert split_authors("Jane Doe") == ("Jane Doe",)
    assert split_authors("Doe, J.; Smith, A.") == ("Doe, J.", "Smith, A.")
    assert split_authors("A Uthor / B Writer") == ("A Uthor", "B Writer")
    assert split_authors("  ") == ()


def test_suggestions_are_stable_and_unique() -> None:
    first = suggest_project_id("SRAM Study", "abc12345")
    assert first == suggest_project_id("SRAM Study", "abc12345")
    assert first == "sram-study-abc12345"
    assert suggest_graph_id("SRAM Study", "abc12345") == "sram-study-graph-abc12345"
    assert suggest_source_id("abc12345") == "paper-abc12345"
    assert suggest_project_id("Other", "abc12345") != first


def test_source_id_validation_matches_evidence_pattern() -> None:
    assert is_valid_source_id("paper-abc12345") is True
    assert is_valid_source_id("a.b_c:d-e") is True
    assert is_valid_source_id("has spaces") is False
    assert is_valid_source_id("has/slash") is False
    assert is_valid_source_id("") is False
    assert is_valid_source_id("x" * 129) is False
