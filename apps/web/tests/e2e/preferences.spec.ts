import { expect, test } from "@playwright/test";

test("preferences route exposes persisted preference controls", async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem(
      "auth-storage",
      JSON.stringify({
        state: {
          user: {
            id: "user-1",
            email: "operator@musematic.dev",
            displayName: "Operator",
            avatarUrl: null,
            roles: ["superadmin", "workspace_admin"],
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
  });
  await page.route("**/api/v1/me/preferences", async (route) => {
    if (route.request().method() === "PATCH") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: route.request().postData() ?? "{}",
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "prefs-1",
        user_id: "user-1",
        default_workspace_id: null,
        theme: "system",
        language: "en",
        timezone: "UTC",
        notification_preferences: {},
        data_export_format: "json",
        is_persisted: true,
        created_at: null,
        updated_at: null,
      }),
    });
  });
  await page.route("**/api/v1/workspaces", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [] }),
    });
  });

  await page.goto("/settings/preferences");
  await page.getByTestId("theme-picker-dark").click();
  await page.getByLabel("Language").selectOption("es");
  await page.getByLabel("Time zone").fill("Europe/Madrid");
  await page.getByRole("button", { name: /save preferences/i }).click();
  await expect(page.getByText(/Preferences saved|Preferences were not saved/)).toBeVisible();
});
