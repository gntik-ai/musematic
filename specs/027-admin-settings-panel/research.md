# Research: Admin Settings Panel

**Branch**: `027-admin-settings-panel` | **Date**: 2026-04-12 | **Phase**: 0

## Decision Log

### Decision 1 — Page Route and Tab Structure
- **Decision**: `apps/web/app/(main)/admin/settings/page.tsx` with a `<AdminSettingsPanel>` client component using shadcn/ui `Tabs` + `TabsList` + `TabsTrigger` + `TabsContent`. Tab routing via URL query param `?tab=users` (default: `users`), synced with Next.js `useRouter` + `useSearchParams`.
- **Rationale**: URL-based tab routing makes each tab deep-linkable (e.g., `/admin/settings?tab=quotas`) and preserves tab state on refresh. `useSearchParams` reads the current tab; `useRouter.push` updates it on tab change. shadcn/ui `Tabs` is the mandated component system.
- **Alternatives considered**: Hash-based routing (`#users`) — rejected; `useSearchParams` is idiomatic App Router. In-memory tab state with Zustand — rejected; URL state is better UX (shareable, browser back/forward works).

### Decision 2 — Route Guard (Admin-Only Access)
- **Decision**: Route guard implemented as a Next.js middleware check at the `(main)/admin/` route group layout level (`layout.tsx`). Reads the user's role from the existing auth store (Zustand); if not `platform_admin`, redirects to `/home` with a 403 toast. The guard runs client-side (in the layout), not as a true Next.js middleware, to avoid edge runtime constraints.
- **Rationale**: Platform admin is a global role, not workspace-scoped. Consistent with the existing `requiredRoles` RBAC filter pattern in the feature 015 scaffold sidebar. A layout-level guard is simpler than per-page checks and applies uniformly to all routes under `(main)/admin/`.
- **Alternatives considered**: Next.js middleware in `middleware.ts` — rejected because reading Zustand auth state from edge runtime is not possible without a separate session cookie approach. Per-page `useEffect` guard — rejected as it causes a visible flash before redirect.

### Decision 3 — Users Tab: Server-Side DataTable
- **Decision**: The Users tab uses the existing shared `DataTable` component (feature 015 scaffold) with server-side pagination, search, and filtering. `useAdminUsers` hook uses TanStack Query with query params `{ search, status, page, sort }`. User actions (approve, reject, suspend, reactivate) use `useMutation` with optimistic row status update. A shadcn/ui `AlertDialog` serves as the confirmation dialog for destructive actions.
- **Rationale**: The platform can have many users — server-side pagination is necessary (client-side filtering of thousands of users would be impractical). The existing DataTable supports server-side mode. TanStack Query `useMutation` with optimistic updates prevents stale card UX, consistent with the feature 026 pending actions pattern.
- **Alternatives considered**: Client-side pagination — rejected for scalability. Custom table — rejected; the scaffold's `DataTable` is the mandated primitive. Row actions in a dropdown menu (`DropdownMenu` from shadcn) — accepted for the per-row action menu (approve, suspend, etc.) since row inline buttons would be too crowded.

### Decision 4 — Settings Forms: React Hook Form + Zod
- **Decision**: All five settings tabs (Signup, Quotas, Connectors, Email, Security) use React Hook Form with Zod validation schemas. `useForm<T>` initialized with `defaultValues` from TanStack Query data. `onSubmit` calls a `useMutation` that PATCHes the relevant settings endpoint. `isDirty` state enables the Save button only when the form has unseen changes.
- **Rationale**: Constitution mandate: React Hook Form + Zod for all forms. `isDirty` prevents accidental re-saves with no changes. Zod schemas enforce validation client-side before submission (FR-019). `defaultValues` from TanStack Query ensures the form always reflects the latest saved state.
- **Alternatives considered**: Uncontrolled form with manual `useState` — rejected (violates constitution). `useForm` reset on query refetch without `isDirty` guard — rejected (would clear user edits when background refetch occurs).

### Decision 5 — Stale Data Detection (Concurrent Editing)
- **Decision**: Each settings API response includes an `updated_at` ISO timestamp. When the user submits a form, the PATCH request includes `If-Unmodified-Since: <loaded_updated_at>`. If the server returns 412 Precondition Failed (another admin modified the settings), a shadcn/ui `Alert` banner appears on the form: "Settings were changed by another administrator. Reload to see the latest values." A "Reload" button calls `queryClient.invalidateQueries()` for that settings key and resets the form.
- **Rationale**: FR-021 requires stale-data warning. The HTTP `If-Unmodified-Since` approach is a clean REST pattern that avoids custom version fields. 412 is the standard response for optimistic concurrency conflict.
- **Alternatives considered**: Polling for changes — rejected as expensive. WebSocket notification of settings changes — over-engineering for an admin-only feature. Version number field in request body — slightly less clean than the standard HTTP header approach.

### Decision 6 — Quotas Tab: Workspace Selector
- **Decision**: The Quotas tab has two sections: "Default Quotas" (numeric inputs for all 5 dimensions) and "Workspace Overrides" (a searchable workspace selector dropdown + override inputs). The workspace selector uses a TanStack Query-backed combobox (shadcn/ui `Command` + `Popover` pattern). Selecting a workspace loads its current override values (or empty if inheriting defaults). The admin can set any subset of the 5 dimensions to override.
- **Rationale**: The two-section layout clearly separates global defaults from per-workspace overrides, matching the spec requirement (FR-011). The combobox pattern is idiomatic for searchable selects in shadcn/ui. Partial overrides (null = inherit default) are simpler than requiring all fields to be set.
- **Alternatives considered**: Inline row in a workspace list table — rejected because the admin needs to see the 5 quota dimensions clearly, which fits a vertical form better than a table row. Separate sub-routes for each workspace — rejected as over-engineering for this admin use case.

