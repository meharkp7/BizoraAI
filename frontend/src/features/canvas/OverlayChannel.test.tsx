import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { useWorkspaceSelection } from "../../lib/store.ts";
import type { MeasuredOverlay } from "../../lib/types.ts";
import { entitiesFixture, graphFixture } from "../../test/fixtures.ts";
import { partLegendEntries } from "./assetModels.ts";
import { PartLegend } from "./EntityLegend.tsx";
import { FlowView } from "./FlowView.tsx";
import { resolutionsByNodeId } from "./graph3d.ts";
import { StructureView } from "./StructureView.tsx";

/** Stage 2 readiness: one measured-overlay push reaches every view. */
const OVERLAY: MeasuredOverlay = {
  run_id: "run-1",
  nodes: {
    input: [{ signal: "vdd", value: 0.5, unit: "V" }],
    encoder: [{ signal: "acc", value: 0.91, unit: null }],
  },
  edges: {},
};

beforeEach(() => {
  useWorkspaceSelection.setState({ selectedNodeIds: [], selectedEdgeIds: [] });
});

describe("measured overlay channel", () => {
  it("lights up the Structure view without code changes", () => {
    const { container } = render(
      <StructureView
        graph={graphFixture}
        layout={null}
        diffStatuses={null}
        entities={entitiesFixture}
        overlay={OVERLAY}
      />,
    );

    expect(container.querySelector('[data-id="encoder"]')?.textContent).toContain(
      "measured",
    );
  });

  it("lights up the Flow view from the same push", () => {
    const { container } = render(
      <FlowView graph={graphFixture} layout={null} diffStatuses={null} overlay={OVERLAY} />,
    );

    expect(container.querySelector('[data-id="encoder"]')?.textContent).toContain(
      "measured",
    );
  });

  it("lights up the 3D part key from the same push", () => {
    const parts = partLegendEntries(
      [
        {
          node_id: "input",
          label: "Image sensor",
          asset_uri: null,
          fallback_package: null,
          illustrative: false,
          mesh: null,
        },
      ],
      graphFixture.nodes,
      resolutionsByNodeId(entitiesFixture),
    );
    render(
      <PartLegend
        entities={entitiesFixture}
        parts={parts}
        assetSummary={{ measured: 1, illustrative: 0, total: 1 }}
        unmodeled={0}
        overlay={OVERLAY}
      />,
    );

    expect(screen.getByText("measured: vdd=0.5V")).toBeInTheDocument();
  });
});
