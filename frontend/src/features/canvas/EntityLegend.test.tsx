import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { entitiesFixture, graphFixture } from "../../test/fixtures.ts";
import { partLegendEntries } from "./assetModels.ts";
import { resolutionsByNodeId } from "./graph3d.ts";
import { DomainBadge, EntityLegend, PartLegend } from "./EntityLegend.tsx";

describe("EntityLegend", () => {
  it("renders the domain badge and one row per symbol", () => {
    render(<EntityLegend entities={entitiesFixture} />);

    expect(screen.getByText(/Electronics · 83% confidence/)).toBeInTheDocument();
    expect(screen.getByText("Bitcell")).toBeInTheDocument();
    expect(screen.getByText("Memory Cell")).toBeInTheDocument();
    expect(screen.getByText("Generic")).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "Symbol key" })).toBeInTheDocument();
  });

  it("explains a generic classification instead of naming a domain", () => {
    render(
      <DomainBadge
        entities={{ ...entitiesFixture, classification: { domain: "generic", confidence: 0, signals: [] } }}
      />,
    );

    expect(
      screen.getByText(/Generic domain — the paper did not match a known system vocabulary\./),
    ).toBeInTheDocument();
  });

  it("renders nothing without entities", () => {
    const { container } = render(<EntityLegend entities={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("stacks inline instead of overlaying when asked", () => {
    render(<EntityLegend entities={entitiesFixture} title="Process key" inline />);
    const legend = screen.getByRole("complementary", { name: "Process key" });
    expect(legend.className).toMatch(/legendInline/);
  });
});

describe("PartLegend", () => {
  const parts = partLegendEntries(
    [
      {
        node_id: "input",
        label: "6T bitcell",
        asset_uri: null,
        fallback_package: null,
        illustrative: false,
        mesh: null,
      },
    ],
    graphFixture.nodes,
    resolutionsByNodeId(entitiesFixture),
  );

  it("rows one modeled part with provenance and node identity", () => {
    render(
      <PartLegend
        entities={entitiesFixture}
        parts={parts}
        assetSummary={{ measured: 1, illustrative: 0, total: 1 }}
        unmodeled={2}
      />,
    );

    const legend = screen.getByRole("complementary", { name: "3D part key" });
    expect(legend).toBeInTheDocument();
    expect(screen.getByText("6T bitcell")).toBeInTheDocument();
    expect(screen.getByText("measured")).toBeInTheDocument();
    expect(screen.getByText(/Image · Memory Cell/)).toBeInTheDocument();
    expect(screen.getByText("3D models: 1 measured · 0 illustrative")).toBeInTheDocument();
    expect(screen.getByText(/2 more components have no part model/)).toBeInTheDocument();
  });

  it("renders nothing without modeled parts", () => {
    const { container } = render(<PartLegend entities={entitiesFixture} parts={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows measured values from the overlay channel on part rows", () => {
    render(
      <PartLegend
        entities={entitiesFixture}
        parts={parts}
        assetSummary={{ measured: 1, illustrative: 0, total: 1 }}
        unmodeled={0}
        overlay={{
          run_id: "run-1",
          nodes: { input: [{ signal: "vdd", value: 0.5, unit: "V" }] },
          edges: {},
        }}
      />,
    );

    expect(screen.getByText("3D models: 1 measured · 0 illustrative")).toBeInTheDocument();
    expect(screen.getByText(/1 measured value from run/)).toBeInTheDocument();
    expect(screen.getByText("measured: vdd=0.5V")).toBeInTheDocument();
  });
});
