import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { useWorkspaceSelection } from "../../lib/store.ts";
import { server } from "../../test/server.ts";
import { WorkspacePage } from "./WorkspacePage.tsx";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function renderPage(onVersionChange: (version: number) => void, version = 2) {
  useWorkspaceSelection.setState({ selectedNodeIds: [], selectedEdgeIds: [] });
  return render(
    <WorkspacePage
      projectId="project-1"
      graphId="graph-1"
      version={version}
      onVersionChange={onVersionChange}
    />,
    { wrapper },
  );
}

describe("canvas editing", () => {
  it("adds a node through the toolbar and navigates to the new revision", async () => {
    const onVersionChange = vi.fn();
    renderPage(onVersionChange);
    await screen.findByRole("heading", { name: "Vision transformer" });

    const form = screen.getByRole("form", { name: "Add component" });
    await userEvent.type(within(form).getByLabelText("Node label"), "Head");
    await userEvent.click(within(form).getByRole("button", { name: "Add" }));

    expect(await screen.findByText("Saved as revision 3.")).toBeInTheDocument();
    expect(onVersionChange).toHaveBeenCalledWith(3);
  });

  it("rejects duplicate node ids locally without a request", async () => {
    const onVersionChange = vi.fn();
    renderPage(onVersionChange);
    await screen.findByRole("heading", { name: "Vision transformer" });

    const form = screen.getByRole("form", { name: "Add component" });
    await userEvent.type(within(form).getByLabelText("Node id"), "encoder");
    await userEvent.type(within(form).getByLabelText("Node label"), "Dup");
    await userEvent.click(within(form).getByRole("button", { name: "Add" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("already used");
    expect(onVersionChange).not.toHaveBeenCalled();
  });

  it("applies inspector configuration edits", async () => {
    const onVersionChange = vi.fn();
    renderPage(onVersionChange);
    await screen.findByRole("heading", { name: "Vision transformer" });

    const nodes = screen.getByRole("list", { name: "Graph nodes" });
    await userEvent.click(within(nodes).getByRole("button", { name: /Transformer encoder/ }));
    const inspector = screen.getByRole("region", { name: "Inspector" });
    const editor = within(inspector).getByLabelText("Node configuration JSON");
    fireEvent.change(editor, { target: { value: '{"layers": 24}' } });
    await userEvent.click(within(inspector).getByRole("button", { name: "Apply configuration" }));

    expect(await screen.findByText("Saved as revision 3.")).toBeInTheDocument();
    expect(onVersionChange).toHaveBeenCalledWith(3);
  });

  it("rejects invalid configuration JSON locally", async () => {
    const onVersionChange = vi.fn();
    renderPage(onVersionChange);
    await screen.findByRole("heading", { name: "Vision transformer" });

    const nodes = screen.getByRole("list", { name: "Graph nodes" });
    await userEvent.click(within(nodes).getByRole("button", { name: /Transformer encoder/ }));
    const inspector = screen.getByRole("region", { name: "Inspector" });
    const editor = within(inspector).getByLabelText("Node configuration JSON");
    fireEvent.change(editor, { target: { value: "{oops" } });
    await userEvent.click(within(inspector).getByRole("button", { name: "Apply configuration" }));

    expect(await screen.findByText("Configuration must be valid JSON.")).toBeInTheDocument();
    expect(onVersionChange).not.toHaveBeenCalled();
  });

  it("surfaces server patch rejections with code and details", async () => {
    server.use(
      http.post("/api/v1/graphs/:projectId/:graphId/patches", () =>
        HttpResponse.json(
          {
            error: {
              code: "INVALID_GRAPH_PATCH",
              message: "The patch would produce an invalid methodology graph.",
              details: { errors: ["graph contains a cycle"] },
            },
          },
          { status: 422 },
        ),
      ),
    );
    const onVersionChange = vi.fn();
    renderPage(onVersionChange);
    await screen.findByRole("heading", { name: "Vision transformer" });

    const form = screen.getByRole("form", { name: "Add component" });
    await userEvent.type(within(form).getByLabelText("Node label"), "Head");
    await userEvent.click(within(form).getByRole("button", { name: "Add" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("INVALID_GRAPH_PATCH");
    expect(onVersionChange).not.toHaveBeenCalled();
  });

  it("undoes and redoes version navigation", async () => {
    const onVersionChange = vi.fn();
    const view = renderPage(onVersionChange);
    await screen.findByRole("heading", { name: "Vision transformer" });

    await userEvent.click(screen.getByRole("button", { name: "← Older" }));
    expect(onVersionChange).toHaveBeenCalledWith(1);
    view.rerender(
      <WorkspacePage projectId="project-1" graphId="graph-1" version={1} onVersionChange={onVersionChange} />,
    );
    await screen.findByRole("heading", { name: "Vision transformer" });
    await userEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(onVersionChange).toHaveBeenCalledWith(2);
  });
});
