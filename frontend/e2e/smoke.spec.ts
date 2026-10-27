import { expect, test } from "@playwright/test";

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
      evidence: [
        {
          source_id: "paper-1",
          page: 4,
          quote: "The encoder stacks twelve blocks.",
          figure_label: null,
          bbox: null,
          locator: null,
          status: "supported",
        },
      ],
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

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/graphs/**/revisions/*", async (route) => {
    await route.fulfill({ json: graph });
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

test("home opens a workspace from IDs", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /made testable/ })).toBeVisible();
  await page.getByPlaceholder("e.g. vit-paper").fill("project-1");
  await page.getByPlaceholder("e.g. vit-base").fill("graph-1");
  await page.getByRole("button", { name: "Open workspace" }).click();
  await expect(page).toHaveURL(/\/g\/project-1\/graph-1$/);
  await expect(page.getByRole("heading", { name: "Vision transformer" })).toBeVisible();
});

test("workspace selects a node and shows its evidence", async ({ page }) => {
  await page.goto("/g/project-1/graph-1");
  await expect(page.getByRole("heading", { name: "Vision transformer" })).toBeVisible();
  await page.getByRole("list", { name: "Graph nodes" }).getByRole("button", {
    name: /Transformer encoder/,
  }).click();
  await expect(page.getByRole("region", { name: "Evidence" })).toContainText(
    "The encoder stacks twelve blocks.",
  );
});

test("theme toggle persists across reloads", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});

test("unknown routes explain themselves", async ({ page }) => {
  await page.goto("/nope");
  await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();
});
