# UI Component Contracts: Agent Marketplace UI

**Branch**: `035-agent-marketplace`

These contracts define the public props interface for each component and the page-level routing contracts.

---

## Page Routes

### `/marketplace` — Marketplace Landing Page
**File**: `apps/web/app/(main)/marketplace/page.tsx`

```
URL params (all optional):
  q              string              Search query text
  capabilities   string (CSV)        Filter by capability
  maturityLevels string (CSV)        Filter by maturity level
  trustTiers     string (CSV)        Filter by trust tier  
  certStatuses   string (CSV)        Filter by cert status
  costTiers      string (CSV)        Filter by cost tier
  tags           string (CSV)        Filter by tag
  sortBy         string              relevance | maturity | rating | cost

Renders:
  - RecommendationCarousel (top, only when ≥3 results)
  - MarketplaceSearchBar (bound to ?q)
  - FilterSidebar (bound to filter params)
  - AgentCardGrid (bound to search params)
  - ComparisonFloatingBar (fixed-position, visible when ≥2 agents selected)
```

### `/marketplace/[namespace]/[name]` — Agent Detail Page
**File**: `apps/web/app/(main)/marketplace/[namespace]/[name]/page.tsx`

```
Path params:
  namespace      string              Agent namespace (from FQN)
  name           string              Agent local name (from FQN)

Renders:
  - AgentDetail (full metadata, trust signals, policies, metrics)
  - AgentRevisions (revision history section)
  - ReviewsSection (reviews list + submit form)
  - InvokeAgentDialog (triggered by "Start Conversation" button)
  - Tabs: Overview | Policies | Quality Metrics | Reviews | Analytics (owner only)
```

### `/marketplace/compare` — Comparison Page
**File**: `apps/web/app/(main)/marketplace/compare/page.tsx`

```
URL params:
  agents         string (CSV)        Comma-separated "namespace%2Fname" pairs (max 4)
  
Renders:
  - ComparisonView (table of agents × attributes)
  - Link back to marketplace with current search state preserved
```

---

## Component Props Contracts

### `MarketplaceSearchBar`
```typescript
interface MarketplaceSearchBarProps {
  initialValue: string
  onSearch: (query: string) => void   // called after 300ms debounce
  isLoading: boolean
}
```

### `FilterSidebar`
```typescript
interface FilterSidebarProps {
  filters: Partial<MarketplaceSearchParams>
  filterMetadata: FilterMetadata       // available capabilities + tags
  onChange: (updated: Partial<MarketplaceSearchParams>) => void
  activeFilterCount: number            // shown on mobile "Filters (N)" button
  isMobile: boolean                    // renders as Sheet vs inline panel
}
```

### `AgentCardGrid`
```typescript
interface AgentCardGridProps {
  agents: AgentCard[]
  isLoading: boolean
  isError: boolean
  hasNextPage: boolean
  onLoadMore: () => void               // triggers fetchNextPage
  isFetchingNextPage: boolean
  emptyState?: ReactNode               // custom empty state override
}
```

### `AgentCard`
```typescript
interface AgentCardProps {
  agent: AgentCard
  isSelected: boolean                  // whether in comparison selection
  onToggleCompare: (fqn: string) => void
  href: string                         // links to detail page
  compact?: boolean                    // used in recommendation carousel
}
```

### `AgentDetail` (layout component)
```typescript
interface AgentDetailProps {
  agent: AgentDetail
  isOwner: boolean                     // shows analytics tab when true
}
```

### `TrustSignalsPanel`
```typescript
interface TrustSignalsPanelProps {
  trustSignals: TrustSignals
}
```

### `AgentRevisions`
```typescript
interface AgentRevisionsProps {
  revisions: AgentRevision[]
  currentVersion: string
}
```

### `PolicyList`
```typescript
interface PolicyListProps {
  policies: PolicySummary[]
}
```

### `QualityMetrics`
```typescript
interface QualityMetricsProps {
  metrics: QualityMetrics
}
```

