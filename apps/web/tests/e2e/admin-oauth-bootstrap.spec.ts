import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const provider = {
  id: "google-provider-id",
  provider_type: "google",
  display_name: "Google",
  enabled: true,
  client_id: "google-client-id",
  client_secret_ref: "secret://google",
  redirect_uri: "https://app.musematic.dev/oauth/google/callback",
  scopes: ["openid", "email", "profile"],
  domain_restrictions: ["musematic.dev"],
  org_restrictions: [],
  group_role_mapping: { "admins@musematic.dev": "platform_admin" },
  default_role: "viewer",
  require_mfa: false,
  source: "env_var",
  last_edited_by: null,
  last_edited_at: null,
  last_successful_auth_at: "2026-04-18T07:30:00.000Z",
  created_at: "2026-04-18T07:00:00.000Z",
  updated_at: "2026-04-18T07:00:00.000Z",
};

async function installAdminAuth(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem(
      "auth-storage",
      JSON.stringify({
        state: {
          refreshToken: "refresh-token",
          user: {
            id: "admin-1",
            email: "pat.admin@musematic.dev",
            displayName: "Pat Admin",
            avatarUrl: null,
            mfaEnrolled: true,
            roles: ["platform_admin"],
            workspaceId: "workspace-1",
          },
        },
        version: 0,
      }),
    );
  });
}

async function routeOAuthApi(page: Page) {
  await page.route("**/api/v1/admin/oauth/providers", async (route) => {
    await route.fulfill({ json: { providers: [provider] } });
  });
  await page.route("**/api/v1/admin/oauth/providers/google", async (route) => {
    await route.fulfill({ json: provider });
  });
  await page.route("**/api/v1/admin/oauth-providers/*/test-connectivity", async (route) => {
    await route.fulfill({
      json: {
        reachable: true,
        auth_url_returned: true,
        diagnostic: "authorization_url_generated",
      },
    });
  });
  await page.route("**/api/v1/admin/oauth-providers/*/rotate-secret", async (route) => {
    await route.fulfill({ status: 204, body: "" });
  });
  await page.route("**/api/v1/admin/oauth-providers/*/reseed-from-env", async (route) => {
    await route.fulfill({
      json: {
        diff: {
          status: "updated",
          changed_fields: { source: "env_var", force_update: true },
        },
      },
    });
  });
  await page.route("**/api/v1/admin/oauth-providers/*/history**", async (route) => {
    await route.fulfill({
      json: {
        entries: [
          {
            timestamp: "2026-04-18T07:15:00.000Z",
            admin_id: null,
            action: "provider_bootstrapped",
            before: null,
            after: { enabled: true, source: "env_var" },
          },
        ],
        next_cursor: null,
      },
    });
  });
  await page.route("**/api/v1/admin/oauth-providers/*/status", async (route) => {
    await route.fulfill({
      json: {
        provider_type: "google",
        source: "env_var",
        last_successful_auth_at: "2026-04-18T07:30:00.000Z",
        auth_count_24h: 3,
        auth_count_7d: 11,
        auth_count_30d: 27,
        active_linked_users: 4,
      },
    });
  });
  await page.route("**/api/v1/admin/oauth-providers/*/rate-limits", async (route) => {
    if (route.request().method() === "PUT") {
      await route.fulfill({
        json: {
          per_ip_max: 20,
          per_ip_window: 60,
          per_user_max: 15,
          per_user_window: 60,
          global_max: 200,
          global_window: 60,
        },
      });
      return;
    }
    await route.fulfill({
      json: {
        per_ip_max: 10,
        per_ip_window: 60,
        per_user_max: 10,
        per_user_window: 60,
        global_max: 100,
        global_window: 60,
      },
    });
  });
}

test.describe("admin OAuth bootstrap panel", () => {
  test.beforeEach(async ({ page }) => {
    await installAdminAuth(page);
    await routeOAuthApi(page);
  });

  test("renders source badge and preserves provider tab in the URL", async ({ page }) => {
    await page.goto("/admin/settings?tab=oauth");

    await expect(page.getByText("Env var")).toBeVisible();
    await page.getByRole("button", { name: "History" }).first().click();
    await expect(page).toHaveURL(/provider_tab=history/);
    await expect(page.getByText("provider_bootstrapped").first()).toBeVisible();
  });

  test("runs connectivity, rotation, reseed, role mapping, and rate limit workflows", async ({
    page,
  }) => {
    await page.goto("/admin/settings?tab=oauth");

    await page.getByRole("button", { name: "Test connectivity" }).first().click();
    await expect(page.getByText("Connectivity check completed")).toBeVisible();

    await page.getByRole("button", { name: "Rotate secret" }).first().click();
    await page.getByRole("dialog").getByLabel("New client secret").fill("rotated-secret");
    await page.getByRole("dialog").getByLabel(/written to Vault/).check();
    await page.getByRole("dialog").getByRole("button", { name: "Save" }).click();
    await expect(page.getByText("Secret rotated successfully")).toBeVisible();

    await page.getByRole("button", { name: "Reseed from env" }).first().click();
    await page.getByRole("dialog").getByLabel(/overwrite manual changes/).check();
    await page.getByRole("dialog").getByRole("switch", { name: "Force update" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Apply" }).click();
    await expect(page.getByText("Provider reseeded")).toBeVisible();
    await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();

    await page.getByRole("button", { name: "Role mappings" }).first().click();
    await expect(page.locator('input[value="admins@musematic.dev"]').first()).toBeVisible();
    await page.getByRole("button", { name: "Save" }).first().click();
    await expect(page.getByText("Role mappings saved")).toBeVisible();

    await page.getByRole("button", { name: "Rate limits" }).first().click();
    await page.getByLabel("Per-IP max").first().fill("20");
    await page.getByRole("button", { name: "Save" }).first().click();
    await expect(page.getByText("Rate limits saved")).toBeVisible();
  });
});
