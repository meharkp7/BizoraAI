"""Tests for figure/text -> diagram-IR extraction (stub provider, no API)."""

import asyncio
import json
from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from bizora.contracts.diagram_ir import (
    CircuitIR,
    MethodologyIR,
    MethodologyNode,
    StructureIR,
)
from bizora.contracts.figures import FigureAttachment, ResponseUsage
from bizora.core.diagram_extraction import (
    DiagramClassification,
    DiagramIRDraft,
    DiagramKind,
    DiagramProviderError,
    FigureIRKind,
    TextIRKind,
    diagram_cache_key,
    extract_figure_diagram,
    extract_paper_diagrams,
    extract_text_diagrams,
    text_cache_key,
)
from bizora.core.diagram_whatif import WhatIfBasis, WhatIfResult


def make_figure(figure_id: str = "fig1") -> FigureAttachment:
    return FigureAttachment(
        figure_id=figure_id,
        page=2,
        image_bytes=b"\x89PNG-fake",
        mime_type="image/png",
        surrounding_text="Figure 1. Bitcell schematic.",
    )


def make_circuit_payload(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "version": 1,
        "title": "bitcell",
        "source": {"figure_id": "fig1", "page": 2},
        "components": [
            {"id": "M1", "type": "nmos", "label": "M1",
             "pins": {"d": "n1", "g": "n2", "s": "gnd"}, "confidence": 0.9},
            {"id": "R1", "type": "resistor", "label": "R1",
             "pins": {"a": "n1", "b": "gnd"}, "confidence": 0.8},
        ],
        "nets": [
            {"id": "gnd", "label": "GND", "role": "ground", "global": True},
            {"id": "n1", "label": "N1", "role": "signal", "global": False},
            {"id": "n2", "label": "N2", "role": "input", "global": False},
        ],
        "ports": [
            {"id": "P1", "net": "n2", "label": "IN", "dir": "in", "side": "left"},
        ],
    }
    base.update(overrides)
    return base


def make_methodology_payload() -> dict[str, Any]:
    return {
        "version": 1,
        "title": "flow",
        "groups": [],
        "nodes": [
            {"id": "n1", "label": "load", "kind": "input", "confidence": 0.9},
            {"id": "n2", "label": "train", "kind": "model", "confidence": 0.8},
        ],
        "edges": [{"from": "n1", "to": "n2", "kind": "data"}],
    }


def make_structure_payload() -> dict[str, Any]:
    return {
        "version": 1,
        "title": "macro",
        "root": {
            "id": "chip", "label": "chip", "kind": "chip", "confidence": 0.9,
            "children": [
                {"id": "arr", "label": "array", "kind": "array",
                 "count": {"rows": 16, "cols": 16}, "confidence": 0.8,
                 "children": [
                     {"id": "cell", "label": "cell", "kind": "cell",
                      "confidence": 0.7, "children": []}
                 ]},
            ],
        },
    }


def parse_draft(kind: str, payload: Mapping[str, Any]) -> DiagramIRDraft:
    if kind == "circuit":
        ir = CircuitIR.model_validate(payload)
    elif kind in ("flow", "methodology"):
        ir = MethodologyIR.model_validate(payload)
    else:
        ir = StructureIR.model_validate(payload)
    return DiagramIRDraft(
        ir=ir, usage=ResponseUsage(input_tokens=10, output_tokens=20)
    )


