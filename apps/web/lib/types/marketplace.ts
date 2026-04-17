export const MATURITY_LEVELS = [
  "draft",
  "beta",
  "production",
  "deprecated",
] as const;

export const TRUST_TIERS = [
  "unverified",
  "basic",
  "standard",
  "certified",
] as const;

export const COST_TIERS = ["free", "low", "medium", "high"] as const;

export const SORT_OPTIONS = [
  "relevance",
  "maturity",
  "rating",
  "cost",
] as const;

export const CERTIFICATION_STATUSES = [
  "none",
  "pending",
  "active",
  "expired",
] as const;

export const POLICY_ENFORCEMENTS = ["block", "warn", "log"] as const;

export const REVIEW_DECISIONS = ["confirm", "override"] as const;

export const RECOMMENDATION_REASONS = [
  "personalized",
  "popular",
  "trending",
] as const;

export type MaturityLevel = (typeof MATURITY_LEVELS)[number];
export type TrustTier = (typeof TRUST_TIERS)[number];
export type CostTier = (typeof COST_TIERS)[number];
export type SortBy = (typeof SORT_OPTIONS)[number];
export type CertificationStatus = (typeof CERTIFICATION_STATUSES)[number];
export type PolicyEnforcement = (typeof POLICY_ENFORCEMENTS)[number];
export type ReviewDecision = (typeof REVIEW_DECISIONS)[number];
export type RecommendationReason = (typeof RECOMMENDATION_REASONS)[number];

export interface AgentCard {
  id: string;
  fqn: string;
  namespace: string;
  localName: string;
  displayName: string;
  shortDescription: string;
  maturityLevel: MaturityLevel;
  trustTier: TrustTier;
  certificationStatus: CertificationStatus;
  costTier: CostTier;
  capabilities: string[];
  tags: string[];
  averageRating: number | null;
  reviewCount: number;
  currentRevision: string;
  createdById: string;
}

export interface AgentDetail extends AgentCard {
  fullDescription: string;
  revisions: AgentRevision[];
  trustSignals: TrustSignals;
  policies: PolicySummary[];
  qualityMetrics: QualityMetrics;
  costBreakdown: CostBreakdown;
  visibility: VisibilityConfig;
}

export interface AgentRevision {
  version: string;
  changeDescription: string;
  publishedAt: string;
  isCurrent: boolean;
}

export interface TrustSignals {
  tier: TrustTier;
  tierHistory: TierHistoryEntry[];
  certificationBadges: CertificationBadge[];
  latestEvaluation: EvaluationSummary | null;
}

export interface TierHistoryEntry {
  tier: TrustTier;
  achievedAt: string;
  revokedAt: string | null;
}

export interface CertificationBadge {
  id: string;
  name: string;
  issuedAt: string;
  expiresAt: string | null;
  isActive: boolean;
}

export interface EvaluationSummary {
  runId: string;
  evalSetName: string;
  aggregateScore: number;
  passedCases: number;
  totalCases: number;
  evaluatedAt: string;
}

export interface PolicySummary {
  id: string;
  name: string;
  type: string;
  enforcement: PolicyEnforcement;
  description: string;
}

export interface QualityMetrics {
  evaluationScore: number | null;
  robustnessScore: number | null;
  lastEvaluatedAt: string | null;
  passRate: number | null;
}

export interface CostBreakdown {
  tier: CostTier;
  estimatedCostPerInvocationUsd: number | null;
  monthlyBudgetCapUsd: number | null;
}

export interface VisibilityConfig {
  isPublicInWorkspace: boolean;
  visibleToCurrentUser: boolean;
}

export interface AgentReview {
  id: string;
  agentFqn: string;
  authorId: string;
  authorName: string;
  rating: number;
  text: string | null;
  createdAt: string;
  updatedAt: string | null;
  isOwnReview: boolean;
}

export interface ReviewSubmission {
  rating: number;
  text?: string | undefined;
}

export interface MarketplaceSearchParams {
  q: string;
  capabilities: string[];
  maturityLevels: MaturityLevel[];
  trustTiers: TrustTier[];
  certificationStatuses: CertificationStatus[];
  costTiers: CostTier[];
  tags: string[];
  sortBy: SortBy;
  page: number;
  pageSize: number;
}

export interface FilterMetadata {
  capabilities: string[];
  tags: string[];
}

export interface RecommendationCarousel {
  agents: AgentCard[];
  reason: RecommendationReason;
  totalAvailable: number;
}

export interface ComparisonRow {
  attribute: string;
  values: Array<string | null>;
}

export interface CreatorAnalytics {
  agentFqn: string;
  periodDays: number;
  usageChart: DailyUsage[];
  satisfactionTrend: WeeklyRating[];
  commonFailures: FailureCategory[];
}

export interface DailyUsage {
  date: string;
  invocations: number;
}

export interface WeeklyRating {
  weekStart: string;
  averageRating: number | null;
}

export interface FailureCategory {
  category: string;
  count: number;
  percentage: number;
}

export interface InvocationRequest {
  agentFqn: string;
  workspaceId: string;
  taskBrief?: string | undefined;
}

export interface AgentIdentifier {
  namespace: string;
  localName: string;
}

export const DEFAULT_MARKETPLACE_SEARCH_PARAMS: MarketplaceSearchParams = {
  q: "",
  capabilities: [],
  maturityLevels: [],
  trustTiers: [],
  certificationStatuses: [],
  costTiers: [],
  tags: [],
  sortBy: "relevance",
  page: 1,
  pageSize: 20,
};

export function splitAgentFqn(fqn: string): AgentIdentifier {
  const separator = fqn.includes(":") ? ":" : "/";
  const [namespace, ...rest] = fqn.split(separator);

  return {
    namespace: namespace ?? "",
    localName: rest.join(separator),
  };
}

export function buildAgentFqn(namespace: string, localName: string): string {
  return `${namespace}:${localName}`;
}

export function buildAgentHref(namespace: string, localName: string): string {
  return `/marketplace/${encodeURIComponent(namespace)}/${encodeURIComponent(localName)}`;
}

export function encodeComparisonHandle(fqn: string): string {
  const { namespace, localName } = splitAgentFqn(fqn);
  return `${namespace}/${localName}`;
}

export function decodeComparisonHandle(value: string): AgentIdentifier {
  const [namespace, ...rest] = value.split("/");
  return {
    namespace: namespace ?? "",
    localName: rest.join("/"),
  };
}

export function humanizeMarketplaceValue(value: string): string {
  return value
    .split(/[-_]/g)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function getActiveMarketplaceFilterCount(
  params: Partial<MarketplaceSearchParams>,
): number {
  return (
    (params.capabilities?.length ?? 0) +
    (params.maturityLevels?.length ?? 0) +
    (params.trustTiers?.length ?? 0) +
    (params.certificationStatuses?.length ?? 0) +
    (params.costTiers?.length ?? 0) +
    (params.tags?.length ?? 0)
  );
}

export function getRecommendationLabel(reason: RecommendationReason): string {
  switch (reason) {
    case "personalized":
      return "Recommended for you";
    case "popular":
      return "Popular agents";
    case "trending":
      return "Trending this week";
  }
}

export function formatUsdCost(value: number | null): string {
  if (value === null) {
    return "Usage-based";
  }

  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}
