import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { entitiesFixture } from "../../test/fixtures.ts";
import { DomainBadge, EntityLegend } from "./EntityLegend.tsx";

describe("EntityLegend", () => {
  it("renders the domain badge and one row per shape", () => {
    render(<EntityLegend entities={entitiesFixture} />);

    expect(screen.getByText(/Electronics · 83% confidence/)).toBeInTheDocument();
    expect(screen.getByText("Package")).toBeInTheDocument();
    expect(screen.getByText("Memory Cell")).toBeInTheDocument();
    expect(screen.getByText("Generic")).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "3D shape key" })).toBeInTheDocument();
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
});
