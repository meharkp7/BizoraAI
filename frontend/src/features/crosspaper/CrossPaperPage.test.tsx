import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import { CrossPaperPage } from "./CrossPaperPage.tsx";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("CrossPaperPage", () => {
  afterEach(() => {
    window.localStorage.clear();
  });

  it("collects graphs into a persisted tray", async () => {
    const user = userEvent.setup();
    render(<CrossPaperPage />, { wrapper });

    const graphs = await screen.findByRole("region", { name: "Graphs" });
    expect(within(graphs).getByText("Vision transformer")).toBeInTheDocument();
    expect(within(graphs).getByText(/2 nodes/)).toBeInTheDocument();

    const addButtons = await within(graphs).findAllByRole("button", { name: "Add to tray" });
    await user.click(addButtons[0]!);

    const tray = screen.getByRole("region", { name: "Tray" });
    expect(await within(tray).findByText("Vision transformer")).toBeInTheDocument();
    expect(
      JSON.parse(window.localStorage.getItem("bizora.crosspaper.tray") ?? "[]"),
    ).toEqual([{ project_id: "project-1", graph_id: "graph-1", title: "Vision transformer" }]);

    await user.click(within(tray).getByRole("button", { name: "Remove" }));
    expect(within(tray).queryByText("Vision transformer")).not.toBeInTheDocument();
  });

  it("restores the tray across visits", async () => {
    window.localStorage.setItem(
      "bizora.crosspaper.tray",
      JSON.stringify([{ project_id: "project-2", graph_id: "graph-2", title: "SRAM PUF" }]),
    );
    render(<CrossPaperPage />, { wrapper });

    const tray = await screen.findByRole("region", { name: "Tray" });
    expect(await within(tray).findByText("SRAM PUF")).toBeInTheDocument();
    expect(within(tray).getByRole("link", { name: "SRAM PUF" })).toHaveAttribute(
      "href",
      "/g/project-2/graph-2",
    );
  });
});