class ScriptedDiagramProvider:
    """Stub DiagramVisionProvider with queued responses and call counts."""

    provider_name = "stub"

    def __init__(self) -> None:
        self.classifications: dict[str, DiagramKind] = {}
        self.figure_payloads: dict[tuple[str, str], dict[str, Any]] = {}
        self.repair_payloads: dict[tuple[str, str], dict[str, Any]] = {}
        self.text_payloads: dict[str, dict[str, Any]] = {}
        self.text_repair_payloads: dict[str, dict[str, Any]] = {}
        self.calls: dict[str, int] = {}
        self.fail_extract: bool = False
        self.fail_whatif: bool = False

    def _count(self, name: str) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1

    async def classify_diagram(
        self, figure: FigureAttachment
    ) -> DiagramClassification:
        self._count("classify")
        return DiagramClassification(
            kind=self.classifications.get(figure.figure_id, DiagramKind.CIRCUIT),
            confidence=0.9,
            usage=ResponseUsage(input_tokens=5, output_tokens=5),
        )

    async def extract_figure_ir(
        self, figure: FigureAttachment, kind: FigureIRKind
    ) -> DiagramIRDraft:
        self._count(f"extract:{kind}")
        if self.fail_extract:
            raise DiagramProviderError("stub extract failure")
        return parse_draft(kind, self.figure_payloads[(figure.figure_id, kind)])

    async def repair_figure_ir(
        self,
        figure: FigureAttachment,
        kind: FigureIRKind,
        broken: dict[str, Any],
        errors: tuple[str, ...],
    ) -> DiagramIRDraft:
        self._count(f"repair:{kind}")
        assert broken and errors
        return parse_draft(kind, self.repair_payloads[(figure.figure_id, kind)])

    async def extract_text_ir(
        self, paper_text: str, kind: TextIRKind
    ) -> DiagramIRDraft:
        self._count(f"text:{kind}")
        assert paper_text.strip()
        return parse_draft(kind, self.text_payloads[kind])

    async def repair_text_ir(
        self,
        paper_text: str,
        kind: TextIRKind,
        broken: dict[str, Any],
        errors: tuple[str, ...],
    ) -> DiagramIRDraft:
        self._count(f"text_repair:{kind}")
        assert paper_text.strip() and broken and errors
        return parse_draft(kind, self.text_repair_payloads[kind])

    async def evaluate_what_if(
        self,
        node: MethodologyNode,
        new_params: dict[str, str],
        paper_text: str,
    ) -> WhatIfResult:
        self._count("whatif")
        assert paper_text.strip()
        if self.fail_whatif:
            raise DiagramProviderError("stub what-if failure")
        return WhatIfResult(
            node_id=node.id,
            node_label=node.label,
            params_previous={key: str(value) for key, value in node.params.items()},
            params_applied=dict(new_params),
            outcome="Estimated stub outcome.",
            basis=(WhatIfBasis(quote="stub quote", page=2),),
            assumptions=("stub assumption",),
            confidence=0.5,
        )


def test_extract_figure_circuit_success_without_repair(tmp_path: Any) -> None:
    import os

    os.environ["BIZORA_CACHE_DIR"] = str(tmp_path)
    try:
        provider = ScriptedDiagramProvider()
        provider.figure_payloads[("fig1", "circuit")] = make_circuit_payload()

        async def run_test() -> None:
            result = await extract_figure_diagram(
                provider, make_figure(), paper_hash="a" * 64
            )

            assert result.kind == DiagramKind.CIRCUIT
            assert isinstance(result.ir, CircuitIR)
            assert result.validation.errors == ()
            assert result.repaired is False
            assert result.from_cache is False
            assert provider.calls.get("repair:circuit", 0) == 0
            assert len(result.usage) == 2  # classify + extract

        asyncio.run(run_test())
    finally:
        del os.environ["BIZORA_CACHE_DIR"]


def test_repair_runs_once_and_keeps_better_result(tmp_path: Any) -> None:
    import os

    os.environ["BIZORA_CACHE_DIR"] = str(tmp_path)
    try:
        provider = ScriptedDiagramProvider()
        broken = make_circuit_payload()
        broken["components"][0]["pins"]["d"] = "ghost"
        provider.figure_payloads[("fig1", "circuit")] = broken
        provider.repair_payloads[("fig1", "circuit")] = make_circuit_payload()

        async def run_test() -> None:
            result = await extract_figure_diagram(
                provider, make_figure(), paper_hash="b" * 64
            )

            assert result.repaired is True
            assert result.validation.errors == ()
            assert provider.calls.get("repair:circuit") == 1

        asyncio.run(run_test())
    finally:
        del os.environ["BIZORA_CACHE_DIR"]


