import { expect, test, type Page, type Route } from "@playwright/test";
import { mockAuthApi, signIn } from "../../e2e/auth/helpers";

async function fulfillJson(route: Route, json: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(json),
  });
}

async function mockTenantContext(page: Page) {
  await page.route("**/api/v1/me/tenant", async (route) => {
    await fulfillJson(route, {
      id: "00000000-0000-0000-0000-000000000001",
      slug: "default",
      kind: "default",
      status: "active",
      display_name: "Musematic",
      branding: {},
    });
  });
}

async function mockMemberships(page: Page, membershipsCount: 1 | 3) {
  const memberships = [
    {
      tenant_id: "00000000-0000-0000-0000-000000000001",
      tenant_slug: "default",
      tenant_kind: "default",
      tenant_display_name: "Musematic",
      user_id_within_tenant: "4d1b0f76-a961-4f8d-8bcb-3f7d5f530001",
      role: "workspace_owner",
      is_current_tenant: true,
      login_url: "http://app.localhost:3000/login",
    },
    {
      tenant_id: "11111111-1111-1111-1111-111111111111",
      tenant_slug: "acme",
      tenant_kind: "enterprise",
      tenant_display_name: "Acme Corp",
      user_id_within_tenant: "4d1b0f76-a961-4f8d-8bcb-3f7d5f530002",
      role: "tenant_admin",
      is_current_tenant: false,
      login_url: "http://acme.localhost:3000/login",
    },
    {
      tenant_id: "22222222-2222-2222-2222-222222222222",
      tenant_slug: "globex",
      tenant_kind: "enterprise",
      tenant_display_name: "Globex",
      user_id_within_tenant: "4d1b0f76-a961-4f8d-8bcb-3f7d5f530003",
      role: "viewer",
      is_current_tenant: false,
      login_url: "http://globex.localhost:3000/login",
    },
  ].slice(0, membershipsCount);

  await page.route("**/api/v1/me/memberships", async (route) => {
    await fulfillJson(route, {
      memberships,
      count: memberships.length,
    });
  });
}

test("tenant switcher hides for one membership and redirects without cross-subdomain cookies", async ({
  page,
}) => {
  await mockTenantContext(page);
  await mockAuthApi(page);

  await mockMemberships(page, 1);
  await page.goto("http://app.localhost:3000/login");
  await signIn(page);
  await expect(page).toHaveURL(/home/);
  await expect(page.getByRole("button", { name: /musematic/i })).toHaveCount(0);

  await mockMemberships(page, 3);
  await page.reload();
  await expect(page.getByRole("button", { name: /musematic/i })).toBeVisible();

  await page.context().addCookies([
    {
      name: "session",
      value: "default-session",
      domain: "app.localhost",
      path: "/",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await page.getByRole("button", { name: /musematic/i }).click();
  await page.getByRole("menuitem", { name: /acme corp/i }).click();
  await expect(page).toHaveURL(/http:\/\/acme\.localhost:3000\/login/);

  const acmeCookies = await page
    .context()
    .cookies("http://acme.localhost:3000");
  expect(
    acmeCookies.find((cookie) => cookie.name === "session"),
  ).toBeUndefined();
});
