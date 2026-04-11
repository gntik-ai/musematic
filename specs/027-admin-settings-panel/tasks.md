# Tasks: Admin Settings Panel

**Input**: Design documents from `/specs/027-admin-settings-panel/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/admin-ui.md ✓, quickstart.md ✓

**Tests**: Included — SC-011 requires ≥95% test coverage. Vitest + RTL per tab, Playwright e2e for critical flows.

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story label [US1]–[US6]

---

## Phase 1: Setup

**Purpose**: Create directory skeleton, type/schema files, and MSW handler stubs.

- [X] T001 Create directory structure: `apps/web/components/features/admin/` (tabs/, users/, connectors/, shared/), `apps/web/lib/types/`, `apps/web/lib/schemas/`, `apps/web/tests/mocks/handlers/`, `apps/web/tests/features/admin/e2e/`
- [X] T002 [P] Create `apps/web/lib/types/admin.ts` — all TypeScript types per data-model.md: UserStatus, UserRole, AdminUserRow, UserAction, AdminUsersResponse, SignupMode, MFAEnforcement, SignupPolicySettings, DefaultQuotas, WorkspaceQuotaOverride, ConnectorTypeGlobalConfig, EmailMode, EmailDeliveryConfig, SecurityPolicySettings, AdminUsersParams
- [X] T003 [P] Create `apps/web/lib/schemas/admin.ts` — all Zod schemas per data-model.md: signupPolicySchema, defaultQuotasSchema, workspaceQuotaOverrideSchema, emailSmtpSchema, emailSesSchema, emailConfigSchema (discriminatedUnion), securityPolicySchema, testEmailSchema
- [X] T004 [P] Create `apps/web/tests/mocks/handlers/admin.ts` — MSW handler stubs for all 18 endpoints listed in quickstart.md (usersHandler, approveHandler, rejectHandler, suspendHandler, reactivateHandler, signupGetHandler, signupPatchHandler, quotasGetHandler, quotasPatchHandler, wsQuotaGetHandler, wsQuotaPatchHandler, workspacesSearchHandler, connectorsGetHandler, connectorPatchHandler, emailGetHandler, emailPatchHandler, emailTestHandler, securityGetHandler, securityPatchHandler) with realistic fixture data
- [X] T005 Register admin MSW handlers in `apps/web/tests/mocks/handlers/index.ts`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Route structure, guard, tab shell, and shared components. Must complete before any user story work.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T006 Create `apps/web/app/(main)/admin/layout.tsx` — route guard: read `useAuthStore().user?.role`, redirect to `/home` + show 403 toast via `useToast` if role is not `platform_admin`; wrap children in layout shell
- [X] T007 Create `apps/web/app/(main)/admin/settings/page.tsx` — RSC shell: read `searchParams.tab`, render `<AdminSettingsPanel defaultTab={searchParams.tab ?? "users"} />`
- [X] T008 Create `apps/web/lib/hooks/use-admin-settings.ts` — `adminQueryKeys` factory + stubs for all 11 hooks (useAdminUsers, useUserActionMutation, useSignupPolicy, useSignupPolicyMutation, useDefaultQuotas, useWorkspaceQuota, useConnectorTypeConfigs, useConnectorTypeToggleMutation, useEmailConfig, useSendTestEmailMutation, useSecurityPolicy) — hook bodies to be filled in per-phase
- [X] T009 [P] Create `apps/web/components/features/admin/shared/StaleDataAlert.tsx` — shadcn Alert with AlertTriangle icon, message "Settings were changed by another administrator. Reload to see the latest values.", "Reload" button calling `onReload` prop
- [X] T010 [P] Create `apps/web/components/features/admin/shared/SettingsFormActions.tsx` — Save button (disabled when `!isDirty || isPending`; text: `isPending` → "Saving…" | `isSaved` → "Saved ✓" | default → "Save") + Reset button (disabled when `!isDirty || isPending`, calls `onReset`); `isSaved` cleared via `useEffect` setTimeout 1500ms
- [X] T011 Create `apps/web/components/features/admin/AdminSettingsPanel.tsx` — "use client"; shadcn `Tabs` with `value={currentTab}` from `useSearchParams()`; `onValueChange` calls `router.push(`?tab=${tab}`)``; render `<UsersTab/>`, `<SignupPolicyTab/>`, `<QuotasTab/>`, `<ConnectorsTab/>`, `<EmailTab/>`, `<SecurityTab/>` as stub imports; `TabsList` with `TabsTrigger` for each of the 6 tabs

