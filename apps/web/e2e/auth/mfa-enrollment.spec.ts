import { expect, test, type Page } from "@playwright/test";
import { mockAuthApi } from "./helpers";

async function installAuthenticatedState(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem(
      "auth-storage",
      JSON.stringify({
        state: {
          user: {
            id: "4d1b0f76-a961-4f8d-8bcb-3f7d5f530001",
            email: "alex@musematic.dev",
            displayName: "Alex Mercer",
            avatarUrl: null,
            roles: ["workspace_admin", "agent_operator", "analytics_viewer"],
            workspaceId: "workspace-1",
            mfaEnrolled: false,
          },
          refreshToken: "mock-refresh-token",
          isAuthenticated: true,
          isLoading: false,
        },
        version: 0,
      }),
    );

    localStorage.setItem(
      "workspace-storage",
      JSON.stringify({
        state: {
          currentWorkspace: {
            id: "workspace-1",
            name: "Risk Ops",
            slug: "risk-ops",
            description: "Primary workspace",
            memberCount: 8,
            createdAt: "2026-04-10T09:00:00.000Z",
          },
          sidebarCollapsed: false,
        },
        version: 0,
      }),
    );
  });
}

test("users without MFA enrolled complete enrollment from the dashboard dialog", async ({
  page,
}) => {
  await mockAuthApi(page, { mfaEnrolled: false });
  await installAuthenticatedState(page);
  await page.goto("/home");

  await expect(page.getByText(/set up authenticator/i)).toBeVisible();
  await expect(page.getByText(/enter this code manually/i)).toBeVisible();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByLabel(/authenticator verification code/i).fill("123456");
  await expect(page.getByText(/save your recovery codes/i)).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(page.getByText(/save your recovery codes/i)).toBeVisible();

  await page
    .getByLabel(/i have saved my recovery codes in a safe place/i)
    .check();
  await page.getByRole("button", { name: /complete setup/i }).click();

  await expect(page.getByText(/save your recovery codes/i)).not.toBeVisible();
  await expect(page.getByRole("heading", { name: /risk ops overview/i })).toBeVisible();
});
