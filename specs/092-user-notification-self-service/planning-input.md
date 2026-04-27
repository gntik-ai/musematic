# UPD-042 — User-Facing Notification Center and Self-Service Security

## Brownfield Context

**Current state (verified in repo):**
- Backend `notifications/router.py`, `notifications/deliverers/{email,webhook}_deliverer.py`, WebSocket hub — fully implemented.
- Backend `auth/mfa.py` + endpoints `/mfa/enroll`, `/mfa/confirm`, `/mfa/verify` — fully implemented.
- Backend `auth/router.py` with `/logout-all`, `/service-accounts` endpoints — present.
- UI has `/profile/page.tsx`, `/settings/page.tsx`, `/login/page.tsx` (with MFA challenge in flow).

**Gaps:**
1. **No notification center UI** — users receive emails and WebSocket events but can never see a history of notifications in the app. No bell icon with unread badge. No preferences page per channel / event type.
2. **No self-service API keys page** — UPD-036 added admin global view (`/admin/api-keys`); users have no page to manage their own tokens.
3. **No MFA self-service page** — users enroll via fragmented UI during login flow; no dedicated `/settings/security/mfa` with QR viewer, backup codes, disable with step-up.
4. **No session management for users** — users can't see their own active sessions or revoke them individually; only admin can (UPD-036).
5. **No consent management for users** — UPD-037 adds consent at signup but users can't view or revoke later.
6. **No self-service DSR submission** — UPD-023 added admin queue; FR-466 says rights "shall be exposable via admin API and UI" but the subject themselves has no portal.

**Extends:**
- UPD-023 Privacy Compliance (user-side DSR submission complements admin queue).
- UPD-028 Notification Channels (notification center is the in-app channel surface).
- UPD-032 Content Safety & Fairness (consent UI complements backend).
- UPD-036 Administrator Workbench (admin already has everything users need for themselves).
- UPD-037 Signup + OAuth (consent captured at signup now needs ongoing management).

**FRs:** FR-649 through FR-657 (section 115).

---

## Summary

UPD-042 brings user-facing surfaces for capabilities that currently exist only as backend endpoints or admin-side functionality. It is almost entirely frontend work — the backend is proven. The feature delivers:

- `/notifications` inbox with real-time updates, filters, bulk actions
- `<NotificationBell>` component on the global shell with unread badge
- `/settings/notifications` preferences matrix (event × channel)
- `/settings/api-keys` self-service tokens
- `/settings/security/mfa` enrollment with QR + backup codes
- `/settings/security/sessions` view and revoke own sessions
- `/settings/privacy/consent` view and revoke consents
- `/settings/privacy/dsr` self-service DSR submission
- `/settings/security/activity` user audit trail filtered to their own actions

Every surface exposes an already-existing backend capability that today is buried or admin-only.

---

## User Scenarios

### User Story 1 — User reviews missed notifications (Priority: P1)

A user was offline yesterday. They log in and want to catch up on what happened.

**Independent Test:** Generate 15 notifications for a test user while offline. User logs in; bell shows unread 15; clicks bell to see recent 5; clicks "See all" to reach `/notifications`; filters to "last 24h"; marks all read.

**Acceptance:**
1. Bell badge shows accurate unread count within 3 seconds of login.
2. Clicking bell reveals dropdown with 5 most recent notifications.
3. `/notifications` shows paginated list with all notifications.
4. Filtering by channel / severity / event type / date range / read state narrows results server-side.
5. "Mark all as read" bulk action clears unread badge.
6. Individual drill-down navigates to the originating resource (execution, goal, incident).
7. Notifications older than retention window (90 days default) are archived and no longer appear in the inbox.

### User Story 2 — User configures notification preferences (Priority: P1)

A user wants email only for critical events, Slack for everyday updates, and does not want SMS.

**Independent Test:** Navigate to `/settings/notifications`. Configure event × channel matrix. Save. Generate events of different severities and verify delivery only through chosen channels.

