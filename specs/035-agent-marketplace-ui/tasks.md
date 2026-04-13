# Tasks: Agent Marketplace UI

**Input**: Design documents from `/specs/035-agent-marketplace-ui/`  
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓

**Organization**: Tasks grouped by user story — each story is independently implementable and testable.  
**Tests**: Included (SC-011 requires ≥95% test coverage across all marketplace UI components).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no incomplete dependencies)
- **[Story]**: Maps task to a specific user story for traceability
- File paths are relative to the `apps/web/` workspace root

---

## Phase 1: Setup

**Purpose**: Create directory structure for all marketplace source files.

- [x] T001 Create directory scaffold: `app/(main)/marketplace/`, `app/(main)/marketplace/[namespace]/[name]/`, `app/(main)/marketplace/compare/`, `components/features/marketplace/`, `lib/hooks/`, `lib/stores/`, `lib/types/`, `lib/schemas/` under `apps/web/`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Types, schemas, store, utility hooks, and TanStack Query data hooks — no UI yet. ALL user stories depend on this phase.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T002 Create all TypeScript types (AgentCard, AgentDetail, AgentRevision, TrustSignals, TierHistoryEntry, CertificationBadge, EvaluationSummary, PolicySummary, QualityMetrics, CostBreakdown, VisibilityConfig, AgentReview, ReviewSubmission, MarketplaceSearchParams, FilterMetadata, RecommendationCarousel, ComparisonRow, CreatorAnalytics, DailyUsage, WeeklyRating, FailureCategory, InvocationRequest, all enums) in `apps/web/lib/types/marketplace.ts`
- [x] T003 Create Zod validation schemas (ReviewSubmissionSchema, InvocationSchema, SearchParamsSchema) in `apps/web/lib/schemas/marketplace.ts`
- [x] T004 Create Zustand comparison store (selectedFqns: string[], add/remove/clear/isSelected/canAdd, max 4, no persist middleware) in `apps/web/lib/stores/use-comparison-store.ts`
- [x] T005 [P] Create `useDebouncedValue<T>(value: T, delay: number)` custom hook using useRef + setTimeout (no external library) in `apps/web/lib/hooks/use-debounced-value.ts`
- [x] T006 [P] Create `useMarketplaceSearch` useInfiniteQuery hook (key: `['marketplace', 'search', params]`, fetchNextPage increments page param) in `apps/web/lib/hooks/use-marketplace-search.ts`
- [x] T007 [P] Create `useAgentDetail(namespace, name)` useQuery hook (key: `['marketplace', 'agent', namespace, name]`) in `apps/web/lib/hooks/use-agent-detail.ts`
- [x] T008 [P] Create `useAgentReviews` useQuery + `useSubmitReview` useMutation (POST, invalidate reviews key on success) + `useEditReview` useMutation (PATCH) in `apps/web/lib/hooks/use-agent-reviews.ts`
- [x] T009 [P] Create `useRecommendations` useQuery hook (key: `['marketplace', 'recommendations']`) in `apps/web/lib/hooks/use-recommendations.ts`
- [x] T010 [P] Create `useCreatorAnalytics(fqn, periodDays?)` useQuery hook (key: `['marketplace', 'analytics', fqn, periodDays]`) in `apps/web/lib/hooks/use-creator-analytics.ts`

**Checkpoint**: Foundation complete — all user story phases can now begin.

---

## Phase 3: User Story 1 — Marketplace Search and Browse (Priority: P1) 🎯 MVP

**Goal**: `/marketplace` page with natural-language search, faceted filters, sort, agent card grid, and infinite scroll.

**Independent Test**: Navigate to `/marketplace`, type "financial analysis" in the search bar, wait 300ms, verify cards update; check "production" maturity filter, verify URL updates to `?maturityLevels=production` and grid filters; scroll to bottom, verify next page of cards loads.

