"""Figure/text -> diagram-IR extraction service.

Each extracted figure is classified (circuit, flow/block diagram,
physical structure, or other) and the matching IR is transcribed through
the Responses API with image input and structured output. Every IR is
validated (see bizora.core.diagram_validation); on errors one repair
call is made and the better result is kept. Methodology and structure
IRs are derived from paper text when no suitable figure exists.

Results are cached by (paper hash, figure id, prompt version) under the
platform cache dir. Providers sit behind DiagramVisionProvider, which
MuseDiagramProvider implements on top of the existing Muse Responses
plumbing. No domain, paper, or part knowledge lives here.
"""

import base64
import json
import os
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Protocol, overload

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from bizora.contracts.diagram_ir import (
    CIRCUIT_IR_JSON_SCHEMA,
    METHODOLOGY_IR_JSON_SCHEMA,
    STRUCTURE_IR_JSON_SCHEMA,
    BlockKind,
    CircuitIR,
    ComponentType,
    MethodologyEdgeKind,
    MethodologyIR,
    MethodologyNode,
    MethodologyNodeKind,
    NetRole,
    PortDirection,
    Side,
    StructureIR,
)
from bizora.contracts.figures import FigureAttachment, ResponseUsage
from bizora.core.diagram_derivation import (
    ENGINE_MIN_BOXES,
    first_array_cell,
    graft_cell_interior,
    methodology_to_circuit,
    methodology_to_structure,
    structure_drawable_boxes,
)
from bizora.core.diagram_validation import (
    DiagramValidationResult,
    normalize_structure_layout,
    validate_diagram,
)
from bizora.core.diagram_whatif import (
    WHATIF_INSTRUCTIONS,
    WHATIF_RESULT_JSON_SCHEMA,
    WhatIfResult,
    whatif_prompt,
)
from bizora.providers.base import MethodologyProviderError
from bizora.providers.muse import MuseMethodologyProvider, MuseProviderError

# Bumped when prompt wording changes render-critical output: v2 pins the
# renderer orientation convention (MOSFET rot-0, inverter apex rule);
# v3 captures stated per-step settings into methodology params so the
# what-if editor has knobs to turn.
PROMPT_VERSION = 4

FigureIRKind = Literal["circuit", "flow", "structure"]
TextIRKind = Literal["methodology", "structure"]

EXPECTED_IR_CLASS: dict[str, type[CircuitIR | MethodologyIR | StructureIR]] = {
    "circuit": CircuitIR,
    "flow": MethodologyIR,
    "structure": StructureIR,
    "methodology": MethodologyIR,
}


class DiagramKind(StrEnum):
    CIRCUIT = "circuit"
    FLOW = "flow"
    STRUCTURE = "structure"
    OTHER = "other"


class DiagramProviderError(MethodologyProviderError):
    """Raised when a diagram provider cannot return a usable IR."""


@dataclass(frozen=True)
class DiagramClassification:
    """Kind assigned to one figure image."""

    kind: DiagramKind
    confidence: float
    usage: ResponseUsage | None = None


@dataclass(frozen=True)
class DiagramIRDraft:
    """One provider-proposed IR; None means honestly absent from the source."""

    ir: CircuitIR | MethodologyIR | StructureIR | None
    usage: ResponseUsage | None = None


@dataclass(frozen=True)
class FigureDiagramResult:
    """Classification plus extracted IR for one figure."""

    figure_id: str
    kind: DiagramKind
    classification_confidence: float
    ir: CircuitIR | MethodologyIR | StructureIR | None
    validation: DiagramValidationResult
    usage: tuple[ResponseUsage, ...] = ()
    repaired: bool = False
    from_cache: bool = False


@dataclass(frozen=True)
class TextDiagramResult:
    """Methodology/structure IRs derived from paper text."""

    methodology: MethodologyIR | None
    methodology_validation: DiagramValidationResult
    structure: StructureIR | None
    structure_validation: DiagramValidationResult
    usage: tuple[ResponseUsage, ...] = ()
    repaired: Mapping[str, bool] = field(default_factory=dict)
    from_cache: Mapping[str, bool] = field(default_factory=dict)


@dataclass(frozen=True)
class PaperDiagrams:
    """All diagram IRs for one paper: figures first, text as fallback."""

    methodology: MethodologyIR | None
    circuits: tuple[CircuitIR, ...]
    structure: StructureIR | None
    validation: Mapping[str, DiagramValidationResult]
    sources: Mapping[str, str]
    usage: tuple[ResponseUsage, ...] = ()


class DiagramVisionProvider(Protocol):
    """Vision calls the diagram pipeline needs (Muse implements these)."""

    provider_name: str

    async def classify_diagram(
        self, figure: FigureAttachment
    ) -> DiagramClassification:
        """Classify one figure image into a diagram kind."""
        ...

    async def extract_figure_ir(
        self, figure: FigureAttachment, kind: FigureIRKind
    ) -> DiagramIRDraft:
        """Transcribe the matching IR from one figure image."""
        ...

    async def repair_figure_ir(
        self,
        figure: FigureAttachment,
        kind: FigureIRKind,
        broken: dict[str, Any],
        errors: tuple[str, ...],
    ) -> DiagramIRDraft:
        """Fix one figure-derived IR given validator errors."""
        ...

    async def extract_text_ir(
        self, paper_text: str, kind: TextIRKind
    ) -> DiagramIRDraft:
        """Derive one IR from paper text."""
        ...

    async def repair_text_ir(
        self,
        paper_text: str,
        kind: TextIRKind,
        broken: dict[str, Any],
        errors: tuple[str, ...],
    ) -> DiagramIRDraft:
        """Fix one text-derived IR given validator errors."""
        ...

    async def evaluate_what_if(
        self,
        node: MethodologyNode,
        new_params: dict[str, str],
        paper_text: str,
    ) -> WhatIfResult:
        """Estimate the outcome of a step under modified settings."""
        ...


