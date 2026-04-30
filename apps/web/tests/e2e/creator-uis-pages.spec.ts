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
      const hideDevOverlays = () => {
        const style = document.createElement("style");
        style.setAttribute("data-creator-ui-test-style", "true");
        style.textContent = `
          .tsqd-parent-container,
          [data-nextjs-dev-tools-button] {
            display: none !important;
            pointer-events: none !important;
          }
        `;
        document.documentElement.appendChild(style);
      };

      if (document.documentElement) {
        hideDevOverlays();
      } else {
        window.addEventListener("DOMContentLoaded", hideDevOverlays, {
          once: true,
        });
      }

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
      return fulfillJson(
        route,
        {
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
        },
        201,
      );
    }

    if (
      path === `/api/v1/context-engineering/profiles/${profileId}` &&
      method === "PUT"
    ) {
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
      });
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

    if (
      path === `/api/v1/context-engineering/profiles/${profileId}/rollback/1`
    ) {
      return fulfillJson(route, {
        id: "66666666-6666-4666-8666-666666666666",
        profile_id: profileId,
        version_number: 2,
        content_snapshot: { name: "default-context-profile" },
        change_summary: "Rollback to version 1",
        created_by: "99999999-9999-4999-8999-999999999999",
        created_at: now,
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
        failure_modes: [
          "continue",
          "warn",
          "throttle",
          "escalate",
          "terminate",
        ],
      });
    }

    if (path === "/api/v1/trust/contracts" && method === "POST") {
      return fulfillJson(
        route,
        {
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
        },
        201,
      );
    }

    if (path === `/api/v1/trust/contracts/${contractId}` && method === "PUT") {
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
      });
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

    if (path === `/api/v1/trust/contracts/${contractId}`) {
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
        attached_revision_id: "77777777-7777-4777-8777-777777777777",
        created_at: now,
        updated_at: now,
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

    if (path === "/api/v1/compositions/agent-blueprint" && method === "POST") {
      return fulfillJson(route, {
        blueprint_id: "88888888-8888-4888-8888-888888888888",
        description: "KYC publication agent",
        low_confidence: false,
        follow_up_questions: [],
        model_config: { provider: "mock", model: "mock-llm" },
        tool_selections: [
          {
            tool_name: "tool://kyc/read",
            relevance_justification: "Reads KYC packages.",
          },
        ],
        connector_suggestions: [],
        policy_recommendations: [],
        context_profile: { retrieval_strategy: "hybrid" },
        llm_reasoning_summary: "Mock blueprint",
        maturity_reasoning: "Ready",
        confidence_score: 0.92,
      });
    }

    return fulfillJson(route, { items: [], total: 0 });
  });
}

test.beforeEach(async ({ page }) => {
  await installState(page);
  await mockCreatorApis(page);
});

async function createContextProfileFromPage(page: Page) {
  await page.goto("/agent-management/creator-ui%3Aagent/context-profile");
  await page.getByRole("button", { name: /Create Profile/i }).click();
  await expect(
    page.getByRole("button", { name: /Update Profile/i }),
  ).toBeVisible();
}

async function createContractFromPage(page: Page) {
  await page.goto("/agent-management/creator-ui%3Aagent/contract");
  await page.getByRole("button", { name: /Create Contract/i }).click();
  await expect(
    page.getByRole("button", { name: /Update Contract/i }),
  ).toBeVisible();
}