- [x] T011 [P] [US1] Implement `StarRating` display-only component (`rating: number | null`, renders "No ratings" when null, size sm/md/lg, `text-yellow-400 dark:text-yellow-300`) in `apps/web/components/features/marketplace/star-rating.tsx`
- [x] T012 [P] [US1] Implement `MarketplaceSearchBar` (`role="search"`, `aria-label="Search agents"` on input, uses `useDebouncedValue(300ms)`, calls `onSearch` after debounce, pushes to URL via `router.push`) in `apps/web/components/features/marketplace/marketplace-search-bar.tsx`
- [x] T013 [P] [US1] Implement `FilterSidebar` (desktop: inline panel with `role="navigation" aria-label="Agent filters"`; mobile: shadcn Sheet triggered by "Filters (N)" button via `useMediaQuery('(max-width: 640px)')`; checkbox groups for maturityLevels, trustTiers, certificationStatuses, costTiers, capabilities, tags; "Clear all filters" button) in `apps/web/components/features/marketplace/filter-sidebar.tsx`
- [x] T014 [P] [US1] Implement `ComparisonFloatingBar` (fixed-position bottom bar, `role="status" aria-live="polite"`, shows "{N} agents selected", "Compare now" button navigates to `/marketplace/compare?agents=…`, "Clear" button calls `useComparisonStore().clear()`, visible when `selectedFqns.length >= 1`) in `apps/web/components/features/marketplace/comparison-floating-bar.tsx`
- [x] T015 [US1] Implement `AgentCard` (name, shortDescription, maturity badge with `aria-label="Maturity: X"`, trust badge with `aria-label="Trust tier: X"`, `StarRating`, cost indicator, Compare toggle button calling `onToggleCompare(fqn)`, disabled with tooltip "Maximum of 4 agents" when `!canAdd && !isSelected`, entire card keyboard-focusable with Enter navigating to `href`) in `apps/web/components/features/marketplace/agent-card.tsx`
- [x] T016 [US1] Implement `AgentCardGrid` (responsive CSS grid, `IntersectionObserver` sentinel triggering `onLoadMore`, loading skeleton (shadcn Skeleton) during `isLoading`, empty state "No agents match your search" when 0 results, error state, no loading indicator when `!hasNextPage`) in `apps/web/components/features/marketplace/agent-card-grid.tsx`
- [x] T017 [US1] Implement `/marketplace` landing page: read `useSearchParams()`, wire `MarketplaceSearchBar`, `FilterSidebar`, sort `Select` (`sortBy` URL param), `AgentCardGrid` (fed by `useMarketplaceSearch`), `ComparisonFloatingBar` (from `useComparisonStore`) in `apps/web/app/(main)/marketplace/page.tsx`

**Checkpoint**: `/marketplace` page fully functional with search, filters, sort, and infinite scroll.

---

## Phase 4: User Story 2 — Agent Detail Page (Priority: P1)

**Goal**: `/marketplace/[namespace]/[name]` page with all metadata sections, trust signals, revisions, policies, quality metrics, and archived-agent handling.

**Independent Test**: Navigate to `/marketplace/finance-ops/kyc-verifier`, verify all tab sections render with correct data; navigate to a non-existent agent URL, verify "This agent is no longer available" message with back link.