**Acceptance:**
1. Preferences page shows full event × channel matrix clearly laid out.
2. Digest mode per channel (immediate / hourly / daily) configurable.
3. Quiet hours (do-not-disturb window) per channel with timezone awareness.
4. Mandatory events (security, incidents) cannot be fully disabled — setting is forced-on with tooltip explanation.
5. Changes persist and apply immediately (no delay beyond cache flush).
6. Test notification action (per event type) triggers a real delivery to verify routing works.

### User Story 3 — Developer manages their personal API tokens (Priority: P1)

A developer writing a custom integration needs a long-lived token with narrow scope.

**Independent Test:** Navigate to `/settings/api-keys`. Create a new token with read-only scope and 30-day expiry. Copy the value once. Try to view it again — not possible. Use it to call `/api/v1/me` successfully. Revoke it. Verify subsequent calls fail.

**Acceptance:**
1. Create form: name, scope selection (subset of platform permissions), expiry (default 90d, max 1y configurable per tenant).
2. Token value displayed exactly once with prominent copy action and warning.
3. After dismissal, token value is never retrievable.
4. List view shows name, scope, created-at, last-used, expires-at, revoke action.
5. MFA step-up required for token creation when MFA is enabled for the user.
6. Revocation takes effect immediately (backend token blacklist / DB flag).

### User Story 4 — User enrolls in MFA (Priority: P1)

A user decides to enable MFA on their account.

**Independent Test:** Navigate to `/settings/security/mfa`. Click "Enable MFA". Scan QR with authenticator app. Enter TOTP code to confirm. Receive backup codes once. Log out and log in again — MFA challenge appears.

**Acceptance:**
1. MFA status panel clearly shows enrolled / not-enrolled / pending.
2. Enrollment flow: QR code + text secret + manual-entry fallback + TOTP confirmation step.
3. Backup codes generated and displayed exactly once after confirmation.
4. Regenerate backup codes action requires current TOTP step-up.
5. Disable MFA action requires password + current TOTP step-up (and blocked when admin policy enforces MFA).
6. Events emit audit chain entries (enrollment, disable, backup codes regen).

### User Story 5 — User revokes a stolen session (Priority: P2)

A user realizes they forgot to log out on a public computer.

**Independent Test:** Navigate to `/settings/security/sessions`. See current session and the public-computer session. Revoke the latter. Verify public-computer session is logged out within 60s.

**Acceptance:**
1. Sessions list shows device type, user-agent summary, city-level geolocation, creation / last-active timestamps.
2. Current session visually distinguished (badge "This session").
3. Revoke action per session + "Revoke all other sessions" bulk action.
4. Revocation propagates within 60 seconds across all pods.
5. Revoked sessions return 401 on next API call with clear message.

### User Story 6 — User submits their own data subject request (Priority: P1)

An EU user wants to download all data the platform holds about them.

**Independent Test:** Navigate to `/settings/privacy/dsr`. Select "Access (download my data)". Confirm. Receive email with download link. Download ZIP with data.

**Acceptance:**
1. Self-service DSR page lists rights: access, rectification, erasure, portability, restriction, objection.
2. Submission pre-fills subject field with current user's identity.
3. Submission triggers the same backend workflow as admin-initiated DSR per UPD-023.
4. User sees their pending and past requests with status, filed-at, completed-at.
5. Erasure explicitly shows irreversibility warning before submission.
6. Audit chain entry emitted with `source=self_service`.

### User Story 7 — User revokes AI disclosure consent (Priority: P2)

A user changes their mind about AI interaction and wants to revoke the consent they gave at signup.

**Independent Test:** Navigate to `/settings/privacy/consent`. See the list of consents. Click revoke on AI disclosure. See the consequences dialog. Confirm. Verify flag changes and platform restricts AI features per policy.

**Acceptance:**
1. Consent list shows type, granted-at, version, current state.
2. Revoke action shows consequences dialog per consent type.
3. Revocation emits audit chain entry.
4. Policy-driven side effects take effect (e.g., AI-dependent features disabled with clear banner).
5. Consent history tab shows chronological grants and revocations.
6. On policy version change, user sees refresh prompt on next login to re-consent or revoke.

---

### Edge Cases

