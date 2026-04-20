import { expect, test } from "@playwright/test";
import { fulfillJson, installFrontendState } from "@/e2e/frontend-expansions/helpers";

test.beforeEach(async ({ page }) => {
  await installFrontendState(page, {
    roles: ["platform_admin", "workspace_admin", "agent_operator"],
  });

  const items = [
    {
      id: "agent-1",
      fqn: "ops:case-triage",
      namespace: "ops",
      localName: "case-triage",
      displayName: "Case Triage",
      shortDescription: "Coordinates case intake.",
      maturityLevel: "production",
      trustTier: "certified",
      certificationStatus: "active",
      costTier: "low",
      capabilities: [],
      tags: [],
      averageRating: 4.8,
      reviewCount: 9,
      currentRevision: "v2",
      createdById: "user-1",
    },
    {
      id: "agent-2",
      fqn: "ops:expired-worker",
      namespace: "ops",
      localName: "expired-worker",
      displayName: "Expired Worker",
      shortDescription: "Expired cert path.",
      maturityLevel: "production",
      trustTier: "certified",
      certificationStatus: "expired",
      costTier: "low",
      capabilities: [],
      tags: [],
      averageRating: 4.2,
      reviewCount: 3,
      currentRevision: "v1",
      createdById: "user-1",
    },
    {
      id: "legacy-1",
      fqn: "legacy-agent",
      namespace: "legacy",
      localName: "legacy-agent",
      displayName: "Legacy Agent",
      shortDescription: "Legacy catalog entry.",
      maturityLevel: "beta",
      trustTier: "basic",
      certificationStatus: "none",
      costTier: "free",
      capabilities: [],
      tags: [],
      averageRating: null,
      reviewCount: 0,
      currentRevision: "v1",
      createdById: "user-1",
    },
  ];

  await page.route("**/api/v1/marketplace/search**", async (route) => {
    await fulfillJson(route, {
      items,
      total: items.length,
      page: 1,
      pageSize: 20,
      hasNext: false,
      hasPrev: false,
    });
  });

  await page.route("**/api/v1/marketplace/filters/metadata", async (route) => {
    await fulfillJson(route, { capabilities: [], tags: [] });
  });

  await page.route("**/api/v1/marketplace/recommendations", async (route) => {
    await fulfillJson(route, { agents: items.slice(0, 2), reason: "personalized", totalAvailable: 2 });
  });
});

test("filters marketplace entries by FQN prefix and exposes legacy plus certification states", async ({ page }) => {
  await page.goto("/marketplace");

  const search = page.getByLabel("Search agents by FQN");
  await search.fill("ops:");

  await expect(page).toHaveURL(/q=ops%3A/);
  await expect(page.getByText("ops:case-triage")).toBeVisible();
  await expect(page.getByText("ops:expired-worker")).toBeVisible();
  await expect(page.getByText("Legacy (uncategorized)")).toBeVisible();
  await expect(page.getByText("Certification expired")).toBeVisible();

  const unavailableButton = page.getByRole("button", { name: "Unavailable" });
  await expect(unavailableButton).toBeDisabled();

  await page.getByLabel("Clear search").click();
  await expect(page).not.toHaveURL(/q=/);
  await expect(page.getByText("legacy-agent")).toBeVisible();
});
