import { expect, test } from "@playwright/test";
import {
  fulfillJson,
  installFrontendState,
  mockCommonAppApi,
  workspaceFixture,
} from "@/e2e/frontend-expansions/helpers";

const executionId = "exec-trajectory-1";

function buildTraceSteps() {
  const trajectorySteps = Array.from({ length: 150 }, (_, index) => ({
    step_number: index + 1,
    type: "analysis",
    agent_fqn: `ops:worker-${((index % 3) + 1).toString()}`,
    content: `Trajectory step ${index + 1} summary.`,
    tool_call: null,
    quality_score:
      index + 1 === 75 ? 0.85 : index % 3 === 0 ? 0.82 : index % 3 === 1 ? 0.68 : 0.42,
    tokens_used: 20 + index,
    duration_ms: 120 + index,
    timestamp: `2026-04-20T10:${String(index % 60).padStart(2, "0")}:00.000Z`,
  }));

  return [
    ...trajectorySteps,
    {
      step_number: 151,
      type: "support",
      agent_fqn: "ops:debater-a",
      content: "Approve the rollback and keep the compliance branch active.",
      tool_call: null,
      quality_score: 0.74,
      tokens_used: 61,
      duration_ms: 220,
      timestamp: "2026-04-20T12:31:00.000Z",
    },
    {
      step_number: 152,
      type: "oppose",
      agent_fqn: null,
      content: "The deleted agent disagreed with the rollback proposal.",
      tool_call: null,
      quality_score: 0.58,
      tokens_used: 49,
      duration_ms: 205,
      timestamp: "2026-04-20T12:32:00.000Z",
    },
    {
      step_number: 153,
      type: "synthesis",
      agent_fqn: "ops:judge",
      content: "Consensus reached after weighting compliance risk.",
      tool_call: null,
      quality_score: 0.81,
      tokens_used: 45,
      duration_ms: 180,
      timestamp: "2026-04-20T12:33:00.000Z",
    },
    {
      step_number: 154,
      type: "thought",
      agent_fqn: "ops:reactor",
      content: "Inspect the policy exception and decide whether rollback is safe.",
      tool_call: null,
      quality_score: 0.77,
      tokens_used: 33,
      duration_ms: 110,
      timestamp: "2026-04-20T12:34:00.000Z",
    },
    {
      step_number: 155,
      type: "action",
      agent_fqn: "ops:reactor",
      content: "Invoke the checkpoint rollback tool.",
      tool_call: {
        tool: "checkpoint.rollback",
        args: {
          checkpoint_id: "checkpoint-2",
        },
      },
      quality_score: 0.73,
      tokens_used: 26,
      duration_ms: 95,
      timestamp: "2026-04-20T12:35:00.000Z",
    },
    {
      step_number: 156,
      type: "observation",
      agent_fqn: "ops:reactor",
      content: "Checkpoint rollback is allowed under the current workspace policy.",
      tool_call: null,
      quality_score: 0.79,
      tokens_used: 22,
      duration_ms: 90,
      timestamp: "2026-04-20T12:36:00.000Z",
    },
  ];
}

