import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { GraphPatch } from "../../lib/types.ts";
import { server } from "../../test/server.ts";
import { useScenarioDrafts } from "./drafts.ts";
import { ScenarioDrafts } from "./ScenarioDrafts.tsx";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function makePatch(patchId: string): GraphPatch {
  return {
    patch_id: patchId,
    base_graph_id: "graph-1",
    base_version: 2,
    operation: "update_node_config",
    target_id: "encoder",
    payload: { config: { layers: 6 } },
    rationale: "Update encoder configuration",
    requested_by: "workspace-ui",
  };
}

function seedDraft(patches: GraphPatch[] = [makePatch("p1")]) {
  const draft = useScenarioDrafts.getState().createDraft({
    name: "Scenario 1",
    projectId: "project-1",
    graphId: "graph-1",
    baseVersion: 2,
    baseTitle: "Vision transformer",
  });
  if (patches.length > 0) useScenarioDrafts.getState().stagePatches(draft.id, patches);
  return draft;
}

describe("ScenarioDrafts", () => {
  beforeEach(() => {
    useScenarioDrafts.getState().reset();
  });

  it("creates a draft from the current version and stages into it", async () => {
    const user = userEvent.setup();
    render(
      <ScenarioDrafts
        projectId="project-1"
        graphId="graph-1"
        currentVersion={2}
        currentTitle="Vision transformer"
        onPromoted={vi.fn()}
      />,
      { wrapper },
    );

    await user.type(screen.getByLabelText("Draft name"), "Fewer layers");
    await user.click(screen.getByRole("button", { name: "Draft from v2" }));

    const panel = screen.getByRole("region", { name: "Scenario drafts" });
    expect(within(panel).getByText("Fewer layers")).toBeInTheDocument();
    expect(within(panel).getByText("staging here")).toBeInTheDocument();
    expect(within(panel).getByText(/base v2/)).toBeInTheDocument();
  });

  it("lists staged ops and removes one", async () => {
    const user = userEvent.setup();
    seedDraft();
    render(
      <ScenarioDrafts
        projectId="project-1"
        graphId="graph-1"
        currentVersion={2}
        currentTitle="Vision transformer"
        onPromoted={vi.fn()}
      />,
      { wrapper },
    );

    const panel = screen.getByRole("region", { name: "Scenario drafts" });
    expect(
      within(panel).getByText("Update encoder configuration (encoder)"),
    ).toBeInTheDocument();

    await user.click(
      within(panel).getByRole("button", { name: "Remove Update encoder configuration" }),
    );
    expect(
      within(panel).queryByText("Update encoder configuration (encoder)"),
    ).not.toBeInTheDocument();
  });

  it("promotes staged ops to one new revision", async () => {
    const user = userEvent.setup();
    const onPromoted = vi.fn();
    seedDraft();
    render(
      <ScenarioDrafts
        projectId="project-1"
        graphId="graph-1"
        currentVersion={2}
        currentTitle="Vision transformer"
        onPromoted={onPromoted}
      />,
      { wrapper },
    );

    await user.click(
      screen.getByRole("button", { name: "Promote to revision" }),
    );

    expect(onPromoted).toHaveBeenCalledWith(3);
    expect(useScenarioDrafts.getState().drafts).toEqual([]);
  });

  it("disables promote for an empty draft", async () => {
    seedDraft([]);
    render(
      <ScenarioDrafts
        projectId="project-1"
        graphId="graph-1"
        currentVersion={2}
        currentTitle="Vision transformer"
        onPromoted={vi.fn()}
      />,
      { wrapper },
    );

    expect(screen.getByRole("button", { name: "Promote to revision" })).toBeDisabled();
  });

  it("explains a stale base in plain words", async () => {
    server.use(
      http.post("/api/v1/graphs/:projectId/:graphId/patches", () =>
        HttpResponse.json(
          {
            error: {
              code: "RESOURCE_CONFLICT",
              message: "The supplied graph is stale.",
              details: {},
            },
          },
          { status: 409 },
        ),
      ),
    );
    const user = userEvent.setup();
    seedDraft();
    render(
      <ScenarioDrafts
        projectId="project-1"
        graphId="graph-1"
        currentVersion={2}
        currentTitle="Vision transformer"
        onPromoted={vi.fn()}
      />,
      { wrapper },
    );

    await user.click(screen.getByRole("button", { name: "Promote to revision" }));

    expect(
      await screen.findByText(/The base v2 is no longer the latest revision/),
    ).toBeInTheDocument();
  });

  it("discards a draft after confirmation", async () => {
    const user = userEvent.setup();
    seedDraft();
    render(
      <ScenarioDrafts
        projectId="project-1"
        graphId="graph-1"
        currentVersion={2}
        currentTitle="Vision transformer"
        onPromoted={vi.fn()}
      />,
      { wrapper },
    );

    await user.click(screen.getByRole("button", { name: "Discard" }));
    await user.click(screen.getByRole("button", { name: "Confirm discard" }));

    expect(useScenarioDrafts.getState().drafts).toEqual([]);
    expect(
      screen.getByText("No drafts for this graph yet."),
    ).toBeInTheDocument();
  });
});
