# Tasks: Trust and Certification Workbench

**Input**: Design documents from `/specs/043-trust-certification-workbench/`  
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US5)

---

## Phase 1: Setup

**Purpose**: TypeScript types, route stubs, Zustand store, sidebar entry

- [X] T001 Create `apps/web/lib/types/trust-workbench.ts` with all TypeScript types: `CertificationStatus`, `CertificationQueueStatus`, `EvidenceType`, `EvidenceResult`, `TrustTierName`, `TrustDimension`, `TRUST_DIMENSION_LABELS`, `TrustRadarChartDataPoint`, `CertificationListEntry`, `CertificationDetail`, `CertificationStatusEvent`, `EvidenceItem`, `TrustDimensionScore`, `TrustDimensionComponent`, `TrustRadarProfile`, `PolicySummary`, `PolicyBinding`, `PolicyRuleProvenance`, `PolicyConflict`, `PrivacyImpactAnalysis`, `PrivacyDataCategory`, `PrivacyConcern`, `ReviewDecisionFormValues`, `CertificationQueueFilters`
- [X] T002 Create route stub `apps/web/app/(main)/trust-workbench/page.tsx` — renders skeleton placeholder
- [X] T003 Create route stub `apps/web/app/(main)/trust-workbench/[certificationId]/page.tsx` — renders skeleton placeholder
- [X] T004 Create `apps/web/lib/stores/use-policy-attachment-store.ts` — Zustand store (not persisted): `isDragging`, `draggedPolicyId`, `draggedPolicyName`, `dropError`; actions `startDrag(policyId, policyName)`, `endDrag()`, `setDropError(error)`, `clearDropError()`
- [X] T005 Add "Trust Workbench" sidebar entry in `apps/web/components/shared/Sidebar.tsx` with route `/trust-workbench` and `requiredRoles: ['trust_certifier', 'platform_admin', 'superadmin']`

---

## Phase 2: Foundational (TanStack Query Hooks)

**Purpose**: All server state hooks — MUST be complete before any user story UI

**⚠️ CRITICAL**: All user story components depend on these hooks

- [X] T006 [P] Create `apps/web/lib/hooks/use-certifications.ts` — `useCertificationQueue(filters: CertificationQueueFilters)` calls `GET /api/v1/trust/certifications` with query params (status, search, sort_by, page, page_size); 300ms debounce for `search` param; `useCertification(certId: string)` calls `GET /api/v1/trust/certifications/{certId}`; query keys `['certificationQueue', filters]` and `['certification', certId]`
- [X] T007 [P] Create `apps/web/lib/hooks/use-certification-actions.ts` — `useApproveCertification()` chains POST `/trust/certifications/{id}/activate` then POST `/trust/certifications/{id}/evidence` (type: `manual_review`, non-blocking on evidence failure); `useRevokeCertification()` calls POST `/trust/certifications/{id}/revoke` with `{ reason: notes }`; `useAddEvidenceRef(certId)` calls POST `/trust/certifications/{id}/evidence`; all mutations invalidate `['certification', certId]` and `['certificationQueue']` on settle; 409 response returns `{ conflictError: true }` for concurrent review detection
- [X] T008 [P] Create `apps/web/lib/hooks/use-trust-radar.ts` — `useTrustRadar(agentId: string)` calls `GET /api/v1/trust/agents/{agentId}/trust-profile`; if 404 falls back to `GET /api/v1/trust/agents/{agentId}/tier` and maps 3-component tier to 7-dimension `TrustRadarProfile` (certification_component → `certification_audit`, behavioral_component → `behavioral_compliance`, guardrail_component → `authorization_access`, remaining 4 dimensions default to 0 with `isWeak: true`); query key `['trustRadar', agentId]`
- [X] T009 [P] Create `apps/web/lib/hooks/use-privacy-impact.ts` — `usePrivacyImpact(agentId: string)` calls `GET /api/v1/trust/agents/{agentId}/privacy-impact`; staleTime 5 minutes; query key `['privacyImpact', agentId]`
- [X] T010 [P] Create `apps/web/lib/hooks/use-policy-catalog.ts` — `usePolicyCatalog(workspaceId: string, search?: string)` calls `GET /api/v1/policies?workspace_id=...&status=active&search=...`; 300ms debounce for search; query key `['policyCatalog', workspaceId, debouncedSearch]`
- [X] T011 [P] Create `apps/web/lib/hooks/use-effective-policies.ts` — `useEffectivePolicies(agentId: string, workspaceId: string)` calls `GET /api/v1/policies/effective/{agentId}?workspace_id=...`; transforms `PolicyRuleProvenance` into `PolicyBinding[]` with source derivation: `scope_type: 'agent'` → `source: 'direct'`, `scope_type: 'workspace'` → `source: 'workspace'` + `sourceLabel: workspaceName`, `scope_type: 'fleet'` → `source: 'fleet'` + `sourceLabel: fleetName`, `scope_type: 'global'` → `source: 'global'`; `canRemove: source === 'direct'`; query key `['effectivePolicies', agentId, workspaceId]`
- [X] T012 [P] Create `apps/web/lib/hooks/use-policy-actions.ts` — `useAttachPolicy()` calls POST `/api/v1/policies/{policyId}/attach` with `{ targetType: 'agent_revision', targetId: agentRevisionId }`; invalidates `['effectivePolicies', agentId]` on settle; `useDetachPolicy()` calls DELETE `/api/v1/policies/{policyId}/attach/{attachmentId}` with optimistic removal from `['effectivePolicies']` cache; rollback on error

