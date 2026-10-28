"""Phase 0 gold-set evaluation harness.

Runs extraction over the papers listed in tests/gold/manifest.json and
prints domain accuracy plus component precision/recall.

Usage:
    python -m bizora.eval_gold [--manifest PATH] [--provider baseline|baseten|muse]
        [--split all|dev|heldout] [--refresh] [--cache-dir PATH]
"""

import argparse
import asyncio
import json
from collections.abc import Mapping
from pathlib import Path

from bizora.contracts.gold import (
    GoldEvalReport,
    GoldManifest,
    GoldPaper,
    GoldPaperResult,
    load_manifest,
)
from bizora.contracts.graph import MethodologyGraph
from bizora.core.entity_service import classify_graph
from bizora.core.extraction_service import MethodologyExtractionService
from bizora.core.papers import (
    DEFAULT_CREATED_BY,
    suggest_graph_id,
    suggest_project_id,
    suggest_source_id,
)
from bizora.core.pdf import extract_text_from_pdf
from bizora.providers.base import (
    MethodologyExtractionRequest,
    MethodologyExtractionResult,
    MethodologyProvider,
)

# Same ceiling as the papers upload path (api.PAPER_TEXT_LIMIT).
EVAL_PAPER_TEXT_LIMIT = 120_000

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = REPO_ROOT / "tests" / "gold" / "manifest.json"
DEFAULT_CACHE_DIR = REPO_ROOT / "tests" / "gold" / ".cache"


class BaselineEmptyProvider:
    """Offline baseline: returns an empty (no-node) draft graph.

    This exercises the real pipeline entry points (PDF ingest, draft
    validation, lexical classification) without any model call, so the
    first `eval_gold` numbers are an honest floor to beat.
    """

    provider_name = "gold-baseline"
    model_name = "empty-graph-v0"

    async def extract_methodology(
        self, request: MethodologyExtractionRequest
    ) -> MethodologyExtractionResult:
        graph = MethodologyGraph(
            schema_version="1.0",
            project_id=request.project_id,
            graph_id=request.graph_id,
            version=1,
            title=request.title or "gold evaluation draft",
            source_ids=[request.source_id],
            nodes=[],
            edges=[],
            created_by=request.created_by,
        )
        return MethodologyExtractionResult(
            draft_graph=graph,
            provider_name=self.provider_name,
            model_name=self.model_name,
        )


def _cache_path(cache_dir: Path, provider_name: str, pdf_sha256: str) -> Path:
    """Return the cache file for one provider run over one PDF hash."""
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in provider_name)
    return cache_dir / f"{safe}_{pdf_sha256}.json"


