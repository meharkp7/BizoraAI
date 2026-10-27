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
  await expect(stage.getByText("Image")).toBeHidden();
  await expect(stage.getByText("Transformer encoder")).toBeHidden();
  expect(problems).toEqual([]);

  // Toggle back to 2D through the toolbar control.
  await page.getByRole("group", { name: "Canvas view" }).getByRole("button", { name: "2D" }).click();
  await expect(page.locator(".react-flow__node")).toHaveCount(2);
  expect(problems).toEqual([]);
});

test("3D list selection syncs to the inspector", async ({ page }) => {
  await page.goto(WORKSPACE_URL);
  const stage = page.getByRole("application", { name: /3D methodology graph/ });
  await expect(stage).toBeVisible();

  await page.locator("ul[aria-label='Graph nodes'] li").nth(1).click();
  await expect(page.getByRole("button", { name: "Replace component" })).toBeVisible();
  await expect(stage.getByText("Transformer encoder")).toBeVisible();
});

test("3D shows a gesture hint and tags for selected connections", async ({ page }) => {
  await page.goto(WORKSPACE_URL);
  const stage = page.getByRole("application", { name: /3D methodology graph/ });
  await expect(stage).toBeVisible();
  await expect(stage.getByText("Drag to orbit")).toBeVisible();

  await page.locator("ul[aria-label='Graph edges'] li").first().click();
  await expect(stage.getByText("input → encoder")).toBeVisible();
});
