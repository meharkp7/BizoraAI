import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { useWorkspaceSelection } from "../../lib/store.ts";
import { entitiesFixture, graphFixture } from "../../test/fixtures.ts";
import { server } from "../../test/server.ts";
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
        view="structure" onViewChange={() => {}} onVersionChange={() => {}}
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
        view="structure" onViewChange={() => {}} onVersionChange={onVersionChange}
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
        view="structure" onViewChange={() => {}} onVersionChange={() => {}}
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
        view="structure" onViewChange={() => {}} onVersionChange={() => {}}
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
        view="structure" onViewChange={() => {}} onVersionChange={() => {}}
      />,
      { wrapper },
    );
    const brief = await screen.findByRole("region", { name: "Research brief" });
    expect(within(brief).getByText("Transformers need huge labeled datasets.")).toBeInTheDocument();
    expect(within(brief).getAllByText("Not stated in the paper.")).toHaveLength(1);
  });

  it("offers the three canvas views through the toolbar", async () => {
    const onViewChange = vi.fn();
    render(
      <WorkspacePage
        projectId="project-1"
        graphId="graph-1"
        version={2}
        view="structure" onViewChange={onViewChange} onVersionChange={() => {}}
      />,
      { wrapper },
    );
    await screen.findByRole("heading", { name: "Vision transformer" });
    const toggle = screen.getByRole("group", { name: "Canvas view" });
    for (const name of ["Structure", "Flow", "3D"]) {
      expect(within(toggle).getByRole("button", { name })).toBeInTheDocument();
    }
    await userEvent.click(within(toggle).getByRole("button", { name: "Flow" }));
    expect(onViewChange).toHaveBeenCalledWith("flow");
  });

  it("shows an honest empty state when the flow side is vacant", async () => {
    render(
      <WorkspacePage
        projectId="project-1"
        graphId="graph-1"
        version={2}
        view="flow" onViewChange={() => {}} onVersionChange={() => {}}
      />,
      { wrapper },
    );
    // Fixture entities are all structural, so the process view is empty.
    expect(await screen.findByText("No process or data nodes in this view.")).toBeInTheDocument();
  });

  it("renders the flow subgraph with a symbol key", async () => {
    server.use(
      http.get("/api/v1/graphs/:projectId/:graphId/revisions/:version/entities", () =>
        HttpResponse.json({
          ...entitiesFixture,
          entities: entitiesFixture.entities.map((entity) =>
            entity.node_id === "encoder"
              ? {
                  ...entity,
                  entity_type: "dataloader",
                  category: "process",
                  physical: false,
                  symbol: "dataset",
                }
              : entity,
          ),
        }),
      ),
    );
    render(
      <WorkspacePage
        projectId="project-1"
        graphId="graph-1"
        version={2}
        view="flow" onViewChange={() => {}} onVersionChange={() => {}}
      />,
      { wrapper },
    );
    expect(await screen.findByRole("complementary", { name: "Flow key" })).toBeInTheDocument();
    // Only the non-physical node reaches the flow canvas.
    expect(document.querySelectorAll(".react-flow__node")).toHaveLength(1);
  });

  it("renders schematic and floorplan as structure modes", async () => {
    server.use(
      http.get("/api/v1/graphs/:projectId/:graphId/revisions/:version", () =>
        HttpResponse.json({
          ...graphFixture,
          nodes: graphFixture.nodes.map((node) =>
            node.id === "input" ? { ...node, config: { array: "2x2" } } : node,
          ),
        }),
      ),
    );
    render(
      <WorkspacePage
        projectId="project-1"
        graphId="graph-1"
        version={2}
        view="structure" onViewChange={() => {}} onVersionChange={() => {}}
      />,
      { wrapper },
    );
    await screen.findByRole("heading", { name: "Vision transformer" });
    const modes = screen.getByRole("group", { name: "Structure mode" });
    await userEvent.click(within(modes).getByRole("button", { name: "Schematic" }));
    expect(screen.getByRole("group", { name: "Chip schematic" })).toBeInTheDocument();
    await userEvent.click(within(modes).getByRole("button", { name: "Floorplan" }));
    expect(screen.getByRole("group", { name: "Array floorplan" })).toBeInTheDocument();
  });
});