- [x] T018 [P] [US2] Implement `TrustSignalsPanel` (trust tier badge, certification badges with issue/expiry dates and `isActive` indicator, `EvaluationSummary` showing score + passedCases/totalCases + date, tier progression timeline from `tierHistory`) in `apps/web/components/features/marketplace/trust-signals-panel.tsx`
- [x] T019 [P] [US2] Implement `AgentRevisions` (chronological list of `AgentRevision[]`, current version highlighted, version + changeDescription + publishedAt formatted with date-fns) in `apps/web/components/features/marketplace/agent-revisions.tsx`
- [x] T020 [P] [US2] Implement `PolicyList` (list of `PolicySummary[]`, each showing name, type, enforcement badge using shadcn Badge variant for block/warn/log) in `apps/web/components/features/marketplace/policy-list.tsx`
- [x] T021 [P] [US2] Implement `QualityMetrics` (evaluationScore, robustnessScore, passRate as percentages, lastEvaluatedAt formatted with date-fns; null values shown as "—") in `apps/web/components/features/marketplace/quality-metrics.tsx`
- [x] T022 [US2] Implement `AgentDetail` layout component: shadcn Tabs with Overview (description + capabilities + TrustSignalsPanel) | Policies (PolicyList) | Quality Metrics (QualityMetrics + AgentRevisions) | Reviews (stub, wired in US4) | Analytics (stub, only rendered in DOM when `isOwner === true`, wired in US7); "Start Conversation" button (disabled + shadcn Tooltip "You don't have access to invoke this agent" when `!agent.visibility.visibleToCurrentUser`) in `apps/web/components/features/marketplace/agent-detail.tsx`
- [x] T023 [US2] Implement `/marketplace/[namespace]/[name]` page: calls `useAgentDetail(namespace, name)`, renders `AgentDetail`, handles archived/missing agent with "This agent is no longer available" + "Back to Marketplace" link (no 404 page) in `apps/web/app/(main)/marketplace/[namespace]/[name]/page.tsx`

**Checkpoint**: Agent detail page fully functional with all sections; archived agent state handled.

---

## Phase 5: User Story 3 — Agent Comparison (Priority: P2)

**Goal**: `/marketplace/compare` side-by-side table for 2–4 agents with N/A indicators and remove button.

**Independent Test**: Select 3 agents from the marketplace (floating bar shows 3), click "Compare now", verify `/marketplace/compare?agents=…` page shows table with 3 columns, all attribute rows, `"—"` for any missing value, and a working "Remove" button per column.

- [x] T024 [US3] Implement `ComparisonView` (table: agents as columns, attribute rows — Display Name, Maturity, Trust Tier, Capabilities, Average Rating, Cost, Latest Eval Score, Active Policies, Certification Badges; `"—"` N/A indicator; per-column remove button calling `onRemove(fqn)`) in `apps/web/components/features/marketplace/comparison-view.tsx`
- [x] T025 [US3] Implement `/marketplace/compare` page: parse `?agents=` CSV (max 4 FQNs), call `useAgentDetail` per FQN, render `ComparisonView`, back-link preserving current search state in `apps/web/app/(main)/marketplace/compare/page.tsx`

**Checkpoint**: Comparison page functional with up to 4 agents, N/A handling, and agent removal.

---

## Phase 6: User Story 4 — Ratings and Reviews (Priority: P2)

**Goal**: Review list with load-more, submit new review, edit own review, zero-review empty state.

**Independent Test**: Navigate to an agent detail page, scroll to Reviews tab; submit a 4-star review with text, verify it appears at the top and the average rating updates; view the same page again, verify "Edit" button replaces the write form.

- [x] T026 [US4] Implement `StarRatingInput` (5 `<button>` elements each wrapping Lucide `Star`, `aria-label="Rate {n} out of 5 stars"`, `aria-current="true"` on selected value, arrow key left/right adjusts value, Enter confirms) in `apps/web/components/features/marketplace/star-rating-input.tsx`
- [x] T027 [US4] Implement `ReviewsSection` (average rating header with `StarRating` + review count; review list with load-more button using `useAgentReviews`; write form with `StarRatingInput` + Textarea + Submit using React Hook Form + `ReviewSubmissionSchema` + `useSubmitReview`; edit mode when `currentUserReview !== null` showing prefilled inline form + `useEditReview`; "No reviews yet" empty state with "Be the first to review" text) in `apps/web/components/features/marketplace/reviews-section.tsx`
- [x] T028 [US4] Wire `ReviewsSection` into the Reviews tab of `AgentDetail`, passing `agentFqn` and `currentUserReview` in `apps/web/components/features/marketplace/agent-detail.tsx`

**Checkpoint**: Reviews tab fully functional; submit/edit reviews work with optimistic update.

---

## Phase 7: User Story 5 — Agent Invocation (Priority: P2)

