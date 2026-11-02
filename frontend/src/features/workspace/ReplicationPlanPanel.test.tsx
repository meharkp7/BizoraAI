import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { server } from "../../test/server.ts";
import { ReplicationPlanPanel } from "./ReplicationPlanPanel.tsx";

const PLAN = {
  project_id: "project-1",
  graph_id: "graph-1",
  version: 2,
  steps: [
    {
      seq: 1,
      node_id: "input",
      label: "Image",
      kind: "input",
      action: "Provide input 'Image' (input).",
      verify: ["Confirm the input format matches the paper's description."],
    },
    {
      seq: 2,
      node_id: "vit",
      label: "ViT backbone",
      kind: "model",
      action: "Build model 'ViT backbone' (vit).",
      verify: ["Confirm parameter counts match the reported architecture."],
    },
  ],
};

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("ReplicationPlanPanel", () => {
  beforeEach(() => {
    window.localStorage.clear();
    server.use(
      http.get("/api/v1/projects/:projectId/graphs/:graphId/replication-plan", () =>
        HttpResponse.json(PLAN),
      ),
    );
  });

  it("lists ordered steps with verify hints", async () => {
    render(<ReplicationPlanPanel projectId="project-1" graphId="graph-1" />, { wrapper });

    expect(await screen.findByText(/0 of 2 steps done/)).toBeInTheDocument();
    expect(screen.getByText(/Provide input 'Image'/)).toBeInTheDocument();
    expect(screen.getByText(/Build model 'ViT backbone'/)).toBeInTheDocument();
    expect(
      screen.getByText("Confirm parameter counts match the reported architecture."),
    ).toBeInTheDocument();
  });

  it("persists checkmarks per graph revision", async () => {
    const { unmount } = render(
      <ReplicationPlanPanel projectId="project-1" graphId="graph-1" />,
      { wrapper },
    );
    const first = await screen.findByRole("checkbox", { name: "Step 1: Image" });
    first.click();
    expect(await screen.findByText(/1 of 2 steps done/)).toBeInTheDocument();
    unmount();

    render(<ReplicationPlanPanel projectId="project-1" graphId="graph-1" />, { wrapper });
    expect(await screen.findByText(/1 of 2 steps done/)).toBeInTheDocument();
    expect(await screen.findByRole("checkbox", { name: "Step 1: Image" })).toBeChecked();
  });

  it("says plainly when the plan is unavailable", async () => {
    server.use(
      http.get("/api/v1/projects/:projectId/graphs/:graphId/replication-plan", () =>
        HttpResponse.json(
          { error: { code: "RESOURCE_NOT_FOUND", message: "Graph not found." } },
          { status: 404 },
        ),
      ),
    );
    render(<ReplicationPlanPanel projectId="nope" graphId="nope" />, { wrapper });

    expect(
      await screen.findByText("The replication plan is unavailable for this graph."),
    ).toBeInTheDocument();
  });

  it("points at the agent instead of a narrate button", async () => {
    render(<ReplicationPlanPanel projectId="project-1" graphId="graph-1" />, { wrapper });

    expect(await screen.findByText(/0 of 2 steps done/)).toBeInTheDocument();
    expect(
      screen.getByText(/Talk through this build hands-free/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Narrate build" })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Stop narration" }),
    ).not.toBeInTheDocument();
  });
});