def test_repair_keeps_original_when_repair_is_worse(tmp_path: Any) -> None:
    import os

    os.environ["BIZORA_CACHE_DIR"] = str(tmp_path)
    try:
        provider = ScriptedDiagramProvider()
        broken = make_circuit_payload()
        broken["components"][0]["pins"]["d"] = "ghost"
        worse = make_circuit_payload()
        worse["components"][0]["pins"]["d"] = "ghost"
        worse["components"][0]["pins"]["g"] = "ghost2"
        provider.figure_payloads[("fig1", "circuit")] = broken
        provider.repair_payloads[("fig1", "circuit")] = worse

        async def run_test() -> None:
            result = await extract_figure_diagram(
                provider, make_figure(), paper_hash="c" * 64
            )

            assert result.repaired is False
            # unknown net 'ghost' + net 'n1' left dangling
            assert len(result.validation.errors) == 2
            assert isinstance(result.ir, CircuitIR)
            assert result.ir.components[0].pins["g"] == "n2"

        asyncio.run(run_test())
    finally:
        del os.environ["BIZORA_CACHE_DIR"]


def test_other_classification_skips_extraction(tmp_path: Any) -> None:
    import os

    os.environ["BIZORA_CACHE_DIR"] = str(tmp_path)
    try:
        provider = ScriptedDiagramProvider()
        provider.classifications["fig1"] = DiagramKind.OTHER

        async def run_test() -> None:
            result = await extract_figure_diagram(
                provider, make_figure(), paper_hash="d" * 64
            )

            assert result.ir is None
            assert result.validation.errors == ()
            assert "extract:circuit" not in provider.calls

        asyncio.run(run_test())
    finally:
        del os.environ["BIZORA_CACHE_DIR"]


def test_text_fallback_when_no_figures(tmp_path: Any) -> None:
    import os

    os.environ["BIZORA_CACHE_DIR"] = str(tmp_path)
    try:
        provider = ScriptedDiagramProvider()
        provider.text_payloads["methodology"] = make_methodology_payload()
        provider.text_payloads["structure"] = make_structure_payload()

        async def run_test() -> None:
            result = await extract_paper_diagrams(
                provider, (), "A 16x16 array of bitcells.", paper_hash="e" * 64
            )

            assert isinstance(result.methodology, MethodologyIR)
            assert isinstance(result.structure, StructureIR)
            assert [circuit.title for circuit in result.circuits] == [
                "flow (system blocks)"
            ]
            assert result.sources["methodology"] == "text"
            assert result.sources["structure"] == "text"
            assert result.sources["circuit:derived"] == "derived:methodology"
            assert result.usage

        asyncio.run(run_test())
    finally:
        del os.environ["BIZORA_CACHE_DIR"]


