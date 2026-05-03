import { expect, test, type Page } from "@playwright/test";
import { mockAuthApi, signIn } from "@/e2e/auth/helpers";

/**
 * UPD-049 refresh (102) T037 — Enterprise tenant cannot publish public.
 *
 * Asserts the UI leg of the FR-741 three-layer refusal (UI + service + DB):
 * 1. Scope picker renders with the public option visibly disabled
 *    (`aria-disabled=true`) for an Enterprise tenant.
 * 2. Workspace and tenant scopes remain enabled.
 *
 * Backend service-layer and DB-CHECK refusal coverage lives in
 * `tests/integration/marketplace/test_publish_public_refused_for_enterprise.py`
 * and `test_check_constraint_refusal.py` respectively (both under the
 * `integration_live` mark — see T035, T036).
 */

const AGENT_ID = "44444444-4444-4444-4444-444444444444";
const FQN = "ops:enterprise-agent";

async function mockEnterpriseTenantApi(page: Page) {
  await page.route(`**/api/v1/registry/agents/${encodeURIComponent(FQN)}**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: AGENT_ID,
        fqn: FQN,
        namespace: "ops",
        localName: "enterprise-agent",
        displayName: "Enterprise Agent",
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
            tenant_id: "acme-tenant-id",
            tenant_slug: "acme",
            tenant_display_name: "Acme",
            tenant_kind: "enterprise",
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

test.describe("Enterprise tenant — public scope disabled in UI", () => {
  test.beforeEach(async ({ page }) => {
    await mockAuthApi(page, { roles: ["platform_admin"] });
    await mockEnterpriseTenantApi(page);
    await signIn(page);
  });

  test("public scope picker option is aria-disabled for enterprise tenant", async ({
    page,
  }) => {
    await page.goto(`/agent-management/${encodeURIComponent(FQN)}/publish`);
    const publicCard = page.getByTestId("scope-picker-public_default_tenant");
    await expect(publicCard).toBeVisible();
    await expect(publicCard).toHaveAttribute("aria-disabled", "true");
    // The other two scope options remain enabled.
    await expect(page.getByTestId("scope-picker-workspace")).toHaveAttribute(
      "aria-disabled",
      "false",
    );
    await expect(page.getByTestId("scope-picker-tenant")).toHaveAttribute(
      "aria-disabled",
      "false",
    );
  });
});
