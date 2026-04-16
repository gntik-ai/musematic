# Tasks: Agent Catalog and Creator Workbench

**Input**: Design documents from `/specs/041-agent-catalog-workbench/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓, quickstart.md ✓

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: User story this task belongs to (US1–US7)

---

## Phase 1: Setup

**Purpose**: TypeScript type definitions and Zustand wizard store — shared foundation for all components and hooks.

- [X] T001 Create all TypeScript type definitions (`AgentCatalogEntry`, `AgentDetail`, `AgentHealthScore`, `AgentRevision`, `RevisionDiff`, `ValidationResult`, `PublicationSummary`, `CompositionBlueprint`, `BlueprintItem<T>`, `VisibilityPattern`, `AgentMaturity`, `AgentStatus`, `AgentRoleType`, `AgentCatalogFilters`) in `apps/web/lib/types/agent-management.ts`
- [X] T002 Create Zustand composition wizard store (`CompositionWizardState`: step 1–4, description, blueprint, customizations, validation_result, is_loading, error — session-only, NOT persisted, reset() clears all state) in `apps/web/lib/stores/use-composition-wizard-store.ts`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: All TanStack Query hooks that power the feature. Every user story depends on at least one of these hooks.

**⚠️ CRITICAL**: No user story component can be built until the relevant hooks in this phase are complete.

- [X] T003 [P] Create `useAgents` (useInfiniteQuery with cursor pagination, `AgentCatalogFilters` params, invalidation on workspace change) and `useAgent(fqn)` (useQuery) in `apps/web/lib/hooks/use-agents.ts`
- [X] T004 [P] Create `useUpdateAgentMetadata` (PUT with `If-Unmodified-Since` header, 412 → throws conflict error), `useValidateAgent`, `usePublishAgent`, `useRollbackRevision` mutations in `apps/web/lib/hooks/use-agent-mutations.ts`
- [X] T005 [P] Create `useUploadAgentPackage` (XMLHttpRequest with `upload.onprogress` → exposes `progress: number`, `abort()` cancel, 422 → returns `validation_errors`) in `apps/web/lib/hooks/use-agent-upload.ts`
- [X] T006 [P] Create `useAgentRevisions(fqn)` (useQuery) and `useRevisionDiff(fqn, base, compare)` (useQuery, skips when base/compare null) in `apps/web/lib/hooks/use-agent-revisions.ts`
- [X] T007 [P] Create `useAgentHealth(fqn)` (useQuery → `AgentHealthScore`) in `apps/web/lib/hooks/use-agent-health.ts`
- [X] T008 [P] Create `useAgentPolicies(fqn)` (useQuery → policy list) in `apps/web/lib/hooks/use-agent-policies.ts`
- [X] T009 [P] Create `useNamespaces(workspace_id)` (useQuery → `{namespace, agent_count}[]`) in `apps/web/lib/hooks/use-namespaces.ts`
- [X] T010 [P] Create `useGenerateBlueprint` (useMutation → POST `/composition/agent-blueprint`) and `useCreateFromBlueprint` (useMutation → POST `/registry/agents`) in `apps/web/lib/hooks/use-composition.ts`

**Checkpoint**: All hooks ready — user story phases can now begin.

---

## Phase 3: User Story 1 — Browse and Search Agent Catalog (Priority: P1) 🎯 MVP

**Goal**: Searchable, filterable, sortable data table of all agents with maturity and status badges. Navigation entry point to agent detail.

**Independent Test**: Open `/agent-management`. Confirm table renders with columns: name, namespace, maturity badge (color-coded), status, revision count, last updated. Type "kyc" in search — confirm filtering within 300ms. Filter by maturity "production" — confirm only matching rows shown. Sort by name — confirm ordering. Click a row — confirm navigation to `/agent-management/{fqn}`.

- [X] T011 [P] [US1] Create `AgentMaturityBadge` (shadcn `Badge`: experimental=gray, beta=blue, production=green, deprecated=red; `size="sm"|"md"` prop) in `apps/web/components/features/agent-management/AgentMaturityBadge.tsx`
- [X] T012 [P] [US1] Create `AgentStatusBadge` (shadcn `Badge` with status color mapping: draft=slate, active=green, archived=gray, pending_review=yellow) in `apps/web/components/features/agent-management/AgentStatusBadge.tsx`
- [X] T013 [US1] Create `AgentDataTable` (shared `DataTable` component with columns: name+namespace, `AgentMaturityBadge`, `AgentStatusBadge`, revision count, last updated via date-fns; `SearchInput` with 300ms debounce; `FilterBar` for maturity/status/namespace multi-select; infinite scroll "Load more" via `useAgents`; row click → `router.push(\`/agent-management/\${encodeURIComponent(fqn)}\`)`) in `apps/web/components/features/agent-management/AgentDataTable.tsx`
- [X] T014 [US1] Create agent catalog page (renders `AgentDataTable`, `workspace_id` from auth store, upload dialog trigger button) in `apps/web/app/(main)/agent-management/page.tsx`

