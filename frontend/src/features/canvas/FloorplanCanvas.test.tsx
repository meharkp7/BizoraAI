import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { useWorkspaceSelection } from "../../lib/store.ts";
import type { GraphEntities, MethodologyGraph } from "../../lib/types.ts";
import { entitiesFixture, graphFixture } from "../../test/fixtures.ts";
import { FloorplanCanvas } from "./FloorplanCanvas.tsx";

function mixedGraph(withDims: boolean): MethodologyGraph {
  return {
    ...graphFixture,
    nodes: [
      { ...graphFixture.nodes[0], id: "cell-a", label: "Bitcell A" },
      { ...graphFixture.nodes[0], id: "cell-b", label: "Bitcell B" },
      {
        ...graphFixture.nodes[1],
        id: "amp",
        label: "Sense amplifier",
        config: withDims ? { array: "2x2" } : {},
      },
    ],
    edges: [],
  };
}

function mixedEntities(graph: MethodologyGraph): GraphEntities {
  return {
    ...entitiesFixture,
    entities: graph.nodes.map((node) => ({
      ...entitiesFixture.entities[0],
      node_id: node.id,
      symbol: node.id.startsWith("cell-") ? "bitcell" : "senseamp",
      entity_type: node.id.startsWith("cell-") ? "memory-cell" : "sense-amplifier",
    })),
  };
}

beforeEach(() => {
  useWorkspaceSelection.getState().clearSelection();
});

describe("FloorplanCanvas", () => {
  it("lays the stated array over labeled periphery blocks", () => {
    const graph = mixedGraph(true);
    const { container } = render(
      <FloorplanCanvas graph={graph} entities={mixedEntities(graph)} />,
    );

    expect(screen.getByRole("group", { name: "Array floorplan" })).toBeInTheDocument();
    expect(container.querySelectorAll('[data-kind="cell"]')).toHaveLength(4);
    expect(container.querySelectorAll('[data-kind="block"]')).toHaveLength(1);
    expect(
      screen.getByText(/2×2 array geometry from.*Sense amplifier.*config/),
    ).toBeInTheDocument();
    expect(screen.getByText(/illustrative, not to scale/)).toBeInTheDocument();
    expect(screen.getByText("Sense ampli…")).toBeInTheDocument();
  });

  it("links every cell to the bitcell node", () => {
    const graph = mixedGraph(true);
    const { container } = render(
      <FloorplanCanvas graph={graph} entities={mixedEntities(graph)} />,
    );

    const cells = container.querySelectorAll('[data-kind="cell"]');
    for (const cell of cells) {
      expect(cell.getAttribute("data-node-id")).toBe("cell-a");
    }
    fireEvent.click(cells[0] as Element);
    expect(useWorkspaceSelection.getState().selectedNodeIds).toEqual(["cell-a"]);
  });

  it("shows measured values from the overlay channel", () => {
    const graph = mixedGraph(true);
    render(
      <FloorplanCanvas
        graph={graph}
        entities={mixedEntities(graph)}
        overlay={{
          run_id: "run-7",
          nodes: { amp: [{ signal: "P", value: 4.4, unit: "uW" }] },
          edges: {},
        }}
      />,
    );
    expect(screen.getByText(/1 measured value from run run-7/)).toBeInTheDocument();
    expect(screen.getByText(/measured: P=4.4uW/)).toBeInTheDocument();
  });

  it("stays hidden when the paper states no array geometry", () => {
    const graph = mixedGraph(false);
    render(<FloorplanCanvas graph={graph} entities={mixedEntities(graph)} />);
    expect(screen.getByText("No array dimensions in this graph.")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Array floorplan" })).not.toBeInTheDocument();
  });

  it("explains an empty floorplan instead of drawing guesses", () => {
    const graph = mixedGraph(true);
    const elsewhere: GraphEntities = {
      ...mixedEntities(graph),
      entities: mixedEntities(graph).entities.map((entity) => ({
        ...entity,
        domain: "deep-learning",
      })),
    };
    render(<FloorplanCanvas graph={graph} entities={elsewhere} />);
    expect(screen.getByText("No chip-level entities in this graph.")).toBeInTheDocument();
  });
});
