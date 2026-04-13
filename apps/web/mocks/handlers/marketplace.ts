import { http, HttpResponse } from "msw";
import type {
  AgentDetail,
  AgentReview,
  CreatorAnalytics,
  RecommendationCarousel,
} from "@/lib/types/marketplace";
import type { PaginatedResponse } from "@/types/api";
import type { Workspace } from "@/types/workspace";

const CURRENT_USER_ID = "4d1b0f76-a961-4f8d-8bcb-3f7d5f530001";

const mockWorkspaces: Workspace[] = [
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
];

type AgentSeed = Pick<
  AgentDetail,
  | "namespace"
  | "localName"
  | "displayName"
  | "shortDescription"
  | "fullDescription"
  | "maturityLevel"
  | "trustTier"
  | "certificationStatus"
  | "costTier"
  | "capabilities"
  | "tags"
  | "createdById"
> & {
  visibleToCurrentUser?: boolean;
};

const templates: AgentSeed[] = [
  {
    namespace: "finance-ops",
    localName: "kyc-verifier",
    displayName: "KYC Verifier",
    shortDescription: "Automates identity checks and AML screening for onboarding flows.",
    fullDescription:
      "KYC Verifier combines identity extraction, sanctions screening, and suspicious pattern review for onboarding and risk operations teams.",
    maturityLevel: "production",
    trustTier: "certified",
    certificationStatus: "active",
    costTier: "low",
    capabilities: ["financial_analysis", "identity_verification", "compliance"],
    tags: ["finance", "compliance", "risk"],
    createdById: CURRENT_USER_ID,
  },
  {
    namespace: "marketing-intel",
    localName: "campaign-optimizer",
    displayName: "Campaign Optimizer",
    shortDescription: "Finds budget leaks and channel mix wins across current campaigns.",
    fullDescription:
      "Campaign Optimizer reviews attribution, spend pacing, and creative fatigue to suggest immediate reallocation opportunities.",
    maturityLevel: "production",
    trustTier: "standard",
    certificationStatus: "active",
    costTier: "medium",
    capabilities: ["forecasting", "analytics", "attribution"],
    tags: ["marketing", "growth", "optimization"],
    createdById: "creator-2",
  },
  {
    namespace: "trust",
    localName: "policy-auditor",
    displayName: "Policy Auditor",
    shortDescription: "Explains policy conflicts and likely enforcement outcomes before runtime.",
    fullDescription:
      "Policy Auditor simulates policy resolution paths so operators can inspect likely blocks, warnings, and exceptions before execution.",
    maturityLevel: "beta",
    trustTier: "certified",
    certificationStatus: "active",
    costTier: "free",
    capabilities: ["policy_reasoning", "risk_assessment", "governance"],
    tags: ["trust", "safety", "governance"],
    createdById: "creator-3",
  },
  {
    namespace: "support",
    localName: "escalation-triage",
    displayName: "Escalation Triage",
    shortDescription: "Classifies support escalations and suggests the next best responder.",
    fullDescription:
      "Escalation Triage summarizes conversation history, detects urgency, and recommends the best queue or specialist for resolution.",
    maturityLevel: "production",
    trustTier: "standard",
    certificationStatus: "pending",
    costTier: "low",
    capabilities: ["classification", "routing", "summarization"],
    tags: ["support", "tickets", "operations"],
    createdById: "creator-4",
  },
  {
    namespace: "security",
    localName: "red-team-simulator",
    displayName: "Red Team Simulator",
    shortDescription: "Stress-tests prompts and tool chains against adversarial input patterns.",
    fullDescription:
      "Red Team Simulator runs curated challenge sets against prompt configurations to expose safety regressions and brittle tool orchestration.",
    maturityLevel: "beta",
    trustTier: "basic",
    certificationStatus: "pending",
    costTier: "high",
    capabilities: ["adversarial_testing", "prompt_analysis", "security"],
    tags: ["security", "red-team", "testing"],
    createdById: "creator-5",
    visibleToCurrentUser: false,
  },
  {
    namespace: "analytics",
    localName: "forecast-studio",
    displayName: "Forecast Studio",
    shortDescription: "Produces short-horizon forecasts for revenue, churn, and staffing demand.",
    fullDescription:
      "Forecast Studio blends recent trend lines with calendar context to generate actionable forecasts and planning notes.",
    maturityLevel: "production",
    trustTier: "standard",
    certificationStatus: "active",
    costTier: "medium",
    capabilities: ["forecasting", "planning", "analytics"],
    tags: ["analytics", "forecasting", "planning"],
    createdById: "creator-6",
  },
];

