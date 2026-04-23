import { expect, test, type Page } from "@playwright/test";
import { mockAuthApi, signIn } from "@/e2e/auth/helpers";

async function mockMarketplaceApi(page: Page) {
  const agentDetail = {
    id: "agent-1",
    fqn: "finance-ops:kyc-verifier",
    namespace: "finance-ops",
    localName: "kyc-verifier",
    displayName: "KYC Verifier",
    shortDescription: "Automates identity checks and AML screening.",
    fullDescription: "Full agent detail content.",
    maturityLevel: "production",
    trustTier: "certified",
    certificationStatus: "active",
    costTier: "low",
    capabilities: ["financial_analysis", "identity_verification"],
    tags: ["finance", "risk"],
    averageRating: 4.7,
    reviewCount: 12,
    currentRevision: "v1.4.0",
    createdById: "4d1b0f76-a961-4f8d-8bcb-3f7d5f530001",
    revisions: [
      {
        version: "v1.4.0",
        changeDescription: "Expanded the tool chain.",
        publishedAt: "2026-04-10T10:00:00.000Z",
        isCurrent: true,
      },
    ],
    trustSignals: {
      tier: "certified",
      tierHistory: [
        {
          tier: "unverified",
          achievedAt: "2025-10-01T10:00:00.000Z",
          revokedAt: null,
        },
        {
          tier: "certified",
          achievedAt: "2026-03-01T10:00:00.000Z",
          revokedAt: null,
        },
      ],
      certificationBadges: [
        {
          id: "cert-1",
          name: "Operational Safety Review",
          issuedAt: "2026-02-20T10:00:00.000Z",
          expiresAt: "2027-02-20T10:00:00.000Z",
          isActive: true,
        },
      ],
      latestEvaluation: {
        runId: "eval-1",
        evalSetName: "Marketplace Regression Set",
        aggregateScore: 0.92,
        passedCases: 46,
        totalCases: 50,
        evaluatedAt: "2026-04-11T12:00:00.000Z",
      },
    },
    policies: [
      {
        id: "policy-1",
        name: "Budget Guardrail",
        type: "budget_cap",
        enforcement: "block",
        description: "Caps invocation spend.",
      },
    ],
    qualityMetrics: {
      evaluationScore: 0.92,
      robustnessScore: 0.87,
      lastEvaluatedAt: "2026-04-11T12:00:00.000Z",
      passRate: 0.92,
    },
    costBreakdown: {
      tier: "low",
      estimatedCostPerInvocationUsd: 0.03,
      monthlyBudgetCapUsd: 250,
    },
    visibility: {
      isPublicInWorkspace: true,
      visibleToCurrentUser: true,
    },
  };
  const policyAuditor = {
    ...agentDetail,
    id: "agent-2",
    fqn: "trust:policy-auditor",
    namespace: "trust",
    localName: "policy-auditor",
    displayName: "Policy Auditor",
  };
  const campaignOptimizer = {
    ...agentDetail,
    id: "agent-3",
    fqn: "marketing-intel:campaign-optimizer",
    namespace: "marketing-intel",
    localName: "campaign-optimizer",
    displayName: "Campaign Optimizer",
  };
  const details = [agentDetail, policyAuditor, campaignOptimizer];
  let reviews = [] as Array<{
    id: string;
    agentFqn: string;
    authorId: string;
    authorName: string;
    rating: number;
    text: string;
    createdAt: string;
    updatedAt: string | null;
    isOwnReview: boolean;
  }>;

  await page.route("**/api/v1/marketplace/search**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: details,
        total: 3,
        page: 1,
        pageSize: 20,
        hasNext: false,
        hasPrev: false,
      }),
      status: 200,
    });
  });

  await page.route("**/api/v1/marketplace/filters/metadata", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        capabilities: ["financial_analysis", "identity_verification"],
        tags: ["finance", "risk"],
      }),
      status: 200,
    });
  });

  await page.route("**/api/v1/marketplace/recommendations", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        agents: details,
        reason: "personalized",
        totalAvailable: 3,
      }),
      status: 200,
    });
  });

  await page.route("**/api/v1/marketplace/agents/*/*", async (route) => {
    const match = route.request().url().match(/agents\/([^/]+)\/([^/?]+)/);
    const namespace = match?.[1] ?? "";
    const localName = match?.[2] ?? "";
    const detail = details.find(
      (entry) => entry.namespace === namespace && entry.localName === localName,
    );

    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(detail ?? agentDetail),
      status: 200,
    });
  });

  await page.route("**/api/v1/marketplace/agents/**/reviews**", async (route) => {
    const request = route.request();
    if (request.method() === "POST") {
      reviews = [
        {
          id: "review-1",
          agentFqn: "finance-ops:kyc-verifier",
          authorId: "4d1b0f76-a961-4f8d-8bcb-3f7d5f530001",
          authorName: "Alex Mercer",
          rating: 4,
          text: "Works well for KYC tasks",
          createdAt: "2026-04-12T10:00:00.000Z",
          updatedAt: null,
          isOwnReview: true,
        },
      ];
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(reviews[0]),
        status: 201,
      });
      return;
    }

    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: reviews,
        total: reviews.length,
        page: 1,
        pageSize: 10,
        hasNext: false,
        hasPrev: false,
      }),
      status: 200,
    });
  });

  await page.route("**/api/v1/marketplace/agents/**/analytics**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        agentFqn: "finance-ops:kyc-verifier",
        periodDays: 30,
        usageChart: [{ date: "2026-04-10", invocations: 12 }],
        satisfactionTrend: [{ weekStart: "2026-03-03", averageRating: 4.5 }],
        commonFailures: [{ category: "timeout", count: 2, percentage: 50 }],
      }),
      status: 200,
    });
  });

  await page.route("**/api/v1/workspaces", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          {
            id: "workspace-1",
            name: "Signal Lab",
            slug: "signal-lab",
            description: "Primary operations workspace",
            memberCount: 18,
            createdAt: "2026-04-10T09:00:00.000Z",
          },
          {
            id: "workspace-2",
            name: "Trust Foundry",
            slug: "trust-foundry",
            description: "Safety and governance programs",
            memberCount: 11,
            createdAt: "2026-04-08T13:30:00.000Z",
          },
        ],
      }),
      status: 200,
    });
  });
}

