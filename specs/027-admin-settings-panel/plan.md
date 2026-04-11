# Implementation Plan: Admin Settings Panel

**Branch**: `027-admin-settings-panel` | **Date**: 2026-04-12 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/027-admin-settings-panel/spec.md`

## Summary

Build a platform-admin-only settings panel (`/admin/settings`) with six tabs: Users, Signup, Quotas, Connectors, Email, and Security. Uses shadcn/ui `Tabs` with URL query param routing (`?tab=users`), a server-side `DataTable` for user management, React Hook Form + Zod for all five settings forms, per-toggle auto-save for the Connectors tab, and `If-Unmodified-Since` / 412 stale-data detection for concurrent admin editing. Route guard at the `(main)/admin/` layout level reads Zustand auth store and redirects non-admins to `/home`.

## Technical Context

**Language/Version**: TypeScript 5.x, React 18+, Next.js 14+ App Router
**Primary Dependencies**: shadcn/ui, Tailwind CSS 3.4+, TanStack Query v5, React Hook Form 7.x, Zod 3.x, Zustand 5.x, date-fns 4.x, Lucide React
**Storage**: N/A (frontend-only feature consuming existing backend APIs)
**Testing**: Vitest + React Testing Library + MSW + Playwright
**Target Platform**: Web browser (desktop primary, mobile 320px+ supported)
**Project Type**: Web application frontend feature
**Performance Goals**: Page load < 2s, tab switch < 500ms, search debounce 300ms, settings save < 3s, test email < 10s
**Constraints**: Admin-only access (platform_admin role). Mobile 320px+ supported. WCAG AA contrast. No custom CSS files.
**Scale/Scope**: 6 tabs, 8 API endpoint groups, 5 settings forms, 11 custom hooks, ~20 component files

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Requirement | Status |
|------|-------------|--------|
| §Frontend.shadcn | All UI primitives from shadcn/ui | PASS — Tabs, DataTable, Card, Switch, Form, Dialog, Alert, Command, Popover, Badge all from shadcn |
| §Frontend.Tailwind | No custom CSS files | PASS — utility-first Tailwind only, CSS custom property tokens from scaffold |
| §Frontend.TanStack | TanStack Query for all server state | PASS — 11 hooks covering all 8 API endpoint groups |
| §Frontend.Zustand | Zustand for client state only | PASS — auth store (existing) for route guard; no new Zustand store added |
| §Frontend.RHF | React Hook Form + Zod for all forms | PASS — all 5 settings forms use RHF + Zod; Connectors uses per-toggle mutation (no form) |
| §Frontend.NoClassComponents | Function components only | PASS — all components are function components with hooks |
| §Frontend.NoCustomCSS | No custom CSS | PASS — zero custom CSS files; Tailwind utilities only |
| §XI.Credentials | Credentials never in LLM context / never plaintext | PASS — Email tab shows `password_set: boolean`, uses "click to update" pattern; `new_password` only sent when explicitly editing |
| §III.DedicatedStores | Use dedicated stores per workload | PASS — frontend reads from existing PostgreSQL-backed APIs; no new store decisions |
| §IV.NoCrossBoundaryDB | No cross-boundary DB access | PASS — frontend-only feature; no DB access |
| §I.AppRouter | Next.js App Router, server components where beneficial | PASS — page.tsx as RSC shell, AdminSettingsPanel as "use client" root component |
| SC-011.Coverage | Test coverage ≥ 95% | PASS — Vitest + RTL per tab + Playwright e2e for critical flows |

**Post-design re-check**: All 12 gates PASS. No constitution violations.

## Project Structure

### Documentation (this feature)

```text
specs/027-admin-settings-panel/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0: 12 decisions
├── data-model.md        # Phase 1: TypeScript types, Zod schemas, hooks
├── quickstart.md        # Phase 1: 14 test scenarios
├── checklists/
│   └── requirements.md  # Spec quality checklist (all pass)
└── contracts/
    └── admin-ui.md      # Phase 1: API contracts + component interaction contracts
