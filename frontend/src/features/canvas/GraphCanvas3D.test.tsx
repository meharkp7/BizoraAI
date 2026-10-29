import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { graphFixture, renderSpecsFixture } from "../../test/fixtures.ts";
import { GraphCanvas3D } from "./GraphCanvas3D.tsx";

function inputSpec() {
  return [{ ...renderSpecsFixture[0], node_id: "input" }];
}

describe("GraphCanvas3D", () => {
  it("explains when WebGL is unavailable instead of crashing", () => {
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      render(
        <GraphCanvas3D
          graph={graphFixture}
          layout={null}
          entities={null}
          assetSpecs={inputSpec()}
        />,
      );
      expect(screen.getByText("3D view is unavailable.")).toBeInTheDocument();
    } finally {
      error.mockRestore();
    }
  });

  it("stays honest when no node has a part model", () => {
    render(<GraphCanvas3D graph={graphFixture} layout={null} entities={null} />);
    expect(screen.getByText("No part models in this view.")).toBeInTheDocument();
    expect(
      screen.getByText(/Nothing here resolves to a catalog part model yet/),
    ).toBeInTheDocument();
  });
});
