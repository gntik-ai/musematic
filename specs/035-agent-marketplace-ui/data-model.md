# Data Model: Agent Marketplace UI

**Branch**: `035-agent-marketplace`  
**Layer**: Frontend TypeScript types and state

---

## TypeScript Types

```typescript
// apps/web/lib/types/marketplace.ts

// ── Enumerations ───────────────────────────────────────────────────────────

export type MaturityLevel = 'draft' | 'beta' | 'production' | 'deprecated'

export type TrustTier = 'unverified' | 'basic' | 'standard' | 'certified'

export type CostTier = 'free' | 'low' | 'medium' | 'high'

export type SortBy = 'relevance' | 'maturity' | 'rating' | 'cost'

export type CertificationStatus = 'none' | 'pending' | 'active' | 'expired'

export type PolicyEnforcement = 'block' | 'warn' | 'log'

export type ReviewDecision = 'confirm' | 'override'

export type RecommendationReason = 'personalized' | 'popular' | 'trending'

// ── Agent Card (grid view) ────────────────────────────────────────────────

export interface AgentCard {
  id: string                    // UUID
  fqn: string                   // namespace:local_name
  namespace: string
  localName: string
  displayName: string
  shortDescription: string
  maturityLevel: MaturityLevel
  trustTier: TrustTier
  certificationStatus: CertificationStatus
  costTier: CostTier
  capabilities: string[]
  tags: string[]
  averageRating: number | null   // 0.0 – 5.0, null if no reviews
  reviewCount: number
  currentRevision: string       // semver string
  createdById: string           // user UUID of creator
}

// ── Agent Detail (full page view) ────────────────────────────────────────

export interface AgentDetail extends AgentCard {
  fullDescription: string
  revisions: AgentRevision[]
  trustSignals: TrustSignals
  policies: PolicySummary[]
  qualityMetrics: QualityMetrics
  costBreakdown: CostBreakdown
  visibility: VisibilityConfig
}

export interface AgentRevision {
  version: string
  changeDescription: string
  publishedAt: string           // ISO-8601
  isCurrent: boolean
}

export interface TrustSignals {
  tier: TrustTier
  tierHistory: TierHistoryEntry[]
  certificationBadges: CertificationBadge[]
  latestEvaluation: EvaluationSummary | null
}

export interface TierHistoryEntry {
  tier: TrustTier
  achievedAt: string            // ISO-8601
  revokedAt: string | null
}

export interface CertificationBadge {
  id: string
  name: string
  issuedAt: string              // ISO-8601
  expiresAt: string | null
  isActive: boolean
}

export interface EvaluationSummary {
  runId: string
  evalSetName: string
  aggregateScore: number        // 0.0 – 1.0
  passedCases: number
  totalCases: number
  evaluatedAt: string           // ISO-8601
}

export interface PolicySummary {
  id: string
  name: string
  type: string                  // e.g., "tool_restriction", "budget_cap"
  enforcement: PolicyEnforcement
  description: string
}

export interface QualityMetrics {
  evaluationScore: number | null       // latest aggregate score, 0.0-1.0
  robustnessScore: number | null       // from robustness test run
  lastEvaluatedAt: string | null       // ISO-8601
  passRate: number | null              // % of cases passed in latest eval
}

export interface CostBreakdown {
  tier: CostTier
  estimatedCostPerInvocationUsd: number | null
  monthlyBudgetCapUsd: number | null
}

export interface VisibilityConfig {
  isPublicInWorkspace: boolean
  visibleToCurrentUser: boolean       // backend-evaluated for this requester
}

// ── Reviews ───────────────────────────────────────────────────────────────

export interface AgentReview {
  id: string
  agentFqn: string
  authorId: string
  authorName: string
  rating: number                // 1-5 integer
  text: string | null
  createdAt: string             // ISO-8601
  updatedAt: string | null
  isOwnReview: boolean          // true if current user authored this review
}

export interface ReviewSubmission {
  rating: number                // 1-5
  text?: string
}

// ── Search & Filters ──────────────────────────────────────────────────────

export interface MarketplaceSearchParams {
  q: string
  capabilities: string[]
  maturityLevels: MaturityLevel[]
  trustTiers: TrustTier[]
  certificationStatuses: CertificationStatus[]
  costTiers: CostTier[]
  tags: string[]
  sortBy: SortBy
  page: number
  pageSize: number
}

export interface FilterMetadata {
  capabilities: string[]        // all available capability strings
  tags: string[]                // all available tags
  // maturityLevels, trustTiers, costTiers are enum-derived (static)
}

// ── Recommendations ───────────────────────────────────────────────────────

export interface RecommendationCarousel {
  agents: AgentCard[]
  reason: RecommendationReason
  totalAvailable: number
}

// ── Comparison ────────────────────────────────────────────────────────────

export interface ComparisonRow {
  attribute: string             // e.g., "Maturity Level", "Trust Tier"
  values: (string | null)[]     // one per agent; null = N/A
}

// ── Creator Analytics ─────────────────────────────────────────────────────

export interface CreatorAnalytics {
  agentFqn: string
  periodDays: number            // default 30
  usageChart: DailyUsage[]
  satisfactionTrend: WeeklyRating[]
  commonFailures: FailureCategory[]
}

export interface DailyUsage {
  date: string                  // YYYY-MM-DD
  invocations: number
}

export interface WeeklyRating {
  weekStart: string             // YYYY-MM-DD (Monday)
  averageRating: number | null  // null if no reviews that week
}

export interface FailureCategory {
  category: string              // e.g., "timeout", "policy_violation", "llm_error"
  count: number
  percentage: number            // 0-100
}

// ── Invocation ────────────────────────────────────────────────────────────

export interface InvocationRequest {
  agentFqn: string
  workspaceId: string
  taskBrief?: string
}
```

