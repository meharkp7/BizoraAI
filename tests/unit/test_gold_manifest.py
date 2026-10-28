"""Tests for the gold-set manifest contract."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from bizora.contracts.gold import (
    GoldManifest,
    GoldPaper,
    load_manifest,
)

GOLD_DIR = Path(__file__).resolve().parents[1] / "gold"


def make_paper(**overrides: object) -> GoldPaper:
    base: dict[str, object] = {
        "paper_id": "demo-paper",
        "pdf_path": "tests/gold/papers/demo-paper.pdf",
        "domain_tags": ["embedded IoT"],
        "components": [
            {
                "name": "ESP32 DevKit",
                "aliases": ["ESP32"],
                "evidence": [{"kind": "figure", "locator": "Fig. 2"}],
            }
        ],
    }
    base.update(overrides)
    return GoldPaper.model_validate(base)


def test_empty_manifest_is_valid() -> None:
    manifest = GoldManifest.model_validate({"version": 1, "papers": []})

    assert manifest.version == 1
    assert manifest.papers == ()


def test_shipped_manifest_has_dev_and_heldout_split() -> None:
    manifest = load_manifest(GOLD_DIR / "manifest.json")

    dev = [p for p in manifest.papers if not p.held_out]
    held_out = [p for p in manifest.papers if p.held_out]
    assert len(dev) >= 15
    assert len(held_out) >= 5
    assert len({p.paper_id for p in manifest.papers}) == len(manifest.papers)
    assert len({p.pdf_path for p in manifest.papers}) == len(manifest.papers)


def test_paper_accepts_full_entry() -> None:
    paper = make_paper()

    assert paper.paper_id == "demo-paper"
    assert paper.components[0].aliases == ("ESP32",)


def test_pdf_path_must_be_relative_pdf() -> None:
    with pytest.raises(ValidationError):
        make_paper(pdf_path="/abs/path/paper.pdf")
    with pytest.raises(ValidationError):
        make_paper(pdf_path="tests/gold/papers/../secret.pdf")
    with pytest.raises(ValidationError):
        make_paper(pdf_path="tests/gold/papers/paper.txt")


def test_domain_tags_require_primary() -> None:
    with pytest.raises(ValidationError):
        make_paper(domain_tags=[])
    with pytest.raises(ValidationError):
        make_paper(domain_tags=["  "])


def test_duplicate_component_names_rejected() -> None:
    with pytest.raises(ValidationError):
        make_paper(
            components=[
                {"name": "Sensor"},
                {"name": "sensor"},
            ]
        )


def test_manifest_rejects_duplicate_ids_and_paths() -> None:
    paper = make_paper()
    with pytest.raises(ValidationError):
        GoldManifest.model_validate(
            {"version": 1, "papers": [paper.model_dump(), paper.model_dump()]}
        )
    other = make_paper(paper_id="other-paper")
    with pytest.raises(ValidationError):
        GoldManifest.model_validate(
            {"version": 1, "papers": [paper.model_dump(), other.model_dump()]}
        )


def test_load_manifest_rejects_bad_json(tmp_path: Path) -> None:
    bad = tmp_path / "manifest.json"
    bad.write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid JSON"):
        load_manifest(bad)


def test_load_manifest_rejects_schema_violation(tmp_path: Path) -> None:
    bad = tmp_path / "manifest.json"
    bad.write_text(json.dumps({"version": 1, "papers": [{"paper_id": "x"}]}), encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid gold manifest"):
        load_manifest(bad)


def test_load_manifest_missing_file() -> None:
    with pytest.raises(ValueError, match="Cannot read"):
        load_manifest(GOLD_DIR / "does-not-exist.json")