```

### Source Code

```text
apps/web/
├── app/
│   └── (main)/
│       └── admin/
│           ├── layout.tsx                           # Route guard (platform_admin only)
│           └── settings/
│               └── page.tsx                         # RSC shell → <AdminSettingsPanel>
│
├── components/
│   └── features/
│       └── admin/
│           ├── AdminSettingsPanel.tsx               # "use client" root, tab routing
│           ├── tabs/
│           │   ├── UsersTab.tsx                     # US1: server-side DataTable
│           │   ├── SignupPolicyTab.tsx               # US2: signup mode + MFA form
│           │   ├── QuotasTab.tsx                    # US3: default quotas + workspace override
│           │   ├── ConnectorsTab.tsx                # US4: toggle list
│           │   ├── EmailTab.tsx                     # US5: SMTP/SES form
│           │   └── SecurityTab.tsx                  # US6: password + session + lockout form
│           ├── users/
│           │   ├── UserActionsMenu.tsx              # Per-row dropdown
│           │   └── UserActionDialog.tsx             # Confirmation dialog
│           ├── connectors/
│           │   └── ConnectorTypeCard.tsx            # Card + Switch toggle
│           └── shared/
│               ├── StaleDataAlert.tsx               # 412 banner
│               └── SettingsFormActions.tsx          # Save/Reset buttons
│
├── lib/
│   ├── types/
│   │   └── admin.ts                                 # All admin TypeScript types
│   ├── schemas/
│   │   └── admin.ts                                 # All Zod validation schemas
│   └── hooks/
│       └── use-admin-settings.ts                    # 11 TanStack Query hooks
│
└── tests/
    ├── mocks/
    │   └── handlers/
    │       └── admin.ts                             # MSW handlers (18 endpoints)
    └── features/
        └── admin/
            ├── AdminSettingsPanel.test.tsx
            ├── UsersTab.test.tsx
            ├── SignupPolicyTab.test.tsx
            ├── QuotasTab.test.tsx
            ├── ConnectorsTab.test.tsx
            ├── EmailTab.test.tsx
            ├── SecurityTab.test.tsx
            └── e2e/
                ├── admin-users.spec.ts
                ├── admin-signup.spec.ts
                └── admin-security.spec.ts
