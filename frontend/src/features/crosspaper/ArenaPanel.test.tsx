import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { ArenaPanel } from "./ArenaPanel.tsx";
import type { TrayEntry } from "./tray.ts";

const TRAY: TrayEntry[] = [
  { project_id: "project-1", graph_id: "graph-1", title: "Vision transformer" },
  { project_id: "project-2", graph_id: "graph-2", title: "SRAM PUF" },
];

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("ArenaPanel", () => {
  it("asks for two tray graphs before comparing", () => {
    render(<ArenaPanel tray={TRAY.slice(0, 1)} />, { wrapper });

    expect(screen.getByText("Add two graphs to the tray to compare them.")).toBeInTheDocument();
  });

  it("compares two sides head-to-head", async () => {
    const user = userEvent.setup();
    render(<ArenaPanel tray={TRAY} />, { wrapper });

    await user.selectOptions(screen.getByLabelText("Side A"), "project-1::graph-1");
    await user.selectOptions(screen.getByLabelText("Side B"), "project-2::graph-2");
    await user.click(screen.getByRole("button", { name: "Compare" }));

    expect(
      await screen.findByText("Structure: Vision transformer vs SRAM PUF"),
    ).toBeInTheDocument();
    expect(screen.getByText("Transformer encoder")).toBeInTheDocument();
    expect(screen.getByText("Ours — Accuracy")).toBeInTheDocument();
    expect(screen.getByText("92%")).toBeInTheDocument();
    expect(screen.getByText("0.88")).toBeInTheDocument();
  });

  it("refuses to compare a side with itself", async () => {
    const user = userEvent.setup();
    render(<ArenaPanel tray={TRAY} />, { wrapper });

    await user.selectOptions(screen.getByLabelText("Side A"), "project-1::graph-1");
    await user.selectOptions(screen.getByLabelText("Side B"), "project-1::graph-1");

    expect(screen.getByRole("button", { name: "Compare" })).toBeDisabled();
  });
});