**Checkpoint**: All hooks ready — user story UI can begin

---

## Phase 3: User Story 1 — Browse Certification Queue (Priority: P1) 🎯 MVP

**Goal**: Searchable, filterable, paginated certification queue DataTable with status tabs.

**Independent Test**: Navigate to `/trust-workbench`. Confirm DataTable renders with columns: entity name/FQN, certification type, status badge, expiration date, evidence count. Confirm tab bar switches between pending/expiring/revoked. Type in search field — results filter within 300ms. Sort by expiration. Click a row — browser navigates to `/trust-workbench/{certificationId}`.

- [X] T013 [P] [US1] Create `apps/web/components/features/trust-workbench/CertificationStatusBadge.tsx` — shadcn/ui `Badge` with variant mapping: `pending` → yellow (`warning`), `active` → green (`default`), `expiring` → orange, `expired` → muted/secondary, `revoked` → red (`destructive`), `superseded` → muted/secondary; when `status === 'expiring'` and `expiresAt` provided show "X days" countdown via `date-fns differenceInDays`; accepts `size?: 'sm' | 'md'`
- [X] T014 [US1] Create `apps/web/components/features/trust-workbench/CertificationDataTable.tsx` — TanStack Table v8 + shadcn DataTable; columns: entity name (linked to agentFqn), certification type, `CertificationStatusBadge`, expiration date (`date-fns format`), evidence count; tab bar for All/Pending/Expiring/Revoked using shadcn `Tabs`; `SearchInput` shared component (300ms debounce); sort by expiration/urgency/created via column headers; pagination with page size selector (20/50/100); `onRowClick` calls `router.push('/trust-workbench/{id}')`; skeleton loading state via `DataTable` skeleton rows
- [X] T015 [US1] Implement `apps/web/app/(main)/trust-workbench/page.tsx` — manages `CertificationQueueFilters` state synced to URL search params (`?status=pending&search=...&page=1`); calls `useCertificationQueue(filters)`; renders `CertificationDataTable` with filters and handlers; page title "Trust Workbench"

**Checkpoint**: Certification queue fully functional — search, filter, sort, navigate to detail

---

## Phase 4: User Story 2 — Review Certification with Evidence (Priority: P1)

**Goal**: Certification detail page with expandable evidence items, status timeline, and approve/reject reviewer form.

**Independent Test**: Navigate to `/trust-workbench/{id}`. Confirm entity info section, status timeline, evidence list. Click an evidence item — confirm it expands to show full data. Fill review notes and click Approve — confirm status changes and success toast. Try submit without notes — confirm "Review notes are required." error. Select Reject with notes — confirm status transitions to revoked.

