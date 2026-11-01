import { expect, test } from "@playwright/test";

test.use({ viewport: { width: 1600, height: 1000 } });

const graph = {
  schema_version: "1.0",
  project_id: "project-1",
  graph_id: "graph-1",
  version: 2,
  title: "Vision transformer",
  source_ids: ["paper-1"],
  nodes: [
    {
      id: "input",
      kind: "input",
      label: "Image",
      description: null,
      config: {},
      input_shape: null,
      output_shape: [null, 768],
      evidence: [],
      provenance: "verified",
      confidence: 0.99,
    },
    {
      id: "encoder",
      kind: "model",
      label: "Transformer encoder",
      description: null,
      config: { layers: 12 },
      input_shape: [null, 768],
      output_shape: [null, 768],
      evidence: [],
      provenance: "extracted",
      confidence: null,
    },
  ],
  edges: [
    {
      id: "e1",
      source: "input",
      target: "encoder",
      relation: "data_flow",
      label: null,
      evidence: [],
      provenance: "extracted",
    },
  ],
  created_by: "test",
  parent_version: 1,
};

const diagrams = {
  methodology: {
    version: 1,
    title: "E2E methodology",
    groups: [],
    nodes: [
      {
        id: "m-input",
        label: "Patch input",
        kind: "input",
        group: null,
        detail: null,
        params: {},
        confidence: 0.9,
        evidence: { page: 2, figure_id: null, quote: "Images are split into patches." },
      },
      {
        id: "m-encode",
        label: "Transformer encoder",
        kind: "model",
        group: null,
        detail: null,
        params: { layers: 12 },
        confidence: 0.95,
        evidence: { page: 4, figure_id: null, quote: "The encoder stacks twelve blocks." },
      },
      {
        id: "m-output",
        label: "Class output",
        kind: "output",
        group: null,
        detail: null,
        params: {},
        confidence: 0.4,
        evidence: null,
      },
    ],
    edges: [
      { from: "m-input", to: "m-encode", label: null, kind: "data" },
      { from: "m-encode", to: "m-output", label: null, kind: "data" },
    ],
  },
  circuits: [
    {
      version: 1,
      title: "E2E cell",
      source: { figure_id: "fig-1", page: 2 },
      components: [
        {
          id: "m1",
          type: "nmos",
          label: "M1",
          value: null,
          pins: { d: "n-out", g: "n-in", s: "n-vss" },
          pin_sides: null,
          placement: { x: 30, y: 40, rot: 0, mirror: false, flip: false },
          confidence: 0.9,
          evidence: { figure_id: "fig-1", bbox: [10, 20, 30, 40], quote: null },
        },
        {
          id: "r1",
          type: "resistor",
          label: "R1",
          value: "1k",
          pins: { a: "n-vdd", b: "n-out" },
          pin_sides: null,
          // Offset in x so a straight glide and a wire route differ.
          placement: { x: 75, y: 15, rot: 0, mirror: false, flip: false },
          confidence: 0.9,
          evidence: { figure_id: "fig-1", bbox: null, quote: null },
        },
      ],
      nets: [
        { id: "n-vdd", label: "VDD", role: "supply", global: true },
        { id: "n-vss", label: "VSS", role: "ground", global: true },
        { id: "n-in", label: "IN", role: "input", global: false },
        { id: "n-out", label: "OUT", role: "signal", global: false },
      ],
      ports: [],
      subcircuits: [],
      layout: null,
    },
  ],
  structure: {
    version: 1,
    title: "E2E chip",
    root: {
      id: "chip",
      label: "test chip",
      kind: "chip",
      count: null,
      dims: null,
      pos: null,
      part: null,
      tensor_shape: null,
      children: [
        {
          id: "arr",
          label: "cell array",
          kind: "array",
          count: { rows: 2, cols: 2 },
          dims: null,
          pos: null,
          part: null,
          tensor_shape: null,
          children: [
            {
              id: "cell",
              label: "cell",
              kind: "cell",
              count: null,
              dims: { w: 1, h: 1, d: 1, unit: null },
              pos: null,
              part: null,
              tensor_shape: null,
              children: [
                {
                  id: "part-nmos",
                  label: "NMOS pair",
                  kind: "part",
                  count: null,
                  dims: null,
                  pos: null,
                  part: null,
                  tensor_shape: null,
                  children: [],
                  confidence: 0.9,
                  evidence: { page: 4, figure_id: null, quote: "Cross-coupled NMOS pair." },
                },
                {
                  id: "part-pmos",
                  label: "PMOS pair",
                  kind: "part",
                  count: null,
                  dims: null,
                  pos: null,
                  part: null,
                  tensor_shape: null,
                  children: [],
                  confidence: 0.9,
                  evidence: { page: 4, figure_id: null, quote: "HVT PMOS pair." },
                },
              ],
              confidence: 0.9,
              evidence: { page: 5, figure_id: null, quote: "Each cell occupied 12 um2." },
            },
          ],
          confidence: 0.9,
          evidence: { page: 5, figure_id: null, quote: "Array of four cells." },
        },
      ],
      confidence: 1,
      evidence: null,
    },
  },
  validation: {
    methodology: { errors: [], warnings: [], stats: { nodes: 3, edges: 2, groups: 0 } },
    "circuit:fig-1": { errors: [], warnings: [], stats: { components: 2, nets: 4, ports: 0 } },
    structure: { errors: [], warnings: [], stats: { blocks: 5 } },
  },
  sources: {
    methodology: "text",
    "circuit:fig-1": "figure:fig-1",
    structure: "text",
  },
};