def test_served_structure_is_arranged_for_render(tmp_path: Any) -> None:
    import os

    os.environ["BIZORA_CACHE_DIR"] = str(tmp_path)
    try:
        provider = ScriptedDiagramProvider()
        provider.text_payloads["methodology"] = make_methodology_payload()
        provider.text_payloads["structure"] = {
            "version": 1,
            "title": "chip",
            "root": {
                "id": "chip",
                "label": "chip",
                "kind": "chip",
                "confidence": 0.9,
                "children": [
                    {
                        "id": "arr",
                        "label": "array",
                        "kind": "array",
                        "count": {"rows": 4, "cols": 4},
                        "confidence": 0.8,
                        "children": [
                            {
                                "id": "cell",
                                "label": "cell",
                                "kind": "cell",
                                "confidence": 0.7,
                                "children": [],
                            },
                            {
                                "id": "gate",
                                "label": "OR gate",
                                "kind": "periphery",
                                "confidence": 0.8,
                                "children": [],
                            },
                        ],
                    },
                    {
                        "id": "ro",
                        "label": "readout",
                        "kind": "periphery",
                        "confidence": 0.8,
                        "children": [],
                    },
                ],
            },
        }

        async def run_test() -> None:
            result = await extract_paper_diagrams(
                provider, (), "An array with shared logic.", paper_hash="d" * 64
            )

            assert isinstance(result.structure, StructureIR)
            assert [c.id for c in result.structure.root.children] == [
                "arr",
                "ro",
                "gate",
            ]
            by_id = {c.id: c for c in result.structure.root.children}
            assert by_id["ro"].pos == "bottom"
            assert by_id["gate"].pos == "right"
            warnings = result.validation["structure"].warnings
            assert any("'gate'" in note for note in warnings)
            assert any("illustratively" in note for note in warnings)

        asyncio.run(run_test())
    finally:
        del os.environ["BIZORA_CACHE_DIR"]


def test_figure_methodology_preferred_over_text(tmp_path: Any) -> None:
    import os

    os.environ["BIZORA_CACHE_DIR"] = str(tmp_path)
    try:
        provider = ScriptedDiagramProvider()
        provider.classifications["fig1"] = DiagramKind.FLOW
        provider.classifications["fig2"] = DiagramKind.CIRCUIT
        provider.figure_payloads[("fig1", "flow")] = make_methodology_payload()
        provider.figure_payloads[("fig2", "circuit")] = make_circuit_payload()
        provider.text_payloads["structure"] = make_structure_payload()

        async def run_test() -> None:
            result = await extract_paper_diagrams(
                provider,
                [make_figure("fig1"), make_figure("fig2")],
                "Some paper text.",
                paper_hash="f" * 64,
            )

            assert isinstance(result.methodology, MethodologyIR)
            assert result.sources["methodology"] == "figure:fig1"
            assert len(result.circuits) == 1
            assert result.sources["structure"] == "text"
            assert "text:methodology" not in provider.calls
            assert provider.calls.get("text:structure") == 1

        asyncio.run(run_test())
    finally:
        del os.environ["BIZORA_CACHE_DIR"]


def test_cache_hit_skips_provider(tmp_path: Any) -> None:
    import os

    os.environ["BIZORA_CACHE_DIR"] = str(tmp_path)
    try:
        provider = ScriptedDiagramProvider()
        provider.figure_payloads[("fig1", "circuit")] = make_circuit_payload()

        async def run_test() -> None:
            first = await extract_figure_diagram(
                provider, make_figure(), paper_hash="1" * 64
            )
            calls_after_first = dict(provider.calls)
            second = await extract_figure_diagram(
                provider, make_figure(), paper_hash="1" * 64
            )

            assert first.from_cache is False
            assert second.from_cache is True
            assert second.ir == first.ir
            assert provider.calls == calls_after_first

        asyncio.run(run_test())
    finally:
        del os.environ["BIZORA_CACHE_DIR"]


def test_cache_keys_vary_by_figure_and_prompt_version() -> None:
    assert diagram_cache_key("a" * 64, "fig1") == diagram_cache_key("a" * 64, "fig1")
    assert diagram_cache_key("a" * 64, "fig1") != diagram_cache_key("a" * 64, "fig2")
    assert diagram_cache_key("a" * 64, "fig1") != diagram_cache_key("b" * 64, "fig1")
    assert "v" in diagram_cache_key("a" * 64, "fig1")
    assert text_cache_key("a" * 64, "methodology") != text_cache_key("b" * 64, "methodology")
    assert text_cache_key("a" * 64, "methodology") != text_cache_key("a" * 64, "structure")