test("context profile page renders editor and history controls", async ({
  page,
}) => {
  await page.goto("/agent-management/creator-ui%3Aagent/context-profile");

  await expect(
    page.getByRole("heading", { name: "Context Profile" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Editor" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sources" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Test" })).toBeVisible();
  await expect(page.getByRole("link", { name: /History/i })).toHaveAttribute(
    "href",
    "/agent-management/creator-ui%3Aagent/context-profile/history",
  );
});

test("context profile page creates a profile and exposes update state", async ({
  page,
}) => {
  await createContextProfileFromPage(page);
});

test("context profile page updates an existing profile id", async ({
  page,
}) => {
  await page.goto("/agent-management/creator-ui%3Aagent/context-profile");
  await page.getByLabel("Profile ID").fill(profileId);
  await page.getByRole("button", { name: /Update Profile/i }).click();
  await expect(
    page.getByRole("button", { name: /Update Profile/i }),
  ).toBeVisible();
});

test("context profile sources tab exposes source, retrieval, and budget controls", async ({
  page,
}) => {
  await page.goto("/agent-management/creator-ui%3Aagent/context-profile");

  await page.getByRole("button", { name: "Sources" }).click();
  await expect(page.getByText("Memory")).toBeVisible();
  await expect(page.getByText("Knowledge graph")).toBeVisible();
  await expect(page.getByText("Execution history")).toBeVisible();
  await expect(page.getByText("Tool outputs")).toBeVisible();
  await expect(page.getByText("External APIs")).toBeVisible();
  await expect(page.getByRole("button", { name: "Hybrid" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.getByLabel("Max tokens")).toHaveValue("8192");
  await expect(page.getByLabel("Max documents")).toHaveValue("50");
});

test("context profile preview is disabled before a profile exists", async ({
  page,
}) => {
  await page.goto("/agent-management/creator-ui%3Aagent/context-profile");

  await page.getByRole("button", { name: "Test" }).click();
  await expect(
    page.getByRole("button", { name: /Run Mock Preview/i }),
  ).toBeDisabled();
});

test("context profile page saves and runs mock preview", async ({ page }) => {
  await createContextProfileFromPage(page);

  await page.getByRole("button", { name: "Test" }).click();
  await page.getByRole("button", { name: /Run Mock Preview/i }).click();
  await expect(page.getByText("Mock context preview response")).toBeVisible();
  await expect(page.getByText("Workspace memory")).toBeVisible();
});

test("context profile preview renders provenance status and score", async ({
  page,
}) => {
  await createContextProfileFromPage(page);

  await page.getByRole("button", { name: "Test" }).click();
  await page.getByRole("button", { name: /Run Mock Preview/i }).click();
  await expect(page.getByText("Included")).toBeVisible();
  await expect(page.getByText("public")).toBeVisible();
  await expect(page.getByText("91%")).toBeVisible();
});

test("context profile history shows versions and rollback action", async ({
  page,
}) => {
  await page.goto(
    "/agent-management/creator-ui%3Aagent/context-profile/history",
  );

  await expect(
    page.getByRole("heading", { name: "Context Profile History" }),
  ).toBeVisible();
  await page.getByLabel("Profile ID").fill(profileId);
  await expect(page.getByText("Version 1")).toBeVisible();
  await expect(page.getByText("Initial profile creation")).toBeVisible();
  await page.getByRole("button", { name: /Compare/i }).click();
  await expect(page.getByText("default-context-profile")).toBeVisible();
  await page.getByRole("button", { name: /Rollback/i }).click();
});

test("contract page renders schema editor and enum summary", async ({
  page,
}) => {
  await page.goto("/agent-management/creator-ui%3Aagent/contract");

  await expect(
    page.getByRole("heading", { name: "Agent Contract" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Editor" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Preview" })).toBeVisible();
  await expect(page.getByText("executor, planner")).toBeVisible();
});

test("contract preview actions are disabled before a contract exists", async ({
  page,
}) => {
  await page.goto("/agent-management/creator-ui%3Aagent/contract");

  await page.getByRole("button", { name: "Preview" }).click();
  await expect(
    page.getByRole("button", { name: /Run Mock Preview/i }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: /Real LLM Preview/i }),
  ).toBeDisabled();
});

test("contract page creates a contract and exposes update state", async ({
  page,
}) => {
  await createContractFromPage(page);
});

test("contract page updates an existing contract id", async ({ page }) => {
  await page.goto("/agent-management/creator-ui%3Aagent/contract");
  await page.getByLabel("Contract ID").fill(contractId);
  await page.getByRole("button", { name: /Update Contract/i }).click();
  await expect(
    page.getByRole("button", { name: /Update Contract/i }),
  ).toBeVisible();
});

test("contract page saves and previews contract clauses", async ({ page }) => {
  await createContractFromPage(page);

  await page.getByRole("button", { name: "Preview" }).click();
  await page.getByRole("button", { name: /Run Mock Preview/i }).click();
  await expect(page.getByText("Mock contract preview response")).toBeVisible();
  await expect(page.getByText("warn")).toBeVisible();
  await expect(page.getByText("expected_outputs").first()).toBeVisible();
});

test("contract preview validates sample input before calling the API", async ({
  page,
}) => {
  await createContractFromPage(page);

  await page.getByRole("button", { name: "Preview" }).click();
  await page.locator("textarea").fill("[]");
  await page.getByRole("button", { name: /Run Mock Preview/i }).click();
  await expect(
    page.getByText("Sample input must be a JSON object."),
  ).toBeVisible();
});

test("real LLM opt-in requires typed confirmation", async ({ page }) => {
  await createContractFromPage(page);

  await page.getByRole("button", { name: "Preview" }).click();
  await page.getByRole("button", { name: /Real LLM Preview/i }).click();
  await expect(
    page.getByRole("heading", { name: "Confirm Real LLM Preview" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Confirm" })).toBeDisabled();
  await page.getByPlaceholder("USE_REAL_LLM").fill("USE_REAL_LLM");
  await page.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText("Mock contract preview response")).toBeVisible();
});

test("contract attach dialog is disabled until save and accepts a revision id", async ({
  page,
}) => {
  await page.goto("/agent-management/creator-ui%3Aagent/contract");
  await expect(
    page.getByRole("button", { name: "Attach to revision" }),
  ).toBeDisabled();

  await page.getByRole("button", { name: /Create Contract/i }).click();
  await page.getByRole("button", { name: "Attach to revision" }).click();
  await expect(
    page.getByRole("heading", { name: "Attach Contract" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Attach", exact: true }),
  ).toBeDisabled();
  await page
    .getByPlaceholder("Revision UUID")
    .fill("77777777-7777-4777-8777-777777777777");
  await page.getByRole("button", { name: "Attach", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Attach Contract" }),
  ).toBeHidden();
});

test("contract template library renders platform templates", async ({
  page,
}) => {
  await page.goto("/agent-management/contracts/library");

  await expect(
    page.getByRole("heading", { name: "Template Library" }),
  ).toBeVisible();
  await expect(page.getByText("Customer support agent contract")).toBeVisible();
  await expect(
    page.getByText("Baseline contract for support agents."),
  ).toBeVisible();
  await expect(page.getByText("customer-support")).toBeVisible();
  await expect(page.getByText("Version 1")).toBeVisible();
});

test("contract template library forks a platform template", async ({
  page,
}) => {
  await page.goto("/agent-management/contracts/library");

  await page.getByRole("button", { name: "Fork" }).click();
  await expect(
    page.getByRole("heading", { name: "Fork template" }),
  ).toBeVisible();
  await expect(page.getByRole("textbox")).toHaveValue(
    "Customer support agent contract copy",
  );
  await page.getByRole("button", { name: "Fork" }).last().click();
});

test("composition wizard blocks navigation until a blueprint is generated", async ({
  page,
}) => {
  await page.goto("/agent-management/wizard");

  await expect(page.getByRole("button", { name: "Back" })).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Next", exact: true }),
  ).toBeDisabled();
});

test("composition wizard renders all creator-contract steps in the stepper", async ({
  page,
}) => {
  await page.goto("/agent-management/wizard");

  for (const label of [
    "Describe",
    "Review Blueprint",
    "Customize",
    "Validate",
    "Context Profile",
    "Test Profile",
    "Contract",
    "Preview Contract",
    "Attach Both",
  ]) {
    await expect(page.getByText(label).first()).toBeVisible();
  }
});

test("composition wizard exposes creator profile and contract steps", async ({
  page,
}) => {
  await page.goto("/agent-management/wizard");

  await expect(page.getByText("Context Profile")).toBeVisible();
  await expect(page.getByText("Test Profile")).toBeVisible();
  await expect(page.getByText("Preview Contract")).toBeVisible();
  await page
    .getByLabel("Agent description")
    .fill(
      "A KYC verification agent that checks identity packages and escalates suspicious findings.",
    );
  await page.getByRole("button", { name: "Generate blueprint" }).click();
  await expect(page.getByRole("heading", { name: /Review/i })).toBeVisible();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Context Profile" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Test Profile" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Contract" })).toBeVisible();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Preview Contract" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Attach Both" }),
  ).toBeVisible();
});