const thinDiagrams = {
  methodology: null,
  circuits: [],
  structure: null,
  validation: {},
  sources: {},
};

const figures = [
  {
    figure_id: "fig-1",
    project_id: "project-1",
    graph_id: "graph-1",
    source_id: "paper-1",
    created_by: "test",
    page: 2,
    label: "Figure 1",
    caption: "Model overview.",
    kind: "diagram",
    mime_type: "image/png",
    sha256: "0".repeat(64),
    byte_size: 42000,
    width: 800,
    height: 600,
    confidence: 0.9,
    regions: [
      {
        region_id: "fig-1-r1",
        figure_id: "fig-1",
        bbox: [0.1, 0.2, 0.3, 0.25],
        node_id: "encoder",
        label: "encoder stack",
        confidence: 0.8,
      },
    ],
  },
];

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/graphs/**/revisions/*", async (route) => {
    await route.fulfill({ json: graph });
  });
  await page.route("**/api/v1/papers/*/diagrams", async (route) => {
    await route.fulfill({ json: diagrams });
  });
  await page.route("**/api/v1/graphs/**/figures", async (route) => {
    await route.fulfill({ json: figures });
  });
  await page.route("**/api/v1/graphs/**/diff*", async (route) => {
    await route.fulfill({
      json: {
        project_id: "project-1",
        graph_id: "graph-1",
        base_version: 1,
        target_version: 2,
        added_nodes: [],
        removed_nodes: [],
        changed_nodes: [],
        added_edges: [],
        removed_edges: [],
        changed_edges: [],
      },
    });
  });
});

test("methodology tab renders the engine SVG and inspects a clicked node", async ({
  page,
}) => {
  await page.goto("/g/project-1/graph-1");
  await expect(page.getByRole("heading", { name: "Vision transformer" })).toBeVisible();
  const canvas = page.getByRole("group", { name: "Methodology diagram" });
  await expect(canvas.locator("[data-node-id]")).toHaveCount(3);
  await expect(page.getByText("2 from paper · 1 assumed")).toBeVisible();

  // Vertical by default (taller than wide), horizontal on request.
  const viewBox = (await canvas.locator("svg").getAttribute("viewBox")) ?? "";
  const [, , w, h] = viewBox.split(" ").map(Number);
  expect(h).toBeGreaterThan(w);
  await page.getByRole("group", { name: "Flow direction" }).getByRole("button", { name: "Horizontal" }).click();
  const wide = ((await canvas.locator("svg").getAttribute("viewBox")) ?? "").split(" ").map(Number);
  expect(wide[2]).toBeGreaterThan(wide[3]);
  await page.getByRole("group", { name: "Flow direction" }).getByRole("button", { name: "Vertical" }).click();

  await canvas.locator('[data-node-id="m-encode"] text').first().click();
  const inspector = page.getByRole("region", { name: "Inspector" });
  await expect(inspector).toContainText("The encoder stacks twelve blocks.");
  await expect(inspector).toContainText("from paper");
});

