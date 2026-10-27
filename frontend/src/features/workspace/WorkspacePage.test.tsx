import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { useWorkspaceSelection } from "../../lib/store.ts";
import { WorkspacePage } from "./WorkspacePage.tsx";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("WorkspacePage", () => {
  it("loads a revision and inspects a selected node with evidence", async () => {
    useWorkspaceSelection.setState({ selectedNodeIds: [], selectedEdgeIds: [] });
    render(
      <WorkspacePage
        projectId="project-1"
        graphId="graph-1"
        version={2}
        onVersionChange={() => {}}
      />,
      { wrapper },
    );

    expect(await screen.findByRole("heading", { name: "Vision transformer" })).toBeInTheDocument();
    expect(screen.getByText(/revision 2/)).toBeInTheDocument();

    const nodes = screen.getByRole("list", { name: "Graph nodes" });
    await userEvent.click(within(nodes).getByRole("button", { name: /Transformer encoder/ }));

    const inspector = screen.getByRole("region", { name: "Inspector" });
    expect(within(inspector).getByText("Transformer encoder")).toBeInTheDocument();
    const evidence = screen.getByRole("region", { name: "Evidence" });
    expect(
      await within(evidence).findByText("The encoder stacks twelve blocks."),
    ).toBeInTheDocument();
  });

  it("steps between revisions", async () => {
    const onVersionChange = vi.fn();
    render(
      <WorkspacePage
        projectId="project-1"
        graphId="graph-1"
        version={2}
        onVersionChange={onVersionChange}
      />,
      { wrapper },
    );
    await screen.findByRole("heading", { name: "Vision transformer" });
    await userEvent.click(screen.getByRole("button", { name: "Newer →" }));
    expect(onVersionChange).toHaveBeenCalledWith(3);
    await userEvent.click(screen.getByRole("button", { name: "← Older" }));
    expect(onVersionChange).toHaveBeenCalledWith(1);
  });

  it("reports a missing revision with recovery", async () => {
    render(
      <WorkspacePage
        projectId="project-1"
        graphId="graph-1"
        version={9}
        onVersionChange={() => {}}
      />,
      { wrapper },
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("Revision 9 does not exist.");
  });

  it("renders the revision diff", async () => {
    render(
      <WorkspacePage
        projectId="project-1"
        graphId="graph-1"
        version={2}
        onVersionChange={() => {}}
      />,
      { wrapper },
    );
    const diff = await screen.findByRole("region", { name: "Revision comparison" });
    expect(await within(diff).findByText(/Changed components \(1\)/)).toBeInTheDocument();
  });

  it("renders the research brief with explicit unknowns", async () => {
    useWorkspaceSelection.setState({ selectedNodeIds: [], selectedEdgeIds: [] });
    render(
      <WorkspacePage
        projectId="project-1"
        graphId="graph-1"
        version={2}
        onVersionChange={() => {}}
      />,
      { wrapper },
    );
    const brief = await screen.findByRole("region", { name: "Research brief" });
    expect(within(brief).getByText("Transformers need huge labeled datasets.")).toBeInTheDocument();
    expect(within(brief).getAllByText("Not stated in the paper.")).toHaveLength(1);
  });
});
