import { describe, expect, it } from "vitest";
import type { DiagramNode } from "../../lib/types.ts";
import { fitMethodologySvg, markWhatIfNodes } from "./methodologySvg.ts";

function node(overrides: Partial<DiagramNode> & { id: string }): DiagramNode {
  return {
    label: overrides.id,
    kind: "process",
    group: null,
    detail: null,
    params: {},
    confidence: 0.9,
    evidence: { page: 1, figure_id: null, quote: "q" },
    ...overrides,
  };
}

const svg = [
  "<svg>",
  '<g data-node-id="a"><rect class="nd" x="0" y="0" width="10" height="10" stroke-dasharray=""/></g>',
  '<g data-node-id="b"><rect class="nd" x="0" y="0" width="10" height="10" stroke-dasharray="5 4"/></g>',
  '<g data-node-id="c"><polygon points="100,0 200,50 100,100 0,50"/></g>',
  '<path d="M400,400 L410,410" class="edge" stroke-dasharray="4 3"/>',
  "</svg>",
].join("");

describe("fitMethodologySvg", () => {
  it("dashes by provenance, not by engine kind", () => {
    const out = fitMethodologySvg(svg, [
      node({ id: "a", confidence: 0.5, evidence: null }),
      node({ id: "b", kind: "evaluation" }),
      node({ id: "c", kind: "decision", confidence: 0.5, evidence: null }),
    ]);

    expect(out).toContain(
      '<rect class="nd" x="0" y="0" width="10" height="10" stroke-dasharray="5 4"/>',
    );
    expect(out).toContain(
      '<polygon points="100,-10 240,50 100,110 -40,50" stroke-dasharray="5 4"/>',
    );
    expect(out).toContain(
      '<rect class="nd" x="0" y="0" width="10" height="10"/>',
    );
    // Distant feedback edge keeps its own dash.
    expect(out).toContain('<path d="M400,400 L410,410" class="edge" stroke-dasharray="4 3"/>');
  });

  it("bridges edge ends floating just off a diamond", () => {
    const withEdge = svg.replace(
      "</svg>",
      '<path d="M 250,50 C 260,50 270,60 280,60" class="edge"/></svg>',
    );
    const out = fitMethodologySvg(withEdge, [
      node({ id: "a" }),
      node({ id: "b" }),
      node({ id: "c", kind: "decision" }),
    ]);

    // Scaled diamond's right vertex is (240,50): stub reaches the border.
    expect(out).toContain("M 240,50 L 250,50 C 260,50 270,60 280,60");
  });

  it("bridges edges carrying marker-end like the engine emits", () => {
    const withEdge = svg.replace(
      "</svg>",
      '<path d="M 250,50 C 260,50 270,60 280,60" class="edge " marker-end="url(#ar)" /></svg>',
    );
    const out = fitMethodologySvg(withEdge, [
      node({ id: "a" }),
      node({ id: "b" }),
      node({ id: "c", kind: "decision" }),
    ]);

    // Regression: greedy d="..." used to capture marker-end="url(#ar)".
    expect(out).toContain("M 240,50 L 250,50 C 260,50 270,60 280,60");
  });

  it("bridges against translated engine diamonds", () => {
    const translated = [
      "<svg>",
      '<g data-node-id="c"><polygon points="0,-50 100,0 0,50 -100,0" transform="translate(200,300)"/></g>',
      '<path d="M 350,300 C 360,300 370,310 380,310" class="edge"/>',
      "</svg>",
    ].join("");
    const out = fitMethodologySvg(translated, [
      node({ id: "c", kind: "decision" }),
    ]);

    // Scaled right vertex: 200 + 100*1.4 = 340.
    expect(out).toContain("M 340,300 L 350,300 C 360,300 370,310 380,310");
  });

  it("leaves distant and interior edge ends alone", () => {
    const withEdges = svg.replace(
      "</svg>",
      '<path d="M 400,400 C 410,400 420,410 430,410" class="edge"/>'
        + '<path class="edge" d="M 100,50 C 110,50 120,60 400,400"/></svg>',
    );
    const out = fitMethodologySvg(withEdges, [
      node({ id: "a" }),
      node({ id: "b" }),
      node({ id: "c", kind: "decision" }),
    ]);

    expect(out).toContain("M 400,400 C 410,400 420,410 430,410");
    expect(out).toContain("M 100,50 C 110,50 120,60 400,400");
  });

  it("scales decision diamonds about their center", () => {
    const out = fitMethodologySvg(svg, [
      node({ id: "a" }),
      node({ id: "b" }),
      node({ id: "c", kind: "decision" }),
    ]);

    // Centroid (100,50); x1.4, y1.2.
    expect(out).toContain('<polygon points="100,-10 240,50 100,110 -40,50"');
  });
});

