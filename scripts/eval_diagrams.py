"""Evaluate diagram-IR extraction on one paper figure.

Renders one PDF page (pdftoppm), crops the target figure, extracts its
diagram IR through the live diagram service, validates it, and compares
a CircuitIR against a gold file when one exists at
tests/gold/diagrams/<paper_id>.circuit.json.

Gold files are supplied separately and never authored here; without
gold the script reports the validator pass rate and dumps the IR.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from PIL import Image

from bizora.contracts.diagram_ir import CircuitIR
from bizora.contracts.figures import FigureAttachment
from bizora.core.diagram_extraction import (
    DiagramKind,
    MuseDiagramProvider,
    count_tokens,
    extract_figure_diagram,
    extract_text_diagrams,
)
from bizora.core.figure_ingest import caption_candidates, find_figure_mentions
from bizora.core.pdf import extract_page_texts


def component_counts(ir: CircuitIR) -> Counter[str]:
    """Count extracted components by type value."""
    return Counter(component.type.value for component in ir.components)


def net_signatures(ir: CircuitIR) -> Counter[tuple[tuple[str, str], ...]]:
    """Describe each net by its sorted (component type, pin) attachments.

    Id-agnostic: two IRs with the same connectivity but different net
    ids produce the same signature multiset.
    """
    pins_by_net: dict[str, list[tuple[str, str]]] = {}
    for component in ir.components:
        for pin, net_id in component.pins.items():
            pins_by_net.setdefault(net_id, []).append((component.type.value, pin))
    return Counter(tuple(sorted(attachments)) for attachments in pins_by_net.values())


def compare_component_counts(pred: CircuitIR, gold: CircuitIR) -> dict[str, Any]:
    """Compare component counts by type between prediction and gold."""
    pred_counts = component_counts(pred)
    gold_counts = component_counts(gold)
    missing = {k: v for k, v in (gold_counts - pred_counts).items()}
    extra = {k: v for k, v in (pred_counts - gold_counts).items()}
    return {
        "predicted": dict(sorted(pred_counts.items())),
        "gold": dict(sorted(gold_counts.items())),
        "missing": missing,
        "extra": extra,
        "match": not missing and not extra,
    }


def compare_connectivity(pred: CircuitIR, gold: CircuitIR) -> dict[str, Any]:
    """Score net connectivity as F1 over net-signature multisets."""
    pred_sigs = net_signatures(pred)
    gold_sigs = net_signatures(gold)
    matched = sum((pred_sigs & gold_sigs).values())
    pred_total = sum(pred_sigs.values())
    gold_total = sum(gold_sigs.values())
    precision = matched / pred_total if pred_total else (1.0 if not gold_total else 0.0)
    recall = matched / gold_total if gold_total else (1.0 if not pred_total else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "matched": matched,
        "predicted_nets": pred_total,
        "gold_nets": gold_total,
    }


def compare_circuit(pred: CircuitIR, gold: CircuitIR) -> dict[str, Any]:
    """Compare an extracted CircuitIR against its gold file."""
    return {
        "component_counts": compare_component_counts(pred, gold),
        "connectivity": compare_connectivity(pred, gold),
    }


def parse_crop_box(value: str) -> tuple[float, float, float, float]:
    """Parse a normalized 0-100 x0,y0,x1,y1 crop box."""
    try:
        parts = tuple(float(part) for part in value.split(","))
    except ValueError as exc:
        raise ValueError(f"invalid crop box {value!r}: need x0,y0,x1,y1 numbers") from exc
    if len(parts) != 4:
        raise ValueError(f"invalid crop box {value!r}: need x0,y0,x1,y1 numbers")
    x0, y0, x1, y1 = parts
    if not (0 <= x0 < x1 <= 100 and 0 <= y0 < y1 <= 100):
        raise ValueError(
            f"invalid crop box {value!r}: need 0 <= x0 < x1 <= 100, 0 <= y0 < y1 <= 100"
        )
    return (x0, y0, x1, y1)


def load_gold_circuit(path: Path) -> CircuitIR:
    """Load a gold CircuitIR file, raising FileNotFoundError when absent."""
    return CircuitIR.model_validate_json(path.read_text(encoding="utf-8"))


def render_page(pdf: Path, page: int, dpi: int, workdir: Path) -> Path:
    """Render one PDF page to PNG with pdftoppm; return the image path."""
    prefix = workdir / "page"
    try:
        proc = subprocess.run(
            [
                "pdftoppm",
                "-png",
                "-r",
                str(dpi),
                "-f",
                str(page),
                "-l",
                str(page),
                str(pdf),
                str(prefix),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("pdftoppm is required but was not found.") from exc
    if proc.returncode != 0:
        raise RuntimeError(f"pdftoppm failed: {proc.stderr.strip()[-300:]}")
    rendered = sorted(workdir.glob("page-*.png"))
    if len(rendered) != 1:
        raise RuntimeError(f"pdftoppm produced no output for page {page}.")
    return rendered[0]


def crop_figure(
    page_png: Path, box: tuple[float, float, float, float], out_png: Path
) -> tuple[int, int]:
    """Crop a normalized box from a page render; return the crop size."""
    with Image.open(page_png) as image:
        width, height = image.size
        x0, y0, x1, y1 = box
        crop = image.crop(
            (
                round(x0 / 100 * width),
                round(y0 / 100 * height),
                round(x1 / 100 * width),
                round(y1 / 100 * height),
            )
        )
        out_png.parent.mkdir(parents=True, exist_ok=True)
        crop.save(out_png, format="PNG")
        return crop.size


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True, help="Paper PDF path.")
    parser.add_argument("--paper-id", required=True, help="Eval paper id.")
    parser.add_argument("--page", type=int, required=True, help="1-based page number.")
    parser.add_argument(
        "--crop",
        required=True,
        help="Normalized figure crop box as x0,y0,x1,y1 (0-100).",
    )
    parser.add_argument("--figure-id", default=None, help="Figure id for the crop.")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output dir (default docs/visual-eval/<paper-id>).",
    )
    parser.add_argument("--dpi", type=int, default=200, help="Render resolution.")
    parser.add_argument(
        "--with-text",
        action="store_true",
        help="Also derive methodology/structure IRs from paper text.",
    )
    parser.add_argument(
        "--gold",
        type=Path,
        default=None,
        help="Gold CircuitIR path (default tests/gold/diagrams/<paper-id>.circuit.json).",
    )
    return parser


async def run_eval(args: argparse.Namespace) -> dict[str, Any]:
    """Run extraction on one cropped figure; dump IRs and print a report."""
    pdf: Path = args.pdf
    paper_id: str = args.paper_id
    page: int = args.page
    if page < 1:
        raise ValueError("--page must be >= 1.")
    box = parse_crop_box(args.crop)
    figure_id = args.figure_id or f"{paper_id}-p{page}-crop"
    out: Path = args.out or Path("docs/visual-eval") / paper_id
    gold_path: Path = args.gold or Path("tests/gold/diagrams") / f"{paper_id}.circuit.json"

    pdf_bytes = pdf.read_bytes()
    paper_hash = hashlib.sha256(pdf_bytes).hexdigest()
    page_texts = extract_page_texts(pdf_bytes)
    pages = {item.page_number: item.text for item in page_texts}
    page_text = pages.get(page, "")

    figures_dir = out / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="eval-diagrams-") as tmp:
        rendered = render_page(pdf, page, args.dpi, Path(tmp))
        full_render = figures_dir / f"page-{page}.png"
        full_render.write_bytes(rendered.read_bytes())
        crop_png = figures_dir / f"{figure_id}.png"
        crop_size = crop_figure(rendered, box, crop_png)

    mentions = find_figure_mentions(page_text)
    candidates = caption_candidates(page_text)
    attachment = FigureAttachment(
        figure_id=figure_id,
        page=page,
        image_bytes=crop_png.read_bytes(),
        mime_type="image/png",
        surrounding_text=page_text[:4000] or None,
        label_hint=", ".join(mentions)[:512] or None,
        caption_hint="\n---\n".join(candidates)[:4000] or None,
    )

    provider = MuseDiagramProvider()
    figure_result = await extract_figure_diagram(provider, attachment, paper_hash=paper_hash)
    usages = list(figure_result.usage)

    circuit: CircuitIR | None = None
    if figure_result.kind is DiagramKind.CIRCUIT and isinstance(figure_result.ir, CircuitIR):
        circuit = figure_result.ir
    (out / "circuit.json").write_text(
        circuit.model_dump_json(by_alias=True, indent=1) if circuit else "null",
        encoding="utf-8",
    )
    figure_validation = {
        "errors": list(figure_result.validation.errors),
        "warnings": list(figure_result.validation.warnings),
        "stats": dict(figure_result.validation.stats),
    }
    (out / "figure-validation.json").write_text(
        json.dumps(figure_validation, indent=1), encoding="utf-8"
    )

    text_section: dict[str, Any] = {}
    passes = [not figure_result.validation.errors]
    if args.with_text:
        full_text = "\n\n".join(f"[Page {item.page_number}]\n{item.text}" for item in page_texts)
        text_result = await extract_text_diagrams(provider, full_text, paper_hash=paper_hash)
        usages.extend(text_result.usage)
        for name, ir, validation in (
            ("methodology", text_result.methodology, text_result.methodology_validation),
            ("structure", text_result.structure, text_result.structure_validation),
        ):
            (out / f"{name}.json").write_text(
                ir.model_dump_json(by_alias=True, indent=1) if ir else "null",
                encoding="utf-8",
            )
            section = {
                "errors": list(validation.errors),
                "warnings": list(validation.warnings),
                "stats": dict(validation.stats),
            }
            (out / f"{name}-validation.json").write_text(
                json.dumps(section, indent=1), encoding="utf-8"
            )
            text_section[name] = section
            passes.append(not validation.errors)

    validator_pass_rate = sum(passes) / len(passes) if passes else 0.0
    total_in, total_out = count_tokens(usages)
    usage_section = {
        "input_tokens": total_in,
        "output_tokens": total_out,
        "calls": [u.model_dump() for u in usages],
    }
    (out / "usage.json").write_text(json.dumps(usage_section, indent=1), encoding="utf-8")

    gold_section: dict[str, Any] = {"path": str(gold_path), "present": False, "comparison": None}
    if gold_path.exists():
        gold_section["present"] = True
        if circuit is None:
            gold_section["comparison"] = {"skipped": "no CircuitIR extracted"}
        else:
            gold_section["comparison"] = compare_circuit(circuit, load_gold_circuit(gold_path))
            (out / "comparison.json").write_text(
                json.dumps(gold_section["comparison"], indent=1), encoding="utf-8"
            )

    report = {
        "paper_id": paper_id,
        "figure_id": figure_id,
        "page": page,
        "crop": list(box),
        "crop_size": list(crop_size),
        "paper_hash": paper_hash,
        "classification": {
            "kind": figure_result.kind.value,
            "confidence": figure_result.classification_confidence,
        },
        "repaired": figure_result.repaired,
        "from_cache": figure_result.from_cache,
        "figure_validation": figure_validation,
        "text": text_section,
        "validator_pass_rate": validator_pass_rate,
        "usage": {"input_tokens": total_in, "output_tokens": total_out, "calls": len(usages)},
        "gold": gold_section,
    }
    (out / "eval-report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def print_report(report: dict[str, Any]) -> None:
    """Print the human-readable eval summary."""
    print(f"paper: {report['paper_id']} figure: {report['figure_id']}")
    cls = report["classification"]
    print(f"classification: {cls['kind']} (confidence {cls['confidence']})")
    fv = report["figure_validation"]
    print(f"figure errors: {len(fv['errors'])} warnings: {len(fv['warnings'])}")
    for error in fv["errors"]:
        print(f"  ERROR {error}")
    for warning in fv["warnings"]:
        print(f"  WARN {warning}")
    print(f"figure stats: {json.dumps(fv['stats'], sort_keys=True)}")
    for name, section in report["text"].items():
        print(
            f"text {name}: errors={len(section['errors'])} "
            f"warnings={len(section['warnings'])} stats={section['stats']}"
        )
    print(f"validator pass rate: {report['validator_pass_rate']:.2f}")
    usage = report["usage"]
    print(f"tokens: in={usage['input_tokens']} out={usage['output_tokens']} calls={usage['calls']}")
    gold = report["gold"]
    if not gold["present"]:
        print(f"gold: MISSING at {gold['path']} (validator pass rate + IR dump only)")
    else:
        print(f"gold: {json.dumps(gold['comparison'], indent=1)}")


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    try:
        report = asyncio.run(run_eval(args))
    except Exception as exc:
        print(f"eval failed: {exc}", file=sys.stderr)
        return 1
    print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
