import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { graphSummariesFixture } from "../../test/fixtures.ts";
import type { GraphSummary } from "../../lib/types.ts";
import { TransplantPanel } from "./TransplantPanel.tsx";
import type { TrayEntry } from "./tray.ts";

const SUMMARIES = graphSummariesFixture as GraphSummary[];
const TRAY: TrayEntry[] = SUMMARIES.map((s) => ({
  project_id: s.project_id,
  graph_id: s.graph_id,
  title: s.title,
}));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("TransplantPanel", () => {
  it("asks for two tray graphs before transplanting", () => {
    render(<TransplantPanel tray={TRAY.slice(0, 1)} summaries={SUMMARIES} />, { wrapper });

    expect(screen.getByText("Add two graphs to the tray to transplant.")).toBeInTheDocument();
  });

  it("moves picked blocks into the target as a new revision", async () => {
    const user = userEvent.setup();
    render(<TransplantPanel tray={TRAY} summaries={SUMMARIES} />, { wrapper });

    await user.selectOptions(screen.getByLabelText("Source graph"), "project-1::graph-1");
    expect(await screen.findByText("Blocks from Vision transformer")).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: /Transformer encoder/ }));
    await user.selectOptions(screen.getByLabelText("Target graph"), "project-2::graph-2");
    await user.click(screen.getByRole("button", { name: "Transplant" }));

    expect(await screen.findByText("Transplant 1 block from graph-1")).toBeInTheDocument();
    expect(screen.getByText(/0 edge\(s\) copied, 1 cut/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "graph-2 v2" })).toHaveAttribute(
      "href",
      "/g/project-2/graph-2",
    );
  });
});
