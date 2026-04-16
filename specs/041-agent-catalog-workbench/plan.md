# Implementation Plan: Agent Catalog and Creator Workbench

**Branch**: `041-agent-catalog-workbench` | **Date**: 2026-04-16 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/041-agent-catalog-workbench/spec.md`

## Summary

Frontend feature providing an agent catalog DataTable with search/filter, agent detail pages with tabbed lifecycle management (metadata editor, revision timeline, health score, publication workflow), drag-and-drop package upload with progress, and a 4-step AI composition wizard. All built on the existing Next.js 14+ App Router + shadcn/ui + TanStack Query stack with no new npm packages.

## Technical Context

**Language/Version**: TypeScript 5.x, React 18+, Next.js 14+ App Router
**Primary Dependencies**: shadcn/ui, TanStack Query v5, Zustand 5.x, React Hook Form 7.x + Zod 3.x, Monaco Editor 0.50+, date-fns 4.x, Lucide React, Tailwind CSS 3.4+
**Storage**: N/A (frontend only — data sourced from registry API 021, composition API 038, policy API 028)
**Testing**: Vitest + RTL (unit/component), Playwright + MSW (E2E)
**Target Platform**: Web browser (Chrome/Firefox/Safari/Edge), responsive (mobile + desktop)
**Project Type**: Frontend feature module within existing Next.js App Router application
**Performance Goals**: Catalog initial load <200ms (TanStack Query cache), infinite scroll pagination, upload progress real-time via XHR
**Constraints**: No new npm packages; dark mode via existing CSS custom properties; all UI via shadcn/ui only
**Scale/Scope**: 7 user stories, 18+ components, 13 hooks, 1 Zustand store, 7 component tests + 3 E2E specs

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Frontend feature — applicable constitution principles (Section 7: Frontend Conventions):

| Principle | Status | Notes |
|-----------|--------|-------|
| Function components only | PASS | All components use function component syntax |
| shadcn/ui for ALL UI primitives | PASS | No raw HTML UI elements; all from shadcn |
| Tailwind CSS for ALL styling | PASS | No custom CSS files; dark mode via CSS custom properties |
| TanStack Query v5 for server state | PASS | All API calls via useQuery/useInfiniteQuery/useMutation |
| Zustand for client state | PASS | Composition wizard uses Zustand store; no React.useState for cross-component state |
| No new npm packages without justification | PASS | All dependencies already in stack (Decision 7 in research.md) |
| Accessible (keyboard + screen reader) | PASS | shadcn/ui components are WAI-ARIA compliant by default |
| Responsive (mobile + desktop) | PASS | Tailwind responsive utilities throughout |

No violations — no Complexity Tracking needed.

## Project Structure

### Documentation (this feature)

```text
specs/041-agent-catalog-workbench/
├── plan.md                    # This file
├── research.md                # Phase 0: 7 decisions
├── data-model.md              # Phase 1: TypeScript types + Zod schema + Zustand store
├── quickstart.md              # Phase 1: project structure + routes + test commands
├── contracts/
│   ├── api-consumed.md        # Phase 1: API endpoints + TanStack Query hook map
│   └── component-contracts.md # Phase 1: component prop interfaces
└── tasks.md                   # Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code (repository root)