function buildAgent(seed: AgentSeed, index: number): AgentDetail {
  const fqn = `${seed.namespace}:${seed.localName}`;
  const evaluationScore = Math.max(0.61, 0.94 - index * 0.01);
  const robustnessScore = Math.max(0.54, 0.89 - index * 0.012);
  const reviewCount = 5 + (index % 7);
  const averageRating = Number((4.8 - (index % 5) * 0.25).toFixed(1));

  return {
    id: `agent-${index + 1}`,
    fqn,
    namespace: seed.namespace,
    localName: seed.localName,
    displayName: seed.displayName,
    shortDescription: seed.shortDescription,
    fullDescription: seed.fullDescription,
    maturityLevel: seed.maturityLevel,
    trustTier: seed.trustTier,
    certificationStatus: seed.certificationStatus,
    costTier: seed.costTier,
    capabilities: seed.capabilities,
    tags: seed.tags,
    averageRating,
    reviewCount,
    currentRevision: `v${1 + Math.floor(index / 6)}.${index % 6}.0`,
    createdById: seed.createdById,
    revisions: [
      {
        version: `v${1 + Math.floor(index / 6)}.${index % 6}.0`,
        changeDescription: "Expanded the tool chain and refreshed evaluations.",
        publishedAt: "2026-04-10T10:00:00.000Z",
        isCurrent: true,
      },
      {
        version: `v${1 + Math.floor(index / 6)}.${Math.max(0, (index % 6) - 1)}.0`,
        changeDescription: "Stabilized prompts and policy defaults.",
        publishedAt: "2026-03-28T10:00:00.000Z",
        isCurrent: false,
      },
    ],
    trustSignals: {
      tier: seed.trustTier,
      tierHistory: [
        {
          tier: "unverified",
          achievedAt: "2025-10-01T10:00:00.000Z",
          revokedAt: null,
        },
        {
          tier: seed.trustTier,
          achievedAt: "2026-03-01T10:00:00.000Z",
          revokedAt: null,
        },
      ],
      certificationBadges:
        seed.certificationStatus === "active"
          ? [
              {
                id: `cert-${index + 1}`,
                name: "Operational Safety Review",
                issuedAt: "2026-02-20T10:00:00.000Z",
                expiresAt: "2027-02-20T10:00:00.000Z",
                isActive: true,
              },
            ]
          : [],
      latestEvaluation: {
        runId: `eval-${index + 1}`,
        evalSetName: "Marketplace Regression Set",
        aggregateScore: evaluationScore,
        passedCases: 42 + index,
        totalCases: 50,
        evaluatedAt: "2026-04-11T12:00:00.000Z",
      },
    },
    policies: [
      {
        id: `policy-budget-${index + 1}`,
        name: "Budget Guardrail",
        type: "budget_cap",
        enforcement: index % 3 === 0 ? "block" : "warn",
        description: "Caps invocation spend and blocks runs that exceed policy limits.",
      },
      {
        id: `policy-tool-${index + 1}`,
        name: "Tool Restriction",
        type: "tool_restriction",
        enforcement: "log",
        description: "Audits access to external tools and produces a trace for reviewers.",
      },
    ],
    qualityMetrics: {
      evaluationScore,
      robustnessScore,
      lastEvaluatedAt: "2026-04-11T12:00:00.000Z",
      passRate: evaluationScore,
    },
    costBreakdown: {
      tier: seed.costTier,
      estimatedCostPerInvocationUsd:
        seed.costTier === "free"
          ? 0
          : seed.costTier === "low"
            ? 0.03
            : seed.costTier === "medium"
              ? 0.18
              : 0.55,
      monthlyBudgetCapUsd:
        seed.costTier === "free"
          ? 0
          : seed.costTier === "low"
            ? 250
            : seed.costTier === "medium"
              ? 900
              : 2100,
    },
    visibility: {
      isPublicInWorkspace: true,
      visibleToCurrentUser: seed.visibleToCurrentUser ?? true,
    },
  };
}

