import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { useWorkspaceSelection } from "../../lib/store.ts";
import { server } from "../../test/server.ts";
import { DiagramFallback } from "./DiagramFallback.tsx";

const nodeLabels = new Map([
  ["input", "Image"],
  ["encoder", "Transformer encoder"],
]);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("DiagramFallback", () => {
  it("shows the reason with the paper's own figure and clickable overlays", async () => {
    useWorkspaceSelection.setState({ selectedNodeIds: [], selectedEdgeIds: [] });
    const user = userEvent.setup();
    render(
      <DiagramFallback
        viewLabel="Methodology"
        reason="too little structure to draw a flow diagram"
        sourceFigureId="paper-1-p2-f1-a1b2c3d4"
        projectId="project-1"
        graphId="graph-1"
        nodeLabels={nodeLabels}
      />,
      { wrapper },
    );
    expect(
      await screen.findByText(/too little structure to draw a flow diagram/),
    ).toBeInTheDocument();
    // The paper's own figure with a linked region overlay.
    expect(await screen.findByAltText("Model overview.")).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Region encoder stack, linked to Transformer encoder" }),
    );
    expect(useWorkspaceSelection.getState().selectedNodeIds).toEqual(["encoder"]);
  });

  it("stays honest when the paper has no figures yet", async () => {
    server.use(
      http.get("/api/v1/graphs/:projectId/:graphId/figures", () => HttpResponse.json([])),
    );
    render(
      <DiagramFallback
        viewLabel="Schematic"
        reason="no circuit diagram was extracted from this paper's figures."
        sourceFigureId={null}
        projectId="project-1"
        graphId="graph-1"
        nodeLabels={nodeLabels}
      />,
      { wrapper },
    );
    expect(await screen.findByText(/no circuit diagram was extracted/)).toBeInTheDocument();
    expect(await screen.findByText(/No figures were ingested/)).toBeInTheDocument();
    expect(document.querySelector("svg")).toBeNull();
  });
});
