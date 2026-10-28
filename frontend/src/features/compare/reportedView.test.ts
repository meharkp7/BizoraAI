import { describe, expect, it } from "vitest";
import type { RunComparison } from "../../lib/types.ts";
import { comparisonFixture } from "../../test/fixtures.ts";
import type { PaperReportedMetric } from "./reportedTypes.ts";
import { buildReportedRows, formatReportedSource } from "./reportedView.ts";

function reported(name: string, rawValue: string): PaperReportedMetric {
  return {
    name,
    raw_value: rawValue,
    value: null,
    unit: null,
    source_id: "paper-1",
    table_id: "table-1",
    page: 4,
    quote: null,
    locator: null,
  };
}

describe("buildReportedRows", () => {
  it("joins measured pairs with reported entries by exact name", () => {
    const rows = buildReportedRows(comparisonFixture, [reported("accuracy", "91%")]);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      name: "accuracy",
      baseline_measured: 0.9,
      variant_measured: 0.92,
    });
    expect(rows[0]?.reported).toHaveLength(1);
  });

  it("covers reported-only names with empty measured sides", () => {
    const rows = buildReportedRows(comparisonFixture, [reported("latency", "3ms")]);
    expect(rows.map((row) => row.name)).toEqual(["accuracy", "latency"]);
    expect(rows[1]).toMatchObject({ baseline_measured: null, variant_measured: null });
  });

  it("never merges differently-cased names", () => {
    const rows = buildReportedRows(comparisonFixture, [reported("Accuracy", "91%")]);
    expect(rows.map((row) => row.name)).toEqual(["Accuracy", "accuracy"]);
  });

  it("handles comparisons with no measured metrics", () => {
    const empty: RunComparison = { ...comparisonFixture, metrics: [] };
    const rows = buildReportedRows(empty, [reported("accuracy", "91%")]);
    expect(rows).toHaveLength(1);
    expect(rows[0]?.baseline_measured).toBeNull();
  });
});

describe("formatReportedSource", () => {
  it("prefers table and page citations", () => {
    expect(formatReportedSource(reported("accuracy", "91%"))).toBe("table-1, p.4");
    const bare: PaperReportedMetric = {
      ...reported("accuracy", "91%"),
      table_id: null,
      page: null,
      locator: null,
    };
    expect(formatReportedSource(bare)).toBe("paper-1");
  });

  it("keeps the short form when a locator is present", () => {
    const located: PaperReportedMetric = {
      ...reported("accuracy", "91%"),
      locator: "Table table-1: column 'Accuracy' row 1",
    };
    expect(formatReportedSource(located)).toBe("table-1, p.4");
    const locatorOnly: PaperReportedMetric = {
      ...located,
      table_id: null,
      page: null,
    };
    expect(formatReportedSource(locatorOnly)).toBe(
      "Table table-1: column 'Accuracy' row 1",
    );
  });
});
