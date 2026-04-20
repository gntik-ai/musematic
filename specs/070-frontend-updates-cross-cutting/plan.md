# Implementation Plan: Frontend Updates for All New Features

**Branch**: `070-frontend-updates-cross-cutting` | **Date**: 2026-04-20 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/070-frontend-updates-cross-cutting/spec.md`

## Summary

Additive, cross-cutting frontend changes that **extend** ten existing Next.js pages (agent authoring, marketplace, workspace view, alerts, governance settings, execution detail, evaluation suite editor, agent profile, trust workbench, operator dashboard) to expose new backend capabilities shipped in features 053–067: FQN identity, visibility patterns, workspace goals (GID), alert rules and bell, governance chain (Observer→Judge→Enforcer), execution trajectory + checkpoints + debate + ReAct cycles, LLM-as-Judge rubric + calibration, A2A/MCP management, third-party certifier management, warm-pool status, verdict feed, decommissioning wizard, and reliability gauges. **No new packages.** All work stays within the existing shadcn/ui + Tailwind + TanStack Query v5 + Zustand + React Hook Form + Zod + Recharts stack. One shared WebSocket client (`lib/ws.ts`) adds three new channel types: `alerts`, `governance-verdicts`, `warm-pool`. All new data hooks follow the `lib/hooks/use-api.ts` factory pattern.

## Technical Context

**Language/Version**: TypeScript 5.x (strict), React 18+
**Primary Dependencies**: Next.js 14+ App Router, shadcn/ui (ALL UI primitives), Tailwind CSS 3.4+, TanStack Query v5, Zustand 5.x, React Hook Form 7.x + Zod 3.x, Recharts 2.x, date-fns 4.x, Lucide React — all already in `apps/web/package.json`; **no new packages**
**Storage**: None (frontend only — all data sourced from backend REST/WebSocket APIs)
**Testing**: Vitest + React Testing Library (unit), Playwright (E2E), MSW (API mocking), existing `__tests__/` and `e2e/` directories
**Target Platform**: Web (modern Chromium, Firefox, Safari); responsive (≥ 768 px primary; degraded stacked layout below)
**Project Type**: Frontend-only feature in existing Next.js monolith (`apps/web/`)
**Performance Goals**: Marketplace FQN search p95 ≤ 500 ms after 300 ms debounce (SC-002); alert bell increments within 3 s of backend event (SC-003); trajectory panel first-100-steps ≤ 1 s, ≥ 50 FPS on 1,000 steps via virtualization (SC-004); rubric-weight validation feedback ≤ 100 ms (SC-005)
**Constraints**: **No new UI library**, no new charting lib (Recharts only), no new drag-and-drop lib (HTML5 native per feature 043), no new state manager. Preserve all existing pages byte-identical on their pre-feature paths — legacy agents render with a "Legacy agent" pill but do NOT break marketplace cards (Assumption 6, FR-003). All destructive actions use existing `ConfirmDialog` with typed-input confirmation (FR-038). All new WebSocket channels reuse existing `WebSocketClient` with exponential-backoff reconnect and 30 s polling fallback (FR-013).
**Scale/Scope**: 10 user stories, 39 functional requirements, ~35 new components, ~22 new hook files, 3 new WebSocket channel types, 3 new settings pages (`alerts`, `governance`, `visibility`), 9 modified pages, ~55 files total. One Playwright scenario per user story (10 total).

## Constitution Check

| Gate | Status | Notes |
|------|--------|-------|
| **Principle I** — Modular monolith | ✅ PASS | Frontend-only; no control-plane bounded-context changes |
| **Principle III** — Dedicated data stores | ✅ PASS | Frontend does not own data stores |
| **Principle IV** — No cross-boundary DB access | ✅ PASS | Reads exclusively via backend REST/WebSocket |
| **Principle VIII** — FQN addressing | ✅ PASS | This feature is **the** UI for FQN — surfaces `namespace:local_name` in forms, cards, searches, governance slots, verdict feeds |
| **Principle IX** — Zero-trust default visibility | ✅ PASS | Visibility patterns editable in agent form + workspace grants tab; legacy agents display "Legacy agent" pill until completed |
| **Principle X** — GID correlation | ✅ PASS | Workspace goal lifecycle surfaced in workspace header; goal-scoped message filter uses GID |
| **Principle XI** — Secrets never in LLM context | ✅ PASS | No LLM interactions introduced |
| **Principle XIII** — Attention/alerts | ✅ PASS | Alert settings page + notification bell realize this principle in the UI |
| **Brownfield Rule 1** — Never rewrite | ✅ PASS | All 9 existing pages **extended** additively; no file replaced wholesale |
| **Brownfield Rule 3** — Preserve existing tests | ✅ PASS | Existing Vitest + Playwright suites must continue to pass (SC-007) |
| **Brownfield Rule 4** — Use existing patterns | ✅ PASS | shadcn/ui + TanStack Query factory + Zustand + `ConfirmDialog` + `EmptyState` + `ConnectionStatusBanner` + `WebSocketClient` — all reused |
| **Brownfield Rule 5** — Reference existing files | ✅ PASS | Every modification cites exact file paths in the Source Code section |
| **Brownfield Rule 7** — Backward-compatible | ✅ PASS | No existing component signatures change; legacy agents render with tolerance (FR-003) |
| **Brownfield Rule 8** — Feature flags | ⚠️ N/A | Frontend changes don't alter backend defaults; feature flags for zero-trust visibility + alerts are backend concerns (features 053, 060) |
| **Reminder 24** — A2A external only | ✅ PASS | A2A management panel is read-mostly: view Agent Card, register MCP servers |

No constitution violations.

## Project Structure

### Documentation (this feature)

```text
specs/070-frontend-updates-cross-cutting/
├── plan.md                   ✅ This file
├── spec.md                   ✅ Feature specification
├── research.md               ✅ Phase 0 output
├── data-model.md             ✅ Phase 1 output (UI entity + hook contracts)
├── quickstart.md             ✅ Phase 1 output (10 user-story scenarios)
├── contracts/
│   ├── ui-components.md      ✅ Phase 1 output
│   └── websocket-channels.md ✅ Phase 1 output
└── checklists/
    └── requirements.md       ✅ Spec validation (all pass)
