import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { useWorkspaceSelection } from "../../lib/store.ts";
import type { GraphEntities } from "../../lib/types.ts";
import { entitiesFixture, graphFixture } from "../../test/fixtures.ts";
import { SchematicCanvas } from "./SchematicCanvas.tsx";

const processEntities: GraphEntities = {
  ...entitiesFixture,
  classification: { domain: "deep-learning", confidence: 0.9, signals: ["training"] },
  entities: entitiesFixture.entities.map((entity) => ({
    ...entity,
    domain: "deep-learning",
    physical: false,
    symbol: "dataset",
  })),
};

beforeEach(() => {
  useWorkspaceSelection.getState().clearSelection();
});

describe("SchematicCanvas", () => {
  it("expands bitcells and marks generic placeholders", () => {
    const { container } = render(<SchematicCanvas graph={graphFixture} entities={entitiesFixture} />);

    expect(screen.getByRole("group", { name: "Chip schematic" })).toBeInTheDocument();
    expect(screen.getByText("Image")).toBeInTheDocument();
    expect(screen.getByText(/canonical 6T/)).toBeInTheDocument();
    expect(screen.getByText("Transformer enc…")).toBeInTheDocument();
    expect(screen.getByText("generic placeholder")).toBeInTheDocument();
    expect(
      container.querySelector('[data-node-id="input"]'),
    ).toBeInTheDocument();
  });

  it("notes the illustrative wiring and any hidden nodes", () => {
    render(<SchematicCanvas graph={graphFixture} entities={entitiesFixture} />);
    expect(screen.getByText(/wiring is illustrative, not a netlist/)).toBeInTheDocument();
    expect(screen.queryByText(/hidden/)).not.toBeInTheDocument();

    const extended = {
      ...graphFixture,
      nodes: [...graphFixture.nodes, { ...graphFixture.nodes[0], id: "stray", label: "Stray" }],
    };
    render(<SchematicCanvas graph={extended} entities={entitiesFixture} />);
    expect(
      screen.getByText(/1 node without an identified electronics part is hidden/),
    ).toBeInTheDocument();
  });

  it("selects a node on click", () => {
    const { container } = render(
      <SchematicCanvas graph={graphFixture} entities={entitiesFixture} />,
    );

    fireEvent.click(container.querySelector('[data-node-id="input"]') as Element);
    expect(useWorkspaceSelection.getState().selectedNodeIds).toEqual(["input"]);
  });

  it("explains an empty schematic instead of drawing guesses", () => {
    render(<SchematicCanvas graph={graphFixture} entities={processEntities} />);
    expect(screen.getByText("No chip-level entities in this graph.")).toBeInTheDocument();

    render(<SchematicCanvas graph={graphFixture} entities={null} />);
    expect(screen.getAllByText("No chip-level entities in this graph.")).toHaveLength(2);
  });
});
