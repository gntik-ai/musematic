import { expect, test, type Page, type Route } from "@playwright/test";
import { getConversationFixtures, resetConversationFixtures } from "../../tests/mocks/handlers/conversations";

async function fulfillJson(route: Route, json: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(json),
  });
}

async function mockConversationApi(page: Page) {
  resetConversationFixtures();
  const fixtures = getConversationFixtures();

  await page.route("**/api/v1/conversations/conversation-1", async (route) => {
    const conversation = fixtures.conversations.find(
      (item) => item.id === "conversation-1",
    );

    await fulfillJson(route, conversation ?? {}, conversation ? 200 : 404);
  });

  await page.route("**/api/v1/interactions/*/messages**", async (route) => {
    const interactionId = route.request().url().split("/").slice(-2)[0] ?? "";
    const items = fixtures.interactionMessages[interactionId] ?? [];

    await fulfillJson(route, {
      items,
      next_cursor: null,
    });
  });

  await page.route(
    "**/api/v1/conversations/conversation-1/branches/*/messages**",
    async (route) => {
      const branchId = route.request().url().split("/").slice(-2)[0] ?? "";
      const items = fixtures.branchMessages[branchId] ?? [];

      await fulfillJson(route, {
        items,
        next_cursor: null,
      });
    },
  );

  await page.route("**/api/v1/workspaces/workspace-1/goals", async (route) => {
    await fulfillJson(route, {
      items: fixtures.workspaceGoals["workspace-1"] ?? [],
    });
  });

  await page.route(
    "**/api/v1/workspaces/workspace-1/goals/*/messages**",
    async (route) => {
      const goalId = route.request().url().split("/").slice(-2)[0] ?? "";
      const items = fixtures.goalMessages[goalId] ?? [];

      await fulfillJson(route, {
        items,
        next_cursor: null,
      });
    },
  );
}

async function seedSession(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem(
      "auth-storage",
      JSON.stringify({
        state: {
          user: {
            id: "user-1",
            email: "alex@musematic.dev",
            displayName: "Alex Mercer",
            avatarUrl: null,
            roles: ["workspace_admin", "agent_operator"],
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

    window.localStorage.setItem(
      "workspace-storage",
      JSON.stringify({
        state: {
          currentWorkspace: {
            id: "workspace-1",
            name: "Current workspace",
            slug: "current-workspace",
            description: null,
            memberCount: 8,
            createdAt: "2026-04-01T08:00:00.000Z",
          },
          workspaceList: [
            {
              id: "workspace-1",
              name: "Current workspace",
              slug: "current-workspace",
              description: null,
              memberCount: 8,
              createdAt: "2026-04-01T08:00:00.000Z",
            },
          ],
          sidebarCollapsed: false,
          isLoading: false,
        },
        version: 0,
      }),
    );

    window.localStorage.setItem("theme", "dark");
  });
}

async function expectNoHorizontalOverflow(page: Page) {
  const hasOverflow = await page.evaluate(() => {
    const root = document.documentElement;
    return root.scrollWidth > root.clientWidth + 1;
  });

  expect(hasOverflow).toBeFalsy();
}

test("conversation workspace stays readable in dark mode and responsive on mobile", async ({ page }) => {
  await seedSession(page);
  await mockConversationApi(page);
  await page.emulateMedia({ colorScheme: "dark" });

  await page.goto("/conversations/conversation-1");

  await expect(page.locator("html")).toHaveClass(/dark/);
  await expect(
    page.getByRole("heading", { name: "Quarterly performance review" }),
  ).toBeVisible();
  await expect(page.locator('[role="tablist"]')).toBeVisible();
  await expect(page.getByRole("tabpanel")).toBeVisible();

  await page.setViewportSize({ width: 320, height: 900 });
  await expectNoHorizontalOverflow(page);
  await expect(page.getByText("finance-ops:analyzer")).toBeVisible();
  await expect(page.getByRole("button", { name: "Goal feed" })).toBeVisible();

  await page.getByRole("button", { name: "Goal feed" }).click();
  const goalSheet = page.getByRole("dialog");
  await expect(goalSheet).toBeVisible();
  await expect(goalSheet.getByRole("combobox")).toHaveValue("goal-1");
  await expectNoHorizontalOverflow(page);

  const mobileSheetBox = await goalSheet.boundingBox();
  expect(mobileSheetBox?.width ?? 0).toBeGreaterThanOrEqual(280);

  await page.setViewportSize({ width: 1280, height: 900 });
  await expectNoHorizontalOverflow(page);
  await expect(page.getByRole("button", { name: "Goal feed" })).toBeVisible();
});