```

### Source Code (all in `apps/web/`)

```text
apps/web/
├── app/(main)/
│   ├── agents/
│   │   ├── create/page.tsx                      # MODIFY: extend AgentForm with FQN+purpose+role+visibility
│   │   └── [id]/
│   │       ├── page.tsx                         # MODIFY: agent profile with Contracts/A2A/MCP tabs
│   │       └── edit/page.tsx                    # MODIFY: same AgentForm as create
│   ├── marketplace/
│   │   ├── page.tsx                             # MODIFY: FQN search + card updates
│   │   └── [namespace]/[name]/page.tsx          # MODIFY: detail with certification status
│   ├── conversations/[id]/page.tsx              # MODIFY: goal header + goal-scoped filter + debug panel
│   ├── settings/
│   │   ├── alerts/page.tsx                      # NEW: alert settings
│   │   ├── governance/page.tsx                  # NEW: governance-chain editor
│   │   └── visibility/page.tsx                  # NEW: visibility-grants editor
│   ├── fleet/[id]/settings/page.tsx             # MODIFY: embed governance-chain editor
│   ├── operator/
│   │   ├── executions/[id]/page.tsx             # MODIFY: trajectory + checkpoints + debate + ReAct
│   │   └── page.tsx                             # MODIFY: warm-pool + verdict feed + decommission + gauges
│   ├── evaluation-testing/suites/[id]/page.tsx  # MODIFY: rubric editor + calibration box plots
│   └── trust-workbench/
│       └── page.tsx                             # MODIFY: add Certifiers + Expiries + Surveillance tabs
├── components/features/
│   ├── agents/
│   │   ├── agent-form-identity-fields.tsx       # NEW
│   │   ├── agent-form-visibility-editor.tsx     # NEW
│   │   ├── agent-profile-contracts-tab.tsx      # NEW
│   │   ├── agent-profile-a2a-tab.tsx            # NEW
│   │   └── agent-profile-mcp-tab.tsx            # NEW
│   ├── marketplace/
│   │   ├── agent-card-fqn.tsx                   # NEW (replaces internals of existing AgentCard)
│   │   └── marketplace-search-fqn.tsx           # MODIFY
│   ├── conversations/
│   │   ├── workspace-goal-header.tsx            # NEW
│   │   ├── goal-scoped-message-filter.tsx       # NEW
│   │   └── decision-rationale-panel.tsx         # NEW
│   ├── alerts/
│   │   ├── alert-settings-page.tsx              # NEW
│   │   ├── notification-bell.tsx                # NEW
│   │   └── per-interaction-mute-toggle.tsx     # NEW
│   ├── governance/
│   │   ├── governance-chain-editor.tsx          # NEW
│   │   └── visibility-grants-editor.tsx         # NEW
│   ├── execution/
│   │   ├── trajectory-viz.tsx                   # NEW
│   │   ├── checkpoint-list.tsx                  # NEW
│   │   ├── debate-transcript.tsx                # NEW
│   │   └── react-cycle-viewer.tsx               # NEW
│   ├── evaluation/
│   │   ├── rubric-editor.tsx                    # NEW
│   │   ├── calibration-boxplot.tsx              # NEW
│   │   └── trajectory-comparison-selector.tsx   # NEW
│   ├── trust/
│   │   ├── certifiers-tab.tsx                   # NEW
│   │   ├── certification-expiry-dashboard.tsx   # NEW
│   │   └── surveillance-panel.tsx               # NEW
│   └── operator/
│       ├── warm-pool-panel.tsx                  # NEW
│       ├── verdict-feed.tsx                     # NEW
│       ├── decommission-wizard.tsx              # NEW
│       └── reliability-gauges.tsx               # NEW
├── lib/
│   ├── ws.ts                                    # MODIFY: add 3 new channel types
│   ├── hooks/
│   │   ├── use-agent-identity-mutations.ts      # NEW
│   │   ├── use-goal-lifecycle.ts                # NEW
│   │   ├── use-alert-rules.ts                   # NEW
│   │   ├── use-alert-feed.ts                    # EXISTING — extend for WS subscription
│   │   ├── use-governance-chain.ts              # NEW
│   │   ├── use-visibility-grants.ts             # NEW
│   │   ├── use-execution-trajectory.ts          # NEW
│   │   ├── use-execution-checkpoints.ts         # NEW
│   │   ├── use-debate-transcript.ts             # NEW
│   │   ├── use-react-cycles.ts                  # NEW
│   │   ├── use-rubric-editor.ts                 # NEW
│   │   ├── use-calibration-scores.ts            # NEW
│   │   ├── use-agent-contracts.ts               # NEW
│   │   ├── use-a2a-agent-card.ts                # NEW
│   │   ├── use-mcp-servers.ts                   # NEW
│   │   ├── use-third-party-certifiers.ts        # NEW
│   │   ├── use-certification-expiries.ts        # NEW
│   │   ├── use-surveillance-signals.ts          # NEW
│   │   ├── use-warm-pool-status.ts              # NEW
│   │   ├── use-verdict-feed.ts                  # NEW
│   │   ├── use-decommission-wizard.ts           # NEW
│   │   └── use-reliability-gauges.ts            # NEW
│   └── validators/
│       ├── fqn-pattern.ts                       # NEW: FQN regex + audience preview
│       └── rubric-weights.ts                    # NEW: sum=1.0 validator
├── types/
│   ├── fqn.ts                                   # NEW
│   ├── goal.ts                                  # NEW
│   ├── alerts.ts                                # NEW
│   ├── governance.ts                            # NEW
│   ├── trajectory.ts                            # NEW
│   ├── evaluation.ts                            # NEW
│   ├── contracts.ts                             # NEW
│   └── operator.ts                              # NEW
├── store/
│   └── alert-store.ts                           # NEW: unread count + dropdown open
└── e2e/                                         # 10 new Playwright scenarios (one per user story)
    ├── agent-fqn-authoring.spec.ts              # US1
    ├── marketplace-fqn-discovery.spec.ts        # US2
    ├── workspace-goal-lifecycle.spec.ts         # US3
    ├── alert-settings-and-bell.spec.ts          # US4
    ├── governance-chain-editor.spec.ts          # US5
    ├── execution-trajectory.spec.ts             # US6
    ├── evaluation-rubric-editor.spec.ts         # US7
    ├── agent-profile-a2a-mcp.spec.ts            # US8
    ├── trust-workbench-certifiers.spec.ts       # US9
    └── operator-dashboard-expansions.spec.ts    # US10