### Decision 7 — Email Tab: Credential Masking
- **Decision**: The Email tab uses a controlled form with type toggle (SMTP / SES). Existing credential fields (SMTP password, SES secret key) are displayed as masked `PasswordInput` components showing `"••••••••"`. These fields have `placeholder="unchanged"` when not editing. To update a credential, the admin clicks an "Update" button next to the field, which clears the masked value and allows entering a new one. On save, only the fields with new (unmasked) values are sent to the backend. A "Send Test Email" inline form uses `useMutation` with a 10-second timeout.
- **Rationale**: FR-016 mandates credential masking. The "click to update" pattern (used in Stripe, GitHub API keys) prevents accidental credential replacement while making it clear how to update. Sending only changed fields avoids re-encrypting credentials that haven't changed.
- **Alternatives considered**: Always-empty password fields requiring re-entry on every save — rejected as terrible UX (admin would need to remember/paste credentials on every form submission). Separate "Credentials" sub-section — slightly more complexity than needed for this use case.

### Decision 8 — Connectors Tab: Toggle List
- **Decision**: The Connectors tab renders a list of connector type cards using shadcn/ui `Card` with a `Switch` toggle on each. `useConnectorTypes` hook fetches the list. Each toggle change immediately calls `useMutation` (no Save button needed — each toggle is an independent atomic operation). A `Badge` shows "Active instances: N" for disabled types that have existing instances, with an `AlertTriangle` icon warning.
- **Rationale**: Toggle switches for independent boolean settings are better UX than a Save button (instant feedback, no accidental batch-disable). The "Active instances" badge addresses the spec's edge case (existing instances remain functional). Atomic per-toggle saves avoid partial-save states.
- **Alternatives considered**: Toggle list with a master Save button — rejected; auto-save on toggle is more intuitive for boolean settings. Checkboxes instead of switches — rejected; `Switch` is the idiomatic shadcn/ui component for on/off settings.

### Decision 9 — API Endpoints Consumed
- **Decision**: Eight backend API endpoint groups consumed:
  1. `GET/PATCH /api/v1/admin/users` — user list + management actions (accounts BC, feature 016)
  2. `POST /api/v1/admin/users/{id}/approve|reject|suspend|reactivate` — user lifecycle actions
  3. `GET/PATCH /api/v1/admin/settings/signup` — signup mode + MFA policy (auth BC, feature 014)
  4. `GET/PATCH /api/v1/admin/settings/quotas` — default quotas (workspaces BC, feature 018)
  5. `GET/PATCH /api/v1/admin/settings/quotas/workspaces/{ws_id}` — per-workspace quota override
  6. `GET/PATCH /api/v1/admin/settings/connectors/{type_slug}` — connector type global config (connectors BC, feature 025)
  7. `GET/PATCH /api/v1/admin/settings/email` — email delivery config (notifications BC); `POST /api/v1/admin/settings/email/test`
  8. `GET/PATCH /api/v1/admin/settings/security` — security policy (auth BC)
- **Rationale**: Admin settings are aggregated under `/api/v1/admin/settings/` prefix for clear access control at the API gateway level. Each settings domain has its own endpoint for independent updates and caching.
- **Alternatives considered**: Single `/api/v1/admin/settings` endpoint returning all settings — rejected; updating a single setting would require sending all settings, risking accidental overwrites. Separate BFF — not needed; the admin panel's endpoints are straightforward enough for direct API consumption.

### Decision 10 — Testing Strategy
- **Decision**: Vitest + RTL for component unit tests (each tab independently). MSW handlers for all 8 API endpoint groups. Playwright e2e for critical admin flows (approve user, change signup mode, save security settings). Coverage target: 95% (SC-011).
- **Rationale**: Consistent with feature 015 scaffold and feature 026 testing approach. MSW allows testing each tab in isolation without a running backend.
- **Alternatives considered**: No e2e tests for admin — rejected; user approval and security policy changes are too critical for unit tests alone.

### Decision 11 — Form Save Feedback
- **Decision**: Each settings form (Signup, Quotas, Email, Security) shows a "Save" button that is disabled when `!isDirty` or during mutation (`isPending`). On successful save, the button briefly shows "Saved ✓" state (1.5s) before returning to "Save". On error, a shadcn/ui `Alert` appears below the form with the error message. The Connectors tab uses per-toggle auto-save with individual loading spinners on each `Switch`.
- **Rationale**: Clear save state prevents the "did my change persist?" confusion. 1.5s success state gives visual confirmation without blocking the user. Per-toggle auto-save avoids a "Save" button for toggle-only interfaces.
- **Alternatives considered**: Global toast for save success — less prominent for settings forms where the user needs clear confirmation. Inline success messages per field — too granular for form-level saves.

### Decision 12 — Mobile Layout for Admin Settings
- **Decision**: On mobile (< 768px), the tab list (`TabsList`) switches from horizontal to a vertical accordion-style nav on the left, using Tailwind `flex-col`. Tab content takes full width. The DataTable on mobile collapses to a card list view (existing DataTable responsive mode from feature 015). Form inputs stack vertically (already default). Quick action buttons in the Users tab collapse into a single dropdown menu per row.
- **Rationale**: Admin settings is primarily a desktop use case, but the spec requires 320px+ support (FR-024, SC-008). Accordion-style vertical tabs are common on mobile admin UIs (e.g., Netlify, Vercel). The DataTable's existing responsive card mode handles the Users tab automatically.
- **Alternatives considered**: Full-width horizontal scrolling tabs on mobile — rejected as poor UX for 6 tabs. Hidden tabs behind a hamburger — rejected as too much discovery friction.
