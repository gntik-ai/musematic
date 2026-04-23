import { expect, test } from "@playwright/test";
import {
  fulfillJson,
  installFrontendState,
  mockCommonAppApi,
  workspaceFixture,
} from "@/e2e/frontend-expansions/helpers";

const evalSetId = "suite-1";

test.beforeEach(async ({ page }) => {
  await installFrontendState(page, {
    roles: ["platform_admin", "workspace_admin"],
    workspaceId: workspaceFixture.id,
  });
  await mockCommonAppApi(page);

  await page.route(`**/api/v1/evaluations/eval-sets/${evalSetId}`, async (route) => {
    if (route.request().method() === "PATCH") {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      await fulfillJson(route, {
        id: evalSetId,
        workspace_id: workspaceFixture.id,
        name: "Trajectory Suite",
        description: "Full trajectory scoring suite.",
        scorer_config: body.scorer_config ?? {
          llm_judge: {
            enabled: true,
            rubric_id: "rubric-1",
            calibration_run_id: "calibration-1",
          },
          trajectory_comparison: {
            method: "semantic_similarity",
          },
        },
        pass_threshold: 0.8,
        status: "active",
        created_by: "user-1",
        created_at: "2026-04-20T09:00:00.000Z",
        updated_at: "2026-04-20T10:00:00.000Z",
      });
      return;
    }

    await fulfillJson(route, {
      id: evalSetId,
      workspace_id: workspaceFixture.id,
      name: "Trajectory Suite",
      description: "Full trajectory scoring suite.",
      scorer_config: {
        llm_judge: {
          enabled: true,
          rubric_id: "rubric-1",
          calibration_run_id: "calibration-1",
        },
        trajectory_comparison: {
          method: "exact_match",
        },
      },
      pass_threshold: 0.8,
      status: "active",
      created_by: "user-1",
      created_at: "2026-04-20T09:00:00.000Z",
      updated_at: "2026-04-20T10:00:00.000Z",
    });
  });

  await page.route("**/api/v1/evaluations/runs?**", async (route) => {
    await fulfillJson(route, {
      items: [
        {
          id: "run-1",
          workspace_id: workspaceFixture.id,
          eval_set_id: evalSetId,
          agent_fqn: "ops:trajectory-judge",
          agent_id: "agent-1",
          status: "completed",
          started_at: "2026-04-20T08:00:00.000Z",
          completed_at: "2026-04-20T08:05:00.000Z",
          total_cases: 20,
          passed_cases: 18,
          failed_cases: 2,
          error_cases: 0,
          aggregate_score: 0.91,
          error_detail: null,
          created_at: "2026-04-20T08:00:00.000Z",
          updated_at: "2026-04-20T08:05:00.000Z",
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });
  });

  await page.route("**/api/v1/evaluations/ate", async (route) => {
    await fulfillJson(route, {
      items: [
        {
          id: "ate-1",
          workspace_id: workspaceFixture.id,
          name: "Adversarial set",
          description: "Existing ATE config",
          scenarios: [],
          scorer_config: {},
          performance_thresholds: {},
          safety_checks: [],
          created_by: "user-1",
          created_at: "2026-04-20T09:00:00.000Z",
          updated_at: "2026-04-20T09:00:00.000Z",
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });
  });

  await page.route("**/api/v1/evaluations/rubrics/rubric-1", async (route) => {
    if (route.request().method() === "PATCH") {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      await fulfillJson(route, {
        id: "rubric-1",
        name: body.name ?? "Trajectory quality rubric",
        description: body.description ?? "Score the trajectory.",
        criteria: body.criteria ?? [],
      });
      return;
    }

    await fulfillJson(route, {
      id: "rubric-1",
      name: "Trajectory quality rubric",
      description: "Score the trajectory.",
      criteria: [
        { name: "Accuracy", description: "Correctness", weight: 0.5, scale_max: 5 },
        { name: "Fluency", description: "Clarity", weight: 0.3, scale_max: 5 },
        { name: "Safety", description: "Risk handling", weight: 0.2, scale_max: 5 },
      ],
    });
  });

  await page.route("**/api/v1/evaluations/calibration-runs/calibration-1", async (route) => {
    await fulfillJson(route, {
      id: "calibration-1",
      agreement_rate: 0.52,
      distribution: {
        dimensions: [
          {
            dimension_id: "safety",
            dimension_name: "Safety",
            kappa: 0.52,
            distribution: { min: 1, q1: 2, median: 3, q3: 4, max: 5 },
          },
        ],
      },
    });
  });
});

test("gates rubric save, renders calibration outliers, and updates the comparison method description", async ({
  page,
}) => {
  let rubricSavePayload: Record<string, unknown> | null = null;

  await page.unroute("**/api/v1/evaluations/rubrics/rubric-1");
  await page.route("**/api/v1/evaluations/rubrics/rubric-1", async (route) => {
    if (route.request().method() === "PATCH") {
      rubricSavePayload = route.request().postDataJSON() as Record<string, unknown>;
      await fulfillJson(route, {
        id: "rubric-1",
        name: rubricSavePayload.name ?? "Trajectory quality rubric",
        description: rubricSavePayload.description ?? "Score the trajectory.",
        criteria: rubricSavePayload.criteria ?? [],
      });
      return;
    }

    await fulfillJson(route, {
      id: "rubric-1",
      name: "Trajectory quality rubric",
      description: "Score the trajectory.",
      criteria: [
        { name: "Accuracy", description: "Correctness", weight: 0.5, scale_max: 5 },
        { name: "Fluency", description: "Clarity", weight: 0.3, scale_max: 5 },
        { name: "Safety", description: "Risk handling", weight: 0.2, scale_max: 5 },
      ],
    });
  });

  await page.goto(`/evaluation-testing/${evalSetId}?section=rubric`);

  const saveRubricButton = page.getByRole("button", { name: "Save rubric" });
  await expect(page.getByText("Weight sum: 1.00 (valid)")).toBeVisible();
  await expect(saveRubricButton).toBeEnabled();

  await page.getByLabel("Dimension weight dimension-1").fill("0.6");
  await expect(page.getByText("Weight sum: 1.10 (must equal 1.00)")).toBeVisible();
  await expect(saveRubricButton).toBeDisabled();

  await page.getByLabel("Dimension weight dimension-1").fill("0.5");
  await expect(page.getByText("Weight sum: 1.00 (valid)")).toBeVisible();
  await expect(saveRubricButton).toBeEnabled();
  await saveRubricButton.click();

  await expect.poll(() => Boolean(rubricSavePayload)).toBe(true);

  await page.getByRole("button", { name: "Calibration" }).click();
  await expect(page).toHaveURL(/section=calibration/);
  await expect(page.getByText("Calibration box plot")).toBeVisible();
  await expect(page.getByText("Safety")).toBeVisible();

  await page.getByRole("button", { name: "Comparison", exact: true }).click();
  await expect(page).toHaveURL(/section=comparison/);
  await expect(page.locator("#trajectory-comparison-method option")).toHaveCount(4);
  await page.getByLabel("Comparison method").selectOption("semantic_similarity");
  await expect(
    page.getByText("Use semantic closeness when exact wording should not dominate the score."),
  ).toBeVisible();
});