def diagram_cache_dir() -> Path:
    """Return the diagram cache directory, honoring test overrides."""
    override = os.environ.get("BIZORA_CACHE_DIR")
    if override:
        return Path(override) / "bizora" / "diagrams"
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "bizora" / "diagrams"


def _check_paper_hash(paper_hash: str) -> str:
    if not paper_hash or not paper_hash.strip():
        raise ValueError("paper_hash must be a non-empty string.")
    return paper_hash.strip().lower()


def _safe_segment(value: str) -> str:
    return "".join(
        char if char.isalnum() or char in "-_." else "_" for char in value
    )


def diagram_cache_key(paper_hash: str, figure_id: str) -> str:
    """Build a stable cache key for one figure's diagram result."""
    digest = _check_paper_hash(paper_hash)
    return f"{digest}-{_safe_segment(figure_id)}-v{PROMPT_VERSION}"


def text_cache_key(paper_hash: str, kind: TextIRKind) -> str:
    """Build a stable cache key for one text-derived IR."""
    digest = _check_paper_hash(paper_hash)
    return f"{digest}-text-{kind}-v{PROMPT_VERSION}"


def _figure_ir_kind(kind: DiagramKind) -> FigureIRKind | None:
    if kind is DiagramKind.CIRCUIT:
        return "circuit"
    if kind is DiagramKind.FLOW:
        return "flow"
    if kind is DiagramKind.STRUCTURE:
        return "structure"
    return None


def _parse_cached_figure_ir(
    kind: DiagramKind, payload: Any
) -> CircuitIR | MethodologyIR | StructureIR | None:
    if payload is None:
        return None
    if kind is DiagramKind.CIRCUIT:
        return CircuitIR.model_validate(payload)
    if kind is DiagramKind.FLOW:
        return MethodologyIR.model_validate(payload)
    if kind is DiagramKind.STRUCTURE:
        return StructureIR.model_validate(payload)
    return None