**Goal**: "Start Conversation" opens Dialog → workspace selector → task brief → redirect to `/conversations/new`.

**Independent Test**: Click "Start Conversation" on a detail page, verify Dialog opens, select a workspace, enter a task brief, click "Start Conversation", verify redirect to `/conversations/new?agent=…&workspace=…&brief=…`.

- [x] T029 [US5] Implement `InvokeAgentDialog` (shadcn Dialog, two-step: Step 1 = workspace `Select`/`RadioGroup` using existing `useWorkspaces()` hook, auto-skip to Step 2 when 1 workspace (show read-only "Selected workspace: X"); Step 2 = task brief `Textarea` (max 500 chars, RHF + `InvocationSchema`); on confirm: `router.push('/conversations/new?agent=<fqn>&workspace=<id>&brief=<encoded text>')`; focus trapped within Dialog; Escape closes and returns focus to trigger) in `apps/web/components/features/marketplace/invoke-agent-dialog.tsx`
- [x] T030 [US5] Wire `InvokeAgentDialog` as the trigger for the "Start Conversation" button in `AgentDetail` (pass `agentFqn`, `agentDisplayName`, `isVisible = agent.visibility.visibleToCurrentUser`) in `apps/web/components/features/marketplace/agent-detail.tsx`

**Checkpoint**: "Start Conversation" full flow functional; disabled state + tooltip working for non-visible agents.

---

## Phase 8: User Story 6 — Recommendation Carousel (Priority: P3)

**Goal**: Personalized or popular agent carousel above search bar; hidden when fewer than 3 results.

**Independent Test**: Load `/marketplace` as a user with interaction history, verify carousel shows ≥3 agent cards with "Recommended for you" header; simulate API returning 2 items, verify carousel not rendered.

- [x] T031 [US6] Implement `RecommendationCarousel` (shadcn `ScrollArea` with `flex flex-nowrap` inner container; `role="region" aria-label="Recommended agents"`; header text: "Recommended for you" when `reason === 'personalized'`, "Popular agents" or "Trending this week" otherwise; compact `AgentCard` variant; returns `null` when `data.agents.length < 3`; no-op when `isLoading` until data arrives) in `apps/web/components/features/marketplace/recommendation-carousel.tsx`
- [x] T032 [US6] Wire `RecommendationCarousel` above `MarketplaceSearchBar` in `/marketplace` landing page, fed by `useRecommendations()` in `apps/web/app/(main)/marketplace/page.tsx`

**Checkpoint**: Carousel renders for users with history; hidden for new users with <3 results.

---

## Phase 9: User Story 7 — Creator Analytics (Priority: P3)

**Goal**: Analytics tab visible only to agent owners showing usage chart, satisfaction trend, and common failures.

**Independent Test**: Log in as an agent creator, navigate to their agent detail page, click Analytics tab, verify BarChart shows daily invocations, LineChart shows weekly ratings, common failures list shows categories with counts; log in as non-owner, verify Analytics tab is not in the DOM.

- [x] T033 [P] [US7] Implement `UsageChart` (Recharts `BarChart` with `DailyUsage[]` data, x-axis date labels, `fill="hsl(var(--chart-1))"`, responsive container) in `apps/web/components/features/marketplace/usage-chart.tsx`
- [x] T034 [P] [US7] Implement `SatisfactionTrendChart` (Recharts `LineChart` with `WeeklyRating[]` data, y-axis domain 0–5, `stroke="hsl(var(--chart-2))"`, null data points shown as gaps, responsive container) in `apps/web/components/features/marketplace/satisfaction-trend-chart.tsx`
- [x] T035 [US7] Implement `CreatorAnalyticsTab` (calls `useCreatorAnalytics(agentFqn)`, renders `UsageChart`, `SatisfactionTrendChart`, common failures list with category + count + percentage; "No usage data yet" empty state when all arrays empty) in `apps/web/components/features/marketplace/creator-analytics-tab.tsx`
- [x] T036 [US7] Wire `CreatorAnalyticsTab` into the Analytics tab of `AgentDetail` — only rendered when `isOwner === true` (not hidden, not rendered); pass `agentFqn` prop in `apps/web/components/features/marketplace/agent-detail.tsx`

