import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { useLibrarySelection, useWorkspaceSelection } from "../../lib/store.ts";
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
});