**Checkpoint**: Admin route guard functional, tab navigation updates URL, all 6 tab stubs render.

---

## Phase 3: User Story 1 — User Management (Priority: P1) 🎯 MVP

**Goal**: Platform admin can search, filter, and manage user accounts (approve, reject, suspend, reactivate) from a server-side DataTable.

**Independent Test**: Navigate to `/admin/settings?tab=users` as a `platform_admin`. Verify table loads with MSW data, search debounce filters rows, approve action opens dialog and optimistically updates status, own row has no suspend action.

### Tests for User Story 1

- [X] T012 [P] [US1] Create `apps/web/tests/features/admin/UsersTab.test.tsx` — test cases: table renders with MSW fixture, search input debounces 300ms, status filter dropdown updates query params, approve action opens UserActionDialog, confirm calls mutation + optimistic row status update, error reverts row, admin's own row shows no Suspend action
- [X] T013 [P] [US1] Create `apps/web/tests/features/admin/e2e/admin-users.spec.ts` — Playwright: login as platform_admin, navigate to Users tab, verify table columns, approve a pending user, verify status badge updates, attempt self-suspend prevention

### Implementation for User Story 1

- [X] T014 [P] [US1] Implement `useAdminUsers` hook in `apps/web/lib/hooks/use-admin-settings.ts` — TanStack Query `useQuery` with `queryKey: adminQueryKeys.users(params)`, `queryFn: api.get<AdminUsersResponse>('/api/v1/admin/users', { params })`, `staleTime: 30_000`
- [X] T015 [P] [US1] Implement `useUserActionMutation` hook in `apps/web/lib/hooks/use-admin-settings.ts` — `useMutation` with `mutationFn: (action) => api.post('/api/v1/admin/users/${userId}/${action}')`, `onMutate`: cancel queries + optimistic update row status, `onError`: rollback via context, `onSettled`: invalidate `["admin","users"]`
- [X] T016 [US1] Create `apps/web/components/features/admin/users/UserActionsMenu.tsx` — shadcn `DropdownMenu`; render actions only from `user.available_actions`; disable Suspend action when `user.id === authStore.user.id` with tooltip "You cannot suspend your own account"; call `onAction(action)` on click
- [X] T017 [US1] Create `apps/web/components/features/admin/users/UserActionDialog.tsx` — shadcn `AlertDialog`; `title` and `description` vary by `action` prop: approve → "Grant platform access", reject → "Block account and send rejection email", suspend → "Invalidate active sessions", reactivate → "Restore platform access"; `isPending` disables confirm button with spinner
- [X] T018 [US1] Implement `apps/web/components/features/admin/tabs/UsersTab.tsx` — local state: `searchValue`, `statusFilter`, `page`, `selectedUser`, `pendingAction`; `useAdminUsers({ search: debouncedSearch, status: statusFilter, page })`; scaffold `DataTable` in server-side mode with columns: name, email (StatusBadge from scaffold), role, last_login_at (date-fns `formatRelative`), created_at, actions (UserActionsMenu); `SearchInput` component; shadcn `Select` for status filter; on action: set `selectedUser + pendingAction` → open `UserActionDialog`; on confirm: call `useUserActionMutation(user.id).mutate(action)`

**Checkpoint**: Users tab fully functional: search, filter, approve/reject/suspend/reactivate with dialogs, optimistic updates, self-suspend blocked.

---

## Phase 4: User Story 2 — Signup and Authentication Policy (Priority: P1)

**Goal**: Admin can change signup mode (open/invite_only/admin_approval) and MFA enforcement (optional/required) with stale-data protection.

**Independent Test**: Navigate to Signup tab, change signup mode, verify Save enables (isDirty), save succeeds with "Saved ✓" feedback. Simulate 412 — verify StaleDataAlert appears, Reload resets form.

### Tests for User Story 2

