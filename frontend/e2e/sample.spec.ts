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
  ],
  edges: [],
  created_by: "test",
  parent_version: 1,
};

test("sample paper opens its seeded workspace", async ({ page }) => {
  await page.route("**/api/v1/papers/sample", async (route) => {
    await route.fulfill({
      json: {
        project_id: "project-1",
        graph_id: "graph-1",
        source_id: "paper-1",
        title: "Vision transformer",
        workspace_path: "/g/project-1/graph-1",
        available: true,
      },
    });
  });
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

  await page.goto("/");
  const section = page.getByRole("region", { name: "Sample paper" });
  await section.getByRole("link", { name: /Vision transformer/ }).click();

  await expect(page).toHaveURL(/\/g\/project-1\/graph-1$/);
  await expect(page.getByRole("heading", { name: "Vision transformer" })).toBeVisible();
});

test("sample paper explains an unseeded workspace", async ({ page }) => {
  await page.route("**/api/v1/papers/sample", async (route) => {
    await route.fulfill({
      json: {
        project_id: "project-1",
        graph_id: "graph-1",
        source_id: "paper-1",
        title: "Vision transformer",
        workspace_path: "/g/project-1/graph-1",
        available: false,
      },
    });
  });

  await page.goto("/");
  const section = page.getByRole("region", { name: "Sample paper" });
  await expect(section.getByText(/not seeded yet/)).toBeVisible();
  await expect(section.getByText("scripts/seed_sample_paper.py")).toBeVisible();
});