```

**Structure Decision**: Feature directory under `components/features/admin/` with sub-directories by domain (tabs/, users/, connectors/, shared/). Mirrors the feature 026 home dashboard pattern for consistency. Types and schemas in `lib/types/admin.ts` and `lib/schemas/admin.ts` to keep them importable from both components and hooks. Route guard in `app/(main)/admin/layout.tsx` — applies uniformly to all future admin routes.

## Implementation Phases

### Phase 1 — Setup & Foundation

**Goal**: Create the route structure, route guard, admin layout, and type/schema files.

**Tasks**:
1. Create `app/(main)/admin/layout.tsx` — route guard reading `useAuthStore().user.role`; redirect + toast if not `platform_admin`
2. Create `app/(main)/admin/settings/page.tsx` — RSC shell importing `<AdminSettingsPanel defaultTab={searchParams.tab} />`
3. Create `lib/types/admin.ts` — all TypeScript types per data-model.md
4. Create `lib/schemas/admin.ts` — all Zod schemas per data-model.md
5. Create `lib/hooks/use-admin-settings.ts` — all 11 TanStack Query hooks (stubs initially)
6. Create `components/features/admin/shared/StaleDataAlert.tsx` — reusable 412 banner
7. Create `components/features/admin/shared/SettingsFormActions.tsx` — Save/Reset buttons with isSaved state

### Phase 2 — Admin Settings Panel Shell & Tab Routing

**Goal**: Create the tabbed panel with URL-based routing.

**Tasks**:
1. Create `AdminSettingsPanel.tsx` — shadcn `Tabs` reading `useSearchParams`, `router.push` on tab change
2. Create stub components for all 6 tabs (empty shell with `<div>Tab content</div>`)
3. Verify tab switching updates URL and survives page refresh (integration test)

### Phase 3 — Users Tab (US1, P1)

**Goal**: Working server-side user table with approve/suspend/reactivate actions.

**Independent Test**: `UsersTab.test.tsx` — MSW mock returns 50 users; verify search debounce, status filter, action dialog flow, optimistic row update, self-suspension prevention.

**Tasks**:
1. Implement `useAdminUsers` hook with TanStack Query
2. Implement `useUserActionMutation` with optimistic status update + rollback on error
3. Implement `UsersTab.tsx` — DataTable (scaffold) with server-side props, search input, status filter
4. Define DataTable column definitions (name, email, status badge, role, last_login, created_at, actions)
5. Implement `UserActionsMenu.tsx` — shadcn DropdownMenu, actions filtered by `available_actions`
6. Implement `UserActionDialog.tsx` — shadcn AlertDialog, confirmation text per action type
7. Disable suspend action on the current admin's own row (compare with auth store user.id)

### Phase 4 — Signup Policy Tab (US2, P1)

**Goal**: Working signup mode + MFA enforcement form with stale-data detection.

**Independent Test**: `SignupPolicyTab.test.tsx` — test form dirty state, save flow, 412 → StaleDataAlert → reload flow.

**Tasks**:
1. Implement `useSignupPolicy` and `useSignupPolicyMutation` hooks
2. Implement `SignupPolicyTab.tsx` — RHF form with `signup_mode` RadioGroup and `mfa_enforcement` Switch
3. Wire `If-Unmodified-Since` header from loaded `updated_at`
4. Handle 412 response: set `isStale` state → render `StaleDataAlert`
5. `StaleDataAlert` reload → `invalidateQueries` + `form.reset(newData)`
6. `isSaved` state: set `true` on success, clear after 1.5s with `setTimeout`

### Phase 5 — Quotas Tab (US3, P2)

**Goal**: Default quotas form + workspace override selector.

**Independent Test**: `QuotasTab.test.tsx` — default quotas save, workspace combobox selection loads override data, partial nulls sent correctly.

**Tasks**:
1. Implement `useDefaultQuotas`, `useWorkspaceQuota` hooks
2. Implement Default Quotas form section — 5 numeric inputs with RHF + `defaultQuotasSchema`
3. Implement workspace combobox — shadcn `Command` + `Popover`, backed by `GET /api/v1/admin/workspaces` search
4. Implement Workspace Override form section — 5 nullable inputs, enabled when workspace selected
5. Wire workspace quota `GET/PATCH` to override form, `enabled: !!selectedWorkspaceId`

### Phase 6 — Connectors Tab (US4, P2)

**Goal**: Toggle list with per-toggle auto-save and active instance warnings.

**Independent Test**: `ConnectorsTab.test.tsx` — toggle calls mutation immediately, optimistic update, API error reverts toggle, warning badge shown for disabled types with active instances.

**Tasks**:
1. Implement `useConnectorTypeConfigs` and `useConnectorTypeToggleMutation` hooks
2. Implement `ConnectorTypeCard.tsx` — shadcn Card + Switch; optimistic toggle; `AlertTriangle` badge when disabled + active_instance_count > 0
3. Implement `ConnectorsTab.tsx` — renders list of ConnectorTypeCard

### Phase 7 — Email Tab (US5, P3)

**Goal**: SMTP/SES form with credential masking and test email.

**Independent Test**: `EmailTab.test.tsx` — masked field not editable initially, "Update Password" reveals input, test email mutation, mode switching resets form.

**Tasks**:
1. Implement `useEmailConfig` and `useSendTestEmailMutation` hooks
2. Implement `EmailTab.tsx` — mode toggle (SMTP/SES), conditional field rendering
3. Implement credential masking: `password_set` renders `"••••••••"` + "Update Password" button; click reveals input + sets `new_password` in form
4. Implement `emailConfigSchema` discriminated union Zod schema (already in schemas file)
5. Implement "Send Test Email" inline form — separate `useForm` instance with `testEmailSchema`
6. Handle 10s timeout scenario (show error if test email takes too long)

### Phase 8 — Security Tab (US6, P3)

**Goal**: Password policy, session duration, lockout settings form.

**Independent Test**: `SecurityTab.test.tsx` — Zod validation errors at boundaries (min_length < 8, session < 15min), save flow, informational banner present.

**Tasks**:
1. Implement `useSecurityPolicy` hook
2. Implement `SecurityTab.tsx` — RHF form with `securityPolicySchema`
3. Add informational shadcn `Alert` (info variant): "Changes apply only to new authentication events — existing sessions are not affected"
4. Wire save with `If-Unmodified-Since` and `StaleDataAlert` handling

### Phase 9 — Polish & Cross-Cutting

**Goal**: Mobile layout, dark mode, accessibility, Playwright e2e tests.

**Tasks**:
1. Mobile: `TabsList` → `flex-col` below 768px breakpoint (`md:flex-row`)
2. Dark mode: verify all shadcn components use theme tokens (no hardcoded colors)
3. Accessibility: verify `aria-label` on all icon-only buttons; verify keyboard tab order; focus trap in dialogs
4. Playwright: `admin-users.spec.ts` — approve user flow, self-suspend prevention
5. Playwright: `admin-signup.spec.ts` — change signup mode, persist across navigation
6. Playwright: `admin-security.spec.ts` — save security settings, validation errors

## Key Decisions

See `research.md` for full rationale. Summary:

1. URL query param tab routing (`?tab=users`) — deep-linkable, browser back/forward works
2. Layout-level route guard — applies to all future `(main)/admin/` routes uniformly
3. Server-side DataTable for Users — scales to thousands of users
4. `If-Unmodified-Since` / 412 for stale-data — standard HTTP pattern, no polling needed
5. Per-toggle auto-save on Connectors — better UX for boolean settings vs master Save
6. "Click to update" credential masking on Email — prevents accidental credential replacement
7. shadcn `Command` + `Popover` combobox for workspace selector — idiomatic shadcn pattern
