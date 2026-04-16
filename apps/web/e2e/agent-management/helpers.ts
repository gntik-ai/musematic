import type { Page, Route } from "@playwright/test";

export const agentCatalogEntries = [
  {
    fqn: "risk:kyc-monitor",
    namespace: "risk",
    local_name: "kyc-monitor",
    name: "KYC Monitor",
    maturity_level: "production",
    status: "draft",
    revision_count: 4,
    latest_revision_number: 4,
    updated_at: "2026-04-16T10:00:00.000Z",
    workspace_id: "workspace-1",
  },
  {
    fqn: "ops:case-triage",
    namespace: "ops",
    local_name: "case-triage",
    name: "Case Triage",
    maturity_level: "beta",
    status: "active",
    revision_count: 2,
    latest_revision_number: 2,
    updated_at: "2026-04-15T09:30:00.000Z",
    workspace_id: "workspace-1",
  },
] as const;

export const agentDetail = {
  ...agentCatalogEntries[0],
  description: "Monitors KYC workflows and flags suspicious activity.",
  tags: ["kyc", "risk"],
  category: "fraud",
  purpose:
    "Monitor KYC workflows, identify suspicious patterns, and escalate them for review.",
  approach: "Pairs deterministic checks with curated workflow tooling.",
  role_type: "executor",
  custom_role: null,
  reasoning_modes: ["deterministic"],
  visibility_patterns: [
    {
      pattern: "risk:*",
      description: "Visible to the risk namespace.",
    },
  ],
  model_config: {
    model_id: "gpt-5.4-mini",
    temperature: 0.2,
  },
  tool_selections: ["transactions", "case-management"],
  connector_suggestions: ["slack"],
  policy_ids: ["policy-1"],
  context_profile_id: "ctx-1",
  source_revision_id: "rev-4",
  last_modified: "2026-04-16T10:00:00.000Z",
} as const;

export async function installAgentManagementState(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem(
      "auth-storage",
      JSON.stringify({
        state: {
          user: {
            id: "user-1",
            email: "operator@musematic.dev",
            displayName: "Operator",
            avatarUrl: null,
            roles: ["workspace_admin", "agent_operator"],
            workspaceId: "workspace-1",
            mfaEnrolled: true,
          },
          accessToken: "mock-access-token",
          refreshToken: "mock-refresh-token",
          isAuthenticated: true,
          isLoading: false,
        },
        version: 0,
      }),
    );

    localStorage.setItem(
      "workspace-storage",
      JSON.stringify({
        state: {
          currentWorkspace: {
            id: "workspace-1",
            name: "Risk Ops",
            slug: "risk-ops",
            description: "Primary risk workspace",
            memberCount: 8,
            createdAt: "2026-04-10T09:00:00.000Z",
          },
          sidebarCollapsed: false,
        },
        version: 0,
      }),
    );
  });
}

function matchSearch(entry: (typeof agentCatalogEntries)[number], search: string): boolean {
  const term = search.trim().toLowerCase();
  if (!term) {
    return true;
  }

  return [entry.name, entry.namespace, entry.fqn].some((value) =>
    value.toLowerCase().includes(term),
  );
}

function matchCsvFilter(value: string, allowedValues: string[]): boolean {
  if (!value) {
    return true;
  }

  return value
    .split(",")
    .filter(Boolean)
    .includes(allowedValues[0] ?? "");
}

export async function mockAgentCatalogApi(page: Page) {
  await page.route("**/api/v1/registry/agents?**", async (route) => {
    const url = new URL(route.request().url());
    const search = url.searchParams.get("search") ?? "";
    const maturity = url.searchParams.get("maturity") ?? "";
    const status = url.searchParams.get("status") ?? "";
    const namespace = url.searchParams.get("namespace") ?? "";

    const items = agentCatalogEntries.filter(
      (entry) =>
        matchSearch(entry, search) &&
        matchCsvFilter(maturity, [entry.maturity_level]) &&
        matchCsvFilter(status, [entry.status]) &&
        matchCsvFilter(namespace, [entry.namespace]),
    );

    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items,
        next_cursor: null,
        total: items.length,
      }),
      status: 200,
    });
  });

  await page.route("**/api/v1/registry/namespaces?**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          { namespace: "risk", agent_count: 1 },
          { namespace: "ops", agent_count: 1 },
        ],
      }),
      status: 200,
    });
  });
}

export async function mockAgentDetailApi(page: Page) {
  await page.route("**/api/v1/registry/agents/risk%3Akyc-monitor", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(agentDetail),
      status: 200,
    });
  });

  await page.route("**/api/v1/registry/agents/risk%3Akyc-monitor/health", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        composite_score: 82,
        components: [
          { label: "Quality", score: 85, weight: 0.5 },
          { label: "Policy", score: 79, weight: 0.5 },
        ],
        computed_at: "2026-04-16T10:00:00.000Z",
      }),
      status: 200,
    });
  });
}

export async function mockMetadataSaveApi(page: Page) {
  let saveCount = 0;

  await page.route(
    "**/api/v1/registry/agents/risk%3Akyc-monitor/metadata",
    async (route: Route) => {
      saveCount += 1;

      if (saveCount === 1) {
        const payload = route.request().postDataJSON() as Record<string, unknown>;
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify({
            ...agentDetail,
            ...payload,
            updated_at: "2026-04-16T11:00:00.000Z",
            last_modified: "2026-04-16T11:00:00.000Z",
          }),
          status: 200,
        });
        return;
      }

      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          error: {
            code: "stale",
            message: "Stale data",
          },
        }),
        status: 412,
      });
    },
  );
}

export async function mockSuccessfulUpload(page: Page, delayMs = 600) {
  await page.route("**/api/v1/registry/agents/upload", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, delayMs));
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        agent_fqn: agentDetail.fqn,
        status: "draft",
        validation_errors: [],
      }),
      status: 201,
    });
  });
}

export async function mockSlowUpload(page: Page, delayMs = 5000) {
  await page.route("**/api/v1/registry/agents/upload", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, delayMs));
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        agent_fqn: agentDetail.fqn,
        status: "draft",
        validation_errors: [],
      }),
      status: 201,
    });
  });
}

