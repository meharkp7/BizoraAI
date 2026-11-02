import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import {
  useLibrarySelection,
  useSchematicSandbox,
  useWorkspaceSelection,
} from "../../lib/store.ts";
import type { GraphPatch } from "../../lib/types.ts";
import { graphFixture } from "../../test/fixtures.ts";
import { ComponentDetailView } from "./ComponentDetail.tsx";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function resetStores(): void {
  useLibrarySelection.setState({ selectedComponentId: "npn-2n3904", indexTab: "library" });
  useWorkspaceSelection.setState({ selectedNodeIds: ["encoder"], selectedEdgeIds: [] });
}

describe("ComponentDetailView", () => {
  it("shows specs, pinout, interfaces, and evidence for the entry", async () => {
    resetStores();
    render(
      <ComponentDetailView graph={graphFixture} onSubmit={() => {}} disabled={false} />,
      { wrapper },
    );

    expect(await screen.findByText("2N3904 NPN transistor")).toBeInTheDocument();
    expect(screen.getByText("Collector current (max)")).toBeInTheDocument();
    expect(screen.getByText("Emitter")).toBeInTheDocument();
    expect(screen.getByText(/NPN emitter terminal/)).toBeInTheDocument();
    expect(screen.getByText(/onsemi 2N3904 datasheet/)).toBeInTheDocument();
    expect(screen.getByText("No verified datasheet or reference yet.")).toBeInTheDocument();
  });

  it("validates a replacement and applies it as a patch", async () => {
    resetStores();
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(
      <ComponentDetailView graph={graphFixture} onSubmit={onSubmit} disabled={false} />,
      { wrapper },
    );

    expect(await screen.findByText(/Compatible: all known interfaces/)).toBeInTheDocument();
    expect(screen.getByText(/Preserved connections \(1\)/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Apply replacement/ }));

    expect(onSubmit).toHaveBeenCalledOnce();
    const [[patches]] = onSubmit.mock.calls as [[GraphPatch[]]];
    expect(patches[0].operation).toBe("replace_node");
    expect(patches[0].target_id).toBe("encoder");
    const node = patches[0].payload["node"] as { label: string; config: Record<string, unknown> };
    expect(node.label).toBe("2N3904 NPN transistor");
    expect(node.config["part"]).toBe("2N3904");
  });

  it("asks for a node selection before previewing a replacement", async () => {
    useLibrarySelection.setState({ selectedComponentId: "npn-2n3904", indexTab: "library" });
    useWorkspaceSelection.setState({ selectedNodeIds: [], selectedEdgeIds: [] });
    render(
      <ComponentDetailView graph={graphFixture} onSubmit={() => {}} disabled={false} />,
      { wrapper },
    );

    expect(await screen.findByText("2N3904 NPN transistor")).toBeInTheDocument();
    expect(screen.getByText(/Select a graph node to replace it/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Apply replacement/ })).not.toBeInTheDocument();
  });

  it("adds the part to the schematic sandbox once a figure is active", async () => {
    const user = userEvent.setup();
    resetStores();
    useSchematicSandbox.setState({ items: [], activeFigureId: "fig-9" });
    try {
      render(
        <ComponentDetailView graph={graphFixture} onSubmit={() => {}} disabled={false} />,
        { wrapper },
      );
      expect(await screen.findByText("2N3904 NPN transistor")).toBeInTheDocument();
      const button = screen.getByRole("button", { name: "Try in schematic" });
      expect(button).toBeEnabled();
      await user.click(button);
      const items = useSchematicSandbox.getState().items;
      expect(items).toHaveLength(1);
      expect(items[0]?.componentId).toBe("npn-2n3904");
      expect(items[0]?.figureId).toBe("fig-9");
      // A BJT has no engine symbol: generic trial block.
      expect(items[0]?.engineType.startsWith("trial:")).toBe(true);
      expect(screen.getByText(/On trial on the schematic ×1/)).toBeInTheDocument();
    } finally {
      useSchematicSandbox.setState({ items: [], activeFigureId: null });
    }
  });

  it("disables schematic trials until the schematic tab opens once", async () => {
    resetStores();
    useSchematicSandbox.setState({ items: [], activeFigureId: null });
    render(
      <ComponentDetailView graph={graphFixture} onSubmit={() => {}} disabled={false} />,
      { wrapper },
    );

    expect(await screen.findByText("2N3904 NPN transistor")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try in schematic" })).toBeDisabled();
    expect(screen.getByText(/Open the Schematic tab once/)).toBeInTheDocument();
  });

  it("adds the component as a new node with a suggested id", async () => {
    resetStores();
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(
      <ComponentDetailView graph={graphFixture} onSubmit={onSubmit} disabled={false} />,
      { wrapper },
    );

    expect(await screen.findByText("2N3904 NPN transistor")).toBeInTheDocument();
    const section = screen.getByRole("region", { name: "Add to graph" });
    expect(
      (within(section).getByLabelText("Node ID") as HTMLInputElement).value,
    ).toBe("2n3904-npn-transistor");

    await user.click(
      within(section).getByRole("button", { name: "Add to graph (new revision)" }),
    );

    expect(onSubmit).toHaveBeenCalledOnce();
    const [[patches]] = onSubmit.mock.calls as [[GraphPatch[]]];
    expect(patches[0].operation).toBe("add_node");
    expect(patches[0].target_id).toBeNull();
    const node = patches[0].payload["node"] as {
      id: string;
      label: string;
      description: string;
      config: Record<string, unknown>;
    };
    expect(node.id).toBe("2n3904-npn-transistor");
    expect(node.label).toBe("2N3904 NPN transistor");
    expect(node.description).toContain("NPN");
    expect(node.config["part"]).toBe("2N3904");
  });

  it("rejects a taken node id with an inline error", async () => {
    resetStores();
    const user = userEvent.setup();
    render(
      <ComponentDetailView graph={graphFixture} onSubmit={() => {}} disabled={false} />,
      { wrapper },
    );

    expect(await screen.findByText("2N3904 NPN transistor")).toBeInTheDocument();
    const section = screen.getByRole("region", { name: "Add to graph" });
    const input = within(section).getByLabelText("Node ID");
    await user.clear(input);
    await user.type(input, "encoder");

    expect(
      within(section).getByText("This ID is already in the graph."),
    ).toBeInTheDocument();
    expect(
      within(section).getByRole("button", { name: "Add to graph (new revision)" }),
    ).toBeDisabled();
  });

  it("offers add-to-graph without a node selection", async () => {
    useLibrarySelection.setState({ selectedComponentId: "npn-2n3904", indexTab: "library" });
    useWorkspaceSelection.setState({ selectedNodeIds: [], selectedEdgeIds: [] });
    render(
      <ComponentDetailView graph={graphFixture} onSubmit={() => {}} disabled={false} />,
      { wrapper },
    );

    expect(await screen.findByText("2N3904 NPN transistor")).toBeInTheDocument();
    const section = screen.getByRole("region", { name: "Add to graph" });
    expect(
      within(section).getByRole("button", { name: "Add to graph (new revision)" }),
    ).toBeEnabled();
  });
});