- [X] T019 [P] [US2] Create `apps/web/tests/features/admin/SignupPolicyTab.test.tsx` — test cases: form pre-populates from MSW fixture, Save disabled when not dirty, Save enabled after change, successful PATCH shows "Saved ✓" for 1.5s then disables, 412 response renders StaleDataAlert, clicking Reload invalidates query + resets form, Reset button reverts unsaved changes
- [X] T020 [P] [US2] Create `apps/web/tests/features/admin/e2e/admin-signup.spec.ts` — Playwright: change signup mode to invite_only, save, navigate away and back, verify persists

### Implementation for User Story 2

- [X] T021 [P] [US2] Implement `useSignupPolicy` and `useSignupPolicyMutation` hooks in `apps/web/lib/hooks/use-admin-settings.ts` — `useSignupPolicy`: TanStack Query `useQuery`; `useSignupPolicyMutation`: `useMutation` with `mutationFn` PATCHing with `If-Unmodified-Since: data._version` header, `onSuccess`: invalidate `adminQueryKeys.signupPolicy()`
- [X] T022 [US2] Implement `apps/web/components/features/admin/tabs/SignupPolicyTab.tsx` — `useForm<SignupPolicySettings>` initialized with `defaultValues` from `useSignupPolicy()` data; `useEffect` to `form.reset(data)` when query data changes (only if not dirty); `signup_mode` as shadcn `RadioGroup` (3 options); `mfa_enforcement` as shadcn `Switch`; `isSaved` local state with `setTimeout(1500ms)` clear; `onSubmit`: call mutation with `{ ...data, _version: loadedData.updated_at }`; on 412 error: set `isStale = true`; `StaleDataAlert` when `isStale`: `onReload` → `queryClient.invalidateQueries` + `form.reset`; `SettingsFormActions` with `isDirty`, `isPending`, `isSaved`, `onReset: () => form.reset()`

**Checkpoint**: Signup tab: form pre-populates, dirty-state Save, If-Unmodified-Since, 412 → StaleDataAlert → Reload all working.

---

## Phase 5: User Story 3 — Workspace Quotas (Priority: P2)

**Goal**: Admin can configure default resource limits and set per-workspace overrides using a searchable combobox.

**Independent Test**: Navigate to Quotas tab, verify 5 default quota inputs load. Select a workspace from combobox, verify override form loads with workspace values. Save override with one non-null field — verify null fields sent as null.

### Tests for User Story 3

- [X] T023 [P] [US3] Create `apps/web/tests/features/admin/QuotasTab.test.tsx` — test cases: default quota form pre-populates, save sends PATCH to `/api/v1/admin/settings/quotas`, workspace combobox search calls `/api/v1/admin/workspaces?search=`, selecting workspace loads override data, saving override with mix of null/number sends correct body, 412 shows StaleDataAlert

### Implementation for User Story 3

- [X] T024 [P] [US3] Implement `useDefaultQuotas` hook in `apps/web/lib/hooks/use-admin-settings.ts` — TanStack Query `useQuery` fetching `/api/v1/admin/settings/quotas`; add `useDefaultQuotasMutation` — `useMutation` PATCHing with `If-Unmodified-Since`, `onSuccess` invalidates `adminQueryKeys.defaultQuotas()`
- [X] T025 [P] [US3] Implement `useWorkspaceQuota` hook in `apps/web/lib/hooks/use-admin-settings.ts` — `useQuery` with `enabled: !!workspaceId`, fetching `/api/v1/admin/settings/quotas/workspaces/${workspaceId}`; add `useWorkspaceQuotaMutation`
- [X] T026 [US3] Implement workspace combobox in `apps/web/components/features/admin/tabs/QuotasTab.tsx` (sub-component) — shadcn `Popover` + `Command`; `useQuery` backing `GET /api/v1/admin/workspaces?search=` debounced input; `selectedWorkspaceId` state; on select: set `selectedWorkspaceId`, close popover
- [X] T027 [US3] Implement `apps/web/components/features/admin/tabs/QuotasTab.tsx` — two sections: (1) Default Quotas: `useForm` with `defaultQuotasSchema`, 5 shadcn `Input` type=number fields, `SettingsFormActions`, 412 → `StaleDataAlert`; (2) Workspace Override: workspace combobox, 5 nullable shadcn `Input` fields (empty = null = inherit default), `useWorkspaceQuota(selectedWorkspaceId)` loads override form values; save calls `useWorkspaceQuotaMutation`