- [X] T016 [P] [US2] Create `apps/web/components/features/trust-workbench/StatusTimeline.tsx` — uses shared `Timeline` component (feature 015); renders `CertificationStatusEvent[]` as vertical timeline; each event shows status label, actor username, timestamp (`date-fns formatDistanceToNow`), and optional notes; current status highlighted; events ordered newest-first
- [X] T017 [P] [US2] Create `apps/web/components/features/trust-workbench/EvidenceItemCard.tsx` — shadcn/ui `Collapsible`; collapsed: evidence type label (human-readable), result badge (green pass / red fail / yellow partial / gray unknown derived from evidenceType + summary keywords), collection timestamp; expanded: summary text + `JsonViewer` shared component if storageRef present; result derivation: scan `summary` for "pass", "fail", "partial" keywords, fallback to `unknown`
- [X] T018 [US2] Create `apps/web/components/features/trust-workbench/EvidenceList.tsx` — renders list of `EvidenceItemCard`; empty state uses shared `EmptyState` component with message "No evidence collected yet" and subtitle "Automated evidence collection may still be in progress"; accepts `items: EvidenceItem[]` and `isLoading?: boolean`; shows skeleton cards when loading
- [X] T019 [US2] Create `apps/web/components/features/trust-workbench/ReviewerForm.tsx` — React Hook Form + Zod schema: `decision: z.enum(['approve', 'reject'])` (required), `notes: z.string().min(1, 'Review notes are required.')` (required), `supportingFiles: z.array(z.instanceof(File)).optional()` with file type/size validation (PDF/PNG/JPG, max 10MB each); on submit calls `useRevokeCertification` (reject) or `useApproveCertification` (approve); when `isExpired` prop is true, decision options change to "Renew"/"Reject"; on 409 response shows alert "A decision has already been recorded — please refresh"; file upload via HTML5 `<input type="file" multiple accept=".pdf,.png,.jpg">`; success → `onDecisionSubmitted()` callback + success toast
- [X] T020 [US2] Create `apps/web/components/features/trust-workbench/CertificationDetailView.tsx` — entity info header (agentFqn, certification type, `CertificationStatusBadge`); `StatusTimeline` below header; shadcn `Tabs` with `?tab=` URL query param routing (default tab: `evidence`); Evidence tab: `EvidenceList` + `ReviewerForm` side-by-side or stacked on mobile; Trust Radar tab placeholder (US3); Policies tab placeholder (US4); Privacy tab placeholder (US5); `tabsConfig` driven by prop to conditionally include tabs
- [X] T021 [US2] Implement `apps/web/app/(main)/trust-workbench/[certificationId]/page.tsx` — reads `certificationId` from params; calls `useCertification(certificationId)`; renders `CertificationDetailView` with certification data; handles 404 with "Certification not found" UI with back button; passes `workspaceId` from workspace store; reads `?tab=` query param for initial tab

**Checkpoint**: Certification detail, evidence review, and decision form fully functional

---

## Phase 5: User Story 3 — View Trust Radar Chart (Priority: P2)

**Goal**: 7-dimension Recharts RadarChart with hover tooltips and warning highlight for weak dimensions.

**Independent Test**: Navigate to `/trust-workbench/{id}?tab=trust-radar`. Confirm radar chart renders with 7 labeled axes (0–100). Hover over a dimension — tooltip shows component scores. A dimension with score <30 shows amber/warning highlight. Chart renders in both light and dark mode.

