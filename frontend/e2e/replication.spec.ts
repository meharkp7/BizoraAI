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

const history = [
  {
    version: 1,
    parent_version: null,
    title: "Vision transformer",
    created_by: "test",
    created_at: "2026-01-01T00:00:00Z",
  },
  {
    version: 2,
    parent_version: 1,
    title: "Vision transformer",
    created_by: "test",
    created_at: "2026-01-02T00:00:00Z",
  },
];

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/graphs/project-1/graph-1/revisions", async (route) => {
    await route.fulfill({ json: history });
  });
  await page.route("**/api/v1/graphs/**/revisions/*", async (route) => {
    await route.fulfill({ json: graph });
  });
  await page.route("**/api/v1/projects/*/graphs/*/replication-plan", async (route) => {
    await route.fulfill({
      json: {
        project_id: "project-1",
        graph_id: "graph-1",
        version: 2,
        steps: [
          {
            seq: 1,
            node_id: "input",
            label: "Image",
            kind: "input",
            action: "Provide input 'Image' (input).",
            verify: ["Confirm the input format matches the paper's description."],
          },
        ],
      },
    });
  });
});

test("workspace shows the replication checklist and tracks progress", async ({ page }) => {
  await page.goto("/g/project-1/graph-1?v=2");
  await expect(page.getByRole("heading", { name: "Vision transformer" })).toBeVisible();

  const panel = page.getByRole("region", { name: "Replication plan" });
  await expect(panel.getByText("Provide input 'Image' (input).")).toBeVisible();
  await expect(panel.getByText("0 of 1 steps done")).toBeVisible();

  await panel.getByRole("checkbox", { name: "Step 1: Image" }).check();
  await expect(panel.getByText("1 of 1 steps done")).toBeVisible();
});

test("replication plan points at the agent voice chat", async ({ page }) => {
  await page.goto("/g/project-1/graph-1?v=2");

  const panel = page.getByRole("region", { name: "Replication plan" });
  await expect(panel.getByText("0 of 1 steps done")).toBeVisible();
  await expect(panel.getByText(/Talk through this build hands-free/)).toBeVisible();
  await expect(panel.getByRole("button", { name: "Narrate build" })).toBeHidden();
});