**Checkpoint**: Quotas tab: default quotas save, workspace combobox loads per-workspace overrides, null fields propagated correctly.

---

## Phase 6: User Story 4 — Connector Configuration (Priority: P2)

**Goal**: Admin can enable/disable connector types globally via per-toggle auto-save with optimistic updates and active-instance warnings.

**Independent Test**: Navigate to Connectors tab, verify 4 connector type cards load. Toggle Email connector off — verify immediate optimistic disable + PATCH called. Simulate API error — verify toggle reverts. Verify AlertTriangle warning shown when disabled type has active instances.

### Tests for User Story 4

- [X] T028 [P] [US4] Create `apps/web/tests/features/admin/ConnectorsTab.test.tsx` — test cases: 4 connector cards render, toggle calls PATCH immediately (no Save button), optimistic update disables switch before response, API error reverts toggle, AlertTriangle shown when `!is_enabled && active_instance_count > 0`, Badge shows instance count

### Implementation for User Story 4

- [X] T029 [P] [US4] Implement `useConnectorTypeConfigs` and `useConnectorTypeToggleMutation` hooks in `apps/web/lib/hooks/use-admin-settings.ts` — `useConnectorTypeConfigs`: `useQuery` fetching `/api/v1/admin/settings/connectors`; `useConnectorTypeToggleMutation(typeSlug)`: `useMutation` with `onMutate`: `cancelQueries` + optimistic `setQueryData` toggling matching slug's `is_enabled`, `onError`: rollback via context, no `onSuccess` invalidation (optimistic update is sufficient)
- [X] T030 [P] [US4] Create `apps/web/components/features/admin/connectors/ConnectorTypeCard.tsx` — shadcn `Card` + `CardHeader` + `CardContent`; `Switch` whose `onCheckedChange` calls `useConnectorTypeToggleMutation(config.slug).mutate(enabled)`; shadcn `Badge` (variant=destructive) showing "⚠ N active instances" when `!config.is_enabled && config.active_instance_count > 0`; Lucide `AlertTriangle` icon next to badge
- [X] T031 [US4] Implement `apps/web/components/features/admin/tabs/ConnectorsTab.tsx` — `useConnectorTypeConfigs()` query; render list of `ConnectorTypeCard` for each config; no master Save button; loading skeleton while query is pending

**Checkpoint**: Connectors tab: toggle auto-saves, optimistic update, error rollback, instance-count warning all working.

---

## Phase 7: User Story 5 — Email Delivery Configuration (Priority: P3)

**Goal**: Admin can configure SMTP or SES email delivery with masked credentials and can send a test email.

**Independent Test**: Navigate to Email tab, verify SMTP password field shows `"••••••••"` and is not editable. Click "Update Password" — verify field clears and becomes editable. Save without changing credential — verify `new_password` absent from PATCH body. Send test email — verify mutation called and result displayed within 10s.

### Tests for User Story 5

- [X] T032 [P] [US5] Create `apps/web/tests/features/admin/EmailTab.test.tsx` — test cases: SMTP mode renders host/port/username/masked-password, password field not editable initially, "Update Password" click clears and reveals input, saving without updating omits new_password from body, SES mode shows region/access_key_id/masked-secret, mode toggle switches rendered fields, "Send Test Email" mutation called with recipient, success message shown, error message shown on failure

### Implementation for User Story 5

- [X] T033 [P] [US5] Implement `useEmailConfig` and `useSendTestEmailMutation` hooks in `apps/web/lib/hooks/use-admin-settings.ts` — `useEmailConfig`: `useQuery` fetching `/api/v1/admin/settings/email`; `useEmailConfigMutation`: `useMutation` PATCHing with `If-Unmodified-Since`; `useSendTestEmailMutation`: `useMutation` POSTing to `/api/v1/admin/settings/email/test` with `{ recipient }`
- [X] T034 [US5] Implement `apps/web/components/features/admin/tabs/EmailTab.tsx` — mode state (`smtp | ses`) synced from loaded config; `useForm` with `emailConfigSchema` (Zod discriminatedUnion); per-mode conditional field rendering; credential masking state: `passwordEditMode: boolean` (false = show `"••••••••"` + "Update Password" button; true = clear field + show `Input type="password"`); same pattern for `sesKeyEditMode`; `new_password` / `new_secret_access_key` only included in submit when edit mode was activated; "Send Test Email" as separate `useForm` instance with `testEmailSchema`; test result (`success`, `message`) shown in shadcn `Alert` below send button; `SettingsFormActions` with `isDirty`, `isPending`, `isSaved`; 412 → `StaleDataAlert`

