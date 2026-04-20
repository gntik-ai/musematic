import { expect, test } from "@playwright/test";
import {
  emitFrontendWsEvent,
  fulfillJson,
  installFrontendState,
  installFrontendWs,
  mockCommonAppApi,
  workspaceFixture,
} from "@/e2e/frontend-expansions/helpers";

const agents = [
  {
    fqn: "risk:fraud-monitor",
    namespace: "risk",
    local_name: "fraud-monitor",
    name: "Fraud Monitor",
    maturity_level: "production",
    status: "active",
    revision_count: 3,
    latest_revision_number: 3,
    updated_at: "2026-04-20T10:00:00.000Z",
    workspace_id: workspaceFixture.id,
  },
  {
    fqn: "ops:verdict-authority",
    namespace: "ops",
    local_name: "verdict-authority",
    name: "Verdict Authority",
    maturity_level: "production",
    status: "active",
    revision_count: 2,
    latest_revision_number: 2,
    updated_at: "2026-04-20T10:05:00.000Z",
    workspace_id: workspaceFixture.id,
  },
  {
    fqn: "ops:large-worker",
    namespace: "ops",
    local_name: "large-worker",
    name: "Large Worker",
    maturity_level: "production",
    status: "active",
    revision_count: 1,
    latest_revision_number: 1,
    updated_at: "2026-04-20T10:10:00.000Z",
    workspace_id: workspaceFixture.id,
  },
];

test.beforeEach(async ({ page }) => {
  await installFrontendState(page, {
    roles: ["platform_admin", "workspace_admin"],
    workspaceId: workspaceFixture.id,
  });
  await installFrontendWs(page);
  await mockCommonAppApi(page);

  await page.route("**/api/v1/dashboard/metrics", async (route) => {
    await fulfillJson(route, {
      active_executions: 12,
      queued_steps: 41,
      pending_approvals: 3,
      recent_failures: 2,
      avg_latency_ms: 6,
      fleet_health_score: 91,
      computed_at: "2026-04-20T10:00:00.000Z",
    });
  });

  await page.route("**/health", async (route) => {
    await fulfillJson(route, {
      status: "healthy",
      uptime_seconds: 172800,
      dependencies: {
        postgresql: { status: "healthy", latency_ms: 14 },
        redis: { status: "healthy", latency_ms: 4 },
        kafka: { status: "degraded", latency_ms: 88 },
        runtime_controller: { status: "healthy", latency_ms: 29 },
      },
    });
  });

  await page.route("**/api/v1/executions?**", async (route) => {
    await fulfillJson(route, {
      items: [
        {
          id: "exec-run-0001",
          workflowName: "Fraud triage",
          workflow_name: "Fraud triage",
          agentFqn: "risk:fraud-monitor",
          agent_fqn: "risk:fraud-monitor",
          currentStepLabel: "Assess evidence",
          current_step_label: "Assess evidence",
          status: "running",
          startedAt: "2026-04-20T09:58:00.000Z",
          started_at: "2026-04-20T09:58:00.000Z",
        },
      ],
      total: 1,
    });
  });

  await page.route("**/api/v1/dashboard/queue-lag", async (route) => {
    await fulfillJson(route, {
      topics: [
        { topic: "orchestration.primary", lag: 14872, warning: true },
        { topic: "attention.requests", lag: 220, warning: false },
      ],
      computed_at: "2026-04-20T10:00:00.000Z",
    });
  });

  await page.route("**/api/v1/dashboard/reasoning-budget-utilization", async (route) => {
    await fulfillJson(route, {
      total_capacity_tokens: 1000000,
      used_tokens: 950000,
      utilization_pct: 95,
      active_execution_count: 12,
      critical_pressure: true,
      computed_at: "2026-04-20T10:00:00.000Z",
    });
  });

  await page.route("**/api/v1/interactions/attention?**", async (route) => {
    await fulfillJson(route, { items: [], total: 0 });
  });

  await page.route("**/api/v1/executions/runtime/warm-pool/status", async (route) => {
    await fulfillJson(route, {
      keys: [
        {
          agent_type: "small",
          target_size: 5,
          available_count: 4,
          dispatched_count: 0,
          warming_count: 1,
          last_dispatch_at: "2026-04-20T09:00:00.000Z",
        },
        {
          agent_type: "medium",
          target_size: 4,
          available_count: 4,
          dispatched_count: 0,
          warming_count: 0,
          last_dispatch_at: "2026-04-20T09:05:00.000Z",
        },
        {
          agent_type: "large",
          target_size: 2,
          available_count: 2,
          dispatched_count: 0,
          warming_count: 0,
          last_dispatch_at: "2026-04-20T09:10:00.000Z",
        },
      ],
    });
  });

  await page.route("**/governance/verdicts", async (route) => {
    await fulfillJson(route, {
      items: [
        {
          id: "verdict-1",
          target_agent_fqn: "risk:fraud-monitor",
          verdict_type: "policy_violation",
          judge_agent_fqn: "ops:judge",
          recommended_action: "warn",
          created_at: "2026-04-20T09:00:00.000Z",
          rationale: "Policy warning",
        },
      ],
      next_cursor: null,
    });
  });

  await page.route("**/api/v1/registry/agents?**", async (route) => {
    await fulfillJson(route, {
      items: agents,
      next_cursor: null,
      total: agents.length,
    });
  });

  await page.route("**/api/v1/registry/agents/*/health", async (route) => {
    await fulfillJson(route, {
      composite_score: 91,
      components: [
        { label: "Reliability", score: 93, weight: 0.4 },
        { label: "Safety", score: 89, weight: 0.3 },
      ],
      computed_at: "2026-04-20T10:00:00.000Z",
    });
  });

  await page.route("**/api/v1/registry/agents/*", async (route) => {
    const encodedId = route.request().url().split("/api/v1/registry/agents/").at(-1) ?? "";
    const fqn = decodeURIComponent(encodedId);
    const match = agents.find((agent) => agent.fqn === fqn) ?? agents[0]!;
    await fulfillJson(route, {
      ...match,
      description: `${match.name} description`,
      tags: ["ops"],
      category: "operations",
      purpose: "Operator dashboard decommission target.",
      approach: "Structured reasoning.",
      role_type: "judge",
      custom_role: null,
      reasoning_modes: ["direct"],
      visibility_patterns: [{ pattern: "workspace:*", description: null }],
      model_config: {},
      tool_selections: [],
      connector_suggestions: [],
      policy_ids: [],
      context_profile_id: null,
      source_revision_id: null,
    });
  });
});

