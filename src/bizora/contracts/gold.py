"""Gold-set manifest contracts for extraction evaluation (Phase 0).

The gold set is a hand-checked list of papers with expected domains,
components, and evidence pointers. It measures extraction quality; it
never special-cases production code (Rule Zero).
"""

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

GOLD_MANIFEST_VERSION = 1

EvidenceKind = Literal["page", "figure", "equation", "table", "quote", "url"]

PaperStatus = Literal["ok", "missing", "error"]


class GoldEvidencePointer(BaseModel):
    """One hand-checked locator grounding an expected component or paper."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: EvidenceKind
    locator: str = Field(
        min_length=1,
        max_length=500,
        description="e.g. 'p.3', 'Fig. 2', 'Table 1', 'Eq. (4)', a short quote, or a URL.",
    )
    note: str | None = Field(default=None, max_length=500)


class GoldComponent(BaseModel):
    """One expected methodology component, with accepted name variants."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=300)
    aliases: tuple[str, ...] = Field(
        default=(),
        description="Accepted spelling/abbreviation variants of name.",
    )
    evidence: tuple[GoldEvidencePointer, ...] = Field(
        default=(),
        description="Paper locators where this component appears.",
    )

    @field_validator("aliases")
    @classmethod
    def _non_blank_aliases(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for alias in value:
            if not alias.strip():
                raise ValueError("aliases must be non-blank")
        return value


class GoldPaper(BaseModel):
    """Expected extraction outcome for one gold-set paper."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    paper_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._:-]{0,127}$")
    pdf_path: str = Field(
        min_length=5,
        max_length=500,
        description="Repo-relative path to the paper PDF (never committed).",
    )
    held_out: bool = Field(
        default=False,
        description="True for papers reserved for testing, never used while building.",
    )
    domain_tags: tuple[str, ...] = Field(
        min_length=1,
        description="Expected open-vocabulary domain labels, primary first.",
    )
    components: tuple[GoldComponent, ...] = ()
    evidence: tuple[GoldEvidencePointer, ...] = Field(
        default=(),
        description="Paper-level evidence pointers (figures, tables, ...).",
    )

    @field_validator("pdf_path")
    @classmethod
    def _relative_pdf_path(cls, value: str) -> str:
        if not value.lower().endswith(".pdf"):
            raise ValueError("pdf_path must point to a .pdf file")
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("pdf_path must be a relative path without '..'")
        return value

    @field_validator("domain_tags")
    @classmethod
    def _non_blank_tags(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for tag in value:
            cleaned = tag.strip()
            if not cleaned or len(cleaned) > 64:
                raise ValueError("domain_tags must be non-blank, at most 64 chars")
        return value

    @model_validator(mode="after")
    def _unique_component_names(self) -> "GoldPaper":
        seen: set[str] = set()
        for component in self.components:
            key = component.name.strip().lower()
            if key in seen:
                raise ValueError(f"duplicate component name: {component.name!r}")
            seen.add(key)
        return self


class GoldManifest(BaseModel):
    """The validated gold-set manifest (tests/gold/manifest.json)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = 1
    papers: tuple[GoldPaper, ...] = ()

    @model_validator(mode="after")
    def _unique_papers(self) -> "GoldManifest":
        paper_ids: set[str] = set()
        pdf_paths: set[str] = set()
        for paper in self.papers:
            if paper.paper_id in paper_ids:
                raise ValueError(f"duplicate paper_id: {paper.paper_id!r}")
            if paper.pdf_path in pdf_paths:
                raise ValueError(f"duplicate pdf_path: {paper.pdf_path!r}")
            paper_ids.add(paper.paper_id)
            pdf_paths.add(paper.pdf_path)
        return self


class GoldPaperResult(BaseModel):
    """Per-paper evaluation outcome."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    paper_id: str = Field(min_length=1, max_length=128)
    status: PaperStatus
    predicted_domain: str | None = None
    domain_match: bool | None = Field(
        default=None,
        description="True when predicted domain is among expected tags.",
    )
    expected_components: int = Field(ge=0)
    predicted_components: int = Field(ge=0)
    matched_expected: int = Field(ge=0)
    matched_predicted: int = Field(ge=0)
    detail: str = Field(default="", max_length=1000)


class GoldEvalReport(BaseModel):
    """Aggregate evaluation outcome over the whole manifest."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_name: str = Field(min_length=1, max_length=128)
    papers_total: int = Field(ge=0)
    evaluated: int = Field(ge=0)
    missing: int = Field(ge=0)
    errors: int = Field(ge=0)
    domain_accuracy: float = Field(ge=0.0, le=1.0)
    component_precision: float = Field(ge=0.0, le=1.0)
    component_recall: float = Field(ge=0.0, le=1.0)
    results: tuple[GoldPaperResult, ...] = ()


def load_manifest(path: Path) -> GoldManifest:
    """Load and validate a gold manifest file."""
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Cannot read gold manifest at {path}: {exc}") from exc
    try:
        raw: Any = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in gold manifest at {path}: {exc}") from exc
    try:
        return GoldManifest.model_validate(raw)
    except Exception as exc:
        raise ValueError(f"Invalid gold manifest at {path}: {exc}") from exc
