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
  const oauthProviders = [
    {
      id: "google-provider-id",
      provider_type: "google",
      display_name: "Google",
      enabled: true,
      client_id: "google-client.apps.googleusercontent.com",
      client_secret_ref: "secret/data/musematic/dev/oauth/google/client-secret",
      redirect_uri: "https://app.musematic.dev/auth/oauth/google/callback",
      scopes: ["openid", "email", "profile"],
      domain_restrictions: ["musematic.dev"],
      org_restrictions: [],
      group_role_mapping: { "admins@musematic.dev": "admin" },
      default_role: "member",
      require_mfa: false,
      source: "env_var",
      last_edited_by: null,
      last_edited_at: null,
      last_successful_auth_at: "2026-04-18T07:30:00.000Z",
      created_at: "2026-04-18T07:00:00.000Z",
      updated_at: "2026-04-18T07:30:00.000Z",
    },
    {
      id: "github-provider-id",
      provider_type: "github",
      display_name: "GitHub",
      enabled: true,
      client_id: "github-client",
      client_secret_ref: "secret/data/musematic/dev/oauth/github/client-secret",
      redirect_uri: "https://app.musematic.dev/auth/oauth/github/callback",
      scopes: ["read:user", "user:email"],
      domain_restrictions: [],
      org_restrictions: ["musematic"],
      group_role_mapping: { "musematic/platform-admins": "admin" },
      default_role: "member",
      require_mfa: false,
      source: "manual",
      last_edited_by: "admin-user-id",
      last_edited_at: "2026-04-18T07:45:00.000Z",
      last_successful_auth_at: null,
      created_at: "2026-04-18T07:00:00.000Z",
      updated_at: "2026-04-18T07:45:00.000Z",
    },
  ];
  const oauthRateLimits = {
    per_ip_max: 10,
    per_ip_window: 60,
    per_user_max: 10,
    per_user_window: 60,
    global_max: 100,
    global_window: 60,
  };

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
  await fulfillJson(page, "**/api/v1/admin/oauth/providers", {
    providers: oauthProviders,
  });
  await fulfillJson(page, "**/api/v1/admin/oauth-providers/*/status", {
    provider_type: "google",
    source: "env_var",
    last_successful_auth_at: "2026-04-18T07:30:00.000Z",
    auth_count_24h: 3,
    auth_count_7d: 11,
    auth_count_30d: 27,
    active_linked_users: 1,
  });
  await fulfillJson(page, "**/api/v1/admin/oauth-providers/*/history", {
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
  });
  await fulfillJson(page, "**/api/v1/admin/oauth-providers/*/rate-limits", oauthRateLimits);
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