test("updates warm pool and verdict feeds live, runs the decommission wizard, and renders reliability gauges", async ({
  page,
}) => {
  let decommissionRequestFqn: string | null = null;

  await page.route("**/api/v1/registry/*/agents/*/decommission", async (route) => {
    const raw = route.request().url().split("/agents/").at(-1)?.split("/decommission")[0] ?? "";
    decommissionRequestFqn = decodeURIComponent(raw);
    await fulfillJson(route, { status: "accepted" }, 202);
  });

  await page.goto("/operator?panel=warm-pool");

  await expect(page.getByRole("heading", { name: "Operator Dashboard" })).toBeVisible();
  await expect(page.getByRole("button", { name: /^small\b/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /^medium\b/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /^large\b/i })).toBeVisible();
  await expect(page.getByText("Within 20%")).toBeVisible();

  await page.getByRole("button", { name: "small" }).click();
  await expect(page.getByText("Recent scaling activity")).toBeVisible();

  await emitFrontendWsEvent(page, {
    channel: "warm-pool",
    type: "warm-pool.updated",
    payload: {
      profile: {
        name: "small",
        targetReplicas: 5,
        actualReplicas: 2,
        deltaStatus: "below_target",
      },
    },
  });

  await expect(page.getByText("2 actual / 5 target")).toBeVisible();
  await expect(page.getByText("Below target")).toBeVisible();
  await page.keyboard.press("Escape");

  await page.getByRole("button", { name: "verdicts" }).click();
  await expect(page.locator('[aria-live="polite"]')).toBeVisible();
  await page.waitForTimeout(100);
  await emitFrontendWsEvent(page, {
    channel: "governance-verdicts",
    type: "verdict.issued",
    payload: {
      id: "verdict-2",
      workspace_id: workspaceFixture.id,
      target_agent_fqn: "ops:verdict-authority",
      verdict_type: "safety_violation",
      judge_agent_fqn: "ops:judge",
      recommended_action: "block",
    },
  });

  await expect(page.locator('[aria-live="polite"]')).toContainText("ops:verdict-authority");
  await expect(page.locator('[aria-live="polite"]')).toContainText("block");
  await expect(page.locator('[aria-live="polite"]')).toBeVisible();

  await page.getByRole("button", { name: "Decommission Agent" }).first().click();
  await expect(page.getByRole("heading", { name: "Decommission agent" })).toBeVisible();
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("Status will transition from active to decommissioned.")).toBeVisible();
  await page.getByRole("button", { name: "Next" }).click();
  const finalConfirmDialog = page.getByRole("alertdialog");
  await finalConfirmDialog.getByPlaceholder("risk:fraud-monitor").fill("risk:fraud-monitor");
  const finalDecommissionButton = finalConfirmDialog.getByRole("button", { name: "Decommission", exact: true });
  await expect(finalDecommissionButton).toBeEnabled();
  await finalDecommissionButton.evaluate((button: HTMLButtonElement) => button.click());

  await expect.poll(() => decommissionRequestFqn).toBe("risk:fraud-monitor");
  await expect(page.getByText("Agent marked for decommission.")).toBeVisible();
  await page.getByRole("button", { name: "Close" }).click();

  await page.getByRole("button", { name: "reliability" }).click();
  await expect(page.getByRole("heading", { name: "API", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Execution", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Event delivery", exact: true })).toBeVisible();
  await expect(page.getByText("99.70%")).toBeVisible();
});
