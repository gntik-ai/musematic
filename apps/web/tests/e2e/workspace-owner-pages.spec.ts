import { expect, test, type Page, type Route } from "@playwright/test";

const now = "2026-04-30T12:00:00.000Z";
const workspaceId = "11111111-1111-4111-8111-111111111111";
const connectorId = "22222222-2222-4222-8222-222222222222";
const challengeId = "33333333-3333-4333-8333-333333333333";
const newOwnerId = "44444444-4444-4444-8444-444444444444";
const iborConnectorId = "55555555-5555-4555-8555-555555555555";

async function fulfillJson(route: Route, payload: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(payload),
  });
}

async function installAuth(page: Page) {
  await page.addInitScript(
    ({ workspaceId }) => {
      window.localStorage.setItem(
        "auth-storage",
        JSON.stringify({
          state: {
            user: {
              id: "99999999-9999-4999-8999-999999999999",
              email: "owner@musematic.dev",
              displayName: "Workspace Owner",
              avatarUrl: null,
              roles: ["workspace_owner", "platform_admin"],
              workspaceId,
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
    },
    { workspaceId },
  );
}

async function mockWorkspaceOwnerApis(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    if (path === "/api/v1/workspaces") {
      return fulfillJson(route, {
        items: [
          {
            id: workspaceId,
            name: "Research Workspace",
            slug: "research",
            description: "Owner workbench fixture",
            memberCount: 4,
            createdAt: now,
          },
        ],
      });
    }

    if (path === `/api/v1/workspaces/${workspaceId}/summary`) {
      return fulfillJson(route, {
        workspace_id: workspaceId,
        active_goals: 3,
        executions_in_flight: 5,
        agent_count: 12,
        budget: { amount: 10000, spent: 6000, currency: "USD" },
        quotas: {
          agents: { used: 12, limit: 20 },
          executions: { used: 5, limit: 10 },
        },
        tags: { domain: ["science", "regulated"] },
        dlp_violations: 2,
        recent_activity: [
          { event_type: "auth.workspace.member_added", created_at: now },
        ],
        cards: {},
        cached_until: now,
      });
    }

    if (path === `/api/v1/workspaces/${workspaceId}/settings`) {
      return fulfillJson(route, {
        workspace_id: workspaceId,
        subscribed_agents: [],
        subscribed_fleets: [],
        subscribed_policies: [],
        subscribed_connectors: [],
        cost_budget: { amount: 10000, hard_cap_enabled: true },
        quota_config: { agents: 20, executions: 10 },
        dlp_rules: { enabled: true },
        residency_config: { region: "eu-west-1", tier: "regulated" },
        updated_at: now,
      });
    }

    if (path === `/api/v1/workspaces/${workspaceId}/members`) {
      if (method === "POST") {
        return fulfillJson(route, {
          id: "member-new",
          workspace_id: workspaceId,
          user_id: newOwnerId,
          role: "member",
          created_at: now,
        });
      }
      return fulfillJson(route, {
        items: [
          {
            id: "member-owner",
            workspace_id: workspaceId,
            user_id: "99999999-9999-4999-8999-999999999999",
            role: "owner",
            created_at: now,
          },
          {
            id: "member-admin",
            workspace_id: workspaceId,
            user_id: newOwnerId,
            role: "admin",
            created_at: now,
          },
        ],
        total: 2,
        page: 1,
        page_size: 50,
        has_next: false,
        has_prev: false,
      });
    }

    if (path.includes(`/api/v1/workspaces/${workspaceId}/members/`)) {
      return fulfillJson(route, method === "DELETE" ? {} : {
        id: "member-admin",
        workspace_id: workspaceId,
        user_id: newOwnerId,
        role: "viewer",
        created_at: now,
      });
    }

    if (path === `/api/v1/workspaces/${workspaceId}/transfer-ownership`) {
      return fulfillJson(route, {
        challenge_id: challengeId,
        action_type: "workspace_transfer_ownership",
        status: "pending",
        expires_at: now,
      });
    }

    if (path === `/api/v1/2pa/challenges/${challengeId}`) {
      return fulfillJson(route, {
        id: challengeId,
        action_type: "workspace_transfer_ownership",
        status: "approved",
        initiator_id: "99999999-9999-4999-8999-999999999999",
        co_signer_id: newOwnerId,
        created_at: now,
        expires_at: now,
        approved_at: now,
        consumed_at: null,
      });
    }

    if (path === `/api/v1/2pa/challenges/${challengeId}/consume`) {
      return fulfillJson(route, {
        id: challengeId,
        action_type: "workspace_transfer_ownership",
        status: "consumed",
        action_result: { workspace_id: workspaceId, owner_id: newOwnerId },
      });
    }

    if (path === `/api/v1/workspaces/${workspaceId}/connectors`) {
      return fulfillJson(route, {
        items: [
          {
            id: connectorId,
            workspace_id: workspaceId,
            connector_type_id: "slack-type",
            connector_type_slug: "slack",
            name: "Slack workspace alerts",
            config: { channel: "#alerts" },
            status: "active",
            health_status: "healthy",
            last_health_check_at: now,
            health_check_error: null,
            messages_sent: 24,
            messages_failed: 1,
            messages_retried: 1,
            messages_dead_lettered: 0,
            credential_keys: ["bot_token"],
            created_at: now,
            updated_at: now,
          },
        ],
        total: 1,
      });
    }

    if (path === `/api/v1/workspaces/${workspaceId}/connectors/${connectorId}`) {
      return fulfillJson(route, {
        id: connectorId,
        workspace_id: workspaceId,
        connector_type_id: "slack-type",
        connector_type_slug: "slack",
        name: "Slack workspace alerts",
        config: { channel: "#alerts" },
        status: "active",
        health_status: "healthy",
        last_health_check_at: now,
        health_check_error: null,
        messages_sent: 24,
        messages_failed: 1,
        messages_retried: 1,
        messages_dead_lettered: 0,
        credential_keys: ["bot_token"],
        created_at: now,
        updated_at: now,
      });
    }

    if (path === `/api/v1/workspaces/${workspaceId}/deliveries`) {
      return fulfillJson(route, {
        items: [
          {
            id: "delivery-1",
            workspace_id: workspaceId,
            connector_instance_id: connectorId,
            destination: "#alerts",
            status: "delivered",
            attempt_count: 1,
            max_attempts: 3,
            delivered_at: now,
            error_history: [],
            created_at: now,
            updated_at: now,
          },
          {
            id: "delivery-2",
            workspace_id: workspaceId,
            connector_instance_id: connectorId,
            destination: "#alerts",
            status: "failed",
            attempt_count: 3,
            max_attempts: 3,
            delivered_at: null,
            error_history: [{ error: "rate_limited" }],
            created_at: now,
            updated_at: now,
          },
        ],
        total: 2,
      });
    }

    if (path === `/api/v1/workspaces/${workspaceId}/visibility`) {
      return fulfillJson(route, {
        workspace_id: workspaceId,
        visibility_agents: ["science:*"],
        visibility_tools: ["tool://lab/*"],
        updated_at: now,
      });
    }

    if (path === `/api/v1/tags/workspace/${workspaceId}`) {
      return fulfillJson(route, {
        entity_type: "workspace",
        entity_id: workspaceId,
        tags: [{ tag: "science", created_by: null, created_at: now }],
      });
    }

    if (path === `/api/v1/labels/workspace/${workspaceId}`) {
      return fulfillJson(route, {
        entity_type: "workspace",
        entity_id: workspaceId,
        labels: [
          {
            key: "region",
            value: "eu",
            created_by: null,
            created_at: now,
            updated_at: now,
            is_reserved: false,
          },
        ],
      });
    }

    if (path === "/api/v1/admin/workspaces") {
      return fulfillJson(route, {
        items: [{ id: workspaceId, name: "Research Workspace" }],
        total: 1,
      });
    }

    if (path === "/api/v1/auth/ibor/connectors") {
      if (method === "POST") {
        return fulfillJson(route, {
          id: iborConnectorId,
          name: "Corporate directory",
          source_type: "ldap",
          sync_mode: "pull",
          cadence_seconds: 3600,
          credential_ref: "secret/data/auth/ibor/corporate-directory",
          role_mapping_policy: [],
          enabled: true,
          last_run_at: now,
          last_run_status: "succeeded",
          created_by: "99999999-9999-4999-8999-999999999999",
          created_at: now,
          updated_at: now,
        });
      }
      return fulfillJson(route, {
        items: [
          {
            id: iborConnectorId,
            name: "Corporate directory",
            source_type: "ldap",
            sync_mode: "pull",
            cadence_seconds: 3600,
            credential_ref: "secret/data/auth/ibor/corporate-directory",
            role_mapping_policy: [],
            enabled: true,
            last_run_at: now,
            last_run_status: "succeeded",
            created_by: "99999999-9999-4999-8999-999999999999",
            created_at: now,
            updated_at: now,
          },
        ],
      });
    }

    if (path === `/api/v1/auth/ibor/connectors/${iborConnectorId}/test-connection`) {
      return fulfillJson(route, {
        connector_id: iborConnectorId,
        success: true,
        steps: [
          { step: "dns_lookup", status: "success", duration_ms: 4, error: null },
          { step: "ldap_bind", status: "success", duration_ms: 9, error: null },
        ],
      });
    }

    if (path === `/api/v1/auth/ibor/connectors/${iborConnectorId}/sync-now`) {
      return fulfillJson(route, {
        run_id: "66666666-6666-4666-8666-666666666666",
        connector_id: iborConnectorId,
        status: "running",
        started_at: now,
      }, 202);
    }

    if (path === `/api/v1/auth/ibor/connectors/${iborConnectorId}/sync-history`) {
      return fulfillJson(route, {
        items: [
          {
            id: "sync-1",
            connector_id: iborConnectorId,
            mode: "pull",
            started_at: now,
            finished_at: now,
            status: "succeeded",
            counts: { users: 12 },
            error_details: [],
            triggered_by: null,
          },
        ],
        next_cursor: null,
      });
    }

    if (path === "/api/v1/me/preferences") {
      return fulfillJson(route, {
        id: "prefs",
        user_id: "99999999-9999-4999-8999-999999999999",
        default_workspace_id: workspaceId,
        theme: "system",
        language: "en",
        timezone: "UTC",
        notification_preferences: {},
        data_export_format: "json",
        is_persisted: true,
        created_at: now,
        updated_at: now,
      });
    }

    return fulfillJson(route, {});
  });
}

test.beforeEach(async ({ page }) => {
  await installAuth(page);
  await mockWorkspaceOwnerApis(page);
});

test.describe("workspace owner workbench", () => {
  test("workspace list and dashboard render scoped summary cards", async ({ page }) => {
    await page.goto("/workspaces");
    await expect(page.getByRole("heading", { name: "Workspaces" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Research Workspace" })).toBeVisible();

    await page.getByRole("link", { name: /open/i }).click();
    await expect(page.getByRole("heading", { name: "Workspace dashboard" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Active goals" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Executions in flight" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Agents" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "DLP violations" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Budget" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Quota usage" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Tags" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Recent activity" })).toBeVisible();
  });

  test("members page covers invite, role change, removal, and 2PA transfer", async ({ page }) => {
    await page.goto(`/workspaces/${workspaceId}/members`);
    await expect(page.getByRole("heading", { name: "Members" })).toBeVisible();
    await expect(page.getByText(newOwnerId)).toBeVisible();

    await page.getByRole("button", { name: "Invite" }).click();
    const inviteDialog = page.getByRole("dialog");
    await inviteDialog.getByLabel("User ID").fill(newOwnerId);
    await inviteDialog.getByLabel("Role").selectOption("viewer");
    await inviteDialog.getByRole("button", { name: "Add member" }).click();

    await page.getByRole("combobox").first().selectOption("viewer");
    await page.getByRole("button", { name: "Remove member" }).last().click();

    await page.getByRole("button", { name: "Transfer ownership" }).click();
    await page.getByLabel("New owner user ID").fill(newOwnerId);
    await page.getByRole("button", { name: "Create 2PA challenge" }).click();
    await expect(page.getByText("Challenge approved")).toBeVisible();
    await page.getByRole("button", { name: "Consume challenge" }).click();
  });

  test("connector setup, detail activity, and rotation surfaces render", async ({ page }) => {
    await page.goto(`/workspaces/${workspaceId}/connectors`);
    await expect(page.getByRole("heading", { name: "Connectors" })).toBeVisible();
    await expect(page.getByText("Workspace-owned", { exact: true })).toBeVisible();

    await page.getByRole("button", { name: "Add connector" }).click();
    await expect(page.getByText("Slack prerequisites")).toBeVisible();
    await page.getByRole("combobox").selectOption("telegram");
    await expect(page.getByText("Telegram prerequisites")).toBeVisible();
    await page.getByRole("combobox").selectOption("email");
    await expect(page.getByText("Email prerequisites")).toBeVisible();
    await page.getByRole("combobox").selectOption("webhook");
    await expect(page.getByText("Webhook prerequisites")).toBeVisible();

    await page.goto(`/workspaces/${workspaceId}/connectors/${connectorId}`);
    await expect(page.getByRole("heading", { name: "Connector detail" })).toBeVisible();
    await expect(page.locator("p").filter({ hasText: /^Delivered$/ })).toBeVisible();
    await expect(page.locator("p").filter({ hasText: /^Failed$/ })).toBeVisible();
    await page.getByRole("button", { name: "Rotate secret" }).click();
    await page.getByLabel("New secret").fill("new-secret-value");
    await page.getByRole("button", { name: "Confirm rotation" }).click();
  });

  test("settings, tags, visibility, and admin IBOR tab render", async ({ page }) => {
    await page.goto(`/workspaces/${workspaceId}/settings`);
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
    await expect(page.getByLabel("Monthly limit")).toHaveValue("10000");
    await page.getByRole("button", { name: "Save budget" }).click();

    await page.goto(`/workspaces/${workspaceId}/tags`);
    await expect(page.getByRole("heading", { name: "Tags", level: 1 })).toBeVisible();
    await expect(page.getByText("science")).toBeVisible();
    await expect(page.getByText("region: eu")).toBeVisible();

    await page.goto(`/workspaces/${workspaceId}/visibility`);
    await expect(page.getByRole("heading", { name: "Visibility", level: 1 })).toBeVisible();
    await expect(page.getByText("grants configured")).toBeVisible();

    await page.goto("/admin/settings?tab=ibor");
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "IBOR connectors" })).toBeVisible();
    const connectorRow = page.getByRole("row", { name: /Corporate directory/ });
    await connectorRow.getByRole("button", { name: "Test" }).click();
    await connectorRow.getByRole("button", { name: "Details" }).click();
    await expect(page.getByText("Sync history")).toBeVisible();
    await expect(page.getByRole("cell", { name: "succeeded" }).nth(1)).toBeVisible();
    await page.getByRole("button", { name: "Connection" }).click();
    await page.getByRole("button", { name: "Create connector draft" }).click();
    await page.getByRole("button", { name: "Run stepped diagnostic" }).click();
    await expect(page.getByText("dns_lookup")).toBeVisible();
    await page.getByRole("button", { name: "Activate" }).click();
    await page.getByRole("button", { name: "Sync now" }).click();
  });
});