```text
apps/web/
├── app/(main)/
│   └── agent-management/
│       ├── page.tsx                           # US1: Agent catalog (DataTable + upload dialog)
│       ├── [fqn]/
│       │   ├── page.tsx                       # US2, US4, US5: Agent detail (tabbed)
│       │   └── revisions/
│       │       └── page.tsx                   # US6: Revision timeline + diff
│       └── wizard/
│           └── page.tsx                       # US7: AI composition wizard
│
├── components/features/agent-management/
│   ├── AgentDataTable.tsx                     # US1: DataTable with search/filter/pagination
│   ├── AgentMaturityBadge.tsx                 # US1: Maturity level badge (experimental/beta/production/deprecated)
│   ├── AgentStatusBadge.tsx                   # US1: Status indicator (draft/active/archived/pending_review)
│   ├── AgentDetailView.tsx                    # US2: Tabbed detail layout (?tab=overview|metadata|policies|certifications|evaluations|revisions)
│   ├── AgentHealthScoreGauge.tsx              # US2: Extends ScoreGauge with breakdown Tooltip
│   ├── AgentMetadataEditor.tsx                # US4: RHF+Zod metadata form
│   ├── FQNInput.tsx                           # US4: Namespace selector + local_name + live preview
│   ├── VisibilityPatternPanel.tsx             # US4: FQN patterns management (add/remove)
│   ├── RoleTypeSelector.tsx                   # US4: 7-option role type dropdown
│   ├── AgentUploadZone.tsx                    # US3: Drag-and-drop + XHR progress bar
│   ├── AgentPublicationPanel.tsx              # US5: Validate + publish panel
│   ├── PublicationConfirmDialog.tsx           # US5: AlertDialog with summary
│   ├── AgentRevisionTimeline.tsx              # US6: Revision list + checkbox multi-select
│   ├── RevisionDiffViewer.tsx                 # US6: Monaco MonacoDiffEditor (YAML, readOnly)
│   ├── CompositionWizard.tsx                  # US7: 4-step wizard container
│   ├── WizardStepDescribe.tsx                 # US7: Step 1 — description input
│   ├── WizardStepReviewBlueprint.tsx          # US7: Step 2 — blueprint review + confidence badges + Accordion
│   ├── WizardStepCustomize.tsx                # US7: Step 3 — customization form
│   └── WizardStepValidate.tsx                 # US7: Step 4 — validate + create
│
├── lib/
│   ├── hooks/
│   │   ├── use-agents.ts                      # useAgents (useInfiniteQuery), useAgent (useQuery)
│   │   ├── use-agent-mutations.ts             # useUpdateAgentMetadata, useValidateAgent, usePublishAgent, useRollbackRevision
│   │   ├── use-agent-upload.ts                # useUploadAgentPackage (XHR + progress events)
│   │   ├── use-agent-revisions.ts             # useAgentRevisions, useRevisionDiff
│   │   ├── use-agent-health.ts                # useAgentHealth
│   │   ├── use-agent-policies.ts              # useAgentPolicies
│   │   ├── use-namespaces.ts                  # useNamespaces
│   │   └── use-composition.ts                 # useGenerateBlueprint, useCreateFromBlueprint
│   └── stores/
│       └── use-composition-wizard-store.ts    # Zustand wizard state (step, description, blueprint, customizations, reset)
│
└── __tests__/
    ├── features/agent-management/
    │   ├── AgentDataTable.test.tsx
    │   ├── AgentMetadataEditor.test.tsx
    │   ├── AgentUploadZone.test.tsx
    │   ├── AgentPublicationPanel.test.tsx
    │   ├── AgentRevisionTimeline.test.tsx
    │   ├── RevisionDiffViewer.test.tsx
    │   └── CompositionWizard.test.tsx
    └── e2e/
        ├── agent-catalog.spec.ts
        ├── agent-metadata-edit.spec.ts
        └── agent-upload.spec.ts
```

**Structure Decision**: Single Next.js App Router frontend feature module. Routes under `app/(main)/agent-management/` following the established route group pattern. Feature components grouped under `components/features/agent-management/`. Hooks in `lib/hooks/` per platform convention. Zustand store in `lib/stores/`. Tests co-located under `__tests__/` by feature and type.

## Implementation Phases

### Phase 1: TypeScript Types and Hook Infrastructure

Create all TypeScript types, TanStack Query hooks, and the Zustand store. This provides the foundation for all components.

**Files**:
- `apps/web/lib/types/agent-management.ts` — all TypeScript interfaces from data-model.md
- `apps/web/lib/hooks/use-agents.ts` — `useAgents` (useInfiniteQuery with cursor pagination), `useAgent`
- `apps/web/lib/hooks/use-agent-mutations.ts` — `useUpdateAgentMetadata`, `useValidateAgent`, `usePublishAgent`, `useRollbackRevision`
- `apps/web/lib/hooks/use-agent-upload.ts` — `useUploadAgentPackage` (XHR with `upload.onprogress`, abort controller)
- `apps/web/lib/hooks/use-agent-revisions.ts` — `useAgentRevisions`, `useRevisionDiff`
- `apps/web/lib/hooks/use-agent-health.ts` — `useAgentHealth`
- `apps/web/lib/hooks/use-agent-policies.ts` — `useAgentPolicies`
- `apps/web/lib/hooks/use-namespaces.ts` — `useNamespaces`
- `apps/web/lib/hooks/use-composition.ts` — `useGenerateBlueprint`, `useCreateFromBlueprint`
- `apps/web/lib/stores/use-composition-wizard-store.ts` — Zustand store (step 1–4, not persisted, resets on navigate-away)