### `ComparisonView`
```typescript
interface ComparisonViewProps {
  agents: AgentDetail[]                // detail-level data for attributes
  onRemove: (fqn: string) => void
}
```

### `ComparisonSelector` (add-to-compare toggle on AgentCard + floating bar)
```typescript
// Reads/writes from useComparisonStore — no props needed for the store state
interface ComparisonFloatingBarProps {
  selectedFqns: string[]
  onClear: () => void
  onCompare: () => void                // navigates to /marketplace/compare
}
```

### `RecommendationCarousel`
```typescript
interface RecommendationCarouselProps {
  data: RecommendationCarousel         // agents[] + reason
  isLoading: boolean
}
// Renders nothing when data.agents.length < 3
```

### `ReviewsSection`
```typescript
interface ReviewsSectionProps {
  agentFqn: string
  currentUserReview: AgentReview | null  // null if user hasn't reviewed
}
// Internally uses useAgentReviews + useSubmitReview + useEditReview hooks
```

### `StarRating` (display-only)
```typescript
interface StarRatingProps {
  rating: number | null                // 0.0 – 5.0; null renders "No ratings"
  reviewCount?: number                 // shown as "(42 reviews)"
  size?: 'sm' | 'md' | 'lg'
}
```

### `StarRatingInput` (interactive)
```typescript
interface StarRatingInputProps {
  value: number                        // 1-5
  onChange: (rating: number) => void
  disabled?: boolean
  name: string                         // for form integration
}
// Each star is a <button aria-label="Rate {n} out of 5 stars">
```

### `InvokeAgentDialog`
```typescript
interface InvokeAgentDialogProps {
  agentFqn: string
  agentDisplayName: string
  isVisible: boolean                   // whether agent is visible to user
  trigger: ReactNode                   // the "Start Conversation" button element
}
// Reads workspace list via existing useWorkspaces() hook
// On confirm: router.push('/conversations/new?agent=...&workspace=...&brief=...')
```

### `CreatorAnalyticsTab`
```typescript
interface CreatorAnalyticsTabProps {
  agentFqn: string
}
// Internally uses useCreatorAnalytics hook
// Only rendered when isOwner === true in AgentDetail
```

### `UsageChart`
```typescript
interface UsageChartProps {
  data: DailyUsage[]
  periodDays: number
}
// Recharts BarChart or AreaChart
```

### `SatisfactionTrendChart`
```typescript
interface SatisfactionTrendChartProps {
  data: WeeklyRating[]
}
// Recharts LineChart with 5.0 max y-axis
```

---

## Accessibility Contracts

All interactive components MUST satisfy:

| Element | Requirement |
|---------|-------------|
| `MarketplaceSearchBar` | `role="search"` wrapper, `aria-label="Search agents"` on input |
| `FilterSidebar` | `role="navigation" aria-label="Agent filters"` on nav wrapper |
| `AgentCard` | Entire card is keyboard-focusable; Enter navigates to detail |
| `StarRatingInput` | Each star is a `<button>` with descriptive `aria-label`; arrow keys adjust value |
| `ComparisonFloatingBar` | `role="status" aria-live="polite"` announces selection changes |
| `InvokeAgentDialog` | Focus trapped within Dialog when open; Escape closes |
| `RecommendationCarousel` | `role="region" aria-label="Recommended agents"` on wrapper |
| Maturity badges | `aria-label="Maturity: Production"` (not just visual badge text) |
| Trust badges | `aria-label="Trust tier: Certified"` |

---

## Dark Mode Contracts

All components MUST use Tailwind `dark:` variants (no hardcoded colors). Color tokens from `globals.css` apply automatically. Specific requirements:

- Star rating filled: `text-yellow-400 dark:text-yellow-300`
- Maturity badges: use shadcn `Badge` variant, not custom colors
- Trust tier colors: use CSS custom property tokens, not hardcoded hex
- Charts (`UsageChart`, `SatisfactionTrendChart`): `stroke` and `fill` colors use `hsl(var(--chart-1))` etc. pattern from globals.css