**Checkpoint**: User Story 1 fully functional — browse, search, filter, navigate.

---

## Phase 4: User Story 2 — View Agent Detail and Health Score (Priority: P1)

**Goal**: Tabbed detail page with metadata overview, composite health score gauge, and section placeholders for policies, certifications, evaluations.

**Independent Test**: Navigate to `/agent-management/{fqn}`. Confirm metadata section (FQN, description, tags, category, maturity, status, revision number). Confirm health score gauge renders with score 0–100 and color coding. Confirm tabs: overview, metadata, policies, certifications, evaluations, revisions. Confirm URL `?tab=` routing works on refresh.

- [X] T015 [P] [US2] Create `AgentHealthScoreGauge` (extends shared `ScoreGauge` component, `showBreakdown` prop → shadcn `Tooltip` listing component scores on hover, `size="sm"|"lg"`, color thresholds: <40=destructive, 40–70=warning, >70=success, uses `useAgentHealth(fqn)`) in `apps/web/components/features/agent-management/AgentHealthScoreGauge.tsx`
- [X] T016 [US2] Create `AgentDetailView` (shadcn `Tabs` with URL query param routing via `useSearchParams` + `router.replace`: tabs = overview | metadata | policies | certifications | evaluations | revisions; overview tab shows `AgentHealthScoreGauge` + metadata summary; other tab slots are stubs wired to later phases) in `apps/web/components/features/agent-management/AgentDetailView.tsx`
- [X] T017 [US2] Create agent detail page (`decodeURIComponent(params.fqn)`, loads `useAgent`, passes to `AgentDetailView`, 404 redirect on not-found) in `apps/web/app/(main)/agent-management/[fqn]/page.tsx`

**Checkpoint**: User Story 2 functional — detail page with health gauge and tab navigation.

---

## Phase 5: User Story 3 — Upload Agent Package (Priority: P2)

**Goal**: Drag-and-drop and file picker upload of `.tar.gz`/`.zip` packages with real-time XHR progress, cancel support, and validation error display.

**Independent Test**: Drag a `.tar.gz` onto the upload zone. Confirm progress bar appears and advances. Confirm success notification with link to new draft agent. Drag an unsupported file — confirm inline error "Unsupported file type. Only .tar.gz and .zip files are accepted." Upload and cancel mid-way — confirm upload aborts.

- [X] T018 [US3] Create `AgentUploadZone` (native `dragenter`/`dragleave`/`dragover`/`drop` on a styled `<div>`, drag active border highlight, `<input type="file" accept=".tar.gz,.zip">` hidden file picker, client-side validation: extension + MIME type before XHR, `useUploadAgentPackage` for XHR → shadcn `Progress` bar, cancel button calls `abort()`, shadcn `Alert` for validation errors array from 422 response, success → `onUploadComplete(fqn)` callback) in `apps/web/components/features/agent-management/AgentUploadZone.tsx`

**Checkpoint**: User Story 3 functional — upload with progress, cancel, and validation feedback.

---

## Phase 6: User Story 4 — Edit Agent Metadata (Priority: P2)

**Goal**: React Hook Form + Zod metadata editor with FQN input, live preview, role type selector, visibility pattern management, and 412 conflict detection on save.

**Independent Test**: Open metadata editor. Clear purpose — confirm immediate Zod error "Purpose is required (minimum 20 characters)". Change namespace — confirm FQN preview updates. Select "custom" role type — confirm custom role input appears. Add pattern "finance-ops:*" — confirm it appears in list. Save valid changes — confirm success toast. Simulate 412 — confirm `StaleDataAlert` appears.

