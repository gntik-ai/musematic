import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { auditedSurfaces, surfacesForGroup, type A11ySurfaceGroup } from "@/tests/a11y/audited-surfaces";

const localePattern = /-(en|es|fr|de|ja|zh-CN)$/;
const themePattern = /^a11y-(light|dark|system|high_contrast)-/;

function contextFromProject(projectName: string) {
  return {
    theme: projectName.match(themePattern)?.[1] ?? "system",
    locale: projectName.match(localePattern)?.[1] ?? "en",
  };
}

async function fulfillJson(page: Page, pattern: string, payload: unknown, status = 200) {
  await page.route(pattern, async (route) => {
    await route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(payload),
    });
  });
}

async function installA11yState(page: Page, theme: string, locale: string) {
  await page.addInitScript(
    ({ theme, locale }) => {
      window.localStorage.setItem(
        "auth-storage",
        JSON.stringify({
          state: {
            user: {
              id: "user-a11y",
              email: "a11y@musematic.dev",
              displayName: "A11y User",
              avatarUrl: null,
              roles: ["superadmin", "platform_admin", "workspace_admin", "agent_operator", "analytics_viewer"],
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
      window.localStorage.setItem("musematic-theme", theme);
      document.cookie = `musematic-theme=${theme}; Path=/; SameSite=Lax`;
      document.cookie = `musematic-locale=${locale}; Path=/; SameSite=Lax`;
    },
    { theme, locale },
  );
}

async function mockA11yApis(page: Page) {
  await fulfillJson(page, "**/api/v1/workspaces", {
    items: [
      {
        id: "workspace-1",
        name: "Risk Ops",
        slug: "risk-ops",
        description: "Primary workspace",
        memberCount: 8,
        createdAt: "2026-04-10T09:00:00.000Z",
      },
    ],
  });
  await fulfillJson(page, "**/api/v1/me/preferences", {
    id: "prefs-1",
    user_id: "user-a11y",
    default_workspace_id: "workspace-1",
    theme: "system",
    language: "en",
    timezone: "UTC",
    notification_preferences: {},
    data_export_format: "json",
    is_persisted: true,
    created_at: "2026-04-10T09:00:00.000Z",
    updated_at: "2026-04-10T09:00:00.000Z",
  });
  await fulfillJson(page, "**/me/alerts**", { items: [], total_unread: 0 });
  await fulfillJson(page, "**/api/v1/locales", { items: [] });
  await fulfillJson(page, "**/api/v1/locales/*", {
    locale_code: "en",
    version: 1,
    translations: {},
    published_at: "2026-04-10T09:00:00.000Z",
  });
}

export function runA11yGroup(group: A11ySurfaceGroup) {
  for (const surface of surfacesForGroup(group)) {
    test(`${surface.id} has no WCAG 2.1 AA violations @a11y`, async ({ page }, testInfo) => {
      const { theme, locale } = contextFromProject(testInfo.project.name);
      await mockA11yApis(page);
      await installA11yState(page, theme, locale);
      await page.goto(`${surface.route}${surface.route.includes("?") ? "&" : "?"}lang=${locale}`);
      await surface.ready(page);
      await page.locator("html").evaluate((html, theme) => {
        html.classList.remove("light", "dark", "system", "high_contrast");
        if (theme !== "system") {
          html.classList.add(String(theme));
        }
      }, theme);
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      expect(results.violations).toEqual([]);
    });
  }
}

export { auditedSurfaces };
