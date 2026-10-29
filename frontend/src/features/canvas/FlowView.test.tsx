import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useWorkspaceSelection } from "../../lib/store.ts";
import type { MethodologyGraph } from "../../lib/types.ts";
import { graphFixture } from "../../test/fixtures.ts";
import { FlowView } from "./FlowView.tsx";

function chainGraph(): MethodologyGraph {
  return {
    ...graphFixture,
    nodes: ["a", "b"].map((id) => ({ ...graphFixture.nodes[0], id, label: `Step ${id}` })),
    edges: [{ ...graphFixture.edges[0], id: "e-ab", source: "a", target: "b" }],
  };
}

beforeEach(() => {
  useWorkspaceSelection.setState({ selectedNodeIds: [], selectedEdgeIds: [] });
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("FlowView", () => {
  it("walks steps in order and selects each node", () => {
    render(<FlowView graph={chainGraph()} layout={null} diffStatuses={null} />);

    expect(screen.getByText("Step 1 of 2")).toBeInTheDocument();
    expect(useWorkspaceSelection.getState().selectedNodeIds).toEqual(["a"]);

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("Step 2 of 2")).toBeInTheDocument();
    expect(useWorkspaceSelection.getState().selectedNodeIds).toEqual(["b"]);

    fireEvent.click(screen.getByRole("button", { name: "Previous" }));
    expect(useWorkspaceSelection.getState().selectedNodeIds).toEqual(["a"]);
  });

  it("jumps to a step and shows its evidence", () => {
    render(<FlowView graph={graphFixture} layout={null} diffStatuses={null} />);

    const steps = screen.getByRole("list", { name: "Method steps" });
    expect(steps).toHaveTextContent("model · p. 4");
    expect(steps).toHaveTextContent("input · no recorded evidence");
    fireEvent.click(screen.getByRole("button", { name: /Transformer encoder/ }));
    expect(useWorkspaceSelection.getState().selectedNodeIds).toEqual(["encoder"]);
  });

  it("plays the walkthrough and stops at the end", () => {
    render(<FlowView graph={chainGraph()} layout={null} diffStatuses={null} />);

    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    act(() => {
      vi.advanceTimersByTime(2600);
    });
    expect(useWorkspaceSelection.getState().selectedNodeIds).toEqual(["b"]);
    expect(screen.getByRole("button", { name: "Pause" })).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(2600);
    });
    expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument();
    expect(useWorkspaceSelection.getState().selectedNodeIds).toEqual(["b"]);
  });

  it("renders nothing without steps", () => {
    const { container } = render(
      <FlowView
        graph={{ ...graphFixture, nodes: [], edges: [] }}
        layout={null}
        diffStatuses={null}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
