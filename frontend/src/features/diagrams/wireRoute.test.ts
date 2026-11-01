import { describe, expect, it } from "vitest";
import { diagramsFixture } from "../../test/fixtures.ts";
import { renderCircuitDiagram } from "./adapters.ts";
import {
  pointAtLength,
  polylineLength,
  routeAlongWires,
} from "./wireRoute.ts";

describe("wireRoute", () => {
  it("routes along an L-shaped wire through the corner", () => {
    const route = routeAlongWires(
      "M 0,0 L 100,0 L 100,100",
      { x: 0, y: 0 },
      { x: 100, y: 100 },
    );
    expect(route).toEqual([
      { x: 0, y: 0 },
      { x: 100, y: 0 },
      { x: 100, y: 100 },
    ]);
  });

  it("snaps off-wire endpoints to the nearest copper", () => {
    const route = routeAlongWires(
      "M 0,0 L 100,0 L 100,100",
      { x: 6, y: 4 },
      { x: 96, y: 104 },
    );
    if (!route) throw new Error("expected a route");
    expect(route[0]).toEqual({ x: 6, y: 4 });
    expect(route[route.length - 1]).toEqual({ x: 96, y: 104 });
    expect(route).toContainEqual({ x: 100, y: 0 });
  });

  it("takes the shorter of two candidate paths", () => {
    // Detour path: 50+120+50+20 = 240. Direct path: 100+100 = 200.
    const route = routeAlongWires(
      "M 0,0 L 50,0 L 50,120 L 100,120 L 100,100 M 0,0 L 0,100 L 100,100",
      { x: 0, y: 0 },
      { x: 100, y: 100 },
    );
    expect(route).toEqual([
      { x: 0, y: 0 },
      { x: 0, y: 100 },
      { x: 100, y: 100 },
    ]);
  });

  it("reaches past dead stubs to connected copper", () => {
    const route = routeAlongWires(
      "M 0,0 L 5,0 M 0,10 L 100,10 L 100,100",
      { x: 2, y: 1 },
      { x: 100, y: 100 },
    );
    if (!route) throw new Error("expected a route");
    expect(route[0]).toEqual({ x: 2, y: 1 });
    expect(route[route.length - 1]).toEqual({ x: 100, y: 100 });
    expect(route).toContainEqual({ x: 100, y: 10 });
  });

  it("routes the first flow step of the real fixture along wires", () => {
    const result = renderCircuitDiagram(diagramsFixture.circuits[0]);
    if (!result.ok) throw new Error("fixture circuit must render");
    const d = result.svg.match(/<path class="wire" d="([^"]*)"/)?.[1] ?? "";
    expect(d.length).toBeGreaterThan(0);
    // Hinted scale: min pairwise placement distance 25 -> max(8, 120/25).
    const route = routeAlongWires(
      d,
      { x: 30 * 8, y: 40 * 8 },
      { x: 30 * 8, y: 15 * 8 },
    );
    expect(route).not.toBeNull();
    // Bends at a trunk instead of cutting straight across.
    expect(route!.length).toBeGreaterThan(2);
  });

  it("returns null when no wire connects the endpoints", () => {
    expect(
      routeAlongWires("M 0,0 L 10,0 M 100,100 L 110,100", { x: 0, y: 0 }, { x: 100, y: 100 }),
    ).toBeNull();
    expect(routeAlongWires("", { x: 0, y: 0 }, { x: 1, y: 1 })).toBeNull();
  });

  it("snaps beside a long run's middle, far from its corners", () => {
    // (100,10) sits 100+ units from both corners: only densified
    // nodes make this routable.
    const route = routeAlongWires("M 0,0 L 200,0", { x: 100, y: 10 }, { x: 190, y: 8 });
    expect(route).not.toBeNull();
    expect(route![0]).toEqual({ x: 100, y: 10 });
    expect(route![route!.length - 1]).toEqual({ x: 190, y: 8 });
    expect(route).toContainEqual({ x: 100, y: 0 });
  });

  it("bridges copper islands through a device span", () => {
    const d = "M 0,0 L 40,0 M 60,0 L 100,0";
    const from = { x: 0, y: 0 };
    const to = { x: 100, y: 0 };
    expect(routeAlongWires(d, from, to)).toBeNull();
    const route = routeAlongWires(d, from, to, [{ x: 35, y: -10, w: 30, h: 20 }]);
    expect(route).not.toBeNull();
    // Straight gap, so collinear waypoints prune to the endpoints.
    expect(route![0]).toEqual(from);
    expect(route![route!.length - 1]).toEqual(to);
  });

  it("ignores degenerate spans and prefers pure copper", () => {
    const d = "M 0,0 L 40,0 M 60,0 L 100,0";
    expect(
      routeAlongWires(d, { x: 0, y: 0 }, { x: 100, y: 0 }, [{ x: 0, y: 0, w: 0, h: 0 }]),
    ).toBeNull();
    const connected = "M 0,0 L 100,0";
    expect(routeAlongWires(connected, { x: 0, y: 0 }, { x: 100, y: 0 })).toEqual(
      routeAlongWires(connected, { x: 0, y: 0 }, { x: 100, y: 0 }, [
        { x: -10, y: -10, w: 120, h: 20 },
      ]),
    );
  });

  it("walks polylines at constant distance", () => {
    const line = [
      { x: 0, y: 0 },
      { x: 100, y: 0 },
      { x: 100, y: 100 },
    ];
    expect(polylineLength(line)).toBe(200);
    expect(pointAtLength(line, 0)).toEqual({ x: 0, y: 0 });
    expect(pointAtLength(line, 100)).toEqual({ x: 100, y: 0 });
    expect(pointAtLength(line, 150)).toEqual({ x: 100, y: 50 });
    expect(pointAtLength(line, 999)).toEqual({ x: 100, y: 100 });
  });
});