def test_empty_text_skips_text_extraction(tmp_path: Any) -> None:
    import os

    os.environ["BIZORA_CACHE_DIR"] = str(tmp_path)
    try:
        provider = ScriptedDiagramProvider()

        async def run_test() -> None:
            result = await extract_text_diagrams(
                provider, "  ", paper_hash="2" * 64
            )

            assert result.methodology is None
            assert result.structure is None
            assert provider.calls == {}

        asyncio.run(run_test())
    finally:
        del os.environ["BIZORA_CACHE_DIR"]


def test_extract_provider_error_propagates(tmp_path: Any) -> None:
    import os

    os.environ["BIZORA_CACHE_DIR"] = str(tmp_path)
    try:
        provider = ScriptedDiagramProvider()
        provider.fail_extract = True

        async def run_test() -> None:
            with pytest.raises(DiagramProviderError):
                await extract_figure_diagram(
                    provider, make_figure(), paper_hash="3" * 64
                )

        asyncio.run(run_test())
    finally:
        del os.environ["BIZORA_CACHE_DIR"]


def test_cached_payload_is_plain_json(tmp_path: Any) -> None:
    import os

    os.environ["BIZORA_CACHE_DIR"] = str(tmp_path)
    try:
        provider = ScriptedDiagramProvider()
        provider.figure_payloads[("fig1", "circuit")] = make_circuit_payload()

        async def run_test() -> None:
            await extract_figure_diagram(
                provider, make_figure(), paper_hash="4" * 64
            )

        asyncio.run(run_test())
        cached_files = list((tmp_path / "bizora" / "diagrams").glob("*.json"))
        assert len(cached_files) == 1
        payload = json.loads(cached_files[0].read_text(encoding="utf-8"))
        assert payload["kind"] == "circuit"
        assert payload["ir"]["title"] == "bitcell"
    finally:
        del os.environ["BIZORA_CACHE_DIR"]


def test_sequence_figures_accepted(tmp_path: Any) -> None:
    import os

    os.environ["BIZORA_CACHE_DIR"] = str(tmp_path)
    try:
        provider = ScriptedDiagramProvider()
        provider.figure_payloads[("fig1", "circuit")] = make_circuit_payload()
        provider.text_payloads["methodology"] = make_methodology_payload()
        provider.text_payloads["structure"] = make_structure_payload()

        async def run_test() -> None:
            figures: Sequence[FigureAttachment] = (make_figure(),)
            result = await extract_paper_diagrams(
                provider, figures, "text", paper_hash="5" * 64
            )
            assert len(result.circuits) == 1

        asyncio.run(run_test())
    finally:
        del os.environ["BIZORA_CACHE_DIR"]


def test_circuit_instructions_define_renderer_orientation() -> None:
    """The circuit prompt must pin the rot-0 convention, or MOSFETs
    transcribe upside-down (PMOS sources rendered below the device)."""
    from bizora.core.diagram_extraction import _CIRCUIT_INSTRUCTIONS

    assert "gate exits left, drain up, source down" in _CIRCUIT_INSTRUCTIONS
    assert "flip true at rot 0" in _CIRCUIT_INSTRUCTIONS
    assert "triangle's apex" in _CIRCUIT_INSTRUCTIONS


def make_unrenderable_structure_payload() -> dict[str, Any]:
    """Array root with a bare total and no grid: contract-valid but
    the engine cannot draw it."""
    return {
        "version": 1,
        "title": "cells",
        "root": {
            "id": "arr", "label": "array", "kind": "array",
            "count": 2000, "confidence": 0.8,
            "children": [
                {"id": "cell", "label": "cell", "kind": "cell",
                 "confidence": 0.7, "children": []},
            ],
        },
    }


