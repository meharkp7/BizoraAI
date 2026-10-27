import { expect, test } from "@playwright/test";

// Wide viewport: the floating minimap must not cover the small fixture graph.
test.use({ viewport: { width: 1600, height: 1000 } });

const WORKSPACE_URL = "/g/project-1/graph-1?v=2";

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

const emptyDiff = {
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
};

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
  await page.route("**/api/v1/graphs/**/patch-batches", async (route) => {
    const batch = (route.request().postDataJSON()) as { patches: { base_version: number }[] };
    const base = batch.patches[0]?.base_version ?? 1;
    await route.fulfill({ json: graphAt(base + 1), status: 201 });
  });
  await page.route("**/api/v1/graphs/**/patches", async (route) => {
    const patch = (route.request().postDataJSON()) as { base_version: number };
    await route.fulfill({ json: graphAt(patch.base_version + 1), status: 201 });
  });
  await page.route("**/api/v1/graphs/**/diff*", async (route) => {
    await route.fulfill({ json: emptyDiff });
  });
});

test("canvas renders nodes and edges", async ({ page }) => {
  await page.goto(WORKSPACE_URL);
  await expect(page.getByRole("heading", { name: "Vision transformer" })).toBeVisible();
  await expect(page.locator(".react-flow__node")).toHaveCount(2);
  await expect(page.locator(".react-flow__edge")).toHaveCount(1);
});

test("dragging a node persists the layout", async ({ page }) => {
  await page.goto(WORKSPACE_URL);
  const node = page.locator('[data-id="input"]');
  await expect(node).toBeVisible();

  const box = await node.boundingBox();
  if (!box) throw new Error("node has no bounding box");
  const putPromise = page.waitForResponse("**/revisions/2/layout");
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 120, box.y + box.height / 2 + 60, { steps: 12 });
  await page.mouse.up();

  const put = await putPromise;
  expect(put.request().method()).toBe("PUT");
  const body = (put.request().postDataJSON()) as {
    positions: { node_id: string; x: number; y: number }[];
    viewport: { x: number; y: number; zoom: number };
  };
  const input = body.positions.find((position) => position.node_id === "input");
  expect(input).toBeDefined();
  // Screen drag of (120, 60) maps through the fitted zoom level.
  const zoom = body.viewport.zoom;
  expect(Math.abs((input?.x ?? 0) - 120 / zoom)).toBeLessThan(15);
  expect(Math.abs((input?.y ?? 0) - 60 / zoom)).toBeLessThan(15);
  await expect(page.getByText("Layout saved")).toBeVisible();
});

test("connecting handles creates an edge revision", async ({ page }) => {
  await page.goto(WORKSPACE_URL);
  await expect(page.locator(".react-flow__node")).toHaveCount(2);

  const postPromise = page.waitForResponse("**/graphs/project-1/graph-1/patches");
  await page.locator('[data-id="input"] .react-flow__handle.source').hover();
  await page.mouse.down();
  await page.locator('[data-id="encoder"] .react-flow__handle.target').hover();
  await page.mouse.up();

  const post = await postPromise;
  const body = (post.request().postDataJSON()) as {
    operation: string;
    payload: { edge: { source: string; target: string } };
  };
  expect(body.operation).toBe("add_edge");
  expect(body.payload.edge).toMatchObject({ source: "input", target: "encoder" });
  await expect(page.getByText("Saved as revision 3.")).toBeVisible();
});

test("delete key removes a node with its edges atomically", async ({ page }) => {
  await page.goto(WORKSPACE_URL);
  await expect(page.locator(".react-flow__node")).toHaveCount(2);

  const postPromise = page.waitForResponse("**/patch-batches");
  await page.locator('[data-id="encoder"]').click();
  await page.keyboard.press("Delete");

  const post = await postPromise;
  const body = (post.request().postDataJSON()) as { patches: { operation: string }[] };
  expect(body.patches.map((patch) => patch.operation)).toEqual(["remove_edge", "remove_node"]);
  await expect(page.getByText("Saved as revision 3.")).toBeVisible();
});

test("patch rejection shows the error banner", async ({ page }) => {
  await page.route("**/api/v1/graphs/**/patches", async (route) => {
    await route.fulfill({
      json: {
        error: {
          code: "INVALID_GRAPH_PATCH",
          message: "The patch would produce an invalid methodology graph.",
          details: {},
        },
      },
      status: 422,
    });
  });
  await page.goto(WORKSPACE_URL);
  await expect(page.locator(".react-flow__node")).toHaveCount(2);

  await page.locator('[data-id="input"] .react-flow__handle.source').hover();
  await page.mouse.down();
  await page.locator('[data-id="encoder"] .react-flow__handle.target').hover();
  await page.mouse.up();

  await expect(page.getByRole("alert")).toContainText("INVALID_GRAPH_PATCH");
});
