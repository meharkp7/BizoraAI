import { expect, test } from "@playwright/test";

test.use({ viewport: { width: 1600, height: 1000 } });

const WORKSPACE_URL = "/g/project-1/graph-1?v=2&view=3d";

const nodes = [
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
];

const edges = [
  {
    id: "e1",
    source: "input",
    target: "encoder",
    relation: "data_flow",
    label: null,
    evidence: [],
    provenance: "extracted",
  },
];

function graphAt(version: number) {
  return {
    schema_version: "1.0",
    project_id: "project-1",
    graph_id: "graph-1",
    version,
    title: "Vision transformer",
    source_ids: ["paper-1"],
    nodes,
    edges,
    created_by: "test",
    parent_version: version > 1 ? version - 1 : null,
  };
}

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/graphs/**/revisions/*", async (route) => {
    const url = route.request().url();
    if (url.endsWith("/layout") || route.request().method() !== "GET") {
      await route.fallback();
      return;
    }
    const version = Number(url.split("/revisions/")[1]);
    await route.fulfill({ json: graphAt(version) });
  });
  await page.route("**/api/v1/graphs/**/revisions/*/layout", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        json: { error: { code: "RESOURCE_NOT_FOUND", message: "No layout.", details: {} } },
        status: 404,
      });
    } else {
      await route.fulfill({ json: route.request().postDataJSON() });
    }
  });
  await page.route("**/api/v1/graphs/**/revisions/*/render-specs", async (route) => {
    const box = {
      parts: [
        {
          name: "body",
          vertices: [
            [-2.45, 0, -1.95],
            [2.45, 0, -1.95],
            [2.45, 1.75, -1.95],
            [-2.45, 1.75, -1.95],
            [-2.45, 0, 1.95],
            [2.45, 0, 1.95],
            [2.45, 1.75, 1.95],
            [-2.45, 1.75, 1.95],
          ],
          faces: [
            [0, 1, 2],
            [0, 2, 3],
            [4, 6, 5],
            [4, 7, 6],
            [0, 4, 5],
            [0, 5, 1],
            [2, 6, 7],
            [2, 7, 3],
            [0, 3, 7],
            [0, 7, 4],
            [1, 5, 6],
            [1, 6, 2],
          ],
        },
      ],
    };
    await route.fulfill({
      json: [
        {
          node_id: "input",
          label: "Embedding table",
          asset_uri: null,
          fallback_package: "soic-8",
          illustrative: true,
          mesh: box,
        },
        {
          node_id: "encoder",
          label: "Attention block",
          asset_uri: null,
          fallback_package: "soic-8",
          illustrative: true,
          mesh: box,
        },
      ],
    });
  });
  await page.route("**/api/v1/graphs/**/revisions/*/entities", async (route) => {
    await route.fulfill({
      json: {
        project_id: "project-1",
        graph_id: "graph-1",
        version: 2,
        classification: { domain: "deep-learning", confidence: 0.9, signals: ["transformer"] },
        entities: [
          {
            node_id: "input",
            domain: "deep-learning",
            entity_type: "embedding",
            display_label: "Embedding",
            generic: false,
            category: "layer",
            physical: true,
            symbol: "embedding",
            model_3d: null,
            interfaces: [{ name: "tensor", kind: "tensor", params: {} }],
            matched_terms: ["embedding"],
            confidence: 0.75,
          },
          {
            node_id: "encoder",
            domain: "deep-learning",
            entity_type: "attention-block",
            display_label: "Attention block",
            generic: false,
            category: "layer",
            physical: true,
            symbol: "attention",
            model_3d: null,
            interfaces: [{ name: "tensor", kind: "tensor", params: {} }],
            matched_terms: ["attention"],
            confidence: 0.75,
          },
        ],
      },
    });
  });
});

test("3D explorer renders without console errors and toggles views", async ({ page }) => {
  const problems: string[] = [];
  page.on("console", (message) => {
    // The missing-layout 404 is by design; the canvas falls back to auto-layout.
    if (message.type() === "error" && !message.text().includes("404")) {
      problems.push(message.text());
    }
  });
  page.on("pageerror", (error) => problems.push(String(error)));

  await page.goto(WORKSPACE_URL);
  await expect(page.getByRole("heading", { name: "Vision transformer" })).toBeVisible();
  const stage = page.getByRole("application", { name: /3D methodology graph/ });
  await expect(stage).toBeVisible();
  await expect(stage.locator("canvas")).toHaveCount(1);
  // Tags stay hidden until hover or selection so dense graphs stay legible.
  // Exact text isolates the floating tags from the legend rows beneath.
  await expect(stage.getByText("Image", { exact: true })).toBeHidden();
  await expect(stage.getByText("Transformer encoder", { exact: true })).toBeHidden();
  expect(problems).toEqual([]);

  // Toggle back to Structure through the toolbar control.
  await page.getByRole("group", { name: "Canvas view" }).getByRole("button", { name: "Structure" }).click();
  await expect(page.locator(".react-flow__node")).toHaveCount(2);
  expect(problems).toEqual([]);
});

test("3D list selection syncs to the inspector", async ({ page }) => {
  await page.goto(WORKSPACE_URL);
  const stage = page.getByRole("application", { name: /3D methodology graph/ });
  await expect(stage).toBeVisible();

  await page.locator("ul[aria-label='Graph nodes'] li").nth(1).click();
  await expect(page.getByRole("button", { name: "Replace component" })).toBeVisible();
  await expect(stage.getByText("Transformer encoder", { exact: true })).toBeVisible();
});

test("3D legend shows the domain and part key", async ({ page }) => {
  await page.goto(WORKSPACE_URL);
  const stage = page.getByRole("application", { name: /3D methodology graph/ });
  await expect(stage).toBeVisible();
  const legend = stage.getByRole("complementary", { name: "3D part key" });
  await expect(legend).toBeVisible();
  await expect(legend.getByText(/Deep learning · 90% confidence/)).toBeVisible();
  const rows = legend.locator("li");
  await expect(rows).toHaveCount(2);
  await expect(rows.nth(0)).toContainText("Embedding table");
  await expect(rows.nth(0)).toContainText("illustrative");
  await expect(rows.nth(1)).toContainText("Attention block");
  await expect(rows.nth(1)).toContainText("Transformer encoder");
  await expect(rows.nth(1)).toContainText("Attention Block");
});

test("3D shows a gesture hint and tags for selected connections", async ({ page }) => {
  await page.goto(WORKSPACE_URL);
  const stage = page.getByRole("application", { name: /3D methodology graph/ });
  await expect(stage).toBeVisible();
  await expect(stage.getByText("Drag to orbit")).toBeVisible();

  await page.locator("ul[aria-label='Graph edges'] li").first().click();
  await expect(stage.getByText("input → encoder")).toBeVisible();
});

test("3D swaps in package visuals and reports provenance counts", async ({ page }) => {
  await page.goto(WORKSPACE_URL);
  const stage = page.getByRole("application", { name: /3D methodology graph/ });
  await expect(stage).toBeVisible();
  const legend = stage.getByRole("complementary", { name: "3D part key" });
  await expect(legend.getByText("3D models: 0 measured · 2 illustrative")).toBeVisible();
});