**Checkpoint**: Analytics tab functional for owners; not present in DOM for non-owners.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: MSW mocks, test coverage, dark mode, keyboard accessibility.

- [x] T037 Create MSW request handlers for all 9 marketplace API endpoints (GET search, GET agent detail, GET reviews, POST review, PATCH review, GET recommendations, GET analytics, GET filter metadata, GET workspaces) in `apps/web/mocks/handlers/marketplace.ts`
- [x] T038 [P] Write Vitest + RTL unit tests for US1 components: `StarRating`, `MarketplaceSearchBar` (debounce fires at 300ms), `FilterSidebar` (desktop inline + mobile Sheet modes), `AgentCard` (compare toggle, disabled state, keyboard Enter), `AgentCardGrid` (skeleton, empty state, IntersectionObserver) in `apps/web/components/features/marketplace/*.test.tsx`
- [x] T039 [P] Write Vitest + RTL unit tests for US2 components: `TrustSignalsPanel`, `AgentRevisions`, `PolicyList`, `QualityMetrics`, `AgentDetail` (tabs render, "Start Conversation" disabled state, Analytics tab absent for non-owners) in `apps/web/components/features/marketplace/*.test.tsx`
- [x] T040 [P] Write Vitest + RTL unit tests for US3–US5 components: `ComparisonView` (N/A indicator, remove button), `StarRatingInput` (aria-labels, arrow key navigation), `ReviewsSection` (submit form, edit mode, empty state), `InvokeAgentDialog` (two-step flow, auto-skip, focus trap, Escape close) in `apps/web/components/features/marketplace/*.test.tsx`
- [x] T041 [P] Write Vitest + RTL unit tests for US6–US7 components: `RecommendationCarousel` (renders ≥3, returns null < 3, reason-based header), `CreatorAnalyticsTab` (empty state), `UsageChart`, `SatisfactionTrendChart` in `apps/web/components/features/marketplace/*.test.tsx`
- [x] T042 Write Playwright E2E tests covering primary flows T01 (search returns results), T07 (agent detail full view), T10 (add agents to comparison), T13 (view and submit review), T16 (invoke agent workspace selection) in `apps/web/e2e/marketplace.spec.ts`
- [x] T043 [P] Audit dark mode: verify `dark:` Tailwind variants on all maturity/trust badges, star rating icons (`dark:text-yellow-300`), chart tokens (`hsl(var(--chart-N))`), and card backgrounds across all 18 components; no hardcoded hex colors
- [x] T044 [P] Audit keyboard navigation: focus trap in `InvokeAgentDialog`, arrow keys in `StarRatingInput`, Enter on `AgentCard` navigates, Tab order through FilterSidebar checkboxes, `role`/`aria-*` attributes on `ComparisonFloatingBar`, `RecommendationCarousel`, and all maturity/trust badges

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — **BLOCKS all user story phases**
- **US1 (Phase 3)**: Depends on Phase 2 — P1, implement first
- **US2 (Phase 4)**: Depends on Phase 2 — P1, can run in parallel with US1
- **US3 (Phase 5)**: Depends on Phase 2 + US1 (ComparisonFloatingBar) + US2 (AgentDetail data model)
- **US4 (Phase 6)**: Depends on Phase 2 + US2 (AgentDetail tab scaffold)
- **US5 (Phase 7)**: Depends on Phase 2 + US2 (AgentDetail "Start Conversation" button)
- **US6 (Phase 8)**: Depends on Phase 2 + US1 (AgentCard compact variant)
- **US7 (Phase 9)**: Depends on Phase 2 + US2 (AgentDetail Analytics tab stub)
- **Polish (Phase 10)**: Depends on all desired user stories complete

### User Story Dependencies

