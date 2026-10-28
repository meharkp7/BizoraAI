import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { comparisonFixture } from "../../test/fixtures.ts";
import { MeasuredVsReportedTable } from "./MeasuredVsReportedTable.tsx";
import type { PaperReportedMetric } from "./reportedTypes.ts";

/** Clearly-marked fake: paper-quoted numbers with evidence pointers. */
const fakeReported: PaperReportedMetric[] = [
  {
    name: "accuracy",
    raw_value: "91%",
    value: 0.91,
    unit: null,
    source_id: "paper-1",
    table_id: "table-1",
    page: 4,
    quote: "Our model reaches 91% accuracy.",
    locator: null,
  },
  {
    name: "latency",
    raw_value: "3ms",
    value: null,
    unit: null,
    source_id: "paper-1",
    table_id: "table-2",
    page: 5,
    quote: null,
    locator: null,
  },
];

describe("MeasuredVsReportedTable", () => {
  it("keeps measured and paper-reported numbers in separate columns", () => {
    render(<MeasuredVsReportedTable comparison={comparisonFixture} reported={fakeReported} />);
    const accuracyRow = screen.getByText("accuracy").closest("tr");
    expect(accuracyRow?.textContent).toContain("0.9");
    expect(accuracyRow?.textContent).toContain("0.92");
    expect(accuracyRow?.textContent).toContain("91%");
    expect(accuracyRow?.textContent).toContain("table-1, p.4");
    expect(screen.getByText("latency")).toBeInTheDocument();
    // Comparability with the paper is assumed, never asserted.
    expect(screen.getByText("Assumed")).toBeInTheDocument();
    expect(screen.getAllByText("Measured").length).toBeGreaterThan(0);
  });

  it("shows an empty hint when nothing is reported", () => {
    render(<MeasuredVsReportedTable comparison={comparisonFixture} reported={[]} />);
    expect(screen.getByText("No paper-reported numbers linked yet.")).toBeInTheDocument();
  });
});