test("schematic tab renders without page errors and inspects a component", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(String(error)));
  await page.goto("/g/project-1/graph-1?view=schematic");
  const canvas = page.getByRole("group", { name: "Schematic diagram" });
  await expect(canvas.locator("[data-id]")).toHaveCount(2);

  await canvas.locator('[data-id="m1"]').click();
  const inspector = page.getByRole("region", { name: "Inspector" });
  await expect(inspector).toContainText("fig-1");
  // Every label carries a background halo so wires never swallow text.
  // String form: the e2e project has no DOM lib, so the browser-side
  // query stays out of the spec's type-checking.
  const paintOrder = await page.evaluate(
    "(() => { const label = document.querySelector(\"[aria-label='Schematic diagram'] .net\"); " +
      "return label ? getComputedStyle(label).paintOrder : null; })()",
  );
  expect(paintOrder).toBe("stroke");
  expect(errors).toEqual([]);
});

test("schematic walkthrough steps through the circuit in flow order", async ({
  page,
}) => {
  await page.goto("/g/project-1/graph-1?view=schematic");
  const walk = page.getByRole("group", { name: "Signal flow walkthrough" });
  await expect(walk.getByText("Step 1 of 2 — M1 (nmos)")).toBeVisible();
  // Mount already opened the first step; Next must follow the flow.
  await expect(page.getByRole("region", { name: "Inspector" })).toContainText("fig-1");
  await walk.getByRole("button", { name: "Next" }).click();
  await expect(walk.getByText("Step 2 of 2 — R1 (resistor)")).toBeVisible();
  await expect(page.getByRole("region", { name: "Inspector" })).toContainText("1k");
  await walk.getByRole("button", { name: "Previous" }).click();
  await expect(walk.getByText("Step 1 of 2 — M1 (nmos)")).toBeVisible();
});

test("walkthrough pulse travels along the wires, not straight", async ({
  page,
}) => {
  await page.goto("/g/project-1/graph-1?view=schematic");
  const walk = page.getByRole("group", { name: "Signal flow walkthrough" });
  await expect(walk.getByText("Step 1 of 2 — M1 (nmos)")).toBeVisible();
  await expect(page.getByTestId("flow-pulse")).toBeVisible();

  // String form: the e2e project has no DOM lib.
  const sampling = page.evaluate(
    "(async () => { const out = []; const t0 = performance.now(); " +
      "while (performance.now() - t0 < 1500) { " +
      "const el = document.querySelector('[data-testid=\"flow-pulse\"]'); " +
      "if (el) out.push([parseFloat(el.style.left), parseFloat(el.style.top)]); " +
      "await new Promise((r) => setTimeout(r, 40)); } return out; })()",
  );
  await walk.getByRole("button", { name: "Next" }).click();
  const samples = (await sampling) as [number, number][];
  expect(samples.length).toBeGreaterThan(8);

  let traveled = 0;
  for (let i = 1; i < samples.length; i++) {
    traveled += Math.hypot(
      samples[i][0] - samples[i - 1][0],
      samples[i][1] - samples[i - 1][1],
    );
  }
  expect(traveled).toBeGreaterThan(60);

  // A wire route bends at corners; a straight glide never leaves the chord.
  const [ax, ay] = samples[0];
  const [bx, by] = samples[samples.length - 1];
  const chord = Math.hypot(bx - ax, by - ay);
  let deviation = 0;
  for (const [x, y] of samples) {
    deviation = Math.max(
      deviation,
      Math.abs((bx - ax) * (ay - y) - (ax - x) * (by - ay)) / chord,
    );
  }
  expect(deviation).toBeGreaterThan(20);

  // ...and it still lands exactly on the next component.
  const stage = await page
    .getByRole("group", { name: "Schematic diagram" })
    .boundingBox();
  const target = await page.locator('[data-id="r1"]').boundingBox();
  if (!stage || !target) throw new Error("schematic must lay out");
  const [lx, ly] = samples[samples.length - 1];
  expect(
    Math.hypot(
      stage.x + lx - (target.x + target.width / 2),
      stage.y + ly - (target.y + target.height / 2),
    ),
  ).toBeLessThan(10);
});

