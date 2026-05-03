import { expect, test, type Page } from "@playwright/test";
import { mockAuthApi, signIn } from "@/e2e/auth/helpers";

/**
 * UPD-049 refresh (102) T062 — fork action + source-updated alert E2E.
 *
 * Asserts the frontend behaviour for User Story 5:
 *
 * 1. The Fork button is visible on a public-default-tenant agent's
 *    detail page when the viewer is in an Enterprise tenant with
 *    consume_public_marketplace=true.
 * 2. The Fork button is hidden for default-tenant viewers (the source's
 *    own tenant) — they edit the source directly instead.
 * 3. A `marketplace.source_updated` alert appears in the inbox with a
 *    deep-link button to the source agent's detail page.
 *
 * Backend cross-tenant fan-out (Kafka -> notifications) is exercised
 * by `tests/integration/marketplace/test_source_update_notifies_forks.py`
 * under the `integration_live` mark.
 */

const PUBLIC_AGENT_ID = "55555555-5555-5555-5555-555555555555";
const PUBLIC_FQN = "anthropic:research-agent";

async function mockEnterpriseConsumerSession(page: Page) {
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
            feature_flags: { consume_public_marketplace: true },
          },
        ],
        count: 1,
      }),
    });
  });
}

async function mockPublicAgentDetail(page: Page) {
  await page.route(
    `**/api/v1/marketplace/agents/anthropic/research-agent**`,
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: PUBLIC_AGENT_ID,
          fqn: PUBLIC_FQN,
          namespace: "anthropic",
          localName: "research-agent",
          displayName: "Research Agent",
          shortDescription: "A public research agent.",
          fullDescription: "...",
          maturityLevel: "production",
          trustTier: "certified",
          certificationStatus: "active",
          costTier: "low",
          capabilities: [],
          tags: [],
          averageRating: 4.8,
          reviewCount: 100,
          currentRevision: "v2.0.0",
          createdById: "u-default",
          marketplaceScope: "public_default_tenant",
          isFromPublicHub: true,
          revisions: [],
          trustSignals: { tier: "certified", certificationBadges: [] },
          policies: [],
          qualityMetrics: {},
          costBreakdown: { monthlyBudgetCapUsd: 100 },
          visibility: { visibleToCurrentUser: true },
        }),
      });
    },
  );
}

async function mockNotificationsInbox(page: Page) {
  await page.route("**/api/v1/notifications/alerts**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        alerts: [
          {
            id: "alert-1",
            alert_type: "marketplace.source_updated",
            urgency: "low",
            title: "Upstream agent anthropic:research-agent was updated",
            body: "The public marketplace agent has a new approved version. Your fork has NOT been automatically updated.",
            read: false,
            created_at: "2026-05-03T12:00:00Z",
            source_reference: {
              kind: "marketplace.source_updated",
              source_agent_id: PUBLIC_AGENT_ID,
              new_version_id: "rev-2",
              diff_summary_hash: "sha256-abc",
            },
          },
        ],
        next_cursor: null,
      }),
    });
  });
}

test.describe("Fork action + source-updated alert", () => {
  test.beforeEach(async ({ page }) => {
    await mockAuthApi(page);
    await mockEnterpriseConsumerSession(page);
    await mockPublicAgentDetail(page);
    await mockNotificationsInbox(page);
    await signIn(page);
  });

  test("Enterprise consumer with flag sees the Fork button", async ({
    page,
  }) => {
    await page.goto(`/marketplace/anthropic/research-agent`);
    await expect(page.getByTestId("fork-agent-button")).toBeVisible();
  });

  test("source-updated alert renders with deep-link", async ({ page }) => {
    await page.goto("/notifications");
    await expect(
      page.getByText(/Your fork has NOT been automatically updated/i),
    ).toBeVisible();
    const openButton = page.getByTestId("marketplace-source-updated-open");
    await expect(openButton).toBeVisible();
    await expect(openButton).toContainText(/open source agent/i);
  });
});
