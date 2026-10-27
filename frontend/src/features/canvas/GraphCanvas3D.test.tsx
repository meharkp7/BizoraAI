import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { graphFixture } from "../../test/fixtures.ts";
import { GraphCanvas3D } from "./GraphCanvas3D.tsx";

describe("GraphCanvas3D", () => {
  it("explains when WebGL is unavailable instead of crashing", () => {
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      render(<GraphCanvas3D graph={graphFixture} layout={null} />);
      expect(screen.getByText("3D view is unavailable.")).toBeInTheDocument();
    } finally {
      error.mockRestore();
    }
  });
});
