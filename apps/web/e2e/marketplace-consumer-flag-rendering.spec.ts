import { expect, test, type Page } from "@playwright/test";
import { mockAuthApi, signIn } from "@/e2e/auth/helpers";

/**
 * UPD-049 refresh (102) T043 — consume-flag rendering on cards.
 *
 * Verifies the visual differentiation per FR-741.2:
 *
 * 1. When the marketplace projection includes a public-origin agent
 *    (`marketplaceScope = "public_default_tenant"` or
 *    `isFromPublicHub = true`), the agent card renders the
 *    `<PublicSourceLabel />` badge.
 * 2. Cards owned by the viewer's tenant do NOT render the badge.
 *
 * Backend visibility filtering (consume-flag on / off) is exercised by
 * `tests/integration/marketplace/test_consume_flag_search.py` and
 * `test_no_consume_flag_isolation.py` under the `integration_live`
 * mark.
 */

const TENANT_AGENT_FQN = "acme:internal-agent";
const PUBLIC_AGENT_FQN = "anthropic:public-agent";

async function mockMixedMarketplace(page: Page) {
  await page.route("**/api/v1/marketplace/agents**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          {
            id: "agent-tenant",
            fqn: TENANT_AGENT_FQN,
            namespace: "acme",
            localName: "internal-agent",
            displayName: "Acme Internal",
            shortDescription: "Tenant-scoped Acme agent.",
            maturityLevel: "production",
            trustTier: "standard",
            certificationStatus: "active",
            costTier: "low",
            capabilities: ["analytics"],
            tags: ["acme"],
            averageRating: 4.5,
            reviewCount: 5,
            currentRevision: "v1.0.0",
            createdById: "u1",
            marketplaceScope: "tenant",
            isFromPublicHub: false,
          },
          {
            id: "agent-public",
            fqn: PUBLIC_AGENT_FQN,
            namespace: "anthropic",
            localName: "public-agent",
            displayName: "Public Hub Agent",
            shortDescription: "Public default-tenant agent.",
            maturityLevel: "production",
            trustTier: "certified",
            certificationStatus: "active",
            costTier: "low",
            capabilities: ["automation"],
            tags: ["public"],
            averageRating: 4.9,
            reviewCount: 200,
            currentRevision: "v3.1.0",
            createdById: "u-default",
            marketplaceScope: "public_default_tenant",
            isFromPublicHub: true,
          },
        ],
        nextCursor: null,
        total: 2,
      }),
    });
  });
}

test.describe("Marketplace browse — public-source label", () => {
  test.beforeEach(async ({ page }) => {
    await mockAuthApi(page);
    await mockMixedMarketplace(page);
    await signIn(page);
  });

  test("public-origin agent card renders the public-source badge", async ({
    page,
  }) => {
    await page.goto("/marketplace");
    // The PublicSourceLabel component renders text "From public marketplace"
    // (or similar) — assert at least one badge appears for the public row.
    const labels = page.getByText(/from public marketplace/i);
    await expect(labels.first()).toBeVisible();
  });

  test("tenant-scoped card does NOT render the public-source badge", async ({
    page,
  }) => {
    await page.goto("/marketplace");
    // Locate the tenant card by its display name and assert no
    // public-source label inside its bounding card.
    const tenantCard = page
      .getByRole("link", { name: /Acme Internal/i })
      .first();
    await expect(tenantCard).toBeVisible();
    const tenantPublicLabel = tenantCard.getByText(/from public marketplace/i);
    await expect(tenantPublicLabel).toHaveCount(0);
  });
});