**Checkpoint**: Email tab: SMTP/SES forms, credential masking, "Update Password" reveal, new credential only sent when changed, test email with result feedback all working.

---

## Phase 8: User Story 6 — Security Settings (Priority: P3)

**Goal**: Admin can configure password policy, session duration, and account lockout settings with Zod validation and clear save feedback.

**Independent Test**: Navigate to Security tab, verify form pre-populates with current values. Set min password length to 7 — verify inline Zod error "Minimum 8 characters". Change session duration to 60 and save — verify PATCH called. Verify informational banner about existing sessions is present.

### Tests for User Story 6

- [X] T035 [P] [US6] Create `apps/web/tests/features/admin/SecurityTab.test.tsx` — test cases: form pre-populates from MSW fixture, Zod error at password_min_length < 8, Zod error at session_duration_minutes < 15, Zod error at lockout_max_attempts > 20, Save disabled while validation errors exist, successful PATCH shows "Saved ✓", informational Alert present in DOM, 412 shows StaleDataAlert
- [X] T036 [P] [US6] Create `apps/web/tests/features/admin/e2e/admin-security.spec.ts` — Playwright: change min password length, save, verify persists; trigger validation error at boundary value; verify existing-sessions banner

### Implementation for User Story 6

- [X] T037 [P] [US6] Implement `useSecurityPolicy` and `useSecurityPolicyMutation` hooks in `apps/web/lib/hooks/use-admin-settings.ts` — `useSecurityPolicy`: `useQuery` fetching `/api/v1/admin/settings/security`; `useSecurityPolicyMutation`: `useMutation` PATCHing with `If-Unmodified-Since`, `onSuccess`: invalidate `adminQueryKeys.securityPolicy()`
- [X] T038 [US6] Implement `apps/web/components/features/admin/tabs/SecurityTab.tsx` — `useForm<SecurityPolicySettings>` with `securityPolicySchema` resolver; three field groups: (1) Password Policy: `password_min_length` Input, 4 boolean `Switch` fields, `password_expiry_days` nullable Input; (2) Session: `session_duration_minutes` Input; (3) Lockout: `lockout_max_attempts` + `lockout_duration_minutes` Inputs; shadcn `Alert` (info variant) below form: "Changes apply only to new authentication events — existing active sessions are not affected."; `SettingsFormActions`; 412 → `StaleDataAlert`

**Checkpoint**: Security tab: all 9 fields with Zod validation, informational banner, If-Unmodified-Since stale-data flow all working.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Mobile layout, dark mode, accessibility, shared component tests, and coverage audit.

- [X] T039 [P] Add mobile layout to `apps/web/components/features/admin/AdminSettingsPanel.tsx` — `TabsList` uses `flex flex-col md:flex-row` so tabs stack vertically below `md` breakpoint; verify no horizontal scroll at 320px
- [X] T040 [P] Create `apps/web/tests/features/admin/AdminSettingsPanel.test.tsx` — test cases: route guard redirects non-admin, URL param `?tab=signup` activates Signup tab, tab click updates URL via `router.push`, all 6 TabsTrigger labels render
- [X] T041 [P] Create `apps/web/tests/features/admin/e2e/admin-route-guard.spec.ts` — Playwright: login as workspace_owner, navigate to `/admin/settings`, verify redirect to `/home` and toast
- [X] T042 [P] Accessibility pass on `apps/web/components/features/admin/` — add `aria-label` to all icon-only buttons (UserActionsMenu kebab, combobox trigger, credential "Update" button); verify all form fields have associated `<label>` or `aria-label`; verify `AlertDialog` has correct `aria-labelledby` and `aria-describedby`
- [ ] T043 [P] Dark mode verification across all 6 tab components — ensure no hardcoded `bg-white`/`text-black` classes; all colors use Tailwind theme tokens (`bg-background`, `text-foreground`, `border-border`, etc.); run quickstart.md Scenario 14 manually
- [ ] T044 Run coverage report: `pnpm vitest run --coverage apps/web/tests/features/admin/`; confirm ≥95% line coverage across all admin feature files; address any gaps

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately; T002, T003, T004, T005 parallelizable
- **Foundational (Phase 2)**: Depends on Phase 1 — T009 and T010 parallelizable; T011 depends on T009 + T010
- **US1 (Phase 3)**: Depends on Foundational; T012 + T013 (tests) and T014 + T015 (hooks) parallelizable; T016 + T017 parallelizable after Phase 1; T018 depends on T014–T017
- **US2 (Phase 4)**: Depends on Foundational; T019 + T020 (tests) and T021 (hooks) parallelizable; T022 depends on T021
- **US3 (Phase 5)**: Depends on Foundational; T023 (tests) + T024 + T025 (hooks) parallelizable; T026 can start with T027; T027 depends on T024 + T025 + T026
- **US4 (Phase 6)**: Depends on Foundational; T028 (tests) + T029 (hooks) + T030 (card) parallelizable; T031 depends on T029 + T030
- **US5 (Phase 7)**: Depends on Foundational; T032 (tests) + T033 (hooks) parallelizable; T034 depends on T033
- **US6 (Phase 8)**: Depends on Foundational; T035 + T036 (tests) + T037 (hooks) parallelizable; T038 depends on T037
- **Polish (Phase 9)**: Depends on all user story phases; T039–T043 parallelizable; T044 (coverage) after all others