test("tabs switch views and track the URL", async ({ page }) => {
  await page.goto("/g/project-1/graph-1");
  await expect(page.getByRole("group", { name: "Methodology diagram" })).toBeVisible();
  const toggle = page.getByRole("group", { name: "Canvas view" });
  await toggle.getByRole("button", { name: "Schematic" }).click();
  await expect(page).toHaveURL(/view=schematic/);
  await expect(page.getByRole("group", { name: "Schematic diagram" })).toBeVisible();
  await toggle.getByRole("button", { name: "Methodology" }).click();
  await expect(page).toHaveURL(/\/g\/project-1\/graph-1$/);
});

test("retired view ids resolve to the new tabs", async ({ page }) => {
  await page.goto("/g/project-1/graph-1?view=structure");
  await expect(page.getByRole("group", { name: "Methodology diagram" })).toBeVisible();
  await page.goto("/g/project-1/graph-1?view=floorplan");
  await expect(
    page.getByRole("application", { name: /3D structure/ }),
  ).toBeVisible();
});

test("3D tab renders the structure and inspects a clicked part", async ({ page }) => {
  await page.goto("/g/project-1/graph-1?view=3d");
  const toggle = page.getByRole("group", { name: "Structure scene" });
  await toggle.getByRole("button", { name: "Full structure" }).click();
  const stage = page.getByRole("application", { name: /3D structure/ });
  await expect(stage).toBeVisible();
  await expect(stage.locator("canvas")).toBeVisible();
  await expect(stage.getByText("cell array")).toBeVisible();

  await stage.locator("canvas").click();
  await expect(page.getByRole("region", { name: "Inspector" })).toContainText(
    "3D structure",
  );
});

test("3D circuit scene shows the schematic components with no board", async ({ page }) => {
  await page.goto("/g/project-1/graph-1?view=3d");
  const toggle = page.getByRole("group", { name: "Structure scene" });
  await toggle.getByRole("button", { name: "Circuit 3D" }).click();
  const circuitView = page.getByRole("application", { name: /E2E cell/ });
  await expect(circuitView).toBeVisible();
  await expect(circuitView.locator("canvas")).toBeVisible();
  await expect(circuitView.getByText("M1")).toBeVisible();
  await expect(circuitView.getByText("R1")).toBeVisible();
  await expect(page.getByText("Textbook structures per component type")).toBeVisible();
});

test("3D parts list spotlights a part into the Inspector", async ({ page }) => {
  await page.goto("/g/project-1/graph-1?view=3d");
  const parts = page.getByRole("group", { name: "Parts in this scene" });
  await parts.getByRole("button", { name: "M1" }).click();
  await expect(parts.getByRole("button", { name: "M1" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.getByRole("region", { name: "Inspector" })).toContainText("M1");
});

test("3D cell interior shows the parts inside one cell", async ({ page }) => {
  await page.goto("/g/project-1/graph-1?view=3d");
  const toggle = page.getByRole("group", { name: "Structure scene" });
  await toggle.getByRole("button", { name: "Cell interior" }).click();
  const detail = page.getByRole("application", { name: /cell \(detail\)/ });
  await expect(detail).toBeVisible();
  await expect(detail.locator("canvas")).toBeVisible();
  await expect(detail.getByText("NMOS pair")).toBeVisible();
  await expect(detail.getByText("PMOS pair")).toBeVisible();
});

test("thin IRs fall back to the paper figure, never a placeholder", async ({
  page,
}) => {
  await page.route("**/api/v1/papers/*/diagrams", async (route) => {
    await route.fulfill({ json: thinDiagrams });
  });
  await page.goto("/g/project-1/graph-1?view=schematic");
  await expect(page.getByText(/the paper's figures yielded nothing suitable/)).toBeVisible();
  await expect(page.getByAltText("Model overview.")).toBeVisible();
  await expect(page.locator("[aria-label='Canvas'] svg")).toHaveCount(0);

  // The fallback overlays stay clickable into the graph inspector.
  await page
    .getByRole("button", { name: "Region encoder stack, linked to Transformer encoder" })
    .click();
  await expect(page.getByRole("region", { name: "Inspector" })).toContainText(
    "Transformer encoder",
  );
});