test.beforeEach(async ({ page }) => {
  await mockAuthApi(page);
  await mockMarketplaceApi(page);
});

test("search returns marketplace results", async ({ page }) => {
  await page.goto("/login");
  await signIn(page);
  await page.goto("/marketplace");

  await page.getByLabel("Search agents").fill("financial analysis agent");
  await expect(page.getByRole("heading", { name: "KYC Verifier", exact: true }).first()).toBeVisible();
});

test("agent detail renders full view", async ({ page }) => {
  await page.goto("/login");
  await signIn(page);
  await page.goto("/marketplace/finance-ops/kyc-verifier");

  await expect(page.getByRole("heading", { name: "KYC Verifier", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Policies", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Reviews" })).toBeVisible();
});

test("comparison flow works from selected cards", async ({ page }) => {
  await page.goto("/login");
  await signIn(page);
  await page.goto("/marketplace");

  await page.getByRole("button", { name: "Compare" }).first().click();
  await page.getByRole("button", { name: "Compare" }).nth(1).click();
  await page.getByRole("button", { name: /compare now/i }).click();

  await expect(page).toHaveURL(/\/marketplace\/compare/);
  await expect(page.getByText("Comparison view")).toBeVisible();
});

test("review submission works", async ({ page }) => {
  await page.goto("/login");
  await signIn(page);
  await page.goto("/marketplace/finance-ops/kyc-verifier");

  await page.getByRole("button", { name: "Reviews", exact: true }).click();
  await page
    .getByRole("radiogroup", { name: "Rating" })
    .getByRole("button", { name: "Rate 4 out of 5 stars", exact: true })
    .click({ force: true });
  await page.getByLabel("Review").fill("Works well for KYC tasks");
  await page.getByRole("button", { name: /submit review/i }).click();

  await expect(page.getByText("Works well for KYC tasks")).toBeVisible();
});

test("invoke flow redirects with workspace selection", async ({ page }) => {
  await page.goto("/login");
  await signIn(page);
  await page.goto("/marketplace/finance-ops/kyc-verifier");

  await expect(
    page.getByRole("button", { name: "Start Conversation", exact: true }),
  ).toBeVisible();

  await page.goto(
    "/conversations/new?agent=finance-ops%3Akyc-verifier&workspace=workspace-1",
  );

  await expect(page).toHaveURL(/\/conversations\/new\?/);
  await expect(page.getByText("Agent: finance-ops:kyc-verifier")).toBeVisible();
  await expect(page.getByText("Workspace: workspace-1")).toBeVisible();
});
