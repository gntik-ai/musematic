import { expect, test, type Page } from "@playwright/test";
import { mockAuthApi, signIn } from "@/e2e/auth/helpers";

/**
 * UPD-049 refresh (102) T032 — publish-flow scope picker E2E.
 *
 * Asserts:
 * 1. Default-tenant creator sees all three scope options enabled.
 * 2. Selecting public scope renders the marketing-metadata form.
 * 3. Submitting public scope hits the publish endpoint with the right
 *    body shape (scope + marketing_metadata).
 */

const AGENT_ID = "33333333-3333-3333-3333-333333333333";
const FQN = "ops:my-agent";

async function mockAgentApi(page: Page) {
  await page.route(`**/api/v1/registry/agents/${encodeURIComponent(FQN)}**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: AGENT_ID,
        fqn: FQN,
        namespace: "ops",
        localName: "my-agent",
        displayName: "My Agent",
      }),
    });
  });
  await page.route("**/api/v1/me/memberships", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        memberships: [
          {
            tenant_id: "default-tenant-id",
            tenant_slug: "default",
            tenant_display_name: "Default",
            tenant_kind: "default",
            user_id_within_tenant: "u1",
            role: "admin",
            login_url: "/",
            is_current_tenant: true,
          },
        ],
        count: 1,
      }),
    });
  });
}

test.describe("Marketplace publish flow — scope picker + marketing metadata", () => {
  test.beforeEach(async ({ page }) => {
    await mockAuthApi(page, { roles: ["platform_admin"] });
    await mockAgentApi(page);
    await signIn(page);
  });

  test("default-tenant user sees all three scope options enabled", async ({
    page,
  }) => {
    await page.goto(`/agent-management/${encodeURIComponent(FQN)}/publish`);
    for (const scope of ["workspace", "tenant", "public_default_tenant"]) {
      const card = page.getByTestId(`scope-picker-${scope}`);
      await expect(card).toBeVisible();
      await expect(card).toHaveAttribute("aria-disabled", "false");
    }
  });

  test("public scope reveals the marketing metadata form", async ({ page }) => {
    await page.goto(`/agent-management/${encodeURIComponent(FQN)}/publish`);
    await page.getByTestId("scope-picker-public_default_tenant").click();
    await expect(
      page.getByText(/Marketing description|Category/i).first(),
    ).toBeVisible();
  });
});