```

## Complexity Tracking

No constitution violations.

**Highest-risk areas**:

1. **Notification bell real-time correctness under WebSocket churn (US4)**: Bell unread-count MUST stay accurate across socket disconnects. Mitigation: reconcile on reconnect — fetch server-side unread count and replace optimistic state. Playwright scenario asserts count matches server truth after a forced drop.
2. **Trajectory virtualization at scale (US6)**: 1,000+ step executions must render at ≥ 50 FPS (SC-004). Reuse existing TanStack Virtual primitive used by `DataTable` — no `react-window`.
3. **Governance-chain drag-and-drop (US5)**: HTML5 native DnD (per feature 043 precedent). Keyboard-only fallback required for accessibility (SC-006).
4. **Legacy-agent tolerance in marketplace (US2)**: Cards render with `namespace=null`/`local_name=null`; FQN search segregates legacy agents into a "Legacy (uncategorized)" bucket rather than hiding them.
5. **Rubric-weights real-time validation (US7)**: Sum recomputation across 10+ dimensions on every keystroke can thrash renders. Mitigation: 50 ms debounce + `React.memo` weight rows; 100 ms feedback target (SC-005).

## Phase 0: Research

**Status**: ✅ Complete — see [research.md](research.md)

Key decisions:

- **D-001**: No new packages — extend existing shadcn/ui + Tailwind + TanStack Query + Recharts stack only.
- **D-002**: HTML5 native drag-and-drop for governance-chain editor (feature 043 precedent).
- **D-003**: Virtualize the trajectory timeline using existing TanStack Virtual primitive used by `DataTable`.
- **D-004**: Reuse existing `WebSocketClient` (`lib/ws.ts`) — add 3 new channel types; no new socket client.
- **D-005**: Alert store: Zustand `alert-store.ts` holds unread count + dropdown state; list hydration via TanStack Query `useInfiniteQuery` with WS-driven cache invalidation.
- **D-006**: Legacy-agent tolerance everywhere FQN is expected: empty inputs + "Complete identity" prompt; cards render with "Legacy agent" pill; FQN search segregates legacy.
- **D-007**: Decommission wizard reuses existing `ConfirmDialog` extended with a `requireTypedConfirmation` prop (extension, not replacement).
- **D-008**: RBAC gates reuse existing `requiredRoles: RoleType[]` pattern — no new role hierarchy.
- **D-009**: Playwright scenarios live in `apps/web/e2e/` next to existing ones; MSW handlers added to `mocks/`.
- **D-010**: Responsive degradation: below 768 px multi-column panels stack single-column; Recharts responsive containers for all charts.
- **D-011**: No new Zustand stores beyond `alert-store.ts`; all other state is server-owned via TanStack Query or URL params.
- **D-012**: Accessibility: color-coded chips always carry text labels; drop zones expose `role="button"`, `tabIndex=0`, keyboard handlers; `aria-live` on verdict feed and bell dropdown (SC-006).

## Phase 1: Design & Contracts

**Status**: ✅ Complete

- [data-model.md](data-model.md) — 19 UI-level entity shapes; hook contracts; URL-param schemas; WS subscription envelopes.
- [contracts/ui-components.md](contracts/ui-components.md) — New component prop signatures, state-ownership boundaries, RBAC per component.
- [contracts/websocket-channels.md](contracts/websocket-channels.md) — 3 new channel types (`alerts`, `governance-verdicts`, `warm-pool`) with message envelope shapes.
- [quickstart.md](quickstart.md) — 10 acceptance scenarios (Q1–Q10), one per user story, with click paths and DOM assertions.
