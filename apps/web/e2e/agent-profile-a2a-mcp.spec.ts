import { expect, test } from "@playwright/test";
import {
  fulfillJson,
  installFrontendState,
  mockCommonAppApi,
  workspaceFixture,
} from "@/e2e/frontend-expansions/helpers";

const agentFqn = "risk:kyc-monitor";

const agentDetail = {
  fqn: agentFqn,
  namespace: "risk",
  local_name: "kyc-monitor",
  name: "KYC Monitor",
  description: "Monitors onboarding signals for high-risk KYC cases.",
  maturity_level: "production",
  status: "active",
  revision_count: 3,
  latest_revision_number: 3,
  updated_at: "2026-04-20T10:00:00.000Z",
  workspace_id: workspaceFixture.id,
  tags: ["kyc", "risk"],
  category: "compliance",
  purpose: "Review KYC trajectories, publish contracts, and expose runtime metadata for trust operations.",
  approach: "Structured verification and escalation.",
  role_type: "judge",
  custom_role: null,
  reasoning_modes: ["direct", "react"],
  visibility_patterns: [{ pattern: "risk:*", description: null }],
  model_config: {},
  tool_selections: [],
  connector_suggestions: [],
  policy_ids: [],
  context_profile_id: null,
  source_revision_id: null,
};

test.beforeEach(async ({ page }) => {
  await installFrontendState(page, {
    roles: ["platform_admin", "workspace_admin", "agent_operator"],
    workspaceId: workspaceFixture.id,
  });
  await mockCommonAppApi(page);

  await page.route(`**/api/v1/registry/agents/${encodeURIComponent(agentFqn)}`, async (route) => {
    await fulfillJson(route, agentDetail);
  });

  await page.route(`**/api/v1/registry/agents/${encodeURIComponent(agentFqn)}/health`, async (route) => {
    await fulfillJson(route, {
      composite_score: 92,
      components: [
        { label: "Reliability", score: 95, weight: 0.4 },
        { label: "Safety", score: 89, weight: 0.3 },
      ],
      computed_at: "2026-04-20T10:00:00.000Z",
    });
  });

  await page.route(`**/api/v1/trust/contracts?agent_id=${encodeURIComponent(agentFqn)}&include_archived=true`, async (route) => {
    await fulfillJson(route, {
      items: [
        {
          id: "contract-1",
          agent_id: agentFqn,
          task_scope: "Version one excerpt",
          is_archived: true,
          created_at: "2026-04-10T00:00:00.000Z",
          updated_at: "2026-04-11T00:00:00.000Z",
        },
        {
          id: "contract-2",
          agent_id: agentFqn,
          task_scope: "Version two excerpt",
          is_archived: true,
          created_at: "2026-04-12T00:00:00.000Z",
          updated_at: "2026-04-13T00:00:00.000Z",
        },
        {
          id: "contract-3",
          agent_id: agentFqn,
          task_scope: "Version three excerpt",
          is_archived: false,
          created_at: "2026-04-14T00:00:00.000Z",
          updated_at: "2026-04-14T00:00:00.000Z",
        },
      ],
      total: 3,
    });
  });

  await page.route("**/.well-known/agent.json", async (route) => {
    await fulfillJson(route, {
      agent: agentFqn,
      skills: ["audit", "triage"],
    });
  });
});

test("shows contract diffs, A2A JSON, and disconnects MCP servers with confirmation", async ({
  page,
}) => {
  let serverItems = [
    {
      server_id: "server-1",
      display_name: "Compliance MCP",
      endpoint_url: "https://mcp.musematic.dev",
      tool_count: 4,
      status: "healthy",
      health: {
        status: "healthy",
        last_success_at: "2026-04-20T10:00:00.000Z",
      },
    },
  ];
  let disconnectedServerId: string | null = null;

  await page.route("**/api/v1/mcp/servers", async (route) => {
    await fulfillJson(route, { items: serverItems, total: serverItems.length });
  });
  await page.route("**/api/v1/mcp/servers/*", async (route) => {
    disconnectedServerId = route.request().url().split("/").at(-1) ?? null;
    serverItems = serverItems.filter((item) => item.server_id !== disconnectedServerId);
    await route.fulfill({ status: 204, body: "" });
  });

  await page.goto(`/agents/${encodeURIComponent(agentFqn)}?tab=contracts`);

  await expect(page.getByRole("heading", { name: "Contracts" })).toBeVisible();
  await expect(page.getByText("active", { exact: true })).toBeVisible();
  await expect(page.getByText("superseded", { exact: true })).toHaveCount(2);

  await page.getByRole("checkbox").nth(0).check();
  await page.getByRole("checkbox").nth(1).check();
  await page.getByRole("button", { name: "Diff" }).click();

  await expect(page.getByText("Contract diff")).toBeVisible();
  await expect(page.getByText("Version one excerpt")).toHaveCount(2);
  await expect(page.getByText("Version two excerpt")).toHaveCount(2);
  await page.getByRole("button", { name: "Close" }).click();

  await page.goto(`/agents/${encodeURIComponent(agentFqn)}?tab=a2a`);
  await expect(page.getByText("A2A profile")).toBeVisible();
  await expect(page.locator("pre").filter({ hasText: agentFqn }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Copy" })).toBeVisible();

  await page.goto(`/agents/${encodeURIComponent(agentFqn)}?tab=mcp`);
  await expect(page.getByText("Compliance MCP")).toBeVisible();
  await expect(page.getByText("4 tools · 0 resources")).toBeVisible();
  await page.getByRole("button", { name: "Disconnect" }).click();
  await expect(page.getByText("Disconnect MCP server")).toBeVisible();
  await page.getByRole("button", { name: "Disconnect" }).last().click();

  await expect.poll(() => disconnectedServerId).toBe("server-1");
  await expect(page.getByText("No MCP servers are registered.")).toBeVisible();
});