def test_errored_figure_structure_falls_back_to_text(tmp_path: Any) -> None:
    import os

    os.environ["BIZORA_CACHE_DIR"] = str(tmp_path)
    try:
        provider = ScriptedDiagramProvider()
        provider.classifications["fig1"] = DiagramKind.STRUCTURE
        broken = make_unrenderable_structure_payload()
        provider.figure_payloads[("fig1", "structure")] = broken
        provider.repair_payloads[("fig1", "structure")] = broken
        provider.text_payloads["methodology"] = make_methodology_payload()
        provider.text_payloads["structure"] = make_structure_payload()

        async def run_test() -> None:
            result = await extract_paper_diagrams(
                provider,
                [make_figure("fig1")],
                "A 16x16 array of bitcells.",
                paper_hash="a" * 64,
            )

            assert isinstance(result.structure, StructureIR)
            assert result.structure.title == "macro"
            assert result.sources["structure"] == "text"
            report = result.validation["structure:figure:fig1"]
            assert any("rows/cols grid" in e for e in report.errors)

        asyncio.run(run_test())
    finally:
        del os.environ["BIZORA_CACHE_DIR"]


def test_parse_text_ir_tolerates_single_item_evidence_lists() -> None:
    from bizora.core.diagram_extraction import _parse_text_ir

    raw = {
        "version": 1,
        "title": "macro",
        "root": {
            "id": "chip",
            "label": "chip",
            "kind": "chip",
            "confidence": 0.9,
            "evidence": [{"page": 5, "quote": "chip quote"}],
            "children": [
                {
                    "id": "arr",
                    "label": "array",
                    "kind": "array",
                    "confidence": 0.8,
                    "evidence": [],
                    "children": [],
                }
            ],
        },
    }

    ir = _parse_text_ir("structure", raw)

    assert ir.root.evidence is not None
    assert ir.root.evidence.page == 5
    assert ir.root.children[0].evidence is None


def test_parse_text_ir_rejects_ambiguous_evidence_lists() -> None:
    from bizora.core.diagram_extraction import DiagramProviderError, _parse_text_ir

    raw = {
        "version": 1,
        "title": "macro",
        "root": {
            "id": "chip",
            "label": "chip",
            "kind": "chip",
            "confidence": 0.9,
            "evidence": [
                {"page": 5, "quote": "first"},
                {"page": 6, "quote": "second"},
            ],
            "children": [],
        },
    }

    with pytest.raises((DiagramProviderError, ValueError)):
        _parse_text_ir("structure", raw)


def test_derived_fallbacks_when_figures_yield_no_structure(tmp_path: Any) -> None:
    import os

    os.environ["BIZORA_CACHE_DIR"] = str(tmp_path)
    try:
        provider = ScriptedDiagramProvider()
        provider.classifications["fig1"] = DiagramKind.FLOW
        provider.figure_payloads[("fig1", "flow")] = make_methodology_payload()

        async def run_test() -> None:
            result = await extract_paper_diagrams(
                provider, [make_figure("fig1")], "", paper_hash="g" * 64
            )

            assert result.sources["methodology"] == "figure:fig1"
            assert [circuit.title for circuit in result.circuits] == [
                "flow (system blocks)"
            ]
            assert result.sources["circuit:derived"] == "derived:methodology"
            assert result.structure is not None
            assert result.structure.title == "flow (system structure)"
            assert result.sources["structure"] == "derived:methodology"
            assert any(
                "derived from the methodology flow" in note
                for note in result.validation["circuit:derived"].warnings
            )

        asyncio.run(run_test())
    finally:
        del os.environ["BIZORA_CACHE_DIR"]


def test_figure_circuits_skip_derivation(tmp_path: Any) -> None:
    import os

    os.environ["BIZORA_CACHE_DIR"] = str(tmp_path)
    try:
        provider = ScriptedDiagramProvider()
        provider.classifications["fig1"] = DiagramKind.FLOW
        provider.classifications["fig2"] = DiagramKind.CIRCUIT
        provider.figure_payloads[("fig1", "flow")] = make_methodology_payload()
        provider.figure_payloads[("fig2", "circuit")] = make_circuit_payload()

        async def run_test() -> None:
            result = await extract_paper_diagrams(
                provider,
                [make_figure("fig1"), make_figure("fig2")],
                "",
                paper_hash="h" * 64,
            )

            assert [circuit.title for circuit in result.circuits] == ["bitcell"]
            assert "circuit:derived" not in result.sources
            assert result.sources["structure"] == "derived:methodology"

        asyncio.run(run_test())
    finally:
        del os.environ["BIZORA_CACHE_DIR"]