function createAgents(): AgentDetail[] {
  const agents: AgentDetail[] = [];

  for (let index = 0; index < 24; index += 1) {
    const template = templates[index % templates.length] ?? templates[0]!;
    const cloneIndex = Math.floor(index / templates.length);
    const suffix = cloneIndex === 0 ? "" : `-${cloneIndex + 1}`;
    agents.push(
      buildAgent(
        {
          ...template,
          localName: `${template.localName}${suffix}`,
          displayName:
            cloneIndex === 0
              ? template.displayName
              : `${template.displayName} ${cloneIndex + 1}`,
        },
        index,
      ),
    );
  }

  return agents;
}

function createReviews(fqn: string, count: number): AgentReview[] {
  return Array.from({ length: count }, (_, index) => ({
    id: `${fqn}-review-${index + 1}`,
    agentFqn: fqn,
    authorId: index === 0 ? CURRENT_USER_ID : `reviewer-${index + 1}`,
    authorName: index === 0 ? "Alex Mercer" : `Reviewer ${index + 1}`,
    rating: index === 0 ? 4 : 5 - (index % 3),
    text:
      index === 0
        ? "Reliable on finance-heavy tasks and easy to operationalize."
        : `Synthetic review ${index + 1} for ${fqn}.`,
    createdAt: `2026-04-${String(11 - (index % 5)).padStart(2, "0")}T09:00:00.000Z`,
    updatedAt: null,
    isOwnReview: index === 0,
  }));
}

function createAnalytics(fqn: string): CreatorAnalytics {
  return {
    agentFqn: fqn,
    periodDays: 30,
    usageChart: Array.from({ length: 7 }, (_, index) => ({
      date: `2026-04-${String(index + 5).padStart(2, "0")}`,
      invocations: 12 + index * 4,
    })),
    satisfactionTrend: Array.from({ length: 6 }, (_, index) => ({
      weekStart: `2026-03-${String(index * 7 + 3).padStart(2, "0")}`,
      averageRating: Number((4.1 + index * 0.08).toFixed(1)),
    })),
    commonFailures: [
      {
        category: "timeout",
        count: 9,
        percentage: 36,
      },
      {
        category: "policy_violation",
        count: 7,
        percentage: 28,
      },
      {
        category: "llm_error",
        count: 4,
        percentage: 16,
      },
    ],
  };
}

function deriveFilterMetadata(agents: AgentDetail[]) {
  return {
    capabilities: Array.from(
      new Set(agents.flatMap((agent) => agent.capabilities)),
    ).sort(),
    tags: Array.from(new Set(agents.flatMap((agent) => agent.tags))).sort(),
  };
}

function createMarketplaceState() {
  const agents = createAgents();
  const reviewsByFqn = Object.fromEntries(
    agents.map((agent, index) => [
      agent.fqn,
      index < 8 ? createReviews(agent.fqn, 4 + (index % 3)) : [],
    ]),
  );
  const analyticsByFqn = Object.fromEntries(
    agents.map((agent) => [agent.fqn, createAnalytics(agent.fqn)]),
  );

  return {
    agents,
    reviewsByFqn,
    analyticsByFqn,
    filterMetadata: deriveFilterMetadata(agents),
    recommendations: {
      agents: agents.slice(0, 4),
      reason: "personalized" as const,
      totalAvailable: 4,
    },
    workspaces: mockWorkspaces,
  };
}

export interface MarketplaceMockState {
  agents: AgentDetail[];
  reviewsByFqn: Record<string, AgentReview[]>;
  analyticsByFqn: Record<string, CreatorAnalytics>;
  filterMetadata: {
    capabilities: string[];
    tags: string[];
  };
  recommendations: RecommendationCarousel;
  workspaces: Workspace[];
}

export const marketplaceFixtures: MarketplaceMockState = createMarketplaceState();

export function resetMarketplaceFixtures(): void {
  const fresh = createMarketplaceState();
  marketplaceFixtures.agents = fresh.agents;
  marketplaceFixtures.reviewsByFqn = fresh.reviewsByFqn;
  marketplaceFixtures.analyticsByFqn = fresh.analyticsByFqn;
  marketplaceFixtures.filterMetadata = fresh.filterMetadata;
  marketplaceFixtures.recommendations = fresh.recommendations;
  marketplaceFixtures.workspaces = fresh.workspaces;
}