- **US1 (P1)**: Independent after Foundational
- **US2 (P1)**: Independent after Foundational — can run in parallel with US1
- **US3 (P2)**: Requires US1 (comparison store, AgentCard) + US2 (AgentDetail types)
- **US4 (P2)**: Requires US2 (AgentDetail tab structure in T022)
- **US5 (P2)**: Requires US2 (AgentDetail "Start Conversation" button in T022)
- **US6 (P3)**: Requires US1 (AgentCard compact variant)
- **US7 (P3)**: Requires US2 (AgentDetail Analytics tab stub in T022)

### Within Each User Story

- Components marked [P] within a phase can run in parallel (different files)
- Sub-components before parent components (StarRating → AgentCard → AgentCardGrid)
- Components before page wiring (all components → page.tsx)
- AgentDetail is updated incrementally: T022 (base) → T028 (Reviews) → T030 (InvokeAgentDialog) → T036 (Analytics)

### Parallel Opportunities

```bash
# Phase 2: All foundational hooks in parallel (different files)
T005: use-debounced-value.ts
T006: use-marketplace-search.ts
T007: use-agent-detail.ts
T008: use-agent-reviews.ts
T009: use-recommendations.ts
T010: use-creator-analytics.ts

# Phase 3 (US1): Leaf components in parallel
T011: marketplace-search-bar.tsx
T012: filter-sidebar.tsx
T013: agent-card.tsx (StarRating) (after T011)
T014: comparison-floating-bar.tsx

# Phase 4 (US2): Section components in parallel
T018: trust-signals-panel.tsx
T019: agent-revisions.tsx
T020: policy-list.tsx
T021: quality-metrics.tsx

# Phase 9 (US7): Chart components in parallel
T033: usage-chart.tsx
T034: satisfaction-trend-chart.tsx

# Phase 10 (Polish): Test suites and audits in parallel
T038, T039, T040, T041: Component test suites (different files)
T043, T044: Dark mode + keyboard audits
```

---

## Implementation Strategy

### MVP First (US1 + US2 Only)

1. Complete Phase 1: Setup (T001)
2. Complete Phase 2: Foundational (T002–T010)
3. Complete Phase 3: US1 Search & Browse (T011–T017)
4. Complete Phase 4: US2 Agent Detail (T018–T023)
5. **STOP and VALIDATE**: Users can discover agents, view details, and assess trust signals
6. Deploy/demo as marketplace MVP

### Incremental Delivery

1. **MVP**: Setup + Foundational + US1 + US2 → Core discovery experience
2. **+US3**: Add Comparison → Side-by-side agent evaluation
3. **+US4**: Add Reviews → Social proof and community feedback
4. **+US5**: Add Invocation → Marketplace drives conversations
5. **+US6**: Add Recommendations → Passive discovery channel
6. **+US7**: Add Creator Analytics → Feedback loop for agent builders
7. **+Polish**: Tests, dark mode, keyboard audit → Production-ready

### Parallel Team Strategy

After Phase 2 (Foundational):
- **Developer A**: US1 (T011–T017) → US6 (T031–T032)
- **Developer B**: US2 (T018–T023) → US4 (T026–T028) → US7 (T033–T036)
- **Developer C**: US3 (T024–T025) → US5 (T029–T030) → Polish (T037–T044)

---

## Notes

- `[P]` = different files, no dependencies on incomplete tasks in same phase
- `[Story]` label maps every implementation task to a user story for traceability
- `AgentDetail` (`agent-detail.tsx`) is updated in 4 separate tasks (T022, T028, T030, T036) — each update adds a new section independently
- `useDebouncedValue` (T005) is the only custom utility hook; all other hooks wrap TanStack Query
- No new npm packages required — all dependencies are already in the stack (shadcn, Recharts, Zustand, TanStack Query, RHF, Zod, MSW)
- ComparisonFloatingBar is part of US1 because it first appears on the marketplace grid
- Verify each story independently before moving to the next
- Commit after each task or logical group
