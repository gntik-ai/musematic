# Quickstart: Admin Settings Panel

**Branch**: `027-admin-settings-panel` | **Date**: 2026-04-12 | **Phase**: 1

Test scenarios for manual verification of all six admin settings tabs. Assumes MSW handlers are active for API mocking.

---

## Prerequisites

- Authenticated as a `platform_admin` user
- MSW handlers registered for all 8 API endpoint groups
- Navigate to `/admin/settings`

---

## Scenario 1 — Route Guard (Non-Admin Access Denied)

**Goal**: Verify non-admin users cannot access admin settings.

**Steps**:
1. Log in as a `workspace_owner` (non-admin) user
2. Navigate directly to `/admin/settings`

**Expected**:
- Redirected to `/home`
- Toast notification: "You do not have permission to access admin settings"
- URL in browser is `/home`, not `/admin/settings`

---

## Scenario 2 — Users Tab: Search and Filter

**Goal**: Verify user table loads and filtering works correctly.

**Setup**: MSW returns 50 users with mixed statuses (active, pending_approval, suspended).

**Steps**:
1. Verify page loads with Users tab active (default)
2. Verify table shows user rows with columns: Name, Email, Status, Role, Last Login, Created
3. Type "john@example.com" in the search input
4. Wait 300ms (debounce)
5. Click the Status filter dropdown, select "pending_approval"

**Expected**:
- Initial table shows first 20 users (paginated)
- After search: table filters to matching users
- After status filter: table shows only `pending_approval` users matching search
- Status badges render with correct colors (pending_approval = yellow, active = green, suspended = orange)

---

## Scenario 3 — Users Tab: Approve a Pending User

**Goal**: Verify the approve action flow with confirmation dialog.

**Setup**: MSW returns a user with `status: "pending_approval"` and `available_actions: ["approve", "reject"]`.

**Steps**:
1. Locate the pending user row
2. Click the Actions menu (kebab/ellipsis) for that row
3. Verify "Approve" and "Reject" actions are available (not "Suspend" or "Reactivate")
4. Click "Approve"
5. Verify confirmation dialog appears with user's name
6. Click "Confirm" in the dialog

**Expected**:
- Dialog shows: "Approve [User Name]? This will grant them access to the platform."
- After confirm: dialog closes
- User row's status badge optimistically updates to "active"
- MSW receives `POST /api/v1/admin/users/{id}/approve`
- Table query re-fetches and shows final state

---

## Scenario 4 — Users Tab: Self-Suspension Prevention

**Goal**: Verify admin cannot suspend their own account.

**Setup**: MSW marks the current admin's user row with no suspend action available.

**Steps**:
1. Locate the row for the currently logged-in admin
2. Click Actions menu

**Expected**:
- "Suspend" action is absent (or disabled with tooltip: "You cannot suspend your own account")
- Other admin users show the Suspend action normally

---

## Scenario 5 — Signup Policy Tab: Change Signup Mode

**Goal**: Verify settings form saves with stale-data protection.

**Steps**:
1. Click the "Signup" tab
2. Verify current signup mode is displayed (e.g., "open")
3. Select "invite_only"
4. Verify Save button enables (form is dirty)
5. Click Save
6. Verify "Saving…" state on button
7. After success: verify "Saved ✓" shows for ~1.5s, then button returns to "Save" (disabled)
8. Navigate away to another tab and back
9. Verify "invite_only" is still selected

**Expected**:
- `PATCH /api/v1/admin/settings/signup` called with `If-Unmodified-Since` header
- Form `isDirty` resets to false after successful save
- Values persist after tab navigation (re-fetched from server)

---

## Scenario 6 — Signup Policy Tab: Stale Data Detection

**Goal**: Verify 412 response triggers the StaleDataAlert.

**Setup**: MSW configured to return `412 Precondition Failed` on the PATCH endpoint.

**Steps**:
1. Navigate to Signup tab
2. Change MFA enforcement to "required"
3. Click Save

**Expected**:
- Alert banner appears: "Settings were changed by another administrator. Reload to see the latest values."
- "Reload" button visible
- Form values remain as edited (not reset yet)
- Clicking "Reload" triggers `GET /api/v1/admin/settings/signup` + resets form to server values
- Alert banner disappears after reload

---

## Scenario 7 — Quotas Tab: Default Quotas

**Goal**: Verify default quota form saves correctly.

**Steps**:
1. Click the "Quotas" tab
2. Verify 5 numeric inputs are visible (max_agents, max_concurrent_executions, max_sandboxes, monthly_token_budget, storage_quota_gb)
3. Change "Max Agents" from 100 to 200
4. Click Save

**Expected**:
- `PATCH /api/v1/admin/settings/quotas` called with updated value
- Success state shown on Save button
- Input remains at 200 after save

---

## Scenario 8 — Quotas Tab: Workspace Override

**Goal**: Verify per-workspace quota override using the combobox selector.

**Steps**:
1. In the Quotas tab, locate the "Workspace Overrides" section
2. Click the workspace combobox, type "acme" to search
3. Select "Acme Corp" workspace from results
4. Verify the 5 quota inputs load with the workspace's current overrides (or blank if inheriting)
5. Set Max Agents override to 500 (leave others blank/null)
6. Click Save Override

**Expected**:
- `GET /api/v1/admin/settings/quotas/workspaces/{id}` called when workspace selected
- `PATCH /api/v1/admin/settings/quotas/workspaces/{id}` called on save
- Null fields sent as `null` (inherit default)
- Save confirmation shown

