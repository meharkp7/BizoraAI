"""Baseline-to-variant run comparison with compatibility rules."""

from sqlalchemy.orm import Session

from bizora.contracts.comparison import (
    ComparisonVerdict,
    ConfigDifference,
    GraphPair,
    MetricComparison,
    RunComparison,
    SkippedMetric,
)
from bizora.contracts.experiment import ExperimentConfig, ResultKind
from bizora.contracts.run import ExperimentRun, MetricRecord, RunState
from bizora.core.errors import BizoraError, ErrorCode
from bizora.db.repository import (
    experiment_run_from_record,
    get_experiment_run,
    list_metrics_for_run,
    metric_record_from_row,
)

_IDENTITY_FIELDS = frozenset({"experiment_id", "graph_id", "graph_version"})


def _compare_metric(name: str, baseline: float, variant: float) -> MetricComparison:
    """Build one metric comparison with safe relative change."""
    if baseline == 0.0:
        return MetricComparison(
            name=name,
            baseline_value=baseline,
            variant_value=variant,
            absolute_change=variant - baseline,
            relative_change=None,
            relative_undefined_reason="Baseline value is zero.",
        )
    return MetricComparison(
        name=name,
        baseline_value=baseline,
        variant_value=variant,
        absolute_change=variant - baseline,
        relative_change=(variant - baseline) / baseline,
    )


def _config_differences(
    baseline: ExperimentConfig, variant: ExperimentConfig
) -> tuple[ConfigDifference, ...]:
    """Return non-identity configuration fields that differ."""
    baseline_dump = baseline.model_dump(mode="json")
    variant_dump = variant.model_dump(mode="json")
    differences: list[ConfigDifference] = []
    for field in sorted(baseline_dump):
        if field in _IDENTITY_FIELDS:
            continue
        if baseline_dump[field] != variant_dump[field]:
            differences.append(
                ConfigDifference(
                    field=field,
                    baseline=baseline_dump[field],
                    variant=variant_dump[field],
                )
            )
    return tuple(differences)


class ComparisonService:
    """Compare two runs under explicit compatibility rules."""

    @staticmethod
    def _load_run(session: Session, run_id: str) -> ExperimentRun:
        """Load one run or raise when it does not exist."""
        record = get_experiment_run(session, run_id)
        if record is None:
            raise BizoraError(
                ErrorCode.RESOURCE_NOT_FOUND,
                "The experiment run does not exist.",
                details={"run_id": run_id},
            )
        return experiment_run_from_record(record)

    @staticmethod
    def _load_metrics(
        session: Session, run_id: str
    ) -> tuple[dict[str, MetricRecord], frozenset[str]]:
        """Load one run's metrics keyed by name, plus duplicated names.

        Metric ids are unique per run but names are not; a duplicated
        name is ambiguous and must never be silently collapsed into one
        comparison value.
        """
        records = [
            metric_record_from_row(row)
            for row in list_metrics_for_run(session, run_id)
        ]
        by_name: dict[str, MetricRecord] = {}
        duplicates: set[str] = set()
        for record in records:
            if record.name in by_name:
                duplicates.add(record.name)
            by_name[record.name] = record
        return by_name, frozenset(duplicates)

    @staticmethod
    def compare_runs(
        session: Session,
        *,
        baseline_run_id: str,
        variant_run_id: str,
    ) -> RunComparison:
        """Compare a variant run against a baseline run."""
        baseline = ComparisonService._load_run(session, baseline_run_id)
        variant = ComparisonService._load_run(session, variant_run_id)
        baseline_metrics, baseline_dupes = ComparisonService._load_metrics(
            session, baseline_run_id
        )
        variant_metrics, variant_dupes = ComparisonService._load_metrics(
            session, variant_run_id
        )
        ambiguous = baseline_dupes | variant_dupes

        graph = GraphPair(
            baseline_graph_id=baseline.config.graph_id,
            baseline_graph_version=baseline.config.graph_version,
            variant_graph_id=variant.config.graph_id,
            variant_graph_version=variant.config.graph_version,
        )
        differences = _config_differences(baseline.config, variant.config)

        invalid_reasons: list[str] = []
        if baseline.state != RunState.SUCCEEDED:
            invalid_reasons.append(
                f"Baseline run is '{baseline.state.value}', not succeeded."
            )
        if variant.state != RunState.SUCCEEDED:
            invalid_reasons.append(
                f"Variant run is '{variant.state.value}', not succeeded."
            )
        if baseline.config.dataset_id != variant.config.dataset_id:
            invalid_reasons.append(
                "Runs use different datasets "
                f"('{baseline.config.dataset_id}' vs "
                f"'{variant.config.dataset_id}')."
            )

        shared_names = sorted(set(baseline_metrics) & set(variant_metrics))
        measured_names = [
            name
            for name in shared_names
            if name not in ambiguous
            and baseline_metrics[name].result_kind == ResultKind.MEASURED
            and variant_metrics[name].result_kind == ResultKind.MEASURED
        ]
        skipped: list[SkippedMetric] = []
        for name in sorted(set(baseline_metrics) | set(variant_metrics)):
            if name in measured_names:
                continue
            if name in ambiguous:
                skipped.append(
                    SkippedMetric(
                        name=name,
                        reason="Metric name is duplicated within a run; excluded as ambiguous.",
                    )
                )
                continue
            if name not in baseline_metrics:
                skipped.append(
                    SkippedMetric(name=name, reason="Only reported by variant run.")
                )
            elif name not in variant_metrics:
                skipped.append(
                    SkippedMetric(name=name, reason="Only reported by baseline run.")
                )
            else:
                skipped.append(
                    SkippedMetric(
                        name=name,
                        reason="Not measured in both runs.",
                    )
                )

        if not measured_names and not invalid_reasons:
            invalid_reasons.append("Runs share no measured metrics.")

        if invalid_reasons:
            return RunComparison(
                baseline_run_id=baseline_run_id,
                variant_run_id=variant_run_id,
                verdict=ComparisonVerdict.INVALID,
                reasons=tuple(invalid_reasons),
                graph=graph,
                metrics=(),
                skipped_metrics=tuple(skipped),
                config_differences=differences,
            )

        confounded_reasons = [
            f"Configuration field '{difference.field}' differs."
            for difference in differences
        ]
        verdict = (
            ComparisonVerdict.CONFOUNDED
            if confounded_reasons
            else ComparisonVerdict.VALID
        )
        return RunComparison(
            baseline_run_id=baseline_run_id,
            variant_run_id=variant_run_id,
            verdict=verdict,
            reasons=tuple(confounded_reasons),
            graph=graph,
            metrics=tuple(
                _compare_metric(
                    name,
                    baseline_metrics[name].value,
                    variant_metrics[name].value,
                )
                for name in measured_names
            ),
            skipped_metrics=tuple(skipped),
            config_differences=differences,
        )