- [X] T019 [P] [US4] Create `FQNInput` (shadcn `Select` populated by `useNamespaces` for namespace, shadcn `Input` for local_name with regex `/^[a-z0-9-]+$/` inline validation, live preview renders `{namespace}:{local_name}`, `disabled` prop) in `apps/web/components/features/agent-management/FQNInput.tsx`
- [X] T020 [P] [US4] Create `RoleTypeSelector` (shadcn `Select` with 7 options: executor/planner/orchestrator/observer/judge/enforcer/custom, when "custom" selected: reveals shadcn `Input` for `customRole` string, `disabled` prop) in `apps/web/components/features/agent-management/RoleTypeSelector.tsx`
- [X] T021 [P] [US4] Create `VisibilityPatternPanel` (add/remove `VisibilityPattern[]`, shadcn `Input` for new pattern, shadcn `Tooltip` informational preview per pattern, `disabled` prop) in `apps/web/components/features/agent-management/VisibilityPatternPanel.tsx`
- [X] T022 [US4] Create `AgentMetadataEditor` (React Hook Form + Zod `MetadataFormSchema`, pre-fills from `useAgent(fqn)`, `If-Unmodified-Since` header tracked from `useAgent` response, `useUpdateAgentMetadata` on submit, 412 error → `StaleDataAlert` inline, `onSaved()` callback, hosts `FQNInput` + `VisibilityPatternPanel` + `RoleTypeSelector`) in `apps/web/components/features/agent-management/AgentMetadataEditor.tsx`

**Checkpoint**: User Story 4 functional — full metadata editing with FQN, visibility patterns, role type, and conflict detection.

---

## Phase 7: User Story 5 — Publish Agent Through Lifecycle Workflow (Priority: P2)

**Goal**: Validate-then-publish workflow with per-check result display, publication confirmation dialog summarizing visibility impact.

**Independent Test**: Open draft agent. Click "Validate" — confirm validation runs and check list renders (pass/fail per item). With all passing, confirm "Publish" button activates. Click "Publish" — confirm `AlertDialog` shows FQN, affected workspaces, status change. Confirm → confirm agent transitions to "active" status.

- [X] T023 [P] [US5] Create `PublicationConfirmDialog` (shadcn `AlertDialog`, receives `PublicationSummary | null`: shows FQN, `affected_workspaces` list, `previous_status` → `new_status` change, `published_at` preview, `onConfirm` / `onCancel` callbacks) in `apps/web/components/features/agent-management/PublicationConfirmDialog.tsx`
- [X] T024 [US5] Create `AgentPublicationPanel` (Validate button → `useValidateAgent` → renders `ValidationCheck[]` list with pass/fail icons per check; Publish button disabled until `ValidationResult.passed === true` → opens `PublicationConfirmDialog`; confirm → `usePublishAgent` → `onPublished()` callback; shows error toast on 409 conflict) in `apps/web/components/features/agent-management/AgentPublicationPanel.tsx`

**Checkpoint**: User Story 5 functional — full draft → validate → publish lifecycle.

---

## Phase 8: User Story 6 — View and Compare Revisions (Priority: P3)

**Goal**: Revision timeline with checkbox multi-select for diff, side-by-side Monaco diff viewer, and rollback with confirmation.

**Independent Test**: Open `/agent-management/{fqn}/revisions`. Confirm timeline shows all revisions with metadata. Check two revisions — confirm "Compare selected" button activates. Confirm Monaco diff viewer renders with YAML content. Click "Rollback to revision 1" — confirm AlertDialog, confirm → confirm new revision created.

- [X] T025 [P] [US6] Create `RevisionDiffViewer` (`dynamic(() => import('...MonacoDiffEditor'), { ssr: false })`, readOnly, `language: 'yaml'`, `original` = `base_content`, `modified` = `compare_content` from `useRevisionDiff(fqn, baseRevision, compareRevision)`, loading skeleton while Monaco loads) in `apps/web/components/features/agent-management/RevisionDiffViewer.tsx`
- [X] T026 [US6] Create `AgentRevisionTimeline` (uses `useAgentRevisions(fqn)`, renders revision list with number/timestamp via date-fns/author/status/change_summary, checkbox multi-select limited to exactly 2 → "Compare selected" button → `onSelectForDiff([a, b])`, "Rollback" button per revision → shadcn `AlertDialog` confirmation → `useRollbackRevision` → `onRollback(revisionNumber)`) in `apps/web/components/features/agent-management/AgentRevisionTimeline.tsx`
- [X] T027 [US6] Create agent revisions page (hosts `AgentRevisionTimeline` + `RevisionDiffViewer`, manages `[baseRevision, compareRevision]` state, passes to diff viewer on "Compare selected") in `apps/web/app/(main)/agent-management/[fqn]/revisions/page.tsx`