def _read_cached_graph(path: Path) -> MethodologyGraph | None:
    """Load a cached draft graph; any problem means a cache miss."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("graph"), dict):
        return None
    try:
        return MethodologyGraph.model_validate(raw["graph"])
    except Exception:
        return None


def _write_cached_graph(
    path: Path, provider_name: str, pdf_sha256: str, graph: MethodologyGraph
) -> None:
    """Persist one successful draft graph keyed by provider and PDF hash."""
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "provider": provider_name,
        "pdf_sha256": pdf_sha256,
        "graph": graph.model_dump(mode="json"),
    }
    path.write_text(json.dumps(record), encoding="utf-8")


def _record_usage(provider: MethodologyProvider, usage: dict[str, int] | None) -> None:
    """Accumulate metered-provider usage; unmetered providers are skipped."""
    if usage is None:
        return
    last = getattr(provider, "last_usage", None)
    if last is None:
        return
    usage["live_calls"] = usage.get("live_calls", 0) + 1
    input_tokens = getattr(last, "input_tokens", None)
    output_tokens = getattr(last, "output_tokens", None)
    if isinstance(input_tokens, int):
        usage["input_tokens"] = usage.get("input_tokens", 0) + input_tokens
    if isinstance(output_tokens, int):
        usage["output_tokens"] = usage.get("output_tokens", 0) + output_tokens


def normalize_term(value: str) -> str:
    """Normalize one component/domain term for comparison."""
    return " ".join(value.strip().lower().split())


def terms_match(expected: str, predicted: str) -> bool:
    """Return whether two component terms refer to the same component.

    Matches on normalized equality or token-set containment in either
    direction, so a terse gold name ("LoRA") matches a descriptive
    predicted label ("LoRA rank decomposition matrices A and B") and
    vice versa. Single generic tokens can over-match; both providers
    face the same scorer, so comparisons stay fair.
    """
    left = normalize_term(expected)
    right = normalize_term(predicted)
    if not left or not right:
        return False
    if left == right:
        return True
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    return left_tokens <= right_tokens or right_tokens <= left_tokens


def domain_matches(predicted: str, expected_tags: tuple[str, ...]) -> bool:
    """Return whether the predicted domain is among the expected tags."""
    expected = {normalize_term(tag) for tag in expected_tags}
    return normalize_term(predicted) in expected


def score_components(
    predicted_labels: tuple[str, ...],
    paper: GoldPaper,
) -> tuple[int, int]:
    """Return (matched_expected, matched_predicted) component counts."""
    predicted = [label for label in predicted_labels if normalize_term(label)]
    expected_names: list[str] = []
    for component in paper.components:
        expected_names.append(component.name)
        expected_names.extend(component.aliases)
    expected_names = [name for name in expected_names if normalize_term(name)]
    matched_expected = 0
    for component in paper.components:
        names = [component.name, *component.aliases]
        if any(terms_match(name, label) for name in names for label in predicted):
            matched_expected += 1
    matched_predicted = sum(
        1 for label in predicted if any(terms_match(name, label) for name in expected_names)
    )
    return matched_expected, matched_predicted


async def evaluate_paper(
    paper: GoldPaper,
    *,
    repo_root: Path,
    provider: MethodologyProvider,
    provider_name: str = "gold-baseline",
    cache_dir: Path | None = None,
    refresh: bool = False,
    usage: dict[str, int] | None = None,
) -> GoldPaperResult:
    """Run the extraction pipeline for one gold paper."""
    pdf_file = repo_root / paper.pdf_path
    if not pdf_file.is_file():
        return GoldPaperResult(
            paper_id=paper.paper_id,
            status="missing",
            expected_components=len(paper.components),
            predicted_components=0,
            matched_expected=0,
            matched_predicted=0,
            detail=f"pdf: {paper.pdf_path}",
        )
    try:
        data = pdf_file.read_bytes()
        pdf = extract_text_from_pdf(data, max_chars=EVAL_PAPER_TEXT_LIMIT)
        short_hash = pdf.sha256[:8]
        request = MethodologyExtractionRequest(
            paper_text=pdf.text,
            project_id=suggest_project_id(paper.paper_id, short_hash),
            graph_id=suggest_graph_id(paper.paper_id, short_hash),
            source_id=suggest_source_id(short_hash),
            created_by=DEFAULT_CREATED_BY,
            title=pdf.doc_title,
        )
        graph: MethodologyGraph | None = None
        cache_file: Path | None = None
        if cache_dir is not None:
            cache_file = _cache_path(cache_dir, provider_name, pdf.sha256)
            if not refresh:
                graph = _read_cached_graph(cache_file)
        if graph is None:
            graph = await MethodologyExtractionService.extract_draft(provider, request)
            _record_usage(provider, usage)
            if cache_file is not None:
                _write_cached_graph(cache_file, provider_name, pdf.sha256, graph)
        classification = classify_graph(graph)
    except Exception as exc:
        return GoldPaperResult(
            paper_id=paper.paper_id,
            status="error",
            expected_components=len(paper.components),
            predicted_components=0,
            matched_expected=0,
            matched_predicted=0,
            detail=f"{type(exc).__name__}: {exc}",
        )
    predicted_labels = tuple(node.label for node in graph.nodes)
    matched_expected, matched_predicted = score_components(predicted_labels, paper)
    match = domain_matches(classification.domain, paper.domain_tags)
    return GoldPaperResult(
        paper_id=paper.paper_id,
        status="ok",
        predicted_domain=classification.domain,
        domain_match=match,
        expected_components=len(paper.components),
        predicted_components=len(predicted_labels),
        matched_expected=matched_expected,
        matched_predicted=matched_predicted,
        detail="",
    )


def summarize(
    manifest: GoldManifest, results: tuple[GoldPaperResult, ...], *, provider_name: str
) -> GoldEvalReport:
    """Aggregate per-paper results into one report."""
    evaluated = sum(1 for item in results if item.status == "ok")
    missing = sum(1 for item in results if item.status == "missing")
    errors = sum(1 for item in results if item.status == "error")
    if evaluated:
        domain_hits = sum(1 for item in results if item.domain_match)
        domain_accuracy = domain_hits / evaluated
    else:
        domain_accuracy = 0.0
    total_expected = sum(item.expected_components for item in results if item.status == "ok")
    total_predicted = sum(item.predicted_components for item in results if item.status == "ok")
    hit_expected = sum(item.matched_expected for item in results if item.status == "ok")
    hit_predicted = sum(item.matched_predicted for item in results if item.status == "ok")
    recall = (hit_expected / total_expected) if total_expected else 0.0
    precision = (hit_predicted / total_predicted) if total_predicted else 0.0
    return GoldEvalReport(
        provider_name=provider_name,
        papers_total=len(manifest.papers),
        evaluated=evaluated,
        missing=missing,
        errors=errors,
        domain_accuracy=domain_accuracy,
        component_precision=precision,
        component_recall=recall,
        results=results,
    )


def format_report(
    report: GoldEvalReport,
    *,
    manifest_path: Path,
    usage: Mapping[str, int] | None = None,
) -> str:
    """Render the report as human-readable lines."""
    lines = [f"gold eval (provider={report.provider_name}, manifest={manifest_path})"]
    for item in report.results:
        if item.status == "missing":
            lines.append(f"[{item.paper_id}] MISSING {item.detail}")
        elif item.status == "error":
            lines.append(f"[{item.paper_id}] ERROR {item.detail}")
        else:
            verdict = "yes" if item.domain_match else "no"
            lines.append(
                f"[{item.paper_id}] ok domain_pred={item.predicted_domain} "
                f"domain_match={verdict} comps_pred={item.predicted_components} "
                f"comps_exp={item.expected_components} "
                f"matched_exp={item.matched_expected} "
                f"matched_pred={item.matched_predicted}"
            )
    lines.append(
        f"papers_total={report.papers_total} evaluated={report.evaluated} "
        f"missing={report.missing} errors={report.errors}"
    )
    lines.append(f"domain_accuracy={report.domain_accuracy:.3f}")
    lines.append(f"component_precision={report.component_precision:.3f}")
    lines.append(f"component_recall={report.component_recall:.3f}")
    if usage is not None and usage.get("live_calls", 0) > 0:
        lines.append(
            f"tokens_input={usage.get('input_tokens', 0)} "
            f"tokens_output={usage.get('output_tokens', 0)} "
            f"live_calls={usage.get('live_calls', 0)}"
        )
    if report.papers_total == 0:
        lines.append("awaiting gold papers: add entries to tests/gold/manifest.json")
        lines.append("  (see tests/gold/README.md; keep PDFs out of git)")
    return "\n".join(lines)


async def run_eval(
    manifest_path: Path,
    *,
    provider: MethodologyProvider,
    provider_name: str,
    repo_root: Path,
    split: str = "all",
    cache_dir: Path | None = None,
    refresh: bool = False,
    usage: dict[str, int] | None = None,
) -> GoldEvalReport:
    """Load the manifest and evaluate the selected split of papers."""
    manifest = load_manifest(manifest_path)
    if split == "dev":
        papers = tuple(paper for paper in manifest.papers if not paper.held_out)
    elif split == "heldout":
        papers = tuple(paper for paper in manifest.papers if paper.held_out)
    elif split == "all":
        papers = manifest.papers
    else:
        raise ValueError(f"Unknown split: {split}")
    manifest = GoldManifest(version=manifest.version, papers=papers)
    results: list[GoldPaperResult] = []
    for paper in manifest.papers:
        results.append(
            await evaluate_paper(
                paper,
                repo_root=repo_root,
                provider=provider,
                provider_name=provider_name,
                cache_dir=cache_dir,
                refresh=refresh,
                usage=usage,
            )
        )
    return summarize(manifest, tuple(results), provider_name=provider_name)


def build_provider(name: str) -> MethodologyProvider:
    """Return the named extraction provider (no secrets printed)."""
    if name == "baseline":
        return BaselineEmptyProvider()
    if name == "baseten":
        from bizora.core.config import get_settings
        from bizora.providers.baseten import BasetenMethodologyProvider

        settings = get_settings()
        if not settings.enable_baseten:
            raise ValueError("Baseten provider is disabled (BIZORA_ENABLE_BASETEN).")
        if not settings.baseten_api_key or not settings.baseten_model_name:
            raise ValueError("Baseten credentials or model configuration are missing.")
        return BasetenMethodologyProvider(
            api_key=settings.baseten_api_key.get_secret_value(),
            model_name=settings.baseten_model_name,
            base_url=settings.baseten_base_url,
        )
    if name == "muse":
        from dotenv import load_dotenv

        from bizora.providers.muse import MuseMethodologyProvider

        load_dotenv(REPO_ROOT / ".env")
        try:
            return MuseMethodologyProvider()
        except ValueError as exc:
            raise ValueError(f"Muse provider unavailable: {exc}") from exc
    raise ValueError(f"Unknown provider: {name}")


def provider_display_name(name: str) -> str:
    """Return the report label for a CLI provider choice."""
    if name == "baseline":
        return BaselineEmptyProvider.provider_name
    return name


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: evaluate the gold manifest and print the report."""
    parser = argparse.ArgumentParser(description="Evaluate extraction on the gold set.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Path to gold manifest JSON (default: tests/gold/manifest.json).",
    )
    parser.add_argument(
        "--provider",
        choices=["baseline", "baseten", "muse"],
        default="baseline",
        help="Extraction provider (default: baseline, offline empty-graph floor).",
    )
    parser.add_argument(
        "--split",
        choices=["all", "dev", "heldout"],
        default="all",
        help="Manifest split to evaluate (default: all).",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Bypass the paper-hash cache and re-run the provider.",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE_DIR,
        help="Draft-graph cache directory (default: tests/gold/.cache).",
    )
    args = parser.parse_args(argv)
    manifest_path: Path = args.manifest
    try:
        provider = build_provider(args.provider)
    except ValueError as exc:
        print(f"gold eval failed: {exc}")
        return 2
    usage: dict[str, int] = {"live_calls": 0, "input_tokens": 0, "output_tokens": 0}
    try:
        report = asyncio.run(
            run_eval(
                manifest_path,
                provider=provider,
                provider_name=provider_display_name(args.provider),
                repo_root=REPO_ROOT,
                split=args.split,
                cache_dir=args.cache_dir,
                refresh=args.refresh,
                usage=usage,
            )
        )
    except ValueError as exc:
        print(f"gold eval failed: {exc}")
        return 2
    print(format_report(report, manifest_path=manifest_path, usage=usage))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
