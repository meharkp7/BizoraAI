import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { entitiesFixture } from "../../test/fixtures.ts";
import { AssetProvenanceBadge, EntityLegend } from "./EntityLegend.tsx";

describe("AssetProvenanceBadge", () => {
  it("announces measured and illustrative counts", () => {
    render(<AssetProvenanceBadge summary={{ measured: 2, illustrative: 3, total: 5 }} />);
    const badge = screen.getByRole("status");
    expect(badge).toHaveTextContent("3D models: 2 measured · 3 illustrative");
    expect(badge).toHaveAttribute(
      "aria-label",
      "2 measured models, 3 illustrative stand-ins",
    );
  });

  it("renders nothing without a summary or with zero visuals", () => {
    const { container: noSummary } = render(<AssetProvenanceBadge summary={null} />);
    expect(noSummary).toBeEmptyDOMElement();
    const { container: empty } = render(
      <AssetProvenanceBadge summary={{ measured: 0, illustrative: 0, total: 0 }} />,
    );
    expect(empty).toBeEmptyDOMElement();
  });

  it("stays honest when every visual is a stand-in", () => {
    render(<AssetProvenanceBadge summary={{ measured: 0, illustrative: 4, total: 4 }} />);
    expect(screen.getByRole("status")).toHaveTextContent("3D models: 0 measured · 4 illustrative");
  });
});

describe("EntityLegend asset indicator", () => {
  it("shows the provenance line alongside the shape key", () => {
    render(
      <EntityLegend
        entities={entitiesFixture}
        assetSummary={{ measured: 1, illustrative: 1, total: 2 }}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("3D models: 1 measured · 1 illustrative");
    expect(screen.getByRole("complementary", { name: "3D shape key" })).toBeInTheDocument();
  });

  it("omits the provenance line when no specs are attached", () => {
    render(<EntityLegend entities={entitiesFixture} />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