**Checkpoint**: User Story 6 functional — revision timeline, diff comparison, and rollback.

---

## Phase 9: User Story 7 — Create Agent via AI Composition Wizard (Priority: P3)

**Goal**: 4-step wizard (describe → review blueprint → customize → validate + create) backed by Zustand store, with AI reasoning visible per blueprint item and confidence-based warnings.

**Independent Test**: Open `/agent-management/wizard`. Enter description. Confirm blueprint generated with Accordion per field showing reasoning + confidence badge. Modify one tool. Confirm warning on impactful change. Complete step 4 — confirm draft agent appears in catalog.

- [X] T028 [P] [US7] Create `WizardStepDescribe` (shadcn `Textarea` for description bound to `store.setDescription`, "Generate Blueprint" button → `useGenerateBlueprint` → `store.setBlueprint`, loading spinner during generation, 503 error → inline error with "Retry" button + link to upload path) in `apps/web/components/features/agent-management/WizardStepDescribe.tsx`
- [X] T029 [P] [US7] Create `WizardStepReviewBlueprint` (receives `CompositionBlueprint`, shadcn `Accordion` per blueprint field showing `value`/`reasoning`/`confidence`, shadcn `Badge` for confidence level (≥0.5 blue, <0.5 yellow), shadcn `Alert` warning variant for low-confidence items, `follow_up_questions` list) in `apps/web/components/features/agent-management/WizardStepReviewBlueprint.tsx`
- [X] T030 [P] [US7] Create `WizardStepCustomize` (form fields for `model_config`, `tool_selections`, `connector_suggestions`, `policy_recommendations` bound to `store.applyCustomization`, shadcn `Alert` warning when change to tool_selections diverges from blueprint's purpose-critical tools) in `apps/web/components/features/agent-management/WizardStepCustomize.tsx`
- [X] T031 [P] [US7] Create `WizardStepValidate` (triggers `useValidateAgent` on mount showing validation preview, `ValidationCheck[]` list, "Create Agent" button enabled when passed → `useCreateFromBlueprint({ blueprint_id, workspace_id, metadata })` → `router.push` to detail page on 201) in `apps/web/components/features/agent-management/WizardStepValidate.tsx`
- [X] T032 [US7] Create `CompositionWizard` container (reads `useCompositionWizardStore`, renders step 1–4 via switch on `store.step`, progress indicator showing current step, Back button → `store.setStep(step - 1)`, Next button → `store.setStep(step + 1)`, Cancel button → `store.reset()` + `router.push('/agent-management')`) in `apps/web/components/features/agent-management/CompositionWizard.tsx`
- [X] T033 [US7] Create AI composition wizard page (renders `CompositionWizard`, `useEffect(() => () => reset(), [reset])` cleanup resets store on unmount) in `apps/web/app/(main)/agent-management/wizard/page.tsx`

**Checkpoint**: User Story 7 functional — full AI composition wizard from description to draft agent creation.

---

## Phase 10: Tests

**Purpose**: Component tests (Vitest + RTL + MSW) and E2E tests (Playwright) covering all user stories per plan.md Phase 9.

- [X] T034 [P] Write `AgentDataTable` component test (MSW mock for GET /registry/agents, renders table columns, search input triggers debounced filter, maturity/status filter updates query, row click calls `router.push`) in `apps/web/__tests__/features/agent-management/AgentDataTable.test.tsx`
- [X] T035 [P] Write `AgentMetadataEditor` component test (Zod schema validation: clears purpose → error, local_name regex invalid → error; FQN preview updates on namespace change; save success → `onSaved` called; 412 response → StaleDataAlert renders) in `apps/web/__tests__/features/agent-management/AgentMetadataEditor.test.tsx`
- [X] T036 [P] Write `AgentUploadZone` component test (invalid file type → inline error, valid `.tar.gz` → XHR mock → progress 0→50→100, cancel during upload → abort called, 422 response → validation errors displayed) in `apps/web/__tests__/features/agent-management/AgentUploadZone.test.tsx`
- [X] T037 [P] Write `AgentPublicationPanel` component test (validate → renders check list with pass/fail, Publish button disabled before validation, enabled after pass, confirm dialog opens on Publish click, 409 response → error toast) in `apps/web/__tests__/features/agent-management/AgentPublicationPanel.test.tsx`
- [X] T038 [P] Write `AgentRevisionTimeline` component test (renders revision list, checkbox select exactly 2 → Compare button activates, >2 checkboxes → third disabled, rollback → AlertDialog opens, confirms → mutation called) in `apps/web/__tests__/features/agent-management/AgentRevisionTimeline.test.tsx`
- [X] T039 [P] Write `RevisionDiffViewer` component test (Monaco mock via `vi.mock`, loading skeleton while dynamic import pending, diff renders with `original`/`modified` content from MSW mock) in `apps/web/__tests__/features/agent-management/RevisionDiffViewer.test.tsx`
- [X] T040 [P] Write `CompositionWizard` component test (initial renders step 1, Next advances to step 2, Back regresses, Cancel resets store to step 1, low-confidence blueprint items show Alert warning in step 2) in `apps/web/__tests__/features/agent-management/CompositionWizard.test.tsx`
- [X] T041 [P] Write agent-catalog E2E test (browse catalog page renders table, search filters results, filter by maturity, click row navigates to detail URL) in `apps/web/e2e/agent-catalog.spec.ts`
- [X] T042 [P] Write agent-metadata-edit E2E test (open metadata tab, change description, clear purpose → error visible, change namespace → FQN preview updates, save → success toast, simulate 412 → StaleDataAlert) in `apps/web/e2e/agent-metadata-edit.spec.ts`
- [X] T043 [P] Write agent-upload E2E test (drag `.tar.gz` file → progress bar appears → success notification, invalid file type → error message, cancel mid-upload → abort) in `apps/web/e2e/agent-upload.spec.ts`

---

## Phase 11: Polish & Cross-Cutting Concerns

**Purpose**: Accessibility, dark mode correctness, responsive layout, and integration validation.

- [X] T044 Add ARIA attributes and keyboard navigation across all agent-management components (aria-label on icon buttons, role on status indicators, keyboard-accessible dropdowns, focus management in dialogs)
- [X] T045 Verify dark mode rendering for all agent-management pages (CSS custom property tokens resolve correctly, no hardcoded colors, maturity/status badge colors contrast pass in dark mode)
- [X] T046 Verify responsive layout at 768px breakpoint for all agent-management pages (catalog table scrollable, metadata editor stacks vertically, wizard readable, diff viewer usable on tablet)
- [X] T047 Run quickstart.md validation (start dev server, navigate `/agent-management`, `/agent-management/{fqn}`, `/agent-management/{fqn}/revisions`, `/agent-management/wizard` — verify no console errors and all routes render)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (types must exist before hooks) — **BLOCKS all user story phases**
- **US1 (Phase 3)**: Requires T003 (useAgents, useAgent) from Phase 2
- **US2 (Phase 4)**: Requires T007 (useAgentHealth) + US1 detail page route exists
- **US3 (Phase 5)**: Requires T005 (useUploadAgentPackage) from Phase 2
- **US4 (Phase 6)**: Requires T004 (useUpdateAgentMetadata) + T009 (useNamespaces) + US2 detail page
- **US5 (Phase 7)**: Requires T004 (useValidateAgent, usePublishAgent) + US4 (metadata editor wired in detail tabs)
- **US6 (Phase 8)**: Requires T006 (useAgentRevisions, useRevisionDiff) + T004 (useRollbackRevision)
- **US7 (Phase 9)**: Requires T002 (wizard store) + T010 (useGenerateBlueprint, useCreateFromBlueprint) + T004 (useValidateAgent)
- **Tests (Phase 10)**: Depends on all US phases complete
- **Polish (Phase 11)**: Depends on all US phases and Tests complete

### User Story Dependencies

- **US1 (P1)**: Independent after Phase 2 — ✅ MVP target
- **US2 (P1)**: Independent after Phase 2 — can develop in parallel with US1
- **US3 (P2)**: Independent after Phase 2 — no dependencies on US1/US2 components
- **US4 (P2)**: Depends on US2 (detail page tabs) for integration, independently buildable
- **US5 (P2)**: Depends on US4 (validation before publish) for UX flow, independently buildable
- **US6 (P3)**: Independent after Phase 2 — separate page route
- **US7 (P3)**: Independent after Phase 1+2 — separate page route

### Parallel Opportunities

- **Phase 1**: T001, T002 can run in parallel
- **Phase 2**: T003–T010 all parallel (separate files)
- **Phase 3**: T011, T012 parallel; T013 after T011+T012; T014 after T013
- **Phase 4**: T015 parallel with T016; T017 after T016
- **Phase 6**: T019, T020, T021 parallel; T022 after T019+T020+T021
- **Phase 7**: T023 parallel with T024; T024 after T023
- **Phase 8**: T025 parallel with T026; T027 after T025+T026
- **Phase 9**: T028, T029, T030, T031 parallel; T032 after T028–T031; T033 after T032
- **Phase 10**: T034–T043 all parallel (separate test files)
- **Phase 11**: T044, T045, T046 parallel; T047 after all

---

## Parallel Example: Phase 2 (Hooks — all independent)

```bash
# Launch all 8 hook implementations simultaneously:
Task: "Create use-agents.ts with useAgents (infinite) + useAgent"
Task: "Create use-agent-mutations.ts with 4 mutations"
Task: "Create use-agent-upload.ts with XHR progress"
Task: "Create use-agent-revisions.ts with revisions + diff"
Task: "Create use-agent-health.ts"
Task: "Create use-agent-policies.ts"
Task: "Create use-namespaces.ts"
Task: "Create use-composition.ts with generate + create"
```

## Parallel Example: Phase 10 (Tests — all independent)

```bash
# Launch all test files simultaneously:
Task: "AgentDataTable.test.tsx"
Task: "AgentMetadataEditor.test.tsx"
Task: "AgentUploadZone.test.tsx"
Task: "AgentPublicationPanel.test.tsx"
Task: "AgentRevisionTimeline.test.tsx"
Task: "RevisionDiffViewer.test.tsx"
Task: "CompositionWizard.test.tsx"
Task: "agent-catalog.spec.ts"
Task: "agent-metadata-edit.spec.ts"
Task: "agent-upload.spec.ts"
```

---

## Implementation Strategy

### MVP First (US1 + US2 — P1 stories only)

1. Complete Phase 1: Setup (T001–T002)
2. Complete Phase 2: Foundational hooks (T003–T010)
3. Complete Phase 3: US1 Catalog (T011–T014)
4. **STOP and VALIDATE**: Browse catalog, search, filter, navigate to detail
5. Complete Phase 4: US2 Detail + Health (T015–T017)
6. **STOP and VALIDATE**: Full agent detail page with health gauge and tabs

### Incremental Delivery

1. Setup + Foundational → hooks ready for all stories
2. US1 (P1) → searchable catalog with navigation
3. US2 (P1) → agent detail hub with health gauge
4. US3 (P2) → upload packages
5. US4 (P2) → edit metadata
6. US5 (P2) → publish agents
7. US6 (P3) → revision history and diff
8. US7 (P3) → AI composition wizard
9. Tests → component + E2E coverage
10. Polish → accessibility, dark mode, responsive

### Parallel Team Strategy

With multiple developers (after Phase 1+2 complete):
- Developer A: US1 → US3 (catalog → upload)
- Developer B: US2 → US4 → US5 (detail → metadata → publish)
- Developer C: US6 → US7 (revisions → wizard)

---

## Notes

- [P] = different files, no blocking dependencies on incomplete tasks
- [USN] maps task to user story from spec.md for traceability
- Monaco MonacoDiffEditor MUST be loaded via `dynamic(..., { ssr: false })` (T025)
- XHR upload (T005, T018) — cannot use `fetch` for progress events
- FQN in URL must be `encodeURIComponent`/`decodeURIComponent` (colon is not URL-safe in path segments)
- `?tab=` routing matches Admin Settings Panel pattern (feature 027) — same `useSearchParams` + `router.replace` pattern
- Zustand wizard store reset in `useEffect` cleanup (T033) — prevents stale state on wizard re-entry
- If-Unmodified-Since / 412 (T004, T022) — matches Admin Settings Panel `StaleDataAlert` pattern (feature 027)
