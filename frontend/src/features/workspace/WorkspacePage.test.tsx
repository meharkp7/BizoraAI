import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { useWorkspaceSelection } from "../../lib/store.ts";
import { graphFixture, thinDiagramsFixture } from "../../test/fixtures.ts";
import { server } from "../../test/server.ts";
import { WorkspacePage } from "./WorkspacePage.tsx";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter>
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </MemoryRouter>
  );
}

describe("WorkspacePage", () => {
  it("loads a revision and inspects a selected node with evidence", async () => {
    useWorkspaceSelection.setState({ selectedNodeIds: [], selectedEdgeIds: [] });
    render(
      <WorkspacePage
        projectId="project-1"
        graphId="graph-1"
        version={2}
        view="methodology" onViewChange={() => {}} onVersionChange={() => {}}
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
        view="methodology" onViewChange={() => {}} onVersionChange={onVersionChange}
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
        view="methodology" onViewChange={() => {}} onVersionChange={() => {}}
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
        view="methodology" onViewChange={() => {}} onVersionChange={() => {}}
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
        view="methodology" onViewChange={() => {}} onVersionChange={() => {}}
      />,
      { wrapper },
    );
    const brief = await screen.findByRole("region", { name: "Research brief" });
    expect(within(brief).getByText("Transformers need huge labeled datasets.")).toBeInTheDocument();
    expect(within(brief).getAllByText("Not stated in the paper.")).toHaveLength(1);
  });

  it("offers the three diagram views through the toolbar", async () => {
    const onViewChange = vi.fn();
    render(
      <WorkspacePage
        projectId="project-1"
        graphId="graph-1"
        version={2}
        view="methodology" onViewChange={onViewChange} onVersionChange={() => {}}
      />,
      { wrapper },
    );
    await screen.findByRole("heading", { name: "Vision transformer" });
    const toggle = screen.getByRole("group", { name: "Canvas view" });
    for (const name of ["Methodology", "Schematic", "3D"]) {
      expect(within(toggle).getByRole("button", { name })).toBeInTheDocument();
    }
    await userEvent.click(within(toggle).getByRole("button", { name: "Schematic" }));
    expect(onViewChange).toHaveBeenCalledWith("schematic");
  });

  it("renders methodology from the diagrams endpoint and inspects a clicked node", async () => {
    useWorkspaceSelection.setState({ selectedNodeIds: [], selectedEdgeIds: [] });
    render(
      <WorkspacePage
        projectId="project-1"
        graphId="graph-1"
        version={2}
        view="methodology" onViewChange={() => {}} onVersionChange={() => {}}
      />,
      { wrapper },
    );
    const canvas = await screen.findByRole("group", { name: "Methodology diagram" });
    expect(canvas.querySelectorAll("[data-node-id]")).toHaveLength(4);
    const node = canvas.querySelector('[data-node-id="m-encode"]');
    if (!node) throw new Error("engine must stamp data-node-id");
    fireEvent.click(node);
    const inspector = screen.getByRole("region", { name: "Inspector" });
    expect(await within(inspector).findByText(/The encoder stacks twelve blocks\./)).toBeInTheDocument();
  });

  it("renders the schematic tab from the diagrams endpoint", async () => {
    render(
      <WorkspacePage
        projectId="project-1"
        graphId="graph-1"
        version={2}
        view="schematic" onViewChange={() => {}} onVersionChange={() => {}}
      />,
      { wrapper },
    );
    const canvas = await screen.findByRole("group", { name: "Schematic diagram" });
    expect(canvas.querySelectorAll("[data-id]")).toHaveLength(3);
  });

  it("renders the 3D tab with an honest WebGL verdict", async () => {
    render(
      <WorkspacePage
        projectId="project-1"
        graphId="graph-1"
        version={2}
        view="3d" onViewChange={() => {}} onVersionChange={() => {}}
      />,
      { wrapper },
    );
    // Opens on the circuit build; jsdom has no WebGL, so the view
    // says so instead of drawing a stand-in.
    expect(await screen.findByRole("heading", { name: "Test cell" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("3D needs WebGL");
  });

  it("falls back to the paper figure on every tab when no IRs were extracted", async () => {
    server.use(
      http.get("/api/v1/papers/:paperId/diagrams", () => HttpResponse.json(thinDiagramsFixture)),
    );
    render(
      <WorkspacePage
        projectId="project-1"
        graphId="graph-1"
        version={2}
        view="schematic" onViewChange={() => {}} onVersionChange={() => {}}
      />,
      { wrapper },
    );
    expect(await screen.findByText(/the paper's figures yielded nothing suitable/)).toBeInTheDocument();
    expect(await screen.findByAltText("Model overview.")).toBeInTheDocument();
    // No diagram drawn (scoped to the diagram group: page chrome like
    // the copilot bot legitimately carries its own SVG).
    expect(screen.queryByRole("group", { name: "Schematic diagram" })).toBeNull();
  });

  it("explains a paper with no diagrams instead of erroring", async () => {
    server.use(
      http.get("/api/v1/papers/:paperId/diagrams", () =>
        HttpResponse.json(
          { error: { code: "RESOURCE_NOT_FOUND", message: "Paper not found.", details: {} } },
          { status: 404 },
        ),
      ),
    );
    render(
      <WorkspacePage
        projectId="project-1"
        graphId="graph-1"
        version={2}
        view="methodology" onViewChange={() => {}} onVersionChange={() => {}}
      />,
      { wrapper },
    );
    expect(await screen.findByText("No diagrams for this paper yet.")).toBeInTheDocument();
  });

  it("explains a graph with no linked paper", async () => {
    server.use(
      http.get("/api/v1/graphs/:projectId/:graphId/revisions/:version", () =>
        HttpResponse.json({ ...graphFixture, source_ids: [] }),
      ),
    );
    render(
      <WorkspacePage
        projectId="project-1"
        graphId="graph-1"
        version={2}
        view="methodology" onViewChange={() => {}} onVersionChange={() => {}}
      />,
      { wrapper },
    );
    expect(await screen.findByText("This graph is not linked to a paper.")).toBeInTheDocument();
  });
});
