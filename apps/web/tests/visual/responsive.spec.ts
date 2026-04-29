import { expect, test, type Page } from "@playwright/test";
import { auditedSurfaces } from "@/tests/a11y/audited-surfaces";
import { marketplaceFixtures } from "@/mocks/handlers/marketplace";

const viewports = [
  { width: 375, height: 812 },
  { width: 768, height: 1024 },
  { width: 1280, height: 900 },
] as const;

const responsiveRoutes = auditedSurfaces
  .map((surface) => ({
    id: surface.id,
    route: surface.route,
    ready: surface.ready,
  }));
const baseUrl = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";

const user = {
  id: "responsive-user",
  email: "responsive@musematic.dev",
  displayName: "Responsive Tester",
  avatarUrl: null,
  roles: [
    "superadmin",
    "platform_admin",
    "workspace_admin",
    "workspace_editor",
    "agent_operator",
    "agent_viewer",
    "analytics_viewer",
    "policy_manager",
    "trust_officer",
    "trust_certifier",
  ],
  workspaceId: "workspace-1",
  mfaEnrolled: true,
};

const preferences = {
  id: "prefs-responsive",
  user_id: user.id,
  default_workspace_id: "workspace-1",
  theme: "system",
  language: "en",
  timezone: "UTC",
  notification_preferences: {},
  data_export_format: "json",
  is_persisted: true,
  created_at: "2026-04-10T09:00:00.000Z",
  updated_at: "2026-04-10T09:00:00.000Z",
};

const incidents = [
  {
    id: "incident-1",
    condition_fingerprint: "capacity:queue-depth",
    severity: "warning",
    status: "open",
    title: "Queue depth above warning threshold",
    description: "The execution queue is elevated in the primary workspace.",
    triggered_at: "2026-04-29T08:15:00.000Z",
    resolved_at: null,
    related_executions: ["execution-1"],
    related_event_ids: ["event-1"],
    runbook_scenario: "queue-depth",
    alert_rule_class: "capacity",
    post_mortem_id: null,
  },
];

const localeVersions = ["en", "es", "fr", "de", "ja", "zh-CN"].map((locale, index) => ({
  id: `locale-${locale}`,
  locale_code: locale,
  version: 1,
  published_at: "2026-04-10T09:00:00.000Z",
  published_by: "responsive-user",
  vendor_source_ref: index === 0 ? "source" : "vendor",
  created_at: "2026-04-10T09:00:00.000Z",
}));

async function installAuthenticatedState(page: Page) {
  await page.addInitScript((sessionUser) => {
    window.localStorage.setItem(
      "auth-storage",
      JSON.stringify({
        state: {
          user: sessionUser,
          accessToken: "mock-access-token",
          refreshToken: "mock-refresh-token",
          isAuthenticated: true,
          isLoading: false,
        },
        version: 0,
      }),
    );
  }, user);
}

async function mockResponsiveApis(page: Page) {
  await page.route("**/api/v1/workspaces", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ items: marketplaceFixtures.workspaces }),
    });
  });
  await page.route("**/api/v1/me/preferences", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(preferences),
    });
  });
  await page.route("**/me/alerts**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ items: [], total_unread: 0, count: 0 }),
    });
  });
  await page.route("**/api/v1/locales", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(localeVersions),
    });
  });
  await page.route("**/api/v1/locales/*", async (route) => {
    const locale = new URL(route.request().url()).pathname.split("/").pop() ?? "en";
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        ...localeVersions.find((entry) => entry.locale_code === locale),
        translations: {},
      }),
    });
  });
  await page.route("**/api/v1/marketplace/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;

    if (path.endsWith("/filters/metadata")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(marketplaceFixtures.filterMetadata),
      });
      return;
    }

    if (path.endsWith("/recommendations")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(marketplaceFixtures.recommendations),
      });
      return;
    }

    if (path.includes("/reviews")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          items: [],
          total: 0,
          page: 1,
          pageSize: 10,
          hasNext: false,
          hasPrev: false,
        }),
      });
      return;
    }

    if (path.includes("/agents/")) {
      const segments = path.split("/").map(decodeURIComponent);
      const namespace = segments.at(-2);
      const name = segments.at(-1);
      const agent =
        marketplaceFixtures.agents.find(
          (entry) => entry.namespace === namespace && entry.localName === name,
        ) ?? marketplaceFixtures.agents[0];

      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(agent),
      });
      return;
    }

    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: marketplaceFixtures.agents,
        total: marketplaceFixtures.agents.length,
        page: 1,
        pageSize: 20,
        hasNext: false,
        hasPrev: false,
      }),
    });
  });
  await page.route("**/api/v1/incidents**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const detail = path.match(/\/api\/v1\/incidents\/([^/]+)$/);
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(
        detail
          ? {
              ...incidents[0],
              external_alerts: [],
              runbook: null,
              runbook_authoring_link: "/operator/runbooks/new?scenario=queue-depth",
              runbook_scenario_unmapped: true,
            }
          : incidents,
      ),
    });
  });
}

for (const { id, route, ready } of responsiveRoutes) {
  for (const viewport of viewports) {
    test(`${id} has no page-level horizontal scroll at ${viewport.width}px`, async ({ page }) => {
      if (id !== "login" && id !== "signup") {
        await installAuthenticatedState(page);
      }
      await mockResponsiveApis(page);
      await page.setViewportSize(viewport);
      await page.goto(new URL(route, baseUrl).toString());
      await ready(page);
      const hasHorizontalScroll = await page.evaluate(
        () => document.documentElement.scrollWidth > window.innerWidth,
      );
      expect(hasHorizontalScroll).toBe(false);
    });
  }
}