---

## Scenario 9 — Connectors Tab: Toggle Disable

**Goal**: Verify per-toggle auto-save with warning for existing instances.

**Setup**: MSW returns connector types; "Email" connector has `active_instance_count: 3`.

**Steps**:
1. Click the "Connectors" tab
2. Verify 4 connector type cards: Slack, Telegram, Webhook, Email
3. Locate Email card — verify "3 active instances" badge with warning icon
4. Toggle Email connector to disabled
5. Verify immediate loading state on the toggle

**Expected**:
- No "Save" button — toggle auto-saves immediately
- `PATCH /api/v1/admin/settings/connectors/email` called with `{ is_enabled: false }`
- Optimistic update: toggle visually disabled immediately
- Warning badge remains visible ("type disabled" warning)
- If API fails: toggle reverts to enabled state

---

## Scenario 10 — Email Tab: Credential Masking

**Goal**: Verify SMTP credentials are masked and only updated when explicitly editing.

**Setup**: MSW returns email config with `password_set: true`.

**Steps**:
1. Click the "Email" tab
2. Verify SMTP host, port, username are visible
3. Verify password field shows `"••••••••"` (masked placeholder)
4. Click "Update Password" button next to the masked field
5. Verify the field clears and becomes an editable text input
6. Type a new password
7. Click Save

**Expected**:
- Initial state: password shows `"••••••••"`, not editable
- After "Update Password": field is cleared and editable
- On save: `new_password` field included in PATCH body
- If save without clicking "Update Password": `new_password` NOT sent in PATCH body

---

## Scenario 11 — Email Tab: Send Test Email

**Goal**: Verify test email flow with success and error states.

**Steps**:
1. Navigate to Email tab
2. Locate "Send Test Email" section
3. Enter recipient email "test@example.com"
4. Click "Send Test Email"
5. Verify loading state

**Success scenario** (MSW returns `{ success: true, message: "Test email sent successfully" }`):
- Success message appears below the form
- Button re-enables

**Failure scenario** (MSW returns `{ success: false, message: "SMTP connection refused" }`):
- Error message appears in a red Alert

---

## Scenario 12 — Security Tab: Password Policy

**Goal**: Verify security settings form with Zod validation.

**Steps**:
1. Click the "Security" tab
2. Verify current password policy values are pre-populated
3. Change "Min Password Length" to 7 (below minimum of 8)
4. Verify inline validation error: "Minimum 8 characters"
5. Change to 16
6. Verify error clears
7. Set "Session Duration" to 10 (below minimum of 15 minutes)
8. Verify validation error: "Minimum 15 minutes"
9. Set to 60 and Save

**Expected**:
- Validation errors appear inline (React Hook Form + Zod)
- Save button remains disabled while validation errors exist
- Informational banner: "Changes apply only to new authentication events"
- On save: `PATCH /api/v1/admin/settings/security` called with updated values

---

## Scenario 13 — Mobile Layout

**Goal**: Verify responsive behavior at 320px viewport width.

**Steps**:
1. Resize browser to 320px width
2. Navigate to `/admin/settings`

**Expected**:
- Tab list renders as vertical accordion (not horizontal)
- No horizontal scroll visible
- DataTable in Users tab renders as card list (scaffold responsive mode)
- Form inputs stack vertically
- All actions accessible via keyboard

---

## Scenario 14 — Dark Mode

**Goal**: Verify all tabs render correctly in dark mode.

**Steps**:
1. Enable dark mode (via app theme toggle)
2. Navigate through all 6 tabs

**Expected**:
- All cards, inputs, badges, and alerts use dark theme tokens
- No white/light backgrounds visible against dark background
- Status badges maintain readable contrast (WCAG AA)
- `StaleDataAlert` and error Alerts visible in dark mode

---

## MSW Handler Summary

```typescript
// apps/web/tests/mocks/handlers/admin.ts

// Users
rest.get('/api/v1/admin/users', usersHandler),
rest.post('/api/v1/admin/users/:id/approve', approveHandler),
rest.post('/api/v1/admin/users/:id/reject', rejectHandler),
rest.post('/api/v1/admin/users/:id/suspend', suspendHandler),
rest.post('/api/v1/admin/users/:id/reactivate', reactivateHandler),

// Settings
rest.get('/api/v1/admin/settings/signup', signupGetHandler),
rest.patch('/api/v1/admin/settings/signup', signupPatchHandler),
rest.get('/api/v1/admin/settings/quotas', quotasGetHandler),
rest.patch('/api/v1/admin/settings/quotas', quotasPatchHandler),
rest.get('/api/v1/admin/settings/quotas/workspaces/:wsId', wsQuotaGetHandler),
rest.patch('/api/v1/admin/settings/quotas/workspaces/:wsId', wsQuotaPatchHandler),
rest.get('/api/v1/admin/workspaces', workspacesSearchHandler),
rest.get('/api/v1/admin/settings/connectors', connectorsGetHandler),
rest.patch('/api/v1/admin/settings/connectors/:slug', connectorPatchHandler),
rest.get('/api/v1/admin/settings/email', emailGetHandler),
rest.patch('/api/v1/admin/settings/email', emailPatchHandler),
rest.post('/api/v1/admin/settings/email/test', emailTestHandler),
rest.get('/api/v1/admin/settings/security', securityGetHandler),
rest.patch('/api/v1/admin/settings/security', securityPatchHandler),
```
