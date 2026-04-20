import { expect, test } from "@playwright/test";
import {
  fulfillJson,
  installFrontendState,
  workspaceFixture,
} from "@/e2e/frontend-expansions/helpers";

test.beforeEach(async ({ page }) => {
  await installFrontendState(page, {
    roles: ["platform_admin", "workspace_admin"],
    workspaceId: workspaceFixture.id,
  });

  await page.route("**/api/v1/workspaces/workspace-1/governance-chain", async (route) => {
    if (route.request().method() === "PUT") {
      await fulfillJson(route, {
        id: "chain-1",
        workspace_id: "workspace-1",
        observer_fqns: ["ops:observer"],
        judge_fqns: ["ops:verdict-authority"],
        enforcer_fqns: [],
        created_at: "2026-04-20T10:00:00.000Z",
      });
      return;
    }

    await fulfillJson(route, {
      id: "chain-1",
      workspace_id: "workspace-1",
      observer_fqns: ["ops:observer"],
      judge_fqns: [],
      enforcer_fqns: [],
      created_at: "2026-04-20T10:00:00.000Z",
    });
  });

  await page.route("**/api/v1/workspaces/workspace-1/visibility", async (route) => {
    if (route.request().method() === "PUT") {
      const payload = route.request().postDataJSON() as Record<string, unknown>;
      await fulfillJson(route, {
        workspace_id: "workspace-1",
        visibility_agents: payload.visibility_agents,
        visibility_tools: [],
        updated_at: "2026-04-20T10:00:00.000Z",
      });
      return;
    }

    await fulfillJson(route, {
      workspace_id: "workspace-1",
      visibility_agents: ["ops:*"],
      visibility_tools: [],
      updated_at: "2026-04-20T10:00:00.000Z",
    });
  });
});

test("edits the governance chain and saves visibility grants", async ({ page }) => {
  let governancePayload: Record<string, unknown> | null = null;
  let visibilityPayload: Record<string, unknown> | null = null;

  await page.unroute("**/api/v1/workspaces/workspace-1/governance-chain");
  await page.route("**/api/v1/workspaces/workspace-1/governance-chain", async (route) => {
    if (route.request().method() === "PUT") {
      governancePayload = route.request().postDataJSON() as Record<string, unknown>;
      await fulfillJson(route, {
        id: "chain-1",
        workspace_id: "workspace-1",
        observer_fqns: ["ops:observer"],
        judge_fqns: ["ops:verdict-authority"],
        enforcer_fqns: [],
        created_at: "2026-04-20T10:00:00.000Z",
      });
      return;
    }

    await fulfillJson(route, {
      id: "chain-1",
      workspace_id: "workspace-1",
      observer_fqns: ["ops:observer"],
      judge_fqns: [],
      enforcer_fqns: [],
      created_at: "2026-04-20T10:00:00.000Z",
    });
  });

  await page.unroute("**/api/v1/workspaces/workspace-1/visibility");
  await page.route("**/api/v1/workspaces/workspace-1/visibility", async (route) => {
    if (route.request().method() === "PUT") {
      visibilityPayload = route.request().postDataJSON() as Record<string, unknown>;
      await fulfillJson(route, {
        workspace_id: "workspace-1",
        visibility_agents: visibilityPayload.visibility_agents,
        visibility_tools: [],
        updated_at: "2026-04-20T10:10:00.000Z",
      });
      return;
    }

    await fulfillJson(route, {
      workspace_id: "workspace-1",
      visibility_agents: ["ops:*"],
      visibility_tools: [],
      updated_at: "2026-04-20T10:00:00.000Z",
    });
  });

  await page.goto("/settings/governance");
  await expect(page.getByText("No judge assigned — default applies.")).toBeVisible();

  await page.getByPlaceholder("agent namespace:fqn for judge").fill("ops:verdict-authority");
  await page.getByRole("button", { name: "Save governance chain" }).click();
  await expect(page.getByText("Confirm governance update")).toBeVisible();
  await page.getByRole("button", { name: "Save" }).nth(1).click();

  await expect.poll(() => governancePayload).not.toBeNull();
  expect(governancePayload).toEqual({
    observer_fqns: ["ops:observer"],
    judge_fqns: ["ops:verdict-authority"],
    enforcer_fqns: [],
    policy_binding_ids: [],
    verdict_to_action_mapping: {},
  });

  await page.goto("/settings/visibility");
  await page.getByRole("button", { name: "Add pattern" }).click();
  await page.locator("main input").last().fill("workspace:*/agent:compliance-*");
  await expect(page.getByText("Agents matching workspace:*/agent:compliance-*")).toBeVisible();
  await page.getByRole("button", { name: "Save visibility grants" }).click();

  await expect.poll(() => visibilityPayload).not.toBeNull();
  expect(visibilityPayload).toEqual({
    visibility_agents: ["ops:*", "workspace:*/agent:compliance-*"],
    visibility_tools: [],
  });
});