- [X] T022 [P] [US3] Create `apps/web/components/features/trust-workbench/TrustDimensionTooltip.tsx` — Recharts custom tooltip; when `active` and `payload` exist renders shadcn `Card` with: dimension label from `TRUST_DIMENSION_LABELS`, overall score (`X / 100`), component breakdown list (name + score), trend icon (↑ up / ↓ down / → stable) from `date-fns` n/a + Lucide `TrendingUp`/`TrendingDown`/`Minus`; for `behavioral_compliance` shows anomaly count if present
- [X] T023 [US3] Create `apps/web/components/features/trust-workbench/TrustRadarChart.tsx` — Recharts `ResponsiveContainer` + `RadarChart` + `PolarGrid` + `PolarAngleAxis` (tick: dimension label from TRUST_DIMENSION_LABELS) + `PolarRadiusAxis` (domain: [0, 100], tickCount: 5) + `Radar` (dataKey: "score", fill/stroke via CSS vars) + `Tooltip` (custom `TrustDimensionTooltip`); data shaped as `TrustRadarChartDataPoint[]` (7 entries); weak dimension detection (score < 30): custom dot render with amber fill `fill-amber-400/60 dark:fill-amber-500/60`; `PolarGrid` gridType="polygon"; dark mode: stroke/fill use Tailwind CSS variable tokens; `isWeak` dimensions also show a small ⚠ icon near the axis tick label; min-height 320px via ResponsiveContainer
- [X] T024 [US3] Add trust-radar tab to `apps/web/components/features/trust-workbench/CertificationDetailView.tsx` — trust-radar tab calls `useTrustRadar(agentId)` inside the tab; renders `TrustRadarChart` when data loaded; loading skeleton (circle placeholder); error state "Trust profile not available"

**Checkpoint**: Trust radar chart fully functional with 7 dimensions, tooltips, weak dimension warnings

---

## Phase 6: User Story 4 — Attach Policies to Agents and Fleets (Priority: P2)

**Goal**: Drag-and-drop policy attachment panel with catalog on left, binding list with inheritance chain on right.

**Independent Test**: Navigate to `/trust-workbench/{id}?tab=policies`. Confirm split view (catalog left, bindings right). Drag a policy card onto the drop zone — confirm policy appears in binding list with "direct" source. Confirm inherited policies show source label ("workspace: X" / "fleet: Y"). Click Remove on a direct binding — confirm ConfirmDialog, then confirm removal. Confirm inherited bindings show no Remove button, only "Manage →" link.

- [X] T025 [P] [US4] Create `apps/web/components/features/trust-workbench/PolicyBindingCard.tsx` — shows policy name, scope type badge, enforcement status badge (active/suspended), source label chip (e.g. "direct", "workspace: Marketing", "fleet: Fraud Detection Fleet"); direct bindings: "Remove" button opens `ConfirmDialog` shared component with warning "Removing this policy will affect enforcement immediately" + calls `useDetachPolicy`; inherited bindings: `sourceEntityUrl` rendered as "Manage →" Lucide `ExternalLink` link; no Remove button
- [X] T026 [P] [US4] Create `apps/web/components/features/trust-workbench/PolicyCatalog.tsx` — calls `usePolicyCatalog(workspaceId, search)` with SearchInput (300ms debounce); each policy card: `draggable={true}`, `onDragStart={(e) => { e.dataTransfer.setData('policyId', policy.id); e.dataTransfer.setData('policyName', policy.name); props.onPolicyDragStart(policy.id, policy.name) }}`; cursor-grab style; policy card shows name, scope type, description excerpt; loading skeleton cards
- [X] T027 [US4] Create `apps/web/components/features/trust-workbench/PolicyBindingList.tsx` — drop zone with `onDrop={(e) => { e.preventDefault(); const id = e.dataTransfer.getData('policyId'); props.onDrop(id) }}`, `onDragOver={(e) => { e.preventDefault(); /* set drag over state */ }}`, `onDragLeave`; `isDragOver` prop → dashed border highlight + background tint; `dropError` prop → red outline + shadcn Tooltip with error text; list of `PolicyBindingCard`; empty state "No policies attached. Drag a policy here to attach it." via shared `EmptyState`
- [X] T028 [US4] Create `apps/web/components/features/trust-workbench/PolicyAttachmentPanel.tsx` — two-column layout (col-1: PolicyCatalog, col-2: PolicyBindingList); reads `usePolicyAttachmentStore` for drag state; `onDrop` calls `useAttachPolicy().mutate({ policyId, agentRevisionId, targetType: 'agent_revision' })`; `onRemove` calls `useDetachPolicy().mutate({ policyId, attachmentId })`; `isDragOver` state set on dragEnter/dragLeave of right column; calls `useEffectivePolicies(agentId, workspaceId)` for binding list data
- [X] T029 [US4] Add policies tab to `apps/web/components/features/trust-workbench/CertificationDetailView.tsx` — policies tab renders `<PolicyAttachmentPanel agentId={...} agentRevisionId={...} workspaceId={...} />`; passes agentRevisionId from certification detail

