# Research & Decisions: Frontend Updates for All New Features

**Feature**: 070-frontend-updates-cross-cutting
**Date**: 2026-04-20

## Context

This feature touches nine existing Next.js pages and adds three new settings pages to surface backend capabilities from features 053–067. The key constraint is Brownfield Rule 1 (never rewrite) + Rule 4 (use existing patterns) + CLAUDE.md requirement: "shadcn/ui (ALL UI primitives), no new charting lib, no new DnD lib". Every decision below is shaped by that constraint.

## Existing Frontend State (Baseline)

| Component / Pattern | Location | Status |
|---|---|---|
| Next.js App Router, `(main)` + `(auth)` route groups | `apps/web/app/(main)/` | ✅ In use |
| `lib/api.ts` — fetch wrapper with JWT injection + 401-refresh-retry | `apps/web/lib/api.ts` | ✅ Reuse |
| `lib/ws.ts` — `WebSocketClient` with exponential backoff + topic subscriptions | `apps/web/lib/ws.ts` | ✅ Reuse; extend with 3 new channel types |
| `lib/hooks/use-api.ts` — factory for TanStack Query hooks | `apps/web/lib/hooks/use-api.ts` | ✅ Reuse pattern |
| `lib/hooks/use-alert-feed.ts` | existing | ✅ Extend for WS subscription |
| `components/shared/ConfirmDialog` | `apps/web/components/shared/` | ✅ Reuse; extend with `requireTypedConfirmation` prop |
| `components/shared/EmptyState`, `ConnectionStatusBanner`, `DataTable` | `apps/web/components/shared/` | ✅ Reuse as-is |
| Zustand stores (`auth-store`, `workspace-store`) | `apps/web/store/` | ✅ Add `alert-store.ts` only |
| Feature 043 trust-workbench with HTML5 native drag-and-drop for policy attachment | `apps/web/app/(main)/trust-workbench/` | ✅ Precedent for US5 governance-chain DnD |
| Feature 035 marketplace with TanStack Query `useInfiniteQuery` + Zustand `useComparisonStore` | `apps/web/app/(main)/marketplace/` | ✅ Extend cards with FQN + expiry pill |
| Feature 044 operator dashboard with existing WS integration | `apps/web/app/(main)/operator/` | ✅ Extend with warm-pool + verdict feed + decommission + gauges |
| Feature 050 evaluation-testing UI | `apps/web/app/(main)/evaluation-testing/` | ✅ Extend suite editor with rubric + calibration |

---

## Decisions

### D-001: No new packages — reuse existing stack only

**Decision**: All new components use shadcn/ui primitives, Tailwind tokens, TanStack Query v5, Zustand, React Hook Form + Zod, Recharts, date-fns, Lucide React. **Nothing added to `package.json`**.

**Rationale**: CLAUDE.md lists the exact stack used for every prior frontend feature (015, 017, 026, 027, 035, 041, 042, 043, 044, 049, 050). Brownfield Rule 4 prohibits divergence. Adding libraries like `@dnd-kit` or `react-window` would fork the convention across features and add bundle weight for features we can already express with existing primitives.

