/* Paper-reported number types. Reported numbers are evidence quotes,
   never measured data: they render in their own column, separate from
   measured values. */

import type { PaperReportedMetric } from "../../lib/types.ts";

export type { PaperReportedMetric };

export interface ReportedComparisonRow {
  name: string;
  baseline_measured: number | null;
  variant_measured: number | null;
  reported: PaperReportedMetric[];
}