def test_kind_normalization_folds_case_and_plurals() -> None:
    from bizora.core.diagram_extraction import _parse_text_ir

    ir = _parse_text_ir(
        "structure",
        {
            "version": 1,
            "title": "Modules",
            "root": {
                "id": "sys",
                "label": "Modules stay verbatim in labels",
                "kind": "Modules",
                "confidence": 0.7,
                "children": [
                    {
                        "id": "enc",
                        "label": "Encoder",
                        "kind": "layers",
                        "confidence": 0.6,
                        "children": [],
                    }
                ],
            },
        },
    )

    assert ir.root.kind.value == "module"
    assert ir.root.children[0].kind.value == "layer"
    assert ir.root.label == "Modules stay verbatim in labels"


def test_kind_normalization_leaves_unknown_kinds_loud() -> None:
    import pytest
    from pydantic import ValidationError

    from bizora.core.diagram_extraction import _parse_text_ir

    with pytest.raises(ValidationError):
        _parse_text_ir(
            "structure",
            {
                "version": 1,
                "title": "x",
                "root": {
                    "id": "sys",
                    "label": "x",
                    "kind": "flux-capacitor",
                    "confidence": 0.5,
                    "children": [],
                },
            },
        )


def test_text_kind_failure_does_not_sink_sibling(tmp_path: Any) -> None:
    import os

    os.environ["BIZORA_CACHE_DIR"] = str(tmp_path)
    try:
        provider = ScriptedDiagramProvider()
        provider.text_payloads["methodology"] = make_methodology_payload()

        async def fail_structure(paper_text: str, kind: str):  # type: ignore[no-untyped-def]
            if kind == "structure":
                raise DiagramProviderError("stub structure failure")
            return await ScriptedDiagramProvider.extract_text_ir(provider, paper_text, kind)  # type: ignore[arg-type]

        provider.extract_text_ir = fail_structure  # type: ignore[method-assign]

        async def run_test() -> None:
            result = await extract_paper_diagrams(
                provider, (), "Some paper text.", paper_hash="i" * 64
            )

            assert result.methodology is not None
            assert result.structure is not None
            assert result.sources["structure"] == "derived:methodology"
            assert result.sources["circuit:derived"] == "derived:methodology"

        asyncio.run(run_test())
    finally:
        del os.environ["BIZORA_CACHE_DIR"]


def test_figure_failure_does_not_sink_siblings(tmp_path: Any) -> None:
    import os

    os.environ["BIZORA_CACHE_DIR"] = str(tmp_path)
    try:
        provider = ScriptedDiagramProvider()
        provider.classifications["fig1"] = DiagramKind.FLOW
        provider.classifications["bad"] = DiagramKind.CIRCUIT
        provider.figure_payloads[("fig1", "flow")] = make_methodology_payload()

        real_extract = provider.extract_figure_ir

        async def fail_bad(figure, kind):  # type: ignore[no-untyped-def]
            if figure.figure_id == "bad":
                raise DiagramProviderError("stub figure failure")
            return await real_extract(figure, kind)

        provider.extract_figure_ir = fail_bad  # type: ignore[method-assign]

        async def run_test() -> None:
            result = await extract_paper_diagrams(
                provider,
                [make_figure("fig1"), make_figure("bad")],
                "",
                paper_hash="j" * 64,
            )

            assert result.sources["methodology"] == "figure:fig1"
            assert result.sources["structure"] == "derived:methodology"

        asyncio.run(run_test())
    finally:
        del os.environ["BIZORA_CACHE_DIR"]