describe("markWhatIfNodes", () => {
  it("badges param nodes at the shape's top-right corner", () => {
    const out = markWhatIfNodes(svg, [
      node({ id: "a", params: { cells: 2000 } }),
      node({ id: "b" }),
      node({ id: "c", kind: "decision", params: { threshold: "0.5" } }),
    ]);
    // Rect node a: maxX 10, minY 0 -> badge at (-1,11).
    expect(out).toContain('<g data-node-id="a"><rect class="nd"');
    expect(out).toContain('transform="translate(-1,11)"');
    expect(out).toContain("Editable settings — click for the what-if editor");
    // Diamond node c: maxX 200, minY 0 -> badge at (189,11).
    expect(out).toContain('transform="translate(189,11)"');
    // Param-less node b stays unbadged: exactly two badges.
    expect(out.match(/class="whatif"/g)).toHaveLength(2);
  });

  it("offsets centered polygons by their translate transform", () => {
    const translated = svg.replace(
      '<g data-node-id="c"><polygon points="100,0 200,50 100,100 0,50"/></g>',
      '<g data-node-id="c"><polygon points="-50,-50 50,0 -50,50 -150,0" transform="translate(150,50)"/></g>',
    );
    const out = markWhatIfNodes(translated, [node({ id: "c", params: { t: 1 } })]);
    // Points maxX 50 + dx 150 = 200; minY -50 + dy 50 = 0.
    expect(out).toContain('transform="translate(189,11)"');
  });

  it("badges dataset and store path outlines from their M/L points", () => {
    const paths = [
      "<svg>",
      '<g data-node-id="d"><path d="M10,20 L96,20 L110,34 L110,80 L10,80 Z"/></g>',
      '<g data-node-id="s"><path d="M10,29 a50,9 0 0 1 100,0 L110,71 a50,9 0 0 1 -100,0 Z"/></g>',
      "</svg>",
    ].join("");
    const out = markWhatIfNodes(paths, [
      node({ id: "d", kind: "dataset", params: { rows: 5 } }),
      node({ id: "s", kind: "store", params: { rows: 5 } }),
    ]);
    // Dataset: maxX 110, minY 20 -> (99,31).
    expect(out).toContain('transform="translate(99,31)"');
    // Store: arc bulge ignored, M/L box (110,29) -> (99,40).
    expect(out).toContain('transform="translate(99,40)"');
  });

  it("leaves unreadable shapes unbadged", () => {
    const bare = '<svg><g data-node-id="a"><circle r="5"/></g></svg>';
    expect(markWhatIfNodes(bare, [node({ id: "a", params: { x: 1 } })])).toBe(bare);
    const curvy = '<svg><g data-node-id="a"><path d="M10,10 C20,20 30,30 40,40"/></g></svg>';
    // A lone moveto is no bounding box: unbadged, like the circle.
    expect(markWhatIfNodes(curvy, [node({ id: "a", params: { x: 1 } })])).toBe(curvy);
  });
});