### User Story Dependencies

- **US1 (P1)**: No dependency on other stories
- **US2 (P1)**: No dependency on other stories — can be worked in parallel with US1
- **US3 (P2)**: No dependency on US1/US2 (different API endpoints and components)
- **US4 (P2)**: No dependency on other stories
- **US5 (P3)**: No dependency on other stories
- **US6 (P3)**: No dependency on other stories

---

## Parallel Example: User Story 1

```bash
# Parallelizable from Phase 2 completion:
Task T012: "Create UsersTab.test.tsx with all test cases"
Task T013: "Create admin-users.spec.ts Playwright e2e"
Task T014: "Implement useAdminUsers hook"
Task T015: "Implement useUserActionMutation hook"
Task T016: "Create UserActionsMenu.tsx"
Task T017: "Create UserActionDialog.tsx"

# Then sequential:
Task T018: "Implement UsersTab.tsx" (depends on T014–T017)
```

## Parallel Example: User Stories 1 + 2 simultaneously

```bash
# Developer A: US1
T012 → T013 → T014 → T015 → T016 → T017 → T018

# Developer B: US2
T019 → T020 → T021 → T022
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2, P1 only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational — CRITICAL, blocks all stories
3. Complete Phase 3: User Story 1 (User Management)
4. Complete Phase 4: User Story 2 (Signup Policy)
5. **STOP and VALIDATE**: Both P1 stories functional — admin can manage users and control signup mode
6. Deploy / demo if ready

### Incremental Delivery

1. Setup + Foundational → Admin route guard + tab shell
2. + US1 → User Management fully working (most critical admin function)
3. + US2 → Signup policy control working (security posture complete)
4. + US3 + US4 → Quotas + Connectors (parallel delivery if staffed)
5. + US5 + US6 → Email config + Security settings (parallel delivery)
6. Polish → Mobile, dark mode, accessibility, coverage audit

### Parallel Team Strategy

With 3 developers after Foundational phase:
- Developer A: US1 (Users) then US3 (Quotas)
- Developer B: US2 (Signup) then US5 (Email)
- Developer C: US4 (Connectors) then US6 (Security)

---

## Notes

- [P] tasks = different files, no blocking dependencies — safe to run in parallel
- SC-011 requires ≥95% coverage — test tasks are required, not optional
- `StaleDataAlert` and `SettingsFormActions` (T009, T010) are shared by US2, US3, US5, US6 — foundational
- `useAdminUsers` staleTime is 30s; settings queries use default staleTime (0) for freshness
- Credential masking in EmailTab (T034) never sends `new_password` unless edit mode was explicitly activated — critical security behavior
- Self-suspension prevention (T016, T018) compares `user.id` with `useAuthStore().user.id` — never relies on `available_actions` alone for the current user's own row
- Test MSW handlers for 412 responses should be set up as `server.use(rest.patch(..., ctx.status(412)))` overrides within specific test cases
