import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { useWorkspaceSelection } from "../../lib/store.ts";
import type { GraphEntities, MethodologyGraph } from "../../lib/types.ts";
import { entitiesFixture, graphFixture } from "../../test/fixtures.ts";
import { FloorplanCanvas } from "./FloorplanCanvas.tsx";

function mixedGraph(): MethodologyGraph {
  return {
    ...graphFixture,
    nodes: [
      { ...graphFixture.nodes[0], id: "cell-a", label: "Bitcell A" },
      { ...graphFixture.nodes[0], id: "cell-b", label: "Bitcell B" },
      { ...graphFixture.nodes[1], id: "amp", label: "Sense amplifier" },
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
  it("lays bitcells over labeled periphery blocks", () => {
    const graph = mixedGraph();
    const { container } = render(
      <FloorplanCanvas graph={graph} entities={mixedEntities(graph)} />,
    );

    expect(screen.getByRole("group", { name: "Array floorplan" })).toBeInTheDocument();
    expect(container.querySelectorAll('[data-kind="cell"]')).toHaveLength(2);
    expect(container.querySelectorAll('[data-kind="block"]')).toHaveLength(1);
    expect(screen.getByText(/2×1 bitcell arrangement/)).toBeInTheDocument();
    expect(screen.getByText("Sense ampli…")).toBeInTheDocument();
  });

  it("selects a block on click", () => {
    const graph = mixedGraph();
    const { container } = render(
      <FloorplanCanvas graph={graph} entities={mixedEntities(graph)} />,
    );

    fireEvent.click(container.querySelector('[data-node-id="amp"]') as Element);
    expect(useWorkspaceSelection.getState().selectedNodeIds).toEqual(["amp"]);
  });

  it("explains an empty floorplan instead of drawing guesses", () => {
    const graph = mixedGraph();
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