**Checkpoint**: Policy attachment drag-and-drop fully functional with inheritance chain display

---

## Phase 7: User Story 5 — View Privacy Impact Analysis (Priority: P3)

**Goal**: Privacy impact panel showing data categories, compliance status, retention durations, and flagged concerns.

**Independent Test**: Navigate to `/trust-workbench/{id}?tab=privacy`. Confirm data categories listed with status badges (green/yellow/red). Retention durations shown per category. Violations highlighted in red with description and recommendation. Analysis timestamp and data sources visible. If analysis is >24h old: stale warning banner + "Request Re-analysis" button visible.

- [X] T030 [P] [US5] Create `apps/web/components/features/trust-workbench/PrivacyDataCategoryRow.tsx` — category name, compliance status badge (`compliant` → green, `warning` → yellow, `violation` → red/destructive), retention duration string; violations: red-highlighted concerns list, each concern shows description + severity badge + recommendation text; compliant categories: show only green badge (no concerns list); shadcn/ui `Card` or bordered row
- [X] T031 [US5] Create `apps/web/components/features/trust-workbench/PrivacyImpactPanel.tsx` — calls `usePrivacyImpact(agentId)`; metadata header: analysis timestamp via `date-fns format` + `formatDistanceToNow`, data sources as comma-separated list; stale detection: `differenceInHours(new Date(), parseISO(analysisTimestamp)) > 24` → shows shadcn `Alert` (warning variant) "Analysis is X hours old" + "Request Re-analysis" button (calls `POST /trust/privacy/assess` or shows "Contact agent owner to re-trigger analysis"); overall compliance summary: if `overallCompliant` → shadcn Alert (success/default) "No privacy concerns identified."; list of `PrivacyDataCategoryRow`; loading skeleton rows; error state "Privacy analysis not available"
- [X] T032 [US5] Add privacy tab to `apps/web/components/features/trust-workbench/CertificationDetailView.tsx` — privacy tab renders `<PrivacyImpactPanel agentId={certification.agentId} />`

**Checkpoint**: All 5 user stories fully functional

---

## Phase 8: Tests + Polish

**Purpose**: Component tests, E2E tests, accessibility, dark mode, responsive layout