### Phase 2: Catalog Page — Agent DataTable (US1)

Agent list page with infinite scroll DataTable, search, and multi-filter.

**Files**:
- `apps/web/components/features/agent-management/AgentMaturityBadge.tsx` — shadcn Badge, colors per spec (experimental=gray, beta=blue, production=green, deprecated=red)
- `apps/web/components/features/agent-management/AgentStatusBadge.tsx` — shadcn Badge, status colors
- `apps/web/components/features/agent-management/AgentDataTable.tsx` — DataTable with SearchInput + FilterBar (namespace multi-select, maturity, status), infinite scroll "Load more", row click → router.push to `[fqn]` page
- `apps/web/app/(main)/agent-management/page.tsx` — catalog page, hosts AgentDataTable + upload dialog trigger

### Phase 3: Agent Detail Page — Overview + Health Score (US2)

Tabbed detail page with health gauge on the Overview tab.

**Files**:
- `apps/web/components/features/agent-management/AgentHealthScoreGauge.tsx` — extends `ScoreGauge` shared component, `showBreakdown` prop → shadcn Tooltip with component scores, color thresholds (<40=red, 40–70=yellow, >70=green)
- `apps/web/components/features/agent-management/AgentDetailView.tsx` — shadcn Tabs, URL query param routing `?tab=overview|metadata|policies|certifications|evaluations|revisions`, default overview tab
- `apps/web/app/(main)/agent-management/[fqn]/page.tsx` — agent detail page, decodes FQN, renders AgentDetailView

### Phase 4: Package Upload (US3)

Drag-and-drop upload zone with XHR progress.

**Files**:
- `apps/web/components/features/agent-management/AgentUploadZone.tsx` — native `dragenter`/`dragleave`/`drop` events, `<input type="file" accept=".tar.gz,.zip">`, client-side extension+MIME validation, `XMLHttpRequest.upload.onprogress` → shadcn Progress, cancel button (xhr.abort()), shadcn Alert for validation errors, calls `useUploadAgentPackage`

### Phase 5: Metadata Editor (US4)

RHF+Zod form with FQN input, visibility patterns, and role type selector.

**Files**:
- `apps/web/components/features/agent-management/FQNInput.tsx` — shadcn Select (namespace from `useNamespaces`) + shadcn Input (local_name with regex `/^[a-z0-9-]+$/`) + live FQN preview `{namespace}:{local_name}`
- `apps/web/components/features/agent-management/VisibilityPatternPanel.tsx` — add/remove FQN patterns, informational tooltip showing matched agents/tools
- `apps/web/components/features/agent-management/RoleTypeSelector.tsx` — shadcn Select (7 options), reveals shadcn Input for custom role name when "custom" selected
- `apps/web/components/features/agent-management/AgentMetadataEditor.tsx` — React Hook Form + Zod (`MetadataFormSchema`), pre-fills from `useAgent`, saves via `useUpdateAgentMetadata`, `If-Unmodified-Since` header for 412 conflict detection

### Phase 6: Publication Workflow (US5)

Validate and publish flow with confirmation dialog.

**Files**:
- `apps/web/components/features/agent-management/PublicationConfirmDialog.tsx` — shadcn AlertDialog, shows PublicationSummary (affected workspaces, status change, visibility impact)
- `apps/web/components/features/agent-management/AgentPublicationPanel.tsx` — "Validate" button → `useValidateAgent` → `ValidationResultDisplay` (check list with pass/fail), "Publish" button (disabled until validation passes) → opens PublicationConfirmDialog

### Phase 7: Revision Timeline + Diff (US6)

Revision list with checkbox multi-select and Monaco side-by-side diff.

**Files**:
- `apps/web/components/features/agent-management/RevisionDiffViewer.tsx` — Monaco `MonacoDiffEditor` (readOnly, language: "yaml"), uses `useRevisionDiff`
- `apps/web/components/features/agent-management/AgentRevisionTimeline.tsx` — uses `useAgentRevisions`, checkbox multi-select (exactly 2) → "Compare selected" → calls `onSelectForDiff`, "Rollback" per revision → shadcn AlertDialog confirmation → `useRollbackRevision`
- `apps/web/app/(main)/agent-management/[fqn]/revisions/page.tsx` — revision timeline page, hosts AgentRevisionTimeline + RevisionDiffViewer

