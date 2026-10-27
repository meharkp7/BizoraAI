import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useWorkspaceSelection } from "../../lib/store.ts";
import { graphFixture, layoutFixture } from "../../test/fixtures.ts";
import { GraphCanvas } from "./GraphCanvas.tsx";

describe("GraphCanvas", () => {
  it("renders graph nodes and restores saved positions", async () => {
    useWorkspaceSelection.setState({ selectedNodeIds: [], selectedEdgeIds: [] });
    const { container } = render(<GraphCanvas graph={graphFixture} layout={layoutFixture} diffStatuses={null} />);

    const nodes = container.querySelectorAll(".react-flow__node");
    expect(nodes).toHaveLength(2);
    expect(screen.getByText("Transformer encoder")).toBeInTheDocument();
    // Edge SVG paths need real measurement; edge mapping is covered in
    // flowElements.test.ts and edge rendering in the e2e suite.

    // Saved layout position (10, 20) wins over auto-layout for "input".
    const inputNode = container.querySelector('[data-id="input"]') as HTMLElement;
    const encoderNode = container.querySelector('[data-id="encoder"]') as HTMLElement;
    expect(inputNode.style.transform).toContain("10px");
    expect(inputNode.style.transform).toContain("20px");
    expect(encoderNode.textContent).toContain("Transformer encoder");
  });

  it("selects a canvas node into the shared store on click", async () => {
    useWorkspaceSelection.setState({ selectedNodeIds: [], selectedEdgeIds: [] });
    const { container } = render(
      <GraphCanvas graph={graphFixture} layout={null} diffStatuses={null} />,
    );

    const nodes = container.querySelectorAll(".react-flow__node");
    expect(nodes).toHaveLength(2);
    // fireEvent (click only): userEvent's synthetic mousedown carries
    // view=null under jsdom, which crashes d3-drag inside React Flow.
    // Real click sequences are covered by the e2e suite.
    fireEvent.click(within(nodes[1] as HTMLElement).getByText("Transformer encoder"));
    expect(useWorkspaceSelection.getState().selectedNodeIds).toEqual(["encoder"]);
  });

  it("applies saved positions that arrive after first paint", () => {
    useWorkspaceSelection.setState({ selectedNodeIds: [], selectedEdgeIds: [] });
    const { container, rerender } = render(
      <GraphCanvas graph={graphFixture} layout={null} diffStatuses={null} />,
    );
    const before = (container.querySelector('[data-id="input"]') as HTMLElement).style
      .transform;
    // The layout query resolves after mount; reload must restore positions.
    rerender(<GraphCanvas graph={graphFixture} layout={layoutFixture} diffStatuses={null} />);
    const after = (container.querySelector('[data-id="input"]') as HTMLElement).style
      .transform;
    expect(after).toContain("10px");
    expect(after).toContain("20px");
    expect(after).not.toBe(before);
  });

  it("applies an explicit layout reset exactly once", () => {
    useWorkspaceSelection.setState({ selectedNodeIds: [], selectedEdgeIds: [] });
    const { container, rerender } = render(
      <GraphCanvas graph={graphFixture} layout={layoutFixture} diffStatuses={null} />,
    );
    const reset = new Map([
      ["input", { x: 300, y: 400 }],
      ["encoder", { x: 10, y: 20 }],
    ]);
    rerender(
      <GraphCanvas
        graph={graphFixture}
        layout={layoutFixture}
        layoutReset={{ id: 7, positions: reset }}
        diffStatuses={null}
      />,
    );
    const inputNode = container.querySelector('[data-id="input"]') as HTMLElement;
    expect(inputNode.style.transform).toContain("300px");
    expect(inputNode.style.transform).toContain("400px");
  });

  it("falls back to auto-layout without saved positions", () => {
    useWorkspaceSelection.setState({ selectedNodeIds: [], selectedEdgeIds: [] });
    const { container } = render(
      <GraphCanvas graph={graphFixture} layout={null} diffStatuses={null} />,
    );
    const nodes = container.querySelectorAll(".react-flow__node");
    const styles = [...nodes].map((node) => (node as HTMLElement).style.transform);
    // Auto-layout layers input above encoder.
    expect(styles[0]).not.toBe(styles[1]);
  });
});