function matchesSearchQuery(agent: AgentDetail, query: string): boolean {
  if (!query) {
    return true;
  }

  const haystack = [
    agent.displayName,
    agent.shortDescription,
    agent.fullDescription,
    agent.namespace,
    agent.localName,
    ...agent.capabilities,
    ...agent.tags,
  ]
    .join(" ")
    .toLowerCase();

  return haystack.includes(query.toLowerCase());
}

function parseCsv(request: Request, key: string): string[] {
  const values = new URL(request.url).searchParams.get(key);
  return values ? values.split(",").filter(Boolean) : [];
}

function sortAgents(agents: AgentDetail[], sortBy: string): AgentDetail[] {
  const nextAgents = [...agents];

  switch (sortBy) {
    case "rating":
      nextAgents.sort(
        (left, right) => (right.averageRating ?? 0) - (left.averageRating ?? 0),
      );
      break;
    case "maturity": {
      const order = {
        production: 3,
        beta: 2,
        draft: 1,
        deprecated: 0,
      } as const;
      nextAgents.sort(
        (left, right) => order[right.maturityLevel] - order[left.maturityLevel],
      );
      break;
    }
    case "cost": {
      const order = {
        free: 0,
        low: 1,
        medium: 2,
        high: 3,
      } as const;
      nextAgents.sort((left, right) => order[left.costTier] - order[right.costTier]);
      break;
    }
    default:
      nextAgents.sort(
        (left, right) => (right.trustSignals.latestEvaluation?.aggregateScore ?? 0) - (left.trustSignals.latestEvaluation?.aggregateScore ?? 0),
      );
  }

  return nextAgents;
}

function refreshAgentRating(fqn: string): void {
  const reviews = marketplaceFixtures.reviewsByFqn[fqn] ?? [];
  const nextAverage =
    reviews.length > 0
      ? Number(
          (
            reviews.reduce((sum, review) => sum + review.rating, 0) / reviews.length
          ).toFixed(1),
        )
      : null;

  marketplaceFixtures.agents = marketplaceFixtures.agents.map((agent) =>
    agent.fqn === fqn
      ? {
          ...agent,
          averageRating: nextAverage,
          reviewCount: reviews.length,
        }
      : agent,
  );
}