- [X] T033 [P] Write `apps/web/__tests__/features/trust-workbench/CertificationDataTable.test.tsx` — renders with mock data; search input filters within debounce; status tab switches filter; sort by expiration changes order; clicking a row calls onRowClick with correct certificationId; pagination renders page controls; empty state renders when no data
- [X] T034 [P] Write `apps/web/__tests__/features/trust-workbench/CertificationDetailView.test.tsx` — entity info renders; status timeline shows events; evidence list renders all items; evidence item expands on click; tab navigation changes active tab; `?tab=evidence` default renders evidence + reviewer form
- [X] T035 [P] Write `apps/web/__tests__/features/trust-workbench/ReviewerForm.test.tsx` — empty notes submit shows "Review notes are required." validation; decision radio required; approve submission calls activate mutation; reject submission calls revoke mutation with notes as reason; 409 response shows concurrent review error message; file input accepts PDF/PNG/JPG; file size >10MB shows validation error
- [X] T036 [P] Write `apps/web/__tests__/features/trust-workbench/TrustRadarChart.test.tsx` — renders 7 axes with correct labels from TRUST_DIMENSION_LABELS; dimension with score <30 has amber/warning class; all 7 data points render in SVG; ResponsiveContainer wraps chart; tooltip renders on simulated hover; dark mode class applied correctly
- [X] T037 [P] Write `apps/web/__tests__/features/trust-workbench/PolicyAttachmentPanel.test.tsx` — policy catalog renders policy cards with draggable attribute; drag start sets dataTransfer data; drop event on binding list calls attach mutation; direct binding shows Remove button; inherited binding shows Manage link (no Remove); remove confirmation dialog appears; confirmed removal calls detach mutation; drop error shows red outline; empty binding list shows empty state message
- [X] T038 [P] Write `apps/web/__tests__/features/trust-workbench/PrivacyImpactPanel.test.tsx` — compliant analysis shows "No privacy concerns identified."; violation category shows red badge and concern description + recommendation; stale analysis (>24h) shows warning banner with "Request Re-analysis"; analysis timestamp and data sources render in metadata header; loading state shows skeleton rows
- [X] T039 [P] Write `apps/web/e2e/trust-workbench-queue.spec.ts` — open `/trust-workbench`; confirm table visible with rows; type in search box; confirm filtered results; click Pending tab; confirm only pending rows; sort by expiration; confirm sort order; click a row; confirm navigation to detail page URL
- [X] T040 [P] Write `apps/web/e2e/trust-workbench-review.spec.ts` — open certification detail; confirm evidence tab active by default; expand evidence item; confirm details visible; fill review notes; click Approve; confirm status badge changes; open new certification; submit without notes; confirm validation error; fill notes; reject; confirm revoked status
- [X] T041 [P] Write `apps/web/e2e/trust-workbench-policy.spec.ts` — open `?tab=policies`; confirm catalog and binding list visible; drag policy card to drop zone; confirm policy appears in binding list as "direct"; confirm inherited policy shows source label; click Remove on direct binding; confirm dialog; confirm binding; confirm binding removed from list
- [X] T042 Accessibility audit in `apps/web/components/features/trust-workbench/` — all interactive elements keyboard-navigable (Tab/Enter/Space); `CertificationDataTable` rows have aria-label; `ReviewerForm` inputs have labels; `EvidenceItemCard` Collapsible toggle has aria-expanded; `TrustRadarChart` has `role="img"` + `aria-label="Trust radar chart for {agentFqn}"`; policy drag-and-drop has keyboard fallback (button "Attach" in catalog as alternative to drag)
- [X] T043 Dark mode verification across all components in `apps/web/components/features/trust-workbench/` — `TrustRadarChart` stroke/fill render correctly with dark: Tailwind classes; `CertificationStatusBadge` colors correct in dark mode; `EvidenceItemCard` expansion visible; `PolicyBindingCard` source label chip readable; `PrivacyDataCategoryRow` violation red readable in dark mode; run `pnpm dev` and toggle dark mode to verify visually
- [X] T044 Responsive layout verification for `apps/web/app/(main)/trust-workbench/` — queue DataTable horizontal scroll on mobile; certification detail tabs scroll on narrow viewport; `PolicyAttachmentPanel` stacks vertically on mobile (catalog above binding list); `TrustRadarChart` min-height 320px preserved on mobile via ResponsiveContainer; run `pnpm dev` and verify at 375px and 1440px breakpoints

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (types from `trust-workbench.ts` used by all hooks) — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2 (`useCertificationQueue`, `useCertification`)
- **US2 (Phase 4)**: Depends on Phase 2 (`useCertification`, `useApproveCertification`, `useRevokeCertification`) + Phase 3 (`CertificationStatusBadge` reused)
- **US3 (Phase 5)**: Depends on Phase 2 (`useTrustRadar`) + Phase 4 (`CertificationDetailView` extended)
- **US4 (Phase 6)**: Depends on Phase 2 (`useEffectivePolicies`, `usePolicyCatalog`, `useAttachPolicy`, `useDetachPolicy`) + Phase 4 (`CertificationDetailView` extended) + Phase 1 (`usePolicyAttachmentStore`)
- **US5 (Phase 7)**: Depends on Phase 2 (`usePrivacyImpact`) + Phase 4 (`CertificationDetailView` extended)
- **Polish (Phase 8)**: Depends on all user story phases

### User Story Dependencies (Critical Path)