### Phase 8: AI Composition Wizard (US7)

4-step wizard with Zustand state management and blueprint review.

**Files**:
- `apps/web/components/features/agent-management/WizardStepDescribe.tsx` — Step 1: shadcn Textarea for description, "Generate Blueprint" button → `useGenerateBlueprint`
- `apps/web/components/features/agent-management/WizardStepReviewBlueprint.tsx` — Step 2: shadcn Accordion per blueprint field, confidence badge, shadcn Alert (warning) for low confidence (<0.5) items, follow-up questions display
- `apps/web/components/features/agent-management/WizardStepCustomize.tsx` — Step 3: customization form for model_config, tool_selections, connector_suggestions, policy_recommendations
- `apps/web/components/features/agent-management/WizardStepValidate.tsx` — Step 4: trigger `useValidateAgent` (preview), "Create Agent" → `useCreateFromBlueprint`, success → navigate to detail page
- `apps/web/components/features/agent-management/CompositionWizard.tsx` — wizard container, reads `useCompositionWizardStore`, renders step 1–4, progress indicator, Back/Next/Cancel navigation
- `apps/web/app/(main)/agent-management/wizard/page.tsx` — wizard page, resets store on unmount

### Phase 9: Tests

**Component tests (Vitest + RTL + MSW)**:
- `apps/web/__tests__/features/agent-management/AgentDataTable.test.tsx` — render, search, filter, row click navigation
- `apps/web/__tests__/features/agent-management/AgentMetadataEditor.test.tsx` — form validation (Zod schema), save success/412 conflict
- `apps/web/__tests__/features/agent-management/AgentUploadZone.test.tsx` — drag-and-drop, file type validation, progress, cancel
- `apps/web/__tests__/features/agent-management/AgentPublicationPanel.test.tsx` — validate flow, publish disabled state, confirmation dialog
- `apps/web/__tests__/features/agent-management/AgentRevisionTimeline.test.tsx` — checkbox selection, diff trigger, rollback confirmation
- `apps/web/__tests__/features/agent-management/RevisionDiffViewer.test.tsx` — Monaco mock, diff content rendered
- `apps/web/__tests__/features/agent-management/CompositionWizard.test.tsx` — step navigation, blueprint rendering, wizard reset

**E2E tests (Playwright)**:
- `apps/web/__tests__/e2e/agent-catalog.spec.ts` — browse catalog, filter by maturity/status, search, navigate to detail
- `apps/web/__tests__/e2e/agent-metadata-edit.spec.ts` — edit metadata form, FQN preview, save + 412 conflict
- `apps/web/__tests__/e2e/agent-upload.spec.ts` — drag-and-drop upload, progress bar, success navigation

## Key Design Decisions

1. **FQN URL encoding**: `encodeURIComponent(fqn)` for the `[fqn]` dynamic segment; `decodeURIComponent(params.fqn)` in pages.
2. **Tab routing**: `?tab=overview` query param via `useSearchParams` + `router.replace` — same pattern as Admin Settings Panel (feature 027).
3. **Upload progress**: `XMLHttpRequest.upload.onprogress` is the only cross-browser way to get byte-level upload progress. `fetch` does not support upload progress events.
4. **Optimistic locking**: `PUT /metadata` includes `If-Unmodified-Since` header. 412 response shows inline `StaleDataAlert` (same component as feature 027).
5. **Monaco lazy import**: `MonacoDiffEditor` loaded via `dynamic(() => import(...), { ssr: false })` to avoid SSR issues with Monaco.
6. **Wizard store reset on unmount**: `useEffect(() => () => reset(), [reset])` in `wizard/page.tsx` prevents stale wizard state on return visits.

## Dependencies

- **FEAT-FE-001** (App scaffold / feature 015) — route groups, `lib/api.ts`, shared components (DataTable, ScoreGauge, EmptyState, SearchInput, FilterBar, ConfirmDialog), Zustand auth store
- **FEAT-INFRA-021** (Agent Registry) — all registry API endpoints
- **FEAT-INFRA-038** (AI Agent Composition) — composition blueprint API
- **FEAT-INFRA-028** (Policy Governance) — policy list API

## No New Packages

All implementation uses packages already in `apps/web/package.json`. See research.md Decision 7 for full list.
