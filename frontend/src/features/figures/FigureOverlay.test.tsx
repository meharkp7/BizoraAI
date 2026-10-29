import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { useWorkspaceSelection } from "../../lib/store.ts";
import { figuresFixture, graphFixture } from "../../test/fixtures.ts";
import { server } from "../../test/server.ts";
import { FigureOverlay } from "./FigureOverlay.tsx";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const nodeLabels = new Map(graphFixture.nodes.map((node) => [node.id, node.label]));

function renderOverlay() {
  return render(
    <FigureOverlay
      projectId="project-1"
      graphId="graph-1"
      version={2}
      nodeLabels={nodeLabels}
    />,
    { wrapper },
  );
}

beforeEach(() => {
  useWorkspaceSelection.setState({ selectedNodeIds: [], selectedEdgeIds: [] });
});

describe("FigureOverlay", () => {
  it("opens the viewer and links regions to graph nodes", async () => {
    const { container } = renderOverlay();

    await userEvent.click(await screen.findByRole("button", { name: "Paper figures (1)" }));
    const dialog = screen.getByRole("dialog", { name: "Paper figure overlay" });
    expect(within(dialog).getByRole("tab", { name: "Figure 1" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(within(dialog).getByText(/1 of 2 regions linked/)).toBeInTheDocument();
    const image = within(dialog).getByRole("img", { name: "Model overview." });
    expect(image.getAttribute("src")).toContain("/figures/paper-1-p2-f1-a1b2c3d4/image");

    const region = container.querySelector(
      '[data-region-id="paper-1-p2-f1-a1b2c3d4-r1"]',
    ) as HTMLElement;
    expect(region.getAttribute("data-node-id")).toBe("encoder");
    fireEvent.click(region);
    expect(useWorkspaceSelection.getState().selectedNodeIds).toEqual(["encoder"]);

    fireEvent.click(within(dialog).getByRole("button", { name: "Transformer encoder" }));
    expect(useWorkspaceSelection.getState().selectedNodeIds).toEqual(["encoder"]);
  });

  it("marks unlinked regions honestly", async () => {
    const { container } = renderOverlay();

    await userEvent.click(await screen.findByRole("button", { name: "Paper figures (1)" }));
    const dialog = screen.getByRole("dialog", { name: "Paper figure overlay" });
    expect(within(dialog).getByText("unlinked")).toBeInTheDocument();
    const unlinked = container.querySelector(
      '[data-region-id="paper-1-p2-f1-a1b2c3d4-r2"]',
    ) as HTMLElement;
    expect(unlinked.tagName).toBe("SPAN");
    expect(unlinked.title).toContain("depicts no graph node");
  });

  it("offers an ingest when no figures exist", async () => {
    server.use(
      http.get("/api/v1/graphs/:projectId/:graphId/figures", () =>
        HttpResponse.json([]),
      ),
      http.post(
        "/api/v1/graphs/:projectId/:graphId/revisions/:version/figures",
        () =>
          HttpResponse.json(
            { figures: figuresFixture, warnings: ["Figure kept as unknown."], truncated: false, skipped: 0 },
            { status: 201 },
          ),
      ),
    );
    renderOverlay();

    await userEvent.click(await screen.findByRole("button", { name: "Paper figures (0)" }));
    const dialog = screen.getByRole("dialog", { name: "Paper figure overlay" });
    const file = new File(["%PDF-1.4 fake"], "paper.pdf", { type: "application/pdf" });
    const input = within(dialog).getByLabelText("Paper PDF") as HTMLInputElement;
    await userEvent.upload(input, file);
    await userEvent.click(within(dialog).getByRole("button", { name: "Locate figures" }));
    expect(await within(dialog).findByText(/Ingested 1 figure/)).toBeInTheDocument();
    expect(within(dialog).getByText("Figure kept as unknown.")).toBeInTheDocument();
  });

  it("numbers untitled figures instead of showing raw ids", async () => {
    server.use(
      http.get("/api/v1/graphs/:projectId/:graphId/figures", () =>
        HttpResponse.json([
          { ...figuresFixture[0], label: null },
          { ...figuresFixture[0], figure_id: "other-id", label: null },
        ]),
      ),
    );
    renderOverlay();

    await userEvent.click(await screen.findByRole("button", { name: "Paper figures (2)" }));
    const dialog = screen.getByRole("dialog", { name: "Paper figure overlay" });
    expect(within(dialog).getByRole("tab", { name: "Untitled 1" })).toBeInTheDocument();
    expect(within(dialog).getByRole("tab", { name: "Untitled 2" })).toBeInTheDocument();
  });

  it("requires a PDF before ingesting", async () => {
    server.use(
      http.get("/api/v1/graphs/:projectId/:graphId/figures", () =>
        HttpResponse.json([]),
      ),
    );
    renderOverlay();

    await userEvent.click(await screen.findByRole("button", { name: "Paper figures (0)" }));
    const dialog = screen.getByRole("dialog", { name: "Paper figure overlay" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Locate figures" }));
    expect(within(dialog).getByText("Choose the paper PDF first.")).toBeInTheDocument();
  });
});