```
Phase 1 (Setup)
  └── Phase 2 (Hooks) — BLOCKS ALL
        ├── Phase 3 (US1 Queue) ← MVP deliverable
        │     └── Phase 4 (US2 Detail+Evidence+Form) ← P1 complete
        │           ├── Phase 5 (US3 Radar) 
        │           ├── Phase 6 (US4 Policies)
        │           └── Phase 7 (US5 Privacy)
        │                 └── Phase 8 (Polish)
```

### Parallel Opportunities

**Phase 2** — all 7 hook files can be written concurrently (T006–T012):
- `use-certifications.ts`, `use-certification-actions.ts`, `use-trust-radar.ts`, `use-privacy-impact.ts`, `use-policy-catalog.ts`, `use-effective-policies.ts`, `use-policy-actions.ts`

**Phase 4** — `StatusTimeline.tsx` and `EvidenceItemCard.tsx` (T016, T017) can be written in parallel before the list and form:
```
T016 StatusTimeline    ─┐
T017 EvidenceItemCard  ─┤→ T018 EvidenceList → T019 ReviewerForm → T020 CertificationDetailView
```

**Phase 5** — `TrustDimensionTooltip.tsx` (T022) can be written before `TrustRadarChart.tsx` (T023) or in parallel:
```
T022 TrustDimensionTooltip ─┐→ T023 TrustRadarChart → T024 Add tab
```

**Phase 6** — `PolicyBindingCard.tsx` and `PolicyCatalog.tsx` (T025, T026) can be written in parallel:
```
T025 PolicyBindingCard ─┐
T026 PolicyCatalog     ─┤→ T027 PolicyBindingList → T028 PolicyAttachmentPanel → T029 Add tab
```

**Phase 8** — All test files T033–T041 can be written in parallel (different files):
```
T033 DataTable.test   ──┐
T034 DetailView.test  ──┤
T035 ReviewerForm.test──┤
T036 RadarChart.test  ──┤→ T042 A11y → T043 Dark mode → T044 Responsive
T037 PolicyPanel.test ──┤
T038 PrivacyPanel.test──┤
T039 E2E queue        ──┤
T040 E2E review       ──┤
T041 E2E policy       ──┘
```

---

## Implementation Strategy

### MVP First (US1 + US2 — P1 Stories Only)

1. Complete Phase 1: Setup (T001–T005)
2. Complete Phase 2: Foundational hooks (T006–T012) — focus on `use-certifications.ts` and `use-certification-actions.ts`
3. Complete Phase 3: Certification queue (T013–T015)
4. Complete Phase 4: Certification detail + evidence + reviewer form (T016–T021)
5. **STOP and VALIDATE**: Both P1 stories fully functional — trust officer can browse queue, review evidence, approve/reject certifications
6. Deploy/demo MVP

### Incremental Delivery (P2 Stories)

7. Complete Phase 5: Trust radar chart (T022–T024) — extends existing detail page
8. Complete Phase 6: Policy attachment (T025–T029) — extends existing detail page
9. **VALIDATE**: P1 + P2 complete

### Final Story (P3)

10. Complete Phase 7: Privacy impact panel (T030–T032)
11. Complete Phase 8: Tests + Polish (T033–T044)

---

## Notes

- T020/T024/T029/T032 all modify `CertificationDetailView.tsx` — implement sequentially (US2 creates it, US3–US5 extend tabs)
- The Recharts `RadarChart` is in the existing `recharts` package — no new dependency needed
- HTML5 drag events in T026–T028 require no external library — native browser API
- T008 (`useTrustRadar`) has a fallback path for the assumed `/trust-profile` endpoint — implement both the primary path and the tier-based fallback
- T011 (`useEffectivePolicies`) performs source derivation from `PolicyRuleProvenance` — the `scopeTargetId` resolves workspace/fleet names; if name resolution requires additional API calls, use `staleTime: Infinity` to cache resolved names
- T007 approval flow is two-step (activate → evidence ref) — the evidence ref failure must be non-blocking; log the failure but don't surface as form error to avoid confusing the reviewer