def load_cached_figure(key: str) -> FigureDiagramResult | None:
    """Return the cached figure result for a key, or None on any miss."""
    try:
        payload: Any = json.loads(
            (diagram_cache_dir() / f"{key}.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None
    try:
        if not isinstance(payload, dict) or payload.get("prompt_version") != PROMPT_VERSION:
            return None
        kind = DiagramKind(str(payload.get("kind")))
        ir = _parse_cached_figure_ir(kind, payload.get("ir"))
        figure_id = str(payload.get("figure_id", ""))
        if not figure_id:
            return None
        validation = validate_diagram(ir) if ir is not None else DiagramValidationResult()
        return FigureDiagramResult(
            figure_id=figure_id,
            kind=kind,
            classification_confidence=float(payload.get("classification_confidence", 0.0)),
            ir=ir,
            validation=validation,
            usage=(),
            repaired=bool(payload.get("repaired", False)),
            from_cache=True,
        )
    except (ValueError, TypeError):
        return None


def save_cached_figure(key: str, result: FigureDiagramResult) -> None:
    """Persist one figure result; a failed write never fails extraction."""
    try:
        directory = diagram_cache_dir()
        directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "prompt_version": PROMPT_VERSION,
            "figure_id": result.figure_id,
            "kind": result.kind.value,
            "classification_confidence": result.classification_confidence,
            "ir": (
                result.ir.model_dump(by_alias=True, mode="json")
                if result.ir is not None
                else None
            ),
            "repaired": result.repaired,
        }
        (directory / f"{key}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
    except (OSError, ValueError):
        pass


def load_cached_text(
    key: str, kind: TextIRKind
) -> tuple[
    CircuitIR | MethodologyIR | StructureIR | None, bool, DiagramValidationResult
] | None:
    """Return (ir, repaired, validation) for a text cache key, or None."""
    try:
        payload: Any = json.loads(
            (diagram_cache_dir() / f"{key}.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None
    try:
        if not isinstance(payload, dict) or payload.get("prompt_version") != PROMPT_VERSION:
            return None
        raw = payload.get("ir")
        if raw is None:
            ir: CircuitIR | MethodologyIR | StructureIR | None = None
        elif kind == "methodology":
            ir = MethodologyIR.model_validate(raw)
        else:
            ir = StructureIR.model_validate(raw)
        repaired = bool(payload.get("repaired", False))
        validation = validate_diagram(ir) if ir is not None else DiagramValidationResult()
        return (ir, repaired, validation)
    except (ValueError, TypeError):
        return None


def save_cached_text(
    key: str,
    ir: CircuitIR | MethodologyIR | StructureIR | None,
    *,
    repaired: bool,
) -> None:
    """Persist one text-derived IR; a failed write never fails extraction."""
    try:
        directory = diagram_cache_dir()
        directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "prompt_version": PROMPT_VERSION,
            "ir": ir.model_dump(by_alias=True, mode="json") if ir is not None else None,
            "repaired": repaired,
        }
        (directory / f"{key}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
    except (OSError, ValueError):
        pass


def _score_validation(validation: DiagramValidationResult) -> tuple[int, int]:
    return (len(validation.errors), len(validation.warnings))


async def _validate_with_repair(
    ir: CircuitIR | MethodologyIR | StructureIR,
    expected: type[CircuitIR | MethodologyIR | StructureIR],
    repair_call: Callable[..., Awaitable[DiagramIRDraft]],
) -> tuple[
    CircuitIR | MethodologyIR | StructureIR, DiagramValidationResult, bool, ResponseUsage | None
]:
    """Validate an IR; on errors run one repair and keep the better result."""
    validation = validate_diagram(ir)
    if not validation.errors:
        return (ir, validation, False, None)
    try:
        repaired_draft: DiagramIRDraft = await repair_call(
            broken=ir.model_dump(by_alias=True, mode="json"),
            errors=validation.errors,
        )
    except DiagramProviderError as exc:
        kept = DiagramValidationResult(
            errors=validation.errors,
            warnings=validation.warnings + (f"repair call failed: {exc}",),
            stats=validation.stats,
        )
        return (ir, kept, False, None)
    repaired = repaired_draft.ir
    if repaired is None or not isinstance(repaired, expected):
        return (ir, validation, False, repaired_draft.usage)
    repaired_validation = validate_diagram(repaired)
    if _score_validation(repaired_validation) < _score_validation(validation):
        return (repaired, repaired_validation, True, repaired_draft.usage)
    return (ir, validation, False, repaired_draft.usage)


async def extract_figure_diagram(
    provider: DiagramVisionProvider,
    figure: FigureAttachment,
    *,
    paper_hash: str,
) -> FigureDiagramResult:
    """Classify one figure and extract its IR, using the cache when possible."""
    key = diagram_cache_key(paper_hash, figure.figure_id)
    cached = load_cached_figure(key)
    if cached is not None:
        return cached

    classification = await provider.classify_diagram(figure)
    if not 0.0 <= classification.confidence <= 1.0:
        raise DiagramProviderError("classification confidence must be within 0-1.")
    usage: list[ResponseUsage] = []
    if classification.usage is not None:
        usage.append(classification.usage)

    figure_kind = _figure_ir_kind(classification.kind)
    if figure_kind is None:
        result = FigureDiagramResult(
            figure_id=figure.figure_id,
            kind=classification.kind,
            classification_confidence=classification.confidence,
            ir=None,
            validation=DiagramValidationResult(),
            usage=tuple(usage),
        )
        save_cached_figure(key, result)
        return result

    expected = EXPECTED_IR_CLASS[figure_kind]
    draft = await provider.extract_figure_ir(figure, figure_kind)
    if draft.usage is not None:
        usage.append(draft.usage)
    if draft.ir is None:
        result = FigureDiagramResult(
            figure_id=figure.figure_id,
            kind=classification.kind,
            classification_confidence=classification.confidence,
            ir=None,
            validation=DiagramValidationResult(),
            usage=tuple(usage),
        )
        save_cached_figure(key, result)
        return result
    if not isinstance(draft.ir, expected):
        raise DiagramProviderError(
            f"provider returned {type(draft.ir).__name__} for '{figure_kind}'."
        )

    async def repair_call(
        *, broken: dict[str, Any], errors: tuple[str, ...]
    ) -> DiagramIRDraft:
        return await provider.repair_figure_ir(figure, figure_kind, broken, errors)

    ir, validation, repaired, repair_usage = await _validate_with_repair(
        draft.ir, expected, repair_call
    )
    if repair_usage is not None:
        usage.append(repair_usage)
    result = FigureDiagramResult(
        figure_id=figure.figure_id,
        kind=classification.kind,
        classification_confidence=classification.confidence,
        ir=ir,
        validation=validation,
        usage=tuple(usage),
        repaired=repaired,
    )
    save_cached_figure(key, result)
    return result


@overload
async def _extract_one_text_ir(
    provider: DiagramVisionProvider,
    paper_text: str,
    kind: Literal["methodology"],
    paper_hash: str,
    usage: list[ResponseUsage],
    repaired_flags: dict[str, bool],
    cache_flags: dict[str, bool],
) -> tuple[MethodologyIR | None, DiagramValidationResult]: ...


@overload
async def _extract_one_text_ir(
    provider: DiagramVisionProvider,
    paper_text: str,
    kind: Literal["structure"],
    paper_hash: str,
    usage: list[ResponseUsage],
    repaired_flags: dict[str, bool],
    cache_flags: dict[str, bool],
) -> tuple[StructureIR | None, DiagramValidationResult]: ...


async def _extract_one_text_ir(
    provider: DiagramVisionProvider,
    paper_text: str,
    kind: TextIRKind,
    paper_hash: str,
    usage: list[ResponseUsage],
    repaired_flags: dict[str, bool],
    cache_flags: dict[str, bool],
) -> tuple[MethodologyIR | StructureIR | None, DiagramValidationResult]:
    key = text_cache_key(paper_hash, kind)
    cached = load_cached_text(key, kind)
    if cached is not None:
        cached_ir, cached_repaired, cached_validation = cached
        repaired_flags[kind] = cached_repaired
        cache_flags[kind] = True
        if kind == "methodology":
            assert cached_ir is None or isinstance(cached_ir, MethodologyIR)
            return (cached_ir, cached_validation)
        assert cached_ir is None or isinstance(cached_ir, StructureIR)
        return (cached_ir, cached_validation)

    cache_flags[kind] = False
    try:
        draft = await provider.extract_text_ir(paper_text, kind)
    except DiagramProviderError as exc:
        # One kind's failure must not sink the other: the surviving
        # IR still serves, and derivation can cover the missing view.
        # Failures stay uncached so retries heal.
        repaired_flags[kind] = False
        return (
            None,
            DiagramValidationResult(errors=(f"{kind} extraction failed: {exc}",)),
        )
    if draft.usage is not None:
        usage.append(draft.usage)
    expected = EXPECTED_IR_CLASS[kind]
    if draft.ir is None:
        save_cached_text(key, None, repaired=False)
        repaired_flags[kind] = False
        return (None, DiagramValidationResult())
    if not isinstance(draft.ir, expected):
        raise DiagramProviderError(
            f"provider returned {type(draft.ir).__name__} for '{kind}'."
        )

    async def repair_call(
        *, broken: dict[str, Any], errors: tuple[str, ...]
    ) -> DiagramIRDraft:
        return await provider.repair_text_ir(paper_text, kind, broken, errors)

    ir, validation, repaired, repair_usage = await _validate_with_repair(
        draft.ir, expected, repair_call
    )
    if repair_usage is not None:
        usage.append(repair_usage)
    save_cached_text(key, ir, repaired=repaired)
    repaired_flags[kind] = repaired
    if kind == "methodology":
        assert isinstance(ir, MethodologyIR)
    else:
        assert isinstance(ir, StructureIR)
    return (ir, validation)


async def extract_text_diagrams(
    provider: DiagramVisionProvider,
    paper_text: str,
    *,
    paper_hash: str,
    want_methodology: bool = True,
    want_structure: bool = True,
) -> TextDiagramResult:
    """Derive methodology/structure IRs from paper text (empty text: nothing)."""
    empty = DiagramValidationResult()
    if not paper_text.strip():
        return TextDiagramResult(
            methodology=None,
            methodology_validation=empty,
            structure=None,
            structure_validation=empty,
            usage=(),
            repaired={},
            from_cache={},
        )
    _check_paper_hash(paper_hash)
    usage: list[ResponseUsage] = []
    repaired_flags: dict[str, bool] = {}
    cache_flags: dict[str, bool] = {}
    methodology: MethodologyIR | None = None
    methodology_validation = empty
    structure: StructureIR | None = None
    structure_validation = empty
    if want_methodology:
        methodology, methodology_validation = await _extract_one_text_ir(
            provider, paper_text, "methodology", paper_hash,
            usage, repaired_flags, cache_flags,
        )
    if want_structure:
        structure, structure_validation = await _extract_one_text_ir(
            provider, paper_text, "structure", paper_hash,
            usage, repaired_flags, cache_flags,
        )
    return TextDiagramResult(
        methodology=methodology,
        methodology_validation=methodology_validation,
        structure=structure,
        structure_validation=structure_validation,
        usage=tuple(usage),
        repaired=repaired_flags,
        from_cache=cache_flags,
    )


async def extract_paper_diagrams(
    provider: DiagramVisionProvider,
    figures: Sequence[FigureAttachment],
    paper_text: str,
    *,
    paper_hash: str,
    source_id: str = "paper",
) -> PaperDiagrams:
    """Extract every diagram IR: figures first, paper text as fallback.

    Circuits come from circuit figures, else derived as system blocks
    from the methodology. Methodology comes from the first flow figure,
    else from text; structure comes from the first structure figure,
    else from text, else derived from the methodology. Every paper
    with a methodology therefore yields all three views.
    """
    figure_results: list[FigureDiagramResult] = []
    for figure in figures:
        try:
            figure_results.append(
                await extract_figure_diagram(provider, figure, paper_hash=paper_hash)
            )
        except DiagramProviderError as exc:
            # One unreadable figure must not sink the paper's other
            # figures: record the failure (uncached, so retries heal)
            # and carry on.
            figure_results.append(
                FigureDiagramResult(
                    figure_id=figure.figure_id,
                    kind=DiagramKind.OTHER,
                    classification_confidence=0.0,
                    ir=None,
                    validation=DiagramValidationResult(
                        errors=(f"figure extraction failed: {exc}",)
                    ),
                )
            )
    usage: list[ResponseUsage] = []
    for result in figure_results:
        usage.extend(result.usage)

    validation: dict[str, DiagramValidationResult] = {}
    sources: dict[str, str] = {}

    circuits: list[CircuitIR] = []
    for result in figure_results:
        if result.kind is DiagramKind.CIRCUIT and isinstance(result.ir, CircuitIR):
            if not result.ir.components:
                # A circuit with no components draws nothing: the
                # classifier fired on text, not a schematic. Report is
                # kept under a suffixed key; the figure is not served.
                validation[f"circuit:figure:{result.figure_id}"] = result.validation
                sources[f"circuit:figure:{result.figure_id}"] = (
                    f"figure:{result.figure_id}"
                )
                continue
            circuits.append(result.ir)
            validation[f"circuit:{result.figure_id}"] = result.validation
            sources[f"circuit:{result.figure_id}"] = f"figure:{result.figure_id}"

    # Figure methodology/structure IRs that still carry validation
    # errors are set aside (report kept under a suffixed key) so the
    # text fallback below can serve a renderable IR instead. Circuits
    # have no fallback: non-empty ones are always served with their
    # report, empty ones are set aside the same way.
    methodology: MethodologyIR | None = None
    for result in figure_results:
        if result.kind is DiagramKind.FLOW and isinstance(result.ir, MethodologyIR):
            if result.validation.errors:
                validation[f"methodology:figure:{result.figure_id}"] = result.validation
                sources[f"methodology:figure:{result.figure_id}"] = (
                    f"figure:{result.figure_id}"
                )
                continue
            methodology = result.ir
            validation["methodology"] = result.validation
            sources["methodology"] = f"figure:{result.figure_id}"
            break

    structure: StructureIR | None = None
    for result in figure_results:
        if result.kind is DiagramKind.STRUCTURE and isinstance(result.ir, StructureIR):
            if result.validation.errors:
                validation[f"structure:figure:{result.figure_id}"] = result.validation
                sources[f"structure:figure:{result.figure_id}"] = (
                    f"figure:{result.figure_id}"
                )
                continue
            structure = result.ir
            validation["structure"] = result.validation
            sources["structure"] = f"figure:{result.figure_id}"
            break

    figure_cell = first_array_cell(structure) if structure is not None else None
    needs_interior = (
        figure_cell is not None
        and not figure_cell.children
        and sources.get("structure", "").startswith("figure:")
    )
    text_structure: StructureIR | None = None
    if (methodology is None or structure is None or needs_interior) and paper_text.strip():
        text_result = await extract_text_diagrams(
            provider,
            paper_text,
            paper_hash=paper_hash,
            want_methodology=methodology is None,
            want_structure=structure is None or needs_interior,
        )
        usage.extend(text_result.usage)
        if methodology is None and text_result.methodology is not None:
            methodology = text_result.methodology
            validation["methodology"] = text_result.methodology_validation
            sources["methodology"] = "text"
        elif methodology is None and text_result.methodology_validation.errors:
            validation["methodology"] = text_result.methodology_validation
        if structure is None and text_result.structure is not None:
            structure = text_result.structure
            validation["structure"] = text_result.structure_validation
            sources["structure"] = "text"
        elif structure is None and text_result.structure_validation.errors:
            validation["structure"] = text_result.structure_validation
        text_structure = text_result.structure

    if needs_interior and text_structure is not None and structure is not None:
        grafted = graft_cell_interior(structure, text_structure)
        if grafted is not None:
            graft_report = validate_diagram(grafted)
            if not graft_report.errors:
                structure = grafted
                prior = validation.get("structure", DiagramValidationResult())
                validation["structure"] = DiagramValidationResult(
                    errors=prior.errors,
                    warnings=prior.warnings
                    + graft_report.warnings
                    + (
                        "Repeated-cell interior transcribed from the paper text "
                        "(the figure shows the array but not the cell contents).",
                    ),
                    stats=dict(graft_report.stats),
                )
                sources["structure:cell-interior"] = "text"

    if not circuits and methodology is not None:
        derived_circuit = methodology_to_circuit(methodology, source_id=source_id)
        if derived_circuit is not None:
            circuits.append(derived_circuit)
            report = validate_diagram(derived_circuit)
            validation["circuit:derived"] = DiagramValidationResult(
                errors=report.errors,
                warnings=report.warnings
                + (
                    "Block schematic derived from the methodology flow "
                    "(no circuit figure in the paper).",
                ),
                stats=report.stats,
            )
            sources["circuit:derived"] = "derived:methodology"

    if (
        structure is not None
        and methodology is not None
        and structure_drawable_boxes(structure) < ENGINE_MIN_BOXES
    ):
        # A lone cell or an empty frame draws nothing: the engine would
        # refuse it, so the methodology derivation below takes over and
        # the warning says so honestly.
        report = validation.get("structure", DiagramValidationResult())
        validation["structure"] = DiagramValidationResult(
            errors=report.errors,
            warnings=report.warnings
            + (
                "Transcribed structure below the engine minimum "
                "(fewer than two boxes); derived from the methodology flow instead.",
            ),
            stats=report.stats,
        )
        structure = None

    if structure is None and methodology is not None:
        derived_structure = methodology_to_structure(methodology)
        if derived_structure is not None:
            structure = derived_structure
            report = validate_diagram(derived_structure)
            prior = validation.get("structure", DiagramValidationResult())
            validation["structure"] = DiagramValidationResult(
                errors=report.errors,
                warnings=prior.warnings
                + report.warnings
                + (
                    "Structure derived from the methodology flow "
                    "(no physical structure in the paper).",
                ),
                stats=report.stats,
            )
            sources["structure"] = "derived:methodology"

    if structure is not None:
        structure, layout_notes = normalize_structure_layout(structure)
        if layout_notes:
            report = validation.get("structure", DiagramValidationResult())
            validation["structure"] = DiagramValidationResult(
                errors=report.errors,
                warnings=report.warnings + layout_notes,
                stats=report.stats,
            )

    return PaperDiagrams(
        methodology=methodology,
        circuits=tuple(circuits),
        structure=structure,
        validation=validation,
        sources=sources,
        usage=tuple(usage),
    )


def count_tokens(usages: Sequence[ResponseUsage]) -> tuple[int, int]:
    """Sum (input, output) tokens over usage records, ignoring unknowns."""
    total_in = sum(u.input_tokens for u in usages if u.input_tokens is not None)
    total_out = sum(u.output_tokens for u in usages if u.output_tokens is not None)
    return (total_in, total_out)


_CLASSIFY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["circuit", "flow", "structure", "other"]},
        "confidence": {"type": "number"},
    },
    "required": ["kind", "confidence"],
    "additionalProperties": False,
}


class _ClassificationPayload(BaseModel):
    """Strict gate for the classifier's JSON output."""

    model_config = ConfigDict(extra="forbid")

    kind: DiagramKind
    confidence: float = Field(ge=0, le=1)


_CLASSIFY_INSTRUCTIONS = (
    "You classify one research-paper figure image into exactly one kind. "
    "Decide from the image pixels first. "
    "circuit: an electrical schematic with wires, transistors, gates, "
    "resistors, capacitors, or other circuit symbols. "
    "flow: a block diagram, flowchart, or methodology diagram made of "
    "labeled boxes, arrows, or swimlanes. "
    "structure: a physical structure or layout: die or microscope photo, "
    "chip floorplan, cross-section, 3D stack, array organization, or "
    "board photograph. "
    "other: anything else (plots, charts, histograms, tables, equations, "
    "measurement setups, text). "
    "Return only the JSON object: no markdown, no commentary, no extra keys."
)

_CIRCUIT_INSTRUCTIONS = (
    "You transcribe an electrical schematic figure into a CircuitIR JSON "
    "object with keys version, title, source, components, nets, ports, "
    "subcircuits, layout. Transcribe ONLY what is drawn: never complete, "
    "fix, or rewire the figure, and never invent components, nets, or "
    "values. Every visible symbol becomes one component with id, type "
    "(nmos, pmos, resistor, capacitor, inductor, diode, vsource, isource, "
    "ground, inverter, buffer, amp, comparator, or block for anything "
    "else), label copied from the printed text, optional value, pins "
    "mapping each pin name to its net id, placement, confidence between "
    "0 and 1, and evidence. Use pin names d,g,s (optional b) for "
    "transistors; a,b for resistor/capacitor/inductor; a,k for diode; "
    "p,n for sources; g for ground; in,out for inverter/buffer; "
    "inp,inn,out for amp/comparator. Every pin's net id must have a "
    "matching net entry with a role (supply, ground, signal, clock, "
    "input, output) and a boolean global flag (the JSON key is "
    "exactly 'global'). External terminals become ports with dir "
    "(in, out, inout) and side (left, right, up, down). Coordinates are "
    "normalized 0-100 over the figure (x right, y down): set placement "
    "from where each element actually appears. Orientation convention, "
    "matching the renderer exactly: at rot 0 with no mirror or flip, a "
    "MOSFET's gate exits left, drain up, source down; an inverter or "
    "buffer points right (in left, out right); two-terminal parts "
    "stand vertical with the first pin up. For an inverter or buffer, "
    "locate the triangle's apex: the apex, usually carrying the output "
    "bubble, points toward the out-net wire, and the flat side faces "
    "the in-net wire. Trace both wires explicitly: the wire touching "
    "the flat side is in, the wire touching the bubble is out; never "
    "assign in/out from left/right position alone. Record the observed "
    "bubble side (for example 'bubble on the left of the triangle') in "
    "the evidence quote. Set rot (0, 90, 180, 270), mirror, and flip so "
    "every pin exits toward its drawn wire: a PMOS whose source wire "
    "leaves upward needs flip true at rot 0, and a left-pointing "
    "inverter needs rot 180. When a symbol's drawn "
    "orientation is ambiguous, choose the orientation whose pins best "
    "meet the drawn wires and lower the confidence. Give low "
    "confidence for uncertain readings and quote printed labels in "
    "evidence. Set version to 1. Output ONLY the JSON object: no "
    "markdown, no commentary, no extra keys."
)

_FLOW_INSTRUCTIONS = (
    "You transcribe a block/flow diagram figure into a MethodologyIR JSON "
    "object with keys version, title, groups, nodes, edges. Transcribe "
    "ONLY what is drawn: every box becomes one node with id, label "
    "copied from the printed text, kind (input, process, decision, "
    "store, model, evaluation, dataset, output), optional group, detail, "
    "params, and confidence between 0 and 1; copy printed settings into "
    "params as string key/value pairs with snake_case keys, leaving it "
    "empty when the box prints none; every arrow becomes one "
    "edge with from/to node ids, optional label, and kind (data, "
    "control, feedback; the JSON key for the source node is exactly "
    "'from'). Grouped or swimlane regions become groups with id, label, "
    "and optional parent. Never complete, fix, or extend the diagram, "
    "and never invent steps, labels, or connections. Give low "
    "confidence for uncertain readings. Set version to 1. Output ONLY "
    "the JSON object: no markdown, no commentary, no extra keys."
)

_STRUCTURE_FIGURE_INSTRUCTIONS = (
    "You transcribe a physical-structure figure (die photo, floorplan, "
    "cross-section, stack, array drawing) into a StructureIR JSON object "
    "with keys version, title, root. Transcribe ONLY what is shown: the "
    "root block and nested children blocks each carry id, label copied "
    "from printed text, kind (chip, array, cell, periphery, module, "
    "board, layer, part, region), optional count (an integer or "
    "{rows, cols} copied from printed dimensions such as '16x16'), "
    "optional dims {w, h, d, unit}, optional pos, part, tensor_shape, "
    "children, and confidence between 0 and 1. An array's first child "
    "is the repeated cell. When the figure shows what is inside the "
    "repeated cell (a cell layout, zoomed cell, or cross-section), "
    "transcribe each visible device as a child of the cell with kind "
    "part and part naming the device (nmos, pmos, resistor, capacitor, "
    "inductor, diode, inverter, buffer, amp, comparator, or block when "
    "the device kind is genuinely unclear). Never complete, fix, or "
    "extend the figure, and never invent blocks, counts, dimensions, "
    "or cell contents the figure does not show. Give low confidence "
    "for uncertain readings. Set version to 1. Output ONLY "
    "the JSON object: no markdown, no commentary, no extra keys."
)

_METHODOLOGY_TEXT_INSTRUCTIONS = (
    "You derive a methodology flow from research-paper text into a "
    "MethodologyIR JSON object with keys version, title, groups, nodes, "
    "edges. Include only steps the text states: each step becomes one "
    "node with id, label, kind (input, process, decision, store, model, "
    "evaluation, dataset, output), optional group, detail, params, "
    "confidence between 0 and 1, and evidence with the page number "
    "from [Page N] markers and a short supporting quote. For each "
    "step, copy every numeric setting and named configuration the text "
    "states for that step into params as string key/value pairs, keys "
    "in snake_case (for example cell_count '2000', technology 'TSMC "
    "65nm', supply_vdd '0.9V', tilt_step_mv '10'); leave params empty "
    "only when the text states no settings for the step. Connect steps "
    "with edges carrying from/to node ids, optional label, and kind "
    "(data, control, feedback; the JSON key for the source node is "
    "exactly 'from'). Never invent steps, parameters, or connections; "
    "use empty arrays when the text states nothing usable. Set version "
    "to 1. Output ONLY the JSON object: no markdown, no commentary, "
    "no extra keys."
)

_STRUCTURE_TEXT_INSTRUCTIONS = (
    "You derive a physical structure from research-paper text into a "
    "StructureIR JSON object with keys version, title, root. Include "
    "only structure the text states: chips, arrays, cells, periphery, "
    "modules, boards, layers, parts, regions. Copy stated dimensions "
    "into count (an integer or {rows, cols}, e.g. '16x16 array' becomes "
    "rows 16, cols 16) and dims {w, h, d, unit}. Each block carries id, "
    "label, kind, optional count, dims, pos, part, tensor_shape, "
    "children, confidence between 0 and 1, and evidence with the page "
    "number from [Page N] markers and a short supporting quote. An "
    "array's first child is the repeated cell. When the text states "
    "what is inside the repeated cell (named devices or a device "
    "count), transcribe each stated device as a child of the cell "
    "with kind part and part naming the device (nmos, pmos, resistor, "
    "capacitor, inductor, diode, inverter, buffer, amp, comparator, "
    "or block when the device kind is genuinely unclear). Never "
    "invent blocks, counts, dimensions, or cell contents. Set version "
    "to 1. Output ONLY the JSON object: no markdown, no commentary, "
    "no extra keys."
)

_REPAIR_INSTRUCTIONS = (
    "You repair one transcribed diagram IR. The input carries the broken "
    "IR JSON plus validator error messages. Fix every listed error with "
    "the smallest change that keeps the transcription faithful to the "
    "source figure or text: correct wrong ids, references, pin names, "
    "and counts, but do not add, remove, or redesign elements that the "
    "errors do not require. Keep confidence values honest. Return the "
    "complete corrected IR as the JSON object, same shape as the input. "
    "Output ONLY the JSON object: no markdown, no commentary, no extra "
    "keys."
)


def _figure_hint_text(figure: FigureAttachment) -> str:
    lines = [
        f"Figure ID: {figure.figure_id}",
        f"Page: {figure.page if figure.page is not None else 'unknown'}",
    ]
    if figure.label_hint:
        lines.append(f"Label hints: {figure.label_hint}")
    if figure.caption_hint:
        lines.append(f"Caption candidates:\n{figure.caption_hint}")
    if figure.surrounding_text:
        lines.append(f"Surrounding text:\n{figure.surrounding_text}")
    return "\n".join(lines)


def _image_content(figure: FigureAttachment) -> list[dict[str, str]]:
    encoded = base64.b64encode(figure.image_bytes).decode("ascii")
    return [
        {"type": "input_text", "text": _figure_hint_text(figure)},
        {
            "type": "input_image",
            "image_url": f"data:{figure.mime_type};base64,{encoded}",
        },
    ]


class MuseDiagramProvider(MuseMethodologyProvider):
    """Diagram classification/extraction over the Muse Responses API."""

    async def classify_diagram(
        self, figure: FigureAttachment
    ) -> DiagramClassification:
        """Classify one figure image into a diagram kind."""
        try:
            data = await self._create_response(
                instructions=_CLASSIFY_INSTRUCTIONS,
                content=_image_content(figure),
                schema_name="DiagramClassification",
                schema=_CLASSIFY_SCHEMA,
            )
            raw = self._response_json_object(data, what="diagram classification")
            payload = _ClassificationPayload.model_validate(raw)
        except (MuseProviderError, ValidationError) as exc:
            raise DiagramProviderError(
                f"Muse diagram classification failed ({exc})."
            ) from exc
        return DiagramClassification(
            kind=payload.kind,
            confidence=payload.confidence,
            usage=self.last_usage,
        )

    async def extract_figure_ir(
        self, figure: FigureAttachment, kind: FigureIRKind
    ) -> DiagramIRDraft:
        """Transcribe one figure image into its IR."""
        instructions, schema_name, schema = _figure_extraction_params(kind)
        try:
            data = await self._create_response(
                instructions=instructions,
                content=_image_content(figure),
                schema_name=schema_name,
                schema=schema,
            )
            raw = self._response_json_object(data, what=f"{kind} diagram")
            ir = _parse_figure_ir(kind, raw, figure)
        except (MuseProviderError, ValidationError) as exc:
            raise DiagramProviderError(
                f"Muse {kind} extraction failed ({exc})."
            ) from exc
        return DiagramIRDraft(ir=ir, usage=self.last_usage)

    async def repair_figure_ir(
        self,
        figure: FigureAttachment,
        kind: FigureIRKind,
        broken: dict[str, Any],
        errors: tuple[str, ...],
    ) -> DiagramIRDraft:
        """Repair one figure-derived IR given validator errors."""
        _instructions, schema_name, schema = _figure_extraction_params(kind)
        content = _image_content(figure) + [
            {
                "type": "input_text",
                "text": _repair_text(kind, broken, errors),
            }
        ]
        try:
            data = await self._create_response(
                instructions=_REPAIR_INSTRUCTIONS,
                content=content,
                schema_name=schema_name,
                schema=schema,
            )
            raw = self._response_json_object(data, what=f"{kind} diagram repair")
            ir = _parse_figure_ir(kind, raw, figure)
        except (MuseProviderError, ValidationError) as exc:
            raise DiagramProviderError(
                f"Muse {kind} repair failed ({exc})."
            ) from exc
        return DiagramIRDraft(ir=ir, usage=self.last_usage)

    async def extract_text_ir(
        self, paper_text: str, kind: TextIRKind
    ) -> DiagramIRDraft:
        """Derive one IR from paper text."""
        instructions, schema_name, schema = _text_extraction_params(kind)
        content = [
            {
                "type": "input_text",
                "text": f"Derive the {kind} IR from this paper text:\n{paper_text}",
            }
        ]
        try:
            data = await self._create_response(
                instructions=instructions,
                content=content,
                schema_name=schema_name,
                schema=schema,
            )
            raw = self._response_json_object(data, what=f"{kind} diagram")
            ir = _parse_text_ir(kind, raw)
        except (MuseProviderError, ValidationError) as exc:
            raise DiagramProviderError(
                f"Muse {kind} text extraction failed ({exc})."
            ) from exc
        return DiagramIRDraft(ir=ir, usage=self.last_usage)

    async def repair_text_ir(
        self,
        paper_text: str,
        kind: TextIRKind,
        broken: dict[str, Any],
        errors: tuple[str, ...],
    ) -> DiagramIRDraft:
        """Repair one text-derived IR given validator errors."""
        _instructions, schema_name, schema = _text_extraction_params(kind)
        content = [
            {
                "type": "input_text",
                "text": (
                    f"Source paper text:\n{paper_text}\n\n"
                    + _repair_text(kind, broken, errors)
                ),
            }
        ]
        try:
            data = await self._create_response(
                instructions=_REPAIR_INSTRUCTIONS,
                content=content,
                schema_name=schema_name,
                schema=schema,
            )
            raw = self._response_json_object(data, what=f"{kind} diagram repair")
            ir = _parse_text_ir(kind, raw)
        except (MuseProviderError, ValidationError) as exc:
            raise DiagramProviderError(
                f"Muse {kind} text repair failed ({exc})."
            ) from exc
        return DiagramIRDraft(ir=ir, usage=self.last_usage)

    async def evaluate_what_if(
        self,
        node: MethodologyNode,
        new_params: dict[str, str],
        paper_text: str,
    ) -> WhatIfResult:
        """Estimate the outcome of a step under modified settings."""
        content = [
            {
                "type": "input_text",
                "text": whatif_prompt(node, new_params, paper_text),
            }
        ]
        try:
            data = await self._create_response(
                instructions=WHATIF_INSTRUCTIONS,
                content=content,
                schema_name="WhatIfResult",
                schema=WHATIF_RESULT_JSON_SCHEMA,
            )
            raw = self._response_json_object(data, what="what-if evaluation")
            result = WhatIfResult.model_validate(raw)
        except (MuseProviderError, ValidationError) as exc:
            raise DiagramProviderError(
                f"Muse what-if evaluation failed ({exc})."
            ) from exc
        return result


def _figure_extraction_params(kind: FigureIRKind) -> tuple[str, str, dict[str, Any]]:
    if kind == "circuit":
        return (_CIRCUIT_INSTRUCTIONS, "CircuitIR", CIRCUIT_IR_JSON_SCHEMA)
    if kind == "flow":
        return (_FLOW_INSTRUCTIONS, "MethodologyIR", METHODOLOGY_IR_JSON_SCHEMA)
    return (
        _STRUCTURE_FIGURE_INSTRUCTIONS,
        "StructureIR",
        STRUCTURE_IR_JSON_SCHEMA,
    )


def _text_extraction_params(kind: TextIRKind) -> tuple[str, str, dict[str, Any]]:
    if kind == "methodology":
        return (
            _METHODOLOGY_TEXT_INSTRUCTIONS,
            "MethodologyIR",
            METHODOLOGY_IR_JSON_SCHEMA,
        )
    return (
        _STRUCTURE_TEXT_INSTRUCTIONS,
        "StructureIR",
        STRUCTURE_IR_JSON_SCHEMA,
    )


def _normalize_evidence_lists(node: Any) -> Any:
    """Coerce unambiguous evidence shapes the model sometimes emits.

    Single-item evidence lists carry exactly one reading, so they fold
    to that object; empty lists mean no evidence. Anything else passes
    through untouched and still fails validation loudly.
    """
    if isinstance(node, dict):
        normalized = {key: _normalize_evidence_lists(value) for key, value in node.items()}
        evidence = normalized.get("evidence")
        if isinstance(evidence, list):
            if len(evidence) == 0:
                normalized["evidence"] = None
            elif len(evidence) == 1:
                normalized["evidence"] = evidence[0]
        return normalized
    if isinstance(node, list):
        return [_normalize_evidence_lists(item) for item in node]
    return node


#: Canonical enum values per kind key in diagram payloads.
_KIND_ENUMS: dict[str, frozenset[str]] = {
    "kind": frozenset(
        [kind.value for kind in BlockKind]
        + [kind.value for kind in MethodologyNodeKind]
        + [kind.value for kind in MethodologyEdgeKind]
    ),
    "role": frozenset(role.value for role in NetRole),
    "dir": frozenset(direction.value for direction in PortDirection),
    "side": frozenset(side.value for side in Side),
    "type": frozenset(component.value for component in ComponentType),
}


def _normalize_ir_kinds(node: Any) -> Any:
    """Coerce near-miss enum spellings the model emits for kind keys.

    Case/plural variants ("Modules", "layers") have exactly one
    reading, so they fold to the canonical value. Labels, quotes, and
    every other key pass through untouched, and anything without a
    reading still fails validation loudly.
    """
    if isinstance(node, dict):
        normalized: dict[Any, Any] = {}
        for key, value in node.items():
            value = _normalize_ir_kinds(value)
            if isinstance(value, str) and key in _KIND_ENUMS:
                lowered = value.strip().lower()
                candidates = _KIND_ENUMS[key]
                if lowered in candidates:
                    value = lowered
                elif lowered.endswith("s") and lowered[:-1] in candidates:
                    value = lowered[:-1]
            normalized[key] = value
        return normalized
    if isinstance(node, list):
        return [_normalize_ir_kinds(item) for item in node]
    return node


def _parse_figure_ir(
    kind: FigureIRKind, raw: Any, figure: FigureAttachment
) -> CircuitIR | MethodologyIR | StructureIR:
    if not isinstance(raw, dict):
        raise DiagramProviderError("Muse output must be a JSON object.")
    raw = _normalize_ir_kinds(_normalize_evidence_lists(raw))
    if kind == "circuit":
        source = raw.get("source")
        if not isinstance(source, dict):
            raw["source"] = {}
            source = raw["source"]
        source["figure_id"] = figure.figure_id
        if figure.page is not None:
            source["page"] = figure.page
        return CircuitIR.model_validate(raw)
    if kind == "flow":
        return MethodologyIR.model_validate(raw)
    return StructureIR.model_validate(raw)


def _parse_text_ir(
    kind: TextIRKind, raw: Any
) -> MethodologyIR | StructureIR:
    if not isinstance(raw, dict):
        raise DiagramProviderError("Muse output must be a JSON object.")
    raw = _normalize_ir_kinds(_normalize_evidence_lists(raw))
    if kind == "methodology":
        return MethodologyIR.model_validate(raw)
    return StructureIR.model_validate(raw)


def _repair_text(
    kind: str, broken: dict[str, Any], errors: tuple[str, ...]
) -> str:
    shown = list(errors[:20])
    if len(errors) > 20:
        shown.append(f"... and {len(errors) - 20} more errors")
    return (
        f"Repair this {kind} IR. Validator errors:\n"
        + "\n".join(f"- {error}" for error in shown)
        + "\n\nBroken IR JSON:\n"
        + json.dumps(broken)
    )