test.beforeEach(async ({ page }) => {
  await installFrontendState(page, {
    roles: ["platform_admin", "workspace_admin", "agent_operator"],
    workspaceId: workspaceFixture.id,
  });
  await mockCommonAppApi(page);

  await page.route(`**/api/v1/executions/${executionId}`, async (route) => {
    await fulfillJson(route, {
      id: executionId,
      workflowName: "Fraud trajectory review",
      workflow_name: "Fraud trajectory review",
      agentFqn: "ops:trajectory-lead",
      agent_fqn: "ops:trajectory-lead",
      currentStepLabel: "Assess rollback viability",
      current_step_label: "Assess rollback viability",
      status: "running",
      startedAt: "2026-04-20T10:00:00.000Z",
      started_at: "2026-04-20T10:00:00.000Z",
    });
  });

  await page.route(`**/api/v1/executions/${executionId}/reasoning-trace?**`, async (route) => {
    await fulfillJson(route, {
      execution_id: executionId,
      technique: "TRACE",
      status: "completed",
      total_tokens: 6120,
      compute_budget_used: 0.74,
      effective_budget_scope: "workflow",
      compute_budget_exhausted: false,
      consensus_reached: true,
      stabilized: true,
      degradation_detected: false,
      last_updated_at: "2026-04-20T12:36:00.000Z",
      steps: buildTraceSteps(),
    });
  });

  await page.route(`**/api/v1/executions/${executionId}/checkpoints?**`, async (route) => {
    await fulfillJson(route, {
      items: [
        {
          id: "checkpoint-1",
          execution_id: executionId,
          checkpoint_number: 1,
          created_at: "2026-04-20T10:10:00.000Z",
          superseded: true,
          policy_snapshot: { type: "every_step" },
        },
        {
          id: "checkpoint-2",
          execution_id: executionId,
          checkpoint_number: 2,
          created_at: "2026-04-20T10:15:00.000Z",
          superseded: false,
          policy_snapshot: { type: "named_steps" },
        },
        {
          id: "checkpoint-3",
          execution_id: executionId,
          checkpoint_number: 3,
          created_at: "2026-04-20T10:20:00.000Z",
          superseded: false,
          policy_snapshot: { type: "pre_tool" },
        },
      ],
      total: 3,
      page: 1,
      page_size: 100,
    });
  });
});

test("renders the execution trajectory drill-down with checkpoints, debate, and ReAct traces", async ({
  page,
}) => {
  let rollbackRequest: { checkpointNumber: number; body: Record<string, unknown> | null } | null = null;

  await page.route(`**/api/v1/executions/${executionId}/rollback/*`, async (route) => {
    const checkpointNumber = Number(route.request().url().split("/").at(-1) ?? "0");
    rollbackRequest = {
      checkpointNumber,
      body: (route.request().postDataJSON() as Record<string, unknown> | null) ?? null,
    };
    await fulfillJson(route, { status: "accepted" }, 202);
  });

  await page.goto(`/operator/executions/${executionId}?step=75`);

  await expect(page.getByRole("heading", { name: "Execution Drill-Down" })).toBeVisible();
  await expect(page.getByText("Showing")).toBeVisible();
  await expect(page.locator('[data-testid="trajectory-step-highlight-75"]')).toBeVisible();
  await expect(page.locator('[data-testid="trajectory-step-highlight-75"]')).toContainText("High efficiency");

  const renderedStepCount = await page.locator('text=/^Step \\d+$/').count();
  expect(renderedStepCount).toBeLessThan(60);

  await page.getByRole("button", { name: "Checkpoints" }).click();
  await expect(page.getByRole("button", { name: "Roll back" })).toHaveCount(3);
  await page.getByRole("button", { name: "Roll back" }).nth(1).click();
  await expect(page.getByText("Roll back to checkpoint #2")).toBeVisible();
  await page.getByPlaceholder("checkpoint-2").fill("checkpoint-2");
  await page.getByRole("button", { name: "Roll back" }).last().click();

  await expect.poll(() => rollbackRequest?.checkpointNumber ?? null).toBe(2);

  await page.getByRole("button", { name: "Debate" }).click();
  await expect(page.getByText("Agent no longer exists")).toBeVisible();
  await expect(page.getByText("Approve the rollback and keep the compliance branch active.")).toBeVisible();

  await page.getByRole("button", { name: "ReAct" }).click();
  await expect(page.getByText("Cycle 1")).toBeVisible();
  await page.getByRole("button", { name: "Thought" }).first().click();
  await expect(page.getByText("Inspect the policy exception and decide whether rollback is safe.")).toBeVisible();
  await page.getByRole("button", { name: "Action" }).first().click();
  await expect(page.getByText('"checkpoint_id": "checkpoint-2"')).toBeVisible();
  await page.getByRole("button", { name: "Observation" }).first().click();
  await expect(page.getByText("Checkpoint rollback is allowed under the current workspace policy.")).toBeVisible();
});
