import { expect, test } from "@playwright/test";
import {
  fulfillJson,
  installFrontendState,
  workspaceFixture,
} from "@/e2e/frontend-expansions/helpers";

const longPurpose =
  "Validate KYC evidence for regulated onboarding flows, escalate ambiguous cases, and keep governance metadata complete for every decision.";

const createdAgent = {
  fqn: "ops:kyc-verifier-v2",
  namespace: "ops",
  local_name: "kyc-verifier-v2",
  name: "KYC Verifier v2",
  description: "KYC verifier",
  maturity_level: "production",
  status: "active",
  revision_count: 1,
  latest_revision_number: 1,
  updated_at: "2026-04-20T10:00:00.000Z",
  workspace_id: workspaceFixture.id,
  tags: ["kyc"],
  category: "compliance",
  purpose: longPurpose,
  approach: "Structured compliance verification.",
  role_type: "verdict_authority",
  custom_role: null,
  reasoning_modes: ["direct"],
  visibility_patterns: [{ pattern: "workspace:*/agent:compliance-*", description: null }],
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

  await page.route("**/api/v1/registry/namespaces?**", async (route) => {
    await fulfillJson(route, {
      items: [
        { namespace: "ops", agent_count: 4 },
        { namespace: "risk", agent_count: 2 },
      ],
    });
  });

  await page.route("**/api/v1/registry/agents/ops%3Akyc-verifier-v2", async (route) => {
    await fulfillJson(route, createdAgent);
  });

  await page.route("**/api/v1/registry/agents/legacy-agent", async (route) => {
    await fulfillJson(route, {
      ...createdAgent,
      fqn: "legacy-agent",
      namespace: null,
      local_name: null,
      name: "Legacy Agent",
      visibility_patterns: [],
    });
  });
});

test("creates an FQN-authored agent and blocks incomplete legacy identity edits", async ({ page }) => {
  let createPayload: Record<string, unknown> | null = null;

  await page.route("**/api/v1/agents", async (route) => {
    createPayload = route.request().postDataJSON() as Record<string, unknown>;
    await fulfillJson(route, createdAgent, 201);
  });

  await page.goto("/agents/create");

  await expect(
    page.locator('select[aria-label="Namespace"] option[value="ops"]'),
  ).toHaveCount(1);

  const submit = page.getByRole("button", { name: "Create Agent" });
  await page.getByLabel("Namespace").selectOption("ops");
  await page.getByLabel("Local Name").fill("kyc-verifier-v2");
  await page.getByLabel("Role Type").selectOption("verdict_authority");
  await page.getByLabel("Purpose").fill("short");

  await expect(page.getByText("5 / 50")).toBeVisible();
  await expect(submit).toBeDisabled();

  await page.getByLabel("Purpose").fill(longPurpose);
  await page.getByRole("button", { name: "Add Pattern" }).click();
  await page.getByLabel("Visibility Pattern 1").fill("workspace:*/agent:compliance-*");

  await expect(page.getByText("Agents matching workspace:*/agent:compliance-*")).toBeVisible();
  await expect(submit).toBeEnabled();

  await submit.click();

  await expect.poll(() => createPayload).not.toBeNull();

  expect(createPayload).toEqual({
    namespace: "ops",
    local_name: "kyc-verifier-v2",
    purpose: longPurpose,
    approach: null,
    role_type: "verdict_authority",
    visibility_patterns: [{ pattern: "workspace:*/agent:compliance-*", description: null }],
  });

  await page.goto("/agents/ops%3Akyc-verifier-v2/edit");
  await expect(page.locator('select[aria-label="Namespace"]')).toHaveValue("ops");

  await page.goto("/agents/legacy-agent/edit");

  await expect(page.getByText("Legacy agent identity required")).toBeVisible();
  await expect(page.getByRole("button", { name: "Save Changes" })).toBeDisabled();
});