export const marketplaceHandlers = [
  http.get("*/api/v1/marketplace/search", ({ request }) => {
    const url = new URL(request.url);
    const query = url.searchParams.get("q") ?? "";
    const maturityLevels = parseCsv(request, "maturityLevels");
    const trustTiers = parseCsv(request, "trustTiers");
    const certificationStatuses = parseCsv(request, "certificationStatuses");
    const costTiers = parseCsv(request, "costTiers");
    const capabilities = parseCsv(request, "capabilities");
    const tags = parseCsv(request, "tags");
    const sortBy = url.searchParams.get("sortBy") ?? "relevance";
    const page = Number(url.searchParams.get("page") ?? "1");
    const pageSize = Number(url.searchParams.get("pageSize") ?? "20");

    const filtered = marketplaceFixtures.agents.filter((agent) => {
      if (!matchesSearchQuery(agent, query)) {
        return false;
      }

      if (maturityLevels.length > 0 && !maturityLevels.includes(agent.maturityLevel)) {
        return false;
      }

      if (trustTiers.length > 0 && !trustTiers.includes(agent.trustTier)) {
        return false;
      }

      if (
        certificationStatuses.length > 0 &&
        !certificationStatuses.includes(agent.certificationStatus)
      ) {
        return false;
      }

      if (costTiers.length > 0 && !costTiers.includes(agent.costTier)) {
        return false;
      }

      if (
        capabilities.length > 0 &&
        !capabilities.every((capability) => agent.capabilities.includes(capability))
      ) {
        return false;
      }

      if (tags.length > 0 && !tags.every((tag) => agent.tags.includes(tag))) {
        return false;
      }

      return true;
    });

    const sorted = sortAgents(filtered, sortBy);
    const start = (page - 1) * pageSize;
    const items = sorted.slice(start, start + pageSize);
    const payload: PaginatedResponse<AgentDetail> = {
      items,
      total: sorted.length,
      page,
      pageSize,
      hasNext: start + pageSize < sorted.length,
      hasPrev: page > 1,
    };

    return HttpResponse.json(payload);
  }),
  http.get("*/api/v1/marketplace/agents/:namespace/:name", ({ params }) => {
    const namespace = String(params.namespace);
    const name = String(params.name);
    const agent = marketplaceFixtures.agents.find(
      (entry) => entry.namespace === namespace && entry.localName === name,
    );

    if (!agent) {
      return HttpResponse.json(
        {
          error: {
            code: "NOT_FOUND",
            message: "Agent not found",
          },
        },
        { status: 404 },
      );
    }

    return HttpResponse.json(agent);
  }),
  http.get("*/api/v1/marketplace/agents/:namespace/:name/reviews", ({ params, request }) => {
    const namespace = String(params.namespace);
    const name = String(params.name);
    const fqn = `${namespace}:${name}`;
    const url = new URL(request.url);
    const page = Number(url.searchParams.get("page") ?? "1");
    const pageSize = Number(url.searchParams.get("pageSize") ?? "10");
    const reviews = marketplaceFixtures.reviewsByFqn[fqn] ?? [];
    const start = (page - 1) * pageSize;
    const items = reviews.slice(start, start + pageSize);

    return HttpResponse.json({
      items,
      total: reviews.length,
      page,
      pageSize,
      hasNext: start + pageSize < reviews.length,
      hasPrev: page > 1,
    });
  }),
  http.post("*/api/v1/marketplace/agents/:namespace/:name/reviews", async ({ params, request }) => {
    const namespace = String(params.namespace);
    const name = String(params.name);
    const fqn = `${namespace}:${name}`;
    const body = (await request.json()) as { rating: number; text?: string };
    const current = marketplaceFixtures.reviewsByFqn[fqn] ?? [];
    const filtered = current.filter((review) => !review.isOwnReview);
    const review: AgentReview = {
      id: `${fqn}-review-own`,
      agentFqn: fqn,
      authorId: CURRENT_USER_ID,
      authorName: "Alex Mercer",
      rating: body.rating,
      text: body.text ?? null,
      createdAt: "2026-04-12T10:00:00.000Z",
      updatedAt: null,
      isOwnReview: true,
    };

    marketplaceFixtures.reviewsByFqn[fqn] = [review, ...filtered];
    refreshAgentRating(fqn);

    return HttpResponse.json(review, { status: 201 });
  }),
  http.patch(
    "*/api/v1/marketplace/agents/:namespace/:name/reviews/:reviewId",
    async ({ params, request }) => {
      const namespace = String(params.namespace);
      const name = String(params.name);
      const reviewId = String(params.reviewId);
      const fqn = `${namespace}:${name}`;
      const body = (await request.json()) as { rating: number; text?: string };
      const reviews = marketplaceFixtures.reviewsByFqn[fqn] ?? [];
      let updatedReview: AgentReview | null = null;

      marketplaceFixtures.reviewsByFqn[fqn] = reviews.map((review) => {
        if (review.id !== reviewId) {
          return review;
        }

        updatedReview = {
          ...review,
          rating: body.rating,
          text: body.text ?? null,
          updatedAt: "2026-04-12T10:30:00.000Z",
        };

        return updatedReview;
      });

      refreshAgentRating(fqn);

      if (!updatedReview) {
        return HttpResponse.json(
          {
            error: {
              code: "NOT_FOUND",
              message: "Review not found",
            },
          },
          { status: 404 },
        );
      }

      return HttpResponse.json(updatedReview);
    },
  ),
  http.get("*/api/v1/marketplace/recommendations", () =>
    HttpResponse.json(marketplaceFixtures.recommendations),
  ),
  http.get("*/api/v1/marketplace/agents/:namespace/:name/analytics", ({ params }) => {
    const namespace = String(params.namespace);
    const name = String(params.name);
    const fqn = `${namespace}:${name}`;
    const analytics = marketplaceFixtures.analyticsByFqn[fqn];

    if (!analytics) {
      return HttpResponse.json(
        {
          error: {
            code: "FORBIDDEN",
            message: "Analytics unavailable",
          },
        },
        { status: 403 },
      );
    }

    return HttpResponse.json(analytics);
  }),
  http.get("*/api/v1/marketplace/filters/metadata", () =>
    HttpResponse.json(marketplaceFixtures.filterMetadata),
  ),
  http.get("*/api/v1/workspaces", () =>
    HttpResponse.json({ items: marketplaceFixtures.workspaces }),
  ),
];
