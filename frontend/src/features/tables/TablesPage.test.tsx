import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { TablesPage } from "./TablesPage.tsx";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("TablesPage", () => {
  it("lists tables and renders the selected one", async () => {
    render(<TablesPage projectId="project-1" graphId="graph-1" />, { wrapper });

    expect(await screen.findByRole("heading", { name: "Results tables" })).toBeInTheDocument();
    const index = screen.getByRole("navigation", { name: "Tables" });
    expect(within(index).getByRole("button", { name: /table-1/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("columnheader", { name: "TM-score" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "AlphaFold2" })).toBeInTheDocument();
    expect(screen.getByText("p. 4")).toBeInTheDocument();
    expect(screen.getByText("Table 1 reports TM-scores on CASP14 targets.")).toBeInTheDocument();

    await userEvent.click(within(index).getByRole("button", { name: /table-2/ }));
    expect(screen.getByRole("columnheader", { name: "RMSD" })).toBeInTheDocument();
    expect(screen.queryByRole("cell", { name: "AlphaFold2" })).not.toBeInTheDocument();
  });

  it("shows an empty state when the graph has no tables", async () => {
    render(<TablesPage projectId="project-1" graphId="other" />, { wrapper });

    expect(await screen.findByText("No results tables.")).toBeInTheDocument();
  });
});