---

## Zustand Store

```typescript
// apps/web/lib/stores/use-comparison-store.ts

interface ComparisonState {
  selectedFqns: string[]        // max 4 entries
  add: (fqn: string) => void
  remove: (fqn: string) => void
  clear: () => void
  isSelected: (fqn: string) => boolean
  canAdd: () => boolean         // false when selectedFqns.length >= 4
}

// Implementation note: No persistence — Zustand without persist middleware.
// Selections are cleared on page refresh (session-scoped per spec).
```

---

## TanStack Query Hooks

```typescript
// apps/web/lib/hooks/use-marketplace-search.ts
export function useMarketplaceSearch(params: MarketplaceSearchParams)
  : UseInfiniteQueryResult<InfiniteData<PaginatedResponse<AgentCard>>>
// key: ['marketplace', 'search', params]
// fetchNextPage increments page param

// apps/web/lib/hooks/use-agent-detail.ts
export function useAgentDetail(namespace: string, name: string)
  : UseQueryResult<AgentDetail>
// key: ['marketplace', 'agent', namespace, name]

// apps/web/lib/hooks/use-agent-reviews.ts
export function useAgentReviews(fqn: string, page: number)
  : UseQueryResult<PaginatedResponse<AgentReview>>
// key: ['marketplace', 'reviews', fqn, page]

export function useSubmitReview(fqn: string)
  : UseMutationResult<AgentReview, Error, ReviewSubmission>
// POST /api/v1/marketplace/agents/{namespace}/{name}/reviews
// On success: invalidate ['marketplace', 'reviews', fqn]

export function useEditReview(fqn: string, reviewId: string)
  : UseMutationResult<AgentReview, Error, ReviewSubmission>
// PATCH /api/v1/marketplace/agents/{namespace}/{name}/reviews/{reviewId}

// apps/web/lib/hooks/use-recommendations.ts
export function useRecommendations()
  : UseQueryResult<RecommendationCarousel>
// key: ['marketplace', 'recommendations']

// apps/web/lib/hooks/use-creator-analytics.ts
export function useCreatorAnalytics(fqn: string, periodDays?: number)
  : UseQueryResult<CreatorAnalytics>
// key: ['marketplace', 'analytics', fqn, periodDays]
// Only called when user is owner/admin — no security concern from calling
// with wrong credentials (backend returns 403, query enters error state)
```

---

## API Endpoints Consumed

| Method | Path | Used By | Response |
|--------|------|---------|----------|
| GET | `/api/v1/marketplace/search` | `useMarketplaceSearch` | `PaginatedResponse<AgentCard>` |
| GET | `/api/v1/marketplace/agents/:ns/:name` | `useAgentDetail` | `AgentDetail` |
| GET | `/api/v1/marketplace/agents/:ns/:name/reviews` | `useAgentReviews` | `PaginatedResponse<AgentReview>` |
| POST | `/api/v1/marketplace/agents/:ns/:name/reviews` | `useSubmitReview` | `AgentReview` |
| PATCH | `/api/v1/marketplace/agents/:ns/:name/reviews/:id` | `useEditReview` | `AgentReview` |
| GET | `/api/v1/marketplace/recommendations` | `useRecommendations` | `RecommendationCarousel` |
| GET | `/api/v1/marketplace/agents/:ns/:name/analytics` | `useCreatorAnalytics` | `CreatorAnalytics` |
| GET | `/api/v1/marketplace/filters/metadata` | `FilterSidebar` | `FilterMetadata` |
| GET | `/api/v1/workspaces` | `InvokeAgentDialog` | `PaginatedResponse<Workspace>` (existing) |

---

## Zod Validation Schemas

```typescript
// apps/web/lib/schemas/marketplace.ts

export const ReviewSubmissionSchema = z.object({
  rating: z.number().int().min(1).max(5),
  text: z.string().max(2000).optional(),
})

export const InvocationSchema = z.object({
  workspaceId: z.string().uuid('Please select a workspace'),
  taskBrief: z.string().max(500).optional(),
})

export const SearchParamsSchema = z.object({
  q: z.string().default(''),
  capabilities: z.array(z.string()).default([]),
  maturityLevels: z.array(z.enum(['draft','beta','production','deprecated'])).default([]),
  trustTiers: z.array(z.enum(['unverified','basic','standard','certified'])).default([]),
  certificationStatuses: z.array(z.string()).default([]),
  costTiers: z.array(z.enum(['free','low','medium','high'])).default([]),
  tags: z.array(z.string()).default([]),
  sortBy: z.enum(['relevance','maturity','rating','cost']).default('relevance'),
})
```
