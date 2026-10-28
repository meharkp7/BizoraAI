/* Client-side measured-vs-reported join. Mirrors
   src/bizora/streaming/comparison_view.py: exact (case-sensitive)
   name matching over the sorted union of measured and reported
   names. Metric names are free text (Rule Zero), never a vocabulary. */

import type { RunComparison } from "../../lib/types.ts";
import type { PaperReportedMetric, ReportedComparisonRow } from "./reportedTypes.ts";

/** Join measured pairs with paper-reported entries by exact name. */
export function buildReportedRows(
  comparison: RunComparison,
  reported: readonly PaperReportedMetric[],
): ReportedComparisonRow[] {
  const measured = new Map<string, { baseline: number; variant: number }>();
  for (const metric of comparison.metrics) {
    measured.set(metric.name, {
      baseline: metric.baseline_value,
      variant: metric.variant_value,
    });
  }
  const byName = new Map<string, PaperReportedMetric[]>();
  for (const entry of reported) {
    const group = byName.get(entry.name) ?? [];
    group.push(entry);
    byName.set(entry.name, group);
  }
  const names = [...new Set([...measured.keys(), ...byName.keys()])].sort();
  return names.map((name) => {
    const pair = measured.get(name);
    return {
      name,
      baseline_measured: pair?.baseline ?? null,
      variant_measured: pair?.variant ?? null,
      reported: byName.get(name) ?? [],
    };
  });
}

/** Short evidence citation for one reported entry. */
export function formatReportedSource(entry: PaperReportedMetric): string {
  const parts: string[] = [];
  if (entry.table_id !== null) parts.push(entry.table_id);
  if (entry.page !== null) parts.push(`p.${entry.page}`);
  if (entry.locator !== null) parts.push(entry.locator);
  if (parts.length === 0) parts.push(entry.source_id);
  return parts.join(", ");
}
