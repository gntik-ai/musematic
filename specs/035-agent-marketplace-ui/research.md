# Research: Agent Marketplace UI

**Branch**: `035-agent-marketplace`  
**Status**: Complete — all unknowns resolved

---

## Decision 1: Search State — URL Params vs Component State

**Decision**: URL query parameters for all search/filter/sort state. Comparison selection in Zustand.

**Rationale**: URL params make search results shareable and support browser back/forward navigation. TanStack Query's `useQuery` accepts derived keys from `useSearchParams()` — when params change, the query re-runs automatically. No custom state sync needed. Comparison selection is explicitly session-scoped (per spec Assumptions) and has no shareable use case, so Zustand is the correct home.

**Implementation**: `useSearchParams()` + `useRouter()` from Next.js App Router. On filter change: `router.push('/marketplace?' + new URLSearchParams(params))`. Debounce only applies to the search input keystroke → URL push, not to the API call (which fires on URL change, already debounced).

**Alternatives considered**: Component state (useState) for search — rejected; search links would not be shareable, browser back would lose the search. Server state in URL + TanStack Query is the idiomatic Next.js App Router pattern.

---

## Decision 2: Debounce Implementation

**Decision**: `useDebouncedValue` custom hook with 300ms delay; implemented via `useRef` + `setTimeout` inside a custom hook. No external debounce library.

**Rationale**: The constitution bans custom CSS files but has no policy on utility hooks. A 10-line `useDebouncedValue` hook covers the need without any additional dependency. The debounce fires a URL push, not a direct API call — this keeps the debounce concern at the UI interaction layer, not the data layer.

**Alternatives considered**: `use-debounce` npm package — rejected; too small a need to justify a dependency. Lodash `debounce` — rejected; lodash is not in the approved stack.

---

## Decision 3: Agent Detail Page Routing

**Decision**: Two-segment dynamic routes: `app/(main)/marketplace/[namespace]/[name]/page.tsx`

**Rationale**: FQNs take the form `namespace:local_name` (e.g., `finance-ops:kyc-verifier`). Encoding a colon in a URL segment (`finance-ops%3Akyc-verifier`) is valid but ugly and fragile in some proxies. Splitting into two clean path segments (`/marketplace/finance-ops/kyc-verifier`) is more readable, canonical, and proxy-safe. The detail page reconstructs the FQN as `${namespace}:${name}` for API calls.

**Comparison page**: `app/(main)/marketplace/compare/page.tsx` with query param `?agents=namespace1%2Fname1,namespace2%2Fname2` (comma-separated encoded pairs).

**Alternatives considered**: Single `[fqn]` segment with percent-encoded colon — rejected; proxy/CDN issues, unreadable URLs. UUID-based routing — rejected; FQN is the canonical identity per constitution §VIII.

---

## Decision 4: Comparison Store

**Decision**: Zustand store `useComparisonStore` with `agents: string[]` (list of FQNs), `add(fqn)`, `remove(fqn)`, `clear()` methods. Max 4 enforcement in `add()`. No persistence (`sessionStorage` would work but spec says session-scoped, not persisted).

**Rationale**: Comparison is the one piece of UI state that must be shared across multiple components simultaneously (agent cards → add-to-compare buttons, floating compare bar, compare page). Zustand provides a lightweight global store without prop drilling. Per spec, comparison selections are not persisted across sessions.

**Floating compare bar**: A fixed-position component showing current selection (0-4 agents) with "Compare" button — visible when ≥2 agents selected. Uses `useComparisonStore`.

**Alternatives considered**: URL query params for comparison — technically feasible but creates awkward URL state when navigating to detail pages mid-comparison. Zustand is cleaner for transient cross-page state.

---

## Decision 5: Star Rating Component

**Decision**: Custom `StarRating` (display) and `StarRatingInput` (interactive) components using Lucide `Star` and `StarHalf` icons with Tailwind `text-yellow-400` / `text-muted-foreground` for filled/empty states. No external star rating library.

**Rationale**: shadcn/ui has no built-in star rating component. A custom implementation with Lucide icons (already in the stack) is 30-40 lines and avoids a new dependency. The interactive version handles keyboard navigation (arrow keys to adjust, Enter to confirm) for WCAG compliance.

