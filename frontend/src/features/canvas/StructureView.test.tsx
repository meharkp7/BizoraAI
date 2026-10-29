import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { useWorkspaceSelection } from "../../lib/store.ts";
import type { GraphEntities, MethodologyGraph } from "../../lib/types.ts";
import { entitiesFixture, graphFixture } from "../../test/fixtures.ts";
import { StructureView } from "./StructureView.tsx";

function graphWithDims(): MethodologyGraph {
  return {
    ...graphFixture,
    nodes: graphFixture.nodes.map((node) =>
      node.id === "input" ? { ...node, config: { array: "4x4" } } : node,
    ),
  };
}

beforeEach(() => {
  useWorkspaceSelection.setState({ selectedNodeIds: [], selectedEdgeIds: [] });
});

describe("StructureView", () => {
  it("offers schematic and floorplan modes when the paper supports them", () => {
    render(
      <StructureView
        graph={graphWithDims()}
        layout={null}
        diffStatuses={null}
        entities={entitiesFixture}
      />,
    );

    expect(screen.getByRole("button", { name: "Diagram" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    fireEvent.click(screen.getByRole("button", { name: "Schematic" }));
    expect(screen.getByRole("group", { name: "Chip schematic" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Floorplan" }));
    expect(screen.getByRole("group", { name: "Array floorplan" })).toBeInTheDocument();
  });

  it("hides unsupported modes instead of inventing them", () => {
    const edgeless: MethodologyGraph = { ...graphFixture, edges: [] };
    render(
      <StructureView
        graph={edgeless}
        layout={null}
        diffStatuses={null}
        entities={entitiesFixture}
      />,
    );

    expect(screen.getByRole("button", { name: "Diagram" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Schematic" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Floorplan" })).not.toBeInTheDocument();
  });

  it("hides the floorplan when no dimensions are stated", () => {
    render(
      <StructureView
        graph={graphFixture}
        layout={null}
        diffStatuses={null}
        entities={entitiesFixture}
      />,
    );

    expect(screen.getByRole("button", { name: "Schematic" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Floorplan" })).not.toBeInTheDocument();
  });

  it("passes the overlay channel into every mode", () => {
    const overlay = {
      run_id: "run-1",
      nodes: { input: [{ signal: "V", value: 1.2, unit: "V" as const }] },
      edges: {},
    };
    const elsewhere: GraphEntities = {
      ...entitiesFixture,
      entities: entitiesFixture.entities.map((entity) => ({ ...entity })),
    };
    const { container } = render(
      <StructureView
        graph={graphWithDims()}
        layout={null}
        diffStatuses={null}
        entities={elsewhere}
        overlay={overlay}
      />,
    );

    expect(container.querySelector('[data-id="input"]')?.textContent).toContain("measured");
    fireEvent.click(screen.getByRole("button", { name: "Schematic" }));
    expect(screen.getByText(/1 measured value from run run-1/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Floorplan" }));
    expect(screen.getByText(/1 measured value from run run-1/)).toBeInTheDocument();
  });
});
