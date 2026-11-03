import { expect, test } from "@playwright/test";

test("quality dashboard shows last eval scores", async ({ page }) => {
  await page.route("**/api/v1/quality/summary", async (route) => {
    await route.fulfill({
      json: {
        generated_at: "2026-11-02T10:00:00+00:00",
        diagram_evals: [
          {
            paper_id: "sram-puf-tilting",
            recorded_at: "2026-10-30T07:53:10+00:00",
            validator_pass_rate: 1.0,
            error_count: 0,
            warning_count: 1,
            input_tokens: 37603,
            output_tokens: 15160,
            provider_calls: 4,
            gold_present: false,
            classification_kind: "circuit",
          },
        ],
        copilot_eval: {
          total: 30,
          passed: 29,
          citation_accuracy: 0.97,
          citation_recall: 1.0,
          writes_detected: false,
          input_tokens: 10,
          output_tokens: 5,
          recorded_at: "2026-11-01T18:25:35+00:00",
        },
      },
    });
  });
  await page.route("**/api/v1/papers/sample", async (route) => {
    await route.fulfill({
      json: {
        project_id: "project-1",
        graph_id: "graph-1",
        source_id: "paper-1",
        title: "Sample",
        workspace_path: "/g/project-1/graph-1",
        available: false,
      },
    });
  });

  await page.goto("/quality");

  await expect(page).toHaveURL(/\/quality$/);
  await expect(page.getByText("29 of 30")).toBeVisible();
  await expect(page.getByText("sram-puf-tilting")).toBeVisible();
});

test("quality dashboard admits missing evals", async ({ page }) => {
  await page.route("**/api/v1/quality/summary", async (route) => {
    await route.fulfill({
      json: { generated_at: "2026-11-02T10:00:00+00:00", diagram_evals: [], copilot_eval: null },
    });
  });

  await page.goto("/quality");
  await expect(page.getByText("Copilot eval has not run yet.")).toBeVisible();
  await expect(page.getByText("No diagram evals yet.")).toBeVisible();
});
