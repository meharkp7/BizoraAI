/* Paper-reported number types. Field names mirror the backend JSON
   verbatim; keep in sync with src/bizora/contracts/streaming.py.
   Reported numbers are evidence quotes, never measured data: they
   render in their own column, separate from measured values. */

export interface PaperReportedMetric {
  name: string;
  raw_value: string;
  value: number | null;
  unit: string | null;
  source_id: string;
  table_id: string | null;
  page: number | null;
  quote: string | null;
  locator: string | null;
}

export interface ReportedComparisonRow {
  name: string;
  baseline_measured: number | null;
  variant_measured: number | null;
  reported: PaperReportedMetric[];
}