**Alternatives considered**:
- `@dnd-kit` for governance-chain DnD — rejected: feature 043 proved HTML5 native DnD is sufficient.
- `react-window` for trajectory virtualization — rejected: TanStack Virtual (already transitive dep via TanStack Table's `DataTable`) covers the case.
- `framer-motion` for verdict-feed flash — rejected: Tailwind `animate-*` utilities suffice.

---

### D-002: HTML5 native drag-and-drop for governance-chain editor (US5)

**Decision**: The Observer/Judge/Enforcer drop zones use HTML5 `draggable=true` + `onDragStart`/`onDragOver`/`onDrop` handlers. A parallel keyboard path (`Tab` to focus → `Space` to pick → arrow keys to move → `Space` to drop, or an explicit "Assign" button in the picker dialog) is the accessibility fallback.

**Rationale**: Matches feature 043 `PolicyAttachmentPanel` precedent. No third-party DnD dependency. Keyboard fallback satisfies SC-006 (WCAG 2.1 AA). The drop zones in governance are simpler than feature 043 policies (3 fixed slots vs. N-to-M attachment), so complexity stays low.

---

### D-003: Virtualize trajectory timeline via TanStack Virtual (existing transitive dep)

**Decision**: Trajectory renders as a vertical list using the same virtualization primitive that backs `DataTable` (feature 015). For executions ≤ 100 steps, render all at once (no virtualization overhead). For > 100 steps, switch to virtualized mode.

**Rationale**: TanStack Virtual is already a transitive dependency of TanStack Table. Introducing `react-window` would violate D-001. The 100-step threshold matches "typical" execution length; above that, users need FPS headroom (SC-004).

---

### D-004: Reuse existing `WebSocketClient` — add 3 new channel types

**Decision**: Extend `lib/ws.ts` to declare three new channel types as string-literal union members: `alerts`, `governance-verdicts`, `warm-pool`. Each has a unique topic-key shape defined in `contracts/websocket-channels.md`. No new client class, no new reconnect logic.

**Rationale**: `WebSocketClient` already handles auth, reconnection (1 s → 30 s exponential), topic subscription refcounts, and 30 s polling fallback (FR-013). Feature 019 (WebSocket hub) registers these channel names server-side; client just subscribes via existing API.

---

### D-005: Alert store pattern — Zustand for UI state, TanStack Query for list

**Decision**: A new `store/alert-store.ts` holds only `unreadCount: number`, `isDropdownOpen: boolean`, and imperative `markAllAsRead()` / `increment()` / `setUnreadCount(n)`. The alert **list** is fetched via the existing `use-alert-feed` hook using `useInfiniteQuery`. A WS subscription in the bell component calls `alertStore.increment()` on new events and invalidates the TanStack Query cache.

**Rationale**: Unread count is client-ephemeral UI state (Zustand territory). Alert list is server truth (TanStack Query territory). Mixing them in one store would duplicate data. On reconnect, the bell fetches server unread count and calls `setUnreadCount(n)` to reconcile optimistic drift.

---

### D-006: Legacy-agent tolerance everywhere FQN is expected

**Decision**:
- **Agent form**: when loading an agent with `namespace=null` or `local_name=null`, pre-fill empty inputs and show a one-time banner "This agent predates FQN — assign a namespace to activate governance features". Save blocked until both are filled (FR-003).
- **Marketplace card**: render with "Legacy agent" neutral-gray pill (no role badge, no expiry pill) — card remains fully functional.
- **Marketplace search**: FQN-prefix queries segregate legacy agents into a dedicated "Legacy (uncategorized)" collapsed bucket at the bottom of the results; a blank search shows all agents, legacy and modern, interleaved.
- **Governance/visibility editors**: legacy agents are selectable but a warning icon next to their entry indicates "FQN missing — visibility patterns will not match this agent".

**Rationale**: Users deploying feature 070 onto a workspace with pre-053 agents must not see broken marketplace cards or crash-prone forms. The tolerance is explicit and testable (edge case in spec + Playwright coverage).

---

### D-007: Decommission wizard extends `ConfirmDialog` — does not replace it

**Decision**: Add an optional `requireTypedConfirmation?: string` prop to the existing `ConfirmDialog`. When present, the confirm button is disabled until the user types the exact value. The decommission wizard passes the agent FQN as the required value. This is the only `ConfirmDialog` signature change.

**Rationale**: Typed-confirmation is a pattern used once today (rollback in feature 043). Extending `ConfirmDialog` keeps the destructive-action UX consistent across the app (FR-038). A separate `TypedConfirmDialog` component would drift.

---

### D-008: RBAC gates reuse existing `requiredRoles` pattern

**Decision**: All new routes and components use the existing `requiredRoles: RoleType[]` prop from `apps/web/lib/rbac.ts`. Mapping:
- `platform_admin` → operator dashboard (all tabs), trust-workbench admin tabs (certifiers), warm-pool panel, decommission wizard, reliability gauges
- `workspace_admin` → governance chain editor, visibility grants editor, alert settings (workspace-wide rules)
- `workspace_member` → workspace goal operations, per-interaction alert overrides, agent authoring (create/edit within own workspace)
- `viewer` → read-only marketplace cards, read-only execution detail, read-only trust workbench

**Rationale**: No new role tiers (Assumption 4). The sidebar already filters routes via `requiredRoles`; new routes follow suit.

---

### D-009: Playwright scenarios + MSW handlers in existing directories

**Decision**: 10 new Playwright `.spec.ts` files in `apps/web/e2e/` (one per user story). MSW handlers for new endpoints added to the existing `apps/web/mocks/` directory. No new test framework, no new mocking layer.

**Rationale**: Consistency with existing coverage. Feature 035 has 1 Playwright file per user story; 070 follows the same pattern.

---

### D-010: Responsive degradation — ≥ 768 px primary, stacked below

**Decision**: All new multi-column panels (governance chain, warm-pool profiles, reliability gauges) use Tailwind responsive utility classes (`md:grid-cols-3`, etc.) to stack into a single column below 768 px. Recharts charts use `<ResponsiveContainer>` with auto height. No mobile-specific components.

**Rationale**: Assumption 9 (chart responsiveness). The operator dashboard is primarily desktop; mobile support is best-effort.

---

### D-011: No new Zustand stores beyond `alert-store.ts`

**Decision**: All other new state is either server-owned (TanStack Query) or URL-param-owned (search filters, expiries-dashboard sort, trajectory step anchor, tab selection via `?tab=`). No new Zustand stores for goal filter, rubric editor, decommission wizard, etc.

**Rationale**: Feature 015 scaffold directs Zustand to minimal UI-ephemeral state. Server truth belongs in TanStack Query; URL state belongs in Next.js `useSearchParams`. Adding stores for every form creates sync bugs.

---

### D-012: Accessibility requirements (WCAG 2.1 AA)

**Decision**:
- Every color-coded chip (expiry, verdict severity, efficiency badge) carries a text label in addition to color.
- Drop zones expose `role="button"`, `tabIndex=0`, `onKeyDown` for Space/Enter to simulate click.
- `aria-live="polite"` on verdict feed and bell dropdown so new entries are announced to screen readers.
- All form inputs have explicit `<Label>` associations (shadcn `Label` primitive).
- Focus rings use Tailwind `focus-visible:ring-2` — never removed.

**Rationale**: SC-006 requires WCAG 2.1 AA. All decisions above are established patterns in features 015, 017, 026, 027 — just enforced consistently on new surfaces.

---

## Resolved Unknowns

None. All spec [NEEDS CLARIFICATION] markers were resolved during spec authoring (there were 0).

---

## Risks

1. **Bundle size growth**: 35 new components, 22 new hooks, 8 new type files. Mitigation: per-route dynamic imports via Next.js `loading.tsx` + code-splitting at the page boundary (already default in App Router). SC-007 regression check ensures marketplace/workspace first-load metrics stay within existing targets.
2. **WebSocket fan-out on operator dashboard**: 3 new channel subscriptions on one page (alerts, verdicts, warm-pool). Mitigation: WebSocketClient already handles multiple topics on one connection — no additional sockets opened.
3. **Legacy-agent edge cases**: Easy to miss a place that assumes FQN exists. Mitigation: a single helper `getDisplayFqn(agent)` returns either `namespace:local_name` or `"[Legacy agent]"` — all surfaces call it.
4. **Cross-feature event-name collisions**: New WebSocket channel names (`alerts`, `governance-verdicts`, `warm-pool`) must not collide with existing topic names. Mitigation: a quick grep confirms they are new.