- **Notification volume spike**: user receives 10,000 notifications in an hour (e.g., budget-alert storm). Inbox must paginate; digest mode for that event type auto-enables with user confirmation banner.
- **User revokes their current session**: API returns clear error; UI shows "You can't revoke the session you're currently using".
- **User disables MFA while admin policy enforces it**: disable action blocked with clear message referring to admin policy.
- **API token creation with insufficient scope privileges**: user requests scope they don't have themselves; backend returns 403; UI surfaces clear rejection.
- **DSR erasure with active executions**: surface clear warning that pending executions will fail; require typed confirmation.
- **Concurrent consent revocation and new interaction**: interactions post-revocation are blocked per policy; grace window for in-flight.

---

## UI Routes (Next.js)

```
apps/web/app/(main)/
├── notifications/
│   └── page.tsx                       # NEW: full inbox with filters
├── settings/
│   ├── page.tsx                       # existing
│   ├── notifications/
│   │   └── page.tsx                   # NEW: preferences matrix
│   ├── api-keys/
│   │   └── page.tsx                   # NEW: self-service tokens
│   ├── security/
│   │   ├── page.tsx                   # NEW: security overview
│   │   ├── mfa/page.tsx               # NEW: MFA enrollment
│   │   ├── sessions/page.tsx          # NEW: session management
│   │   └── activity/page.tsx          # NEW: user audit trail
│   └── privacy/
│       ├── consent/page.tsx           # NEW: consent management
│       └── dsr/page.tsx               # NEW: self-service DSR
```

## Shared Components

- `<NotificationBell>` — global shell component with badge, dropdown, WebSocket subscription to `user.notification.new`
- `<NotificationListItem>` — reusable row for inbox and dropdown
- `<NotificationFilters>` — filter UI for inbox
- `<EventChannelMatrix>` — preferences matrix with digest / quiet-hours controls
- `<APIKeyCreateDialog>` — modal with one-time display pattern
- `<MfaEnrollFlow>` — stepper: enable → QR → confirm → backup codes
- `<BackupCodesDisplay>` — one-time render with copy / download actions
- `<SessionList>` — list of user's own sessions
- `<ConsentCard>` — per-consent card with revoke action
- `<DsrSubmissionForm>` — multi-step DSR form with irreversibility warnings

## Backend Additions

Minimal. Mostly the backend already supports these flows; gaps to fill:
- `GET /api/v1/me/notifications` (new): paginated user's own notifications with filters.
- `POST /api/v1/me/notifications/mark-all-read` / `POST /api/v1/me/notifications/{id}/mark-read`.
- `GET /api/v1/me/notification-preferences` / `PUT`.
- `GET /api/v1/me/api-keys` / `POST` / `DELETE /{id}` (scoped to current user; complements admin `/admin/api-keys`).
- `GET /api/v1/me/sessions` / `DELETE /{id}` / `POST /revoke-others`.
- `GET /api/v1/me/consent` / `POST /revoke`.
- `POST /api/v1/me/dsr` / `GET /api/v1/me/dsr` (user-scoped submission routes alongside admin endpoints).
- `GET /api/v1/me/activity` (user's own audit trail entries).

All new endpoints are scoped to `current_user` and never accept a `user_id` parameter to prevent authorization confusion.

## Acceptance Criteria

- [ ] `<NotificationBell>` renders in the global shell on authenticated pages
- [ ] Unread badge updates in real time via WebSocket
- [ ] `/notifications` paginates, filters, search, bulk actions all functional
- [ ] `/settings/notifications` matrix persists and takes effect
- [ ] `/settings/api-keys` create shows value once; revocation takes immediate effect
- [ ] MFA page: enroll, backup codes, regenerate, disable flows all working
- [ ] Session management revokes within 60s
- [ ] Consent revocation emits audit chain entry and triggers side effects
- [ ] Self-service DSR submission produces same result as admin-initiated
- [ ] All new pages pass axe-core AA (zero violations)
- [ ] All new pages localized in 6 languages
- [ ] Extended J03 Consumer journey covers notification center and consent flow
- [ ] Extended J10 Privacy Officer journey cross-links admin-DSR with self-service-DSR
