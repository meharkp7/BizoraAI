import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { useLibrarySelection, useWorkspaceSelection } from "../../lib/store.ts";
import type { GraphPatch } from "../../lib/types.ts";
import { graphFixture } from "../../test/fixtures.ts";
import { server } from "../../test/server.ts";
import { CopilotPanel } from "./CopilotPanel.tsx";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("CopilotPanel", () => {
  it("answers with library cards that open the library", async () => {
    useWorkspaceSelection.setState({ selectedNodeIds: ["encoder"], selectedEdgeIds: [] });
    useLibrarySelection.setState({ selectedComponentId: null, indexTab: "graph" });
    const user = userEvent.setup();
    render(
      <CopilotPanel
        projectId="project-1"
        graph={graphFixture}
        disabled={false}
        onSubmit={() => {}}
      />,
      { wrapper },
    );

    await user.type(screen.getByLabelText("Copilot message"), "find NPN transistor");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    expect(await screen.findByText(/Closest library matches/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open in library" }));
    expect(useLibrarySelection.getState().selectedComponentId).toBe("npn-2n3904");
    expect(useLibrarySelection.getState().indexTab).toBe("library");
  });

  it("approves a replacement proposal as a patch", async () => {
    useWorkspaceSelection.setState({ selectedNodeIds: ["encoder"], selectedEdgeIds: [] });
    server.use(
      http.post("/api/v1/graphs/:projectId/:graphId/revisions/:version/copilot", () =>
        HttpResponse.json({
          reply: "2N3904 NPN transistor is compatible with Transformer encoder.",
          cards: [
            {
              kind: "proposal",
              title: "Replace Transformer encoder with 2N3904 NPN transistor",
              body: "All known interfaces are preserved.",
              component_ids: ["npn-2n3904"],
              node_id: "encoder",
            },
          ],
          proposal: {
            node_id: "encoder",
            component_id: "npn-2n3904",
            kind: "component",
            label: "2N3904 NPN transistor",
            description: "NPN transistor.",
            config: { part: "2N3904" },
            rationale: "Test proposal.",
          },
        }),
      ),
    );
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(
      <CopilotPanel
        projectId="project-1"
        graph={graphFixture}
        disabled={false}
        onSubmit={onSubmit}
      />,
      { wrapper },
    );

    await user.type(screen.getByLabelText("Copilot message"), "replace encoder with 2N3904");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    expect(await screen.findByText(/is compatible with/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Approve and apply" }));

    expect(onSubmit).toHaveBeenCalledOnce();
    const [[patches]] = onSubmit.mock.calls as [[GraphPatch[]]];
    expect(patches[0].operation).toBe("replace_node");
    expect(patches[0].target_id).toBe("encoder");
  });

  it("approves a config-only proposal as a config patch", async () => {
    useWorkspaceSelection.setState({ selectedNodeIds: ["encoder"], selectedEdgeIds: [] });
    server.use(
      http.post("/api/v1/graphs/:projectId/:graphId/revisions/:version/copilot", () =>
        HttpResponse.json({
          reply: "Ready to set layers.",
          cards: [
            {
              kind: "proposal",
              title: "Set layers on Transformer encoder",
              body: "layers = 24",
              component_ids: [],
              node_id: "encoder",
            },
          ],
          proposal: {
            node_id: "encoder",
            component_id: null,
            kind: "model",
            label: "Transformer encoder",
            description: null,
            config: { layers: 24 },
            rationale: "Test config proposal.",
          },
        }),
      ),
    );
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(
      <CopilotPanel
        projectId="project-1"
        graph={graphFixture}
        disabled={false}
        onSubmit={onSubmit}
      />,
      { wrapper },
    );

    await user.type(screen.getByLabelText("Copilot message"), "set layers to 24");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    expect(await screen.findByText("Ready to set layers.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Approve and apply" }));

    expect(onSubmit).toHaveBeenCalledOnce();
    const [[patches]] = onSubmit.mock.calls as [[GraphPatch[]]];
    expect(patches[0].operation).toBe("update_node_config");
    expect(patches[0].payload["config"]).toEqual({ layers: 24 });
  });
});
