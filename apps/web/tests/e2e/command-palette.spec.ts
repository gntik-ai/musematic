import { expect, test } from "@playwright/test";

test("command palette exposes language and help commands", async ({ page }) => {
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
  await page.goto("/home?lang=es");
  await page.keyboard.press(process.platform === "darwin" ? "Meta+K" : "Control+K");
  await expect(page.getByTestId("command-input")).toBeVisible();
  await page.getByTestId("command-input").fill("idioma");
  await expect(page.getByText(/Cambiar idioma|Switch language/)).toBeVisible();
  await page.keyboard.press("Escape");
  await page.keyboard.press("?");
  await expect(page.getByRole("dialog", { name: /keyboard shortcuts/i })).toBeVisible();
});