**StarRatingInput**: Renders 5 `<button>` elements, each wrapping a `Star` icon. `aria-label="Rate {n} out of 5 stars"` on each button. `aria-current="true"` on the selected rating.

**Alternatives considered**: `react-stars`, `react-rating` — rejected; adds a dependency for a trivial component that also needs to match the shadcn/Tailwind design system.

---

## Decision 6: Invocation Flow

**Decision**: shadcn `Dialog` component with a two-step flow: (1) workspace selector (`Select` or `RadioGroup`) + (2) task brief (`Textarea` + confirm `Button`). Auto-advances to step 2 when only one workspace available.

**Redirect target**: `router.push('/conversations/new?agent=<fqn>&workspace=<workspaceId>&brief=<encoded text>')`. The conversations page (feature 024) reads these params on load.

**Rationale**: A Dialog modal keeps the user in the marketplace context while completing the invocation setup. Using URL params for the redirect (rather than router state) makes the conversation page linkable and supports browser refresh.

**Alternatives considered**: `Sheet` (slide-in drawer) — suitable but Dialog is more conventional for a confirmation flow. Separate page route for invocation — rejected; too much navigation for a 2-step flow.

---

## Decision 7: Creator Analytics Tab Visibility

**Decision**: Tab is rendered conditionally based on `workspaceRole === 'owner' || workspaceRole === 'admin' || currentUser.id === agent.createdById`. Evaluated from existing Zustand `auth-store` + agent detail API response. Tab is not rendered in DOM for non-owners (not just hidden with CSS).

**Rationale**: The constitution §IX (zero-trust visibility) and §VI (policy is machine-enforced) both dictate that enforcement happens in the backend — but the UI must not render affordances that mislead users about their access. If a non-owner somehow calls the analytics API, the backend will return 403. The UI just avoids showing the tab to prevent confusion.

**Alternatives considered**: Always render the tab and show a 403 error state inside — rejected; bad UX, exposes the existence of owner-only data.

---

## Decision 8: Recommendations Carousel

**Decision**: shadcn `ScrollArea` with `flex flex-nowrap` inner container, overflowing horizontally. Uses the same `AgentCard` component (compact variant). `useRecommendations()` TanStack Query hook; fallback reason shown in carousel header text ("Trending agents" vs "Recommended for you").

**Visibility rule**: Carousel hidden entirely when API returns fewer than 3 agents (or error). Uses `data.agents.length >= 3` guard before rendering.

**Alternatives considered**: Custom carousel with `embla-carousel` — considered but `ScrollArea` is simpler and already in shadcn. No autoplay needed (content is static agent cards, not media).

---

## Decision 9: Reviews Pagination

**Decision**: Offset-based pagination with shadcn `Button` "Load more" (not infinite scroll) for reviews. Infinite scroll is reserved for the main search grid (which may have 100s of results). Reviews list is typically short; "Load more" is less disruptive on a detail page.

**TanStack Query**: `useInfiniteQuery` for the search grid (infinite scroll). `useQuery` with page param for reviews (load more button advances `page` param).

**Alternatives considered**: Infinite scroll for reviews — rejected; reviews section is below the fold on the detail page; infinite scroll would conflict with normal page scroll behavior.

---

## Decision 10: FilterSidebar — Mobile Collapse

**Decision**: On mobile breakpoint (`sm:` down), the filter sidebar renders as a `Sheet` (slide-in drawer) triggered by a "Filters" button. On desktop, it renders inline as a fixed sidebar. Uses `useMediaQuery('(max-width: 640px)')` hook to choose rendering mode.

**Rationale**: The spec requires mobile filters to collapse to a drawer. shadcn `Sheet` is the correct primitive. A single `FilterSidebar` component handles both modes, rendering differently based on breakpoint.

**Alternatives considered**: Always render as a `Sheet` and show on desktop too — rejected; desktop users benefit from always-visible filters for rapid iteration. Separate `FilterSidebar` and `FilterDrawer` components — rejected; duplication with no benefit.
