import { expect, test, type Page, type Route } from "@playwright/test";

const now = "2026-04-30T12:00:00.000Z";
const workspaceId = "11111111-1111-4111-8111-111111111111";
const profileId = "22222222-2222-4222-8222-222222222222";
const contractId = "33333333-3333-4333-8333-333333333333";
const templateId = "44444444-4444-4444-8444-444444444444";

async function fulfillJson(route: Route, payload: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(payload),
  });
}

async function installState(page: Page) {
  await page.addInitScript(
    ({ workspaceId }) => {
      window.localStorage.setItem(
        "auth-storage",
        JSON.stringify({
          state: {
            user: {
              id: "99999999-9999-4999-8999-999999999999",
              email: "creator@musematic.dev",
              displayName: "Creator",
              avatarUrl: null,
              roles: ["agent_owner", "workspace_admin"],
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
      window.localStorage.setItem(
        "workspace-storage",
        JSON.stringify({
          state: {
            currentWorkspace: {
              id: workspaceId,
              name: "Creator Workspace",
              slug: "creator",
              description: "Creator UI fixture",
              memberCount: 3,
              createdAt: "2026-04-30T12:00:00.000Z",
            },
            sidebarCollapsed: false,
          },
          version: 0,
        }),
      );
    },
    { workspaceId },
  );
}

async function mockCreatorApis(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    if (path === "/api/v1/context-engineering/profiles/schema") {
      return fulfillJson(route, {
        type: "object",
        properties: {
          name: { type: "string" },
          source_config: { type: "array" },
        },
      });
    }

    if (path === "/api/v1/context-engineering/profiles" && method === "POST") {
      return fulfillJson(route, {
        id: profileId,
        workspace_id: workspaceId,
        name: "default-context-profile",
        description: "Creator-authored profile",
        source_config: [],
        budget_config: {},
        compaction_strategies: [],
        quality_weights: {},
        privacy_overrides: {},
        is_default: false,
        created_at: now,
        updated_at: now,
      }, 201);
    }

    if (path === `/api/v1/context-engineering/profiles/${profileId}/preview`) {
      return fulfillJson(route, {
        sources: [
          {
            origin: "Workspace memory",
            snippet: "long_term_memory matched through hybrid retrieval.",
            score: 0.91,
            included: true,
            classification: "public",
          },
        ],
        mock_response: "Mock context preview response",
        completion_metadata: { model: "mock-creator-preview-v1" },
        was_fallback: false,
      });
    }

    if (path === `/api/v1/context-engineering/profiles/${profileId}/versions`) {
      return fulfillJson(route, {
        versions: [
          {
            id: "55555555-5555-4555-8555-555555555555",
            profile_id: profileId,
            version_number: 1,
            content_snapshot: { name: "default-context-profile" },
            change_summary: "Initial profile creation",
            created_by: "99999999-9999-4999-8999-999999999999",
            created_at: now,
          },
        ],
        next_cursor: null,
      });
    }

    if (path === "/api/v1/trust/contracts/schema") {
      return fulfillJson(route, {
        type: "object",
        properties: {
          agent_id: { type: "string" },
          task_scope: { type: "string" },
        },
      });
    }

    if (path === "/api/v1/trust/contracts/schema-enums") {
      return fulfillJson(route, {
        resource_types: ["workspace", "agent_revision"],
        role_types: ["executor", "planner"],
        workspace_constraints: ["workspace_visibility"],
        failure_modes: ["continue", "warn", "throttle", "escalate", "terminate"],
      });
    }

    if (path === "/api/v1/trust/contracts" && method === "POST") {
      return fulfillJson(route, {
        id: contractId,
        workspace_id: workspaceId,
        agent_id: "creator-ui:agent",
        task_scope: "Answer customer questions using approved sources.",
        expected_outputs: { required: ["answer", "citations"] },
        quality_thresholds: { minimum_confidence: 0.72 },
        time_constraint_seconds: null,
        cost_limit_tokens: null,
        escalation_conditions: { pii_detected: "escalate" },
        success_criteria: { must_include_citation: true },
        enforcement_policy: "warn",
        is_archived: false,
        attached_revision_id: null,
        created_at: now,
        updated_at: now,
      }, 201);
    }

    if (path === `/api/v1/trust/contracts/${contractId}/preview`) {
      return fulfillJson(route, {
        clauses_triggered: ["task_scope", "expected_outputs"],
        clauses_satisfied: ["task_scope"],
        clauses_violated: ["expected_outputs"],
        final_action: "warn",
        mock_response: "Mock contract preview response",
        was_fallback: false,
      });
    }

    if (path === "/api/v1/trust/contracts/templates") {
      return fulfillJson(route, {
        items: [
          {
            id: templateId,
            name: "Customer support agent contract",
            description: "Baseline contract for support agents.",
            category: "customer-support",
            template_content: {},
            version_number: 1,
            forked_from_template_id: null,
            created_by_user_id: null,
            is_platform_authored: true,
            is_published: true,
            created_at: now,
            updated_at: now,
          },
        ],
        total: 1,
      });
    }

    if (path === `/api/v1/trust/contracts/${templateId}/fork`) {
      return fulfillJson(route, { id: contractId }, 201);
    }

    return fulfillJson(route, { items: [], total: 0 });
  });
}

test.beforeEach(async ({ page }) => {
  await installState(page);
  await mockCreatorApis(page);
});

test("context profile page saves and runs mock preview", async ({ page }) => {
  await page.goto("/agent-management/creator-ui%3Aagent/context-profile");

  await expect(page.getByRole("heading", { name: "Context Profile" })).toBeVisible();
  await page.getByRole("button", { name: /Create Profile/i }).click();
  await expect(page.getByRole("button", { name: /Update Profile/i })).toBeVisible();

  await page.getByRole("button", { name: "Test" }).click();
  await page.getByRole("button", { name: /Run Mock Preview/i }).click();
  await expect(page.getByText("Mock context preview response")).toBeVisible();
  await expect(page.getByText("Workspace memory")).toBeVisible();
});

test("contract page saves and previews contract clauses", async ({ page }) => {
  await page.goto("/agent-management/creator-ui%3Aagent/contract");

  await expect(page.getByRole("heading", { name: "Agent Contract" })).toBeVisible();
  await expect(page.getByText("executor, planner")).toBeVisible();
  await page.getByRole("button", { name: /Create Contract/i }).click();
  await expect(page.getByRole("button", { name: /Update Contract/i })).toBeVisible();

  await page.getByRole("button", { name: "Preview" }).click();
  await page.getByRole("button", { name: /Run Mock Preview/i }).click();
  await expect(page.getByText("Mock contract preview response")).toBeVisible();
  await expect(page.getByText("expected_outputs").first()).toBeVisible();
});

test("contract template library renders platform templates", async ({ page }) => {
  await page.goto("/agent-management/contracts/library");

  await expect(page.getByRole("heading", { name: "Template Library" })).toBeVisible();
  await expect(page.getByText("Customer support agent contract")).toBeVisible();
  await expect(page.getByText("Baseline contract for support agents.")).toBeVisible();
});
