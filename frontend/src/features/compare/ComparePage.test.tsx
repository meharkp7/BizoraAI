import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { server } from "../../test/server.ts";
import { ComparePage } from "./ComparePage.tsx";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function submitComparison(): void {
  fireEvent.change(screen.getByLabelText("Baseline run ID"), {
    target: { value: "run-ok" },
  });
  fireEvent.change(screen.getByLabelText("Variant run ID"), {
    target: { value: "run-bad" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Compare" }));
}

describe("ComparePage", () => {
  it("shows measured values beside quoted paper numbers", async () => {
    render(<ComparePage />, { wrapper });
    submitComparison();

    expect(await screen.findByText("Measured vs paper-reported")).toBeInTheDocument();
    // The reported query runs after the comparison resolves, so allow
    // the cascade to settle.
    expect(await screen.findByText("0.89", {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByText("(table-1, p.4)")).toBeInTheDocument();
  });

  it("explains when no paper numbers are linked", async () => {
    server.use(
      http.get("/api/v1/experiments/runs/:runId/reported-metrics", () =>
        HttpResponse.json([]),
      ),
    );
    render(<ComparePage />, { wrapper });
    submitComparison();

    expect(await screen.findByText("Measured vs paper-reported")).toBeInTheDocument();
    expect(
      screen.getByText("No paper-reported numbers linked yet."),
    ).toBeInTheDocument();
  });
});
