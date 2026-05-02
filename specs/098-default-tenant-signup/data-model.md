# Phase 1 — Data Model

**Feature**: UPD-048 — Public Signup at Default Tenant Only
**Date**: 2026-05-02

This document specifies the database schema introduced or modified by UPD-048. Two new tables, both tenant-scoped per UPD-046 conventions.

## Entity 1 — `UserOnboardingState`

**Owning bounded context**: `apps/control-plane/src/platform/accounts/`
**Table**: `user_onboarding_states`
**Owner**: `accounts/models.py`
**Migration**: `106_user_onboarding_states.py`
**RLS**: Tenant-scoped per UPD-046 conventions.

### Columns

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK, `DEFAULT gen_random_uuid()` | |
| `tenant_id` | `UUID` | `NOT NULL REFERENCES tenants(id)` | UPD-046 convention. |
| `user_id` | `UUID` | `NOT NULL REFERENCES users(id)` | |
| `step_workspace_named` | `BOOLEAN` | `NOT NULL DEFAULT false` | Step 1 completion. |
| `step_invitations_sent_or_skipped` | `BOOLEAN` | `NOT NULL DEFAULT false` | Step 2 completion (either invited teammates OR skipped). |
| `step_first_agent_created_or_skipped` | `BOOLEAN` | `NOT NULL DEFAULT false` | Step 3 completion. Hidden if UPD-022 not deployed. |
| `step_tour_started_or_skipped` | `BOOLEAN` | `NOT NULL DEFAULT false` | Step 4 completion. |
| `last_step_attempted` | `VARCHAR(32)` | `NOT NULL DEFAULT 'workspace_named'`, `CHECK (last_step_attempted IN ('workspace_named', 'invitations', 'first_agent', 'tour', 'done'))` | Resume position. |
| `dismissed_at` | `TIMESTAMPTZ` | NULL | Set when user clicks "Dismiss". Re-launch from Settings clears this. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT now()` | |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT now()` | Auto-updated via TimestampMixin pattern. |

### Indexes

- `user_onboarding_states_pkey` (implicit on `id`).
- `user_onboarding_states_user_unique` UNIQUE on `(user_id)` — at most one onboarding state per user.
- `user_onboarding_states_tenant_idx` on `(tenant_id)`.

### RLS

```sql
ALTER TABLE user_onboarding_states ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON user_onboarding_states
  USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
ALTER TABLE user_onboarding_states FORCE ROW LEVEL SECURITY;
```

## Entity 2 — `TenantFirstAdminInvitation`

**Owning bounded context**: `apps/control-plane/src/platform/accounts/`
**Table**: `tenant_first_admin_invitations`
**Owner**: `accounts/models.py`
**Migration**: `107_tenant_first_admin_invitations.py`
**RLS**: Tenant-scoped per UPD-046 conventions.

### Columns

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK, `DEFAULT gen_random_uuid()` | |
| `tenant_id` | `UUID` | `NOT NULL REFERENCES tenants(id)` | The Enterprise tenant being onboarded. |
| `token_hash` | `VARCHAR(128)` | `NOT NULL UNIQUE` | SHA-256 hash of the single-use token; the raw token never persists. |
| `target_email` | `VARCHAR(320)` | `NOT NULL` | First admin's email. |
| `expires_at` | `TIMESTAMPTZ` | `NOT NULL` | Default 7 days from `created_at`; configurable via `signup.firstAdminInviteTtlDays`. |
| `consumed_at` | `TIMESTAMPTZ` | NULL | Set once when the user completes the setup flow. |
| `prior_token_invalidated_at` | `TIMESTAMPTZ` | NULL | Set on this row when this token is superseded by a resend. |
| `setup_step_state` | `JSONB` | `NOT NULL DEFAULT '{}'::jsonb` | Tracks completion per setup step (TOS, password, MFA, workspace, invitations). |
| `mfa_required` | `BOOLEAN` | `NOT NULL DEFAULT true` | Always true for first-admin role; field exists for forward-compat with future role-specific overrides. |
| `created_by_super_admin_id` | `UUID` | `NOT NULL REFERENCES users(id)` | Super admin who issued the invitation. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT now()` | |
| `consumed_by_user_id` | `UUID` | NULL | The newly-created tenant-admin user record once setup completes. |

### Indexes

- `tenant_first_admin_invitations_pkey` (implicit).
- `tenant_first_admin_invitations_token_unique` UNIQUE on `(token_hash)`.
- `tenant_first_admin_invitations_tenant_active_idx` on `(tenant_id, expires_at)` `WHERE consumed_at IS NULL AND prior_token_invalidated_at IS NULL` — for "find the active invitation for this tenant" queries (used by resend).
- `tenant_first_admin_invitations_target_email_idx` on `(target_email, expires_at)` — for invitation-acceptance lookups.

### RLS

Same pattern as `user_onboarding_states`. Cross-tenant lookups use the platform-staff session; super admin lookups always scope to the resolved tenant via `request.state.tenant`.

### State machine — `TenantFirstAdminInvitation` lifecycle

```text
   (super admin issues)
         │
         ↓
   ┌───────────┐
   │  pending  │ ── (user consumes by completing setup) ──→ ┌─────────────┐
   └───────────┘                                             │  consumed   │
         │ (super admin clicks "Resend")                     └─────────────┘
         ↓
   ┌────────────────────┐  (a fresh row is created;
   │ prior_invalidated  │   this row is terminal and inert)
   └────────────────────┘

   ┌───────────┐
   │  pending  │ ── (expires_at <= now()) ──→ (effectively expired; no row state change;
   └───────────┘                                acceptance attempts return the standard
                                                "expired link" surface)
```

Resend invalidates the prior row's `prior_token_invalidated_at` and creates a new row with a fresh `token_hash`. The prior row is preserved for audit-chain replay.

## Modification — `Workspace.is_default` partial unique index

**Owning bounded context**: existing `apps/control-plane/src/platform/workspaces/`
**Migration**: included in `106_user_onboarding_states.py` as a small additive index.

The `Workspace` model already has `is_default: Mapped[bool]` (line 88 of `workspaces/models.py`). UPD-048 adds a partial unique index to enforce "at most one default workspace per user":

```sql
CREATE UNIQUE INDEX workspaces_user_default_unique
  ON workspaces (created_by_user_id)
  WHERE is_default = true;
```

This makes `WorkspacesService.create_default_workspace()` idempotent under concurrent calls — the second caller's INSERT raises a unique-violation, the service catches it and returns the existing workspace (per Risk Posture mitigation in plan.md).

## State machine — `UserOnboardingState` wizard progression

```text
   (default-tenant signup verified)
              │
              ↓
   ┌──────────────────────┐
   │  workspace_named     │ ── (rename + Next) ──→ ┌──────────────┐
   └──────────────────────┘                          │ invitations  │
              │                                      └──────────────┘
              │ (Dismiss)                                    │
              ↓                                              │ (Send + Next OR Skip)
   ┌──────────────────────┐                                  ↓
   │  dismissed (any)     │                          ┌──────────────┐
   └──────────────────────┘                          │ first_agent  │
              ↑                                       └──────────────┘
              │ (Dismiss anywhere)                            │
              │                                               │ (Create + Next OR Skip)
              │                                               ↓
              │                                       ┌──────────────┐
              │                                       │  tour        │
              │                                       └──────────────┘
              │                                               │
              │                                               │ (Start tour OR Skip)
              │                                               ↓
              │                                       ┌──────────────┐
              └─────────────────── (re-launch from Settings) ┤  done    │
                                                              └──────────────┘
```

`dismissed_at` is set on Dismiss; re-launch from Settings clears it and resumes at the first incomplete step. The "done" state is terminal but re-launchable (sets `dismissed_at = NULL` and decrements `last_step_attempted` to the first incomplete step).

## Existing tables touched (no schema change, only behaviour)

- **`users`** (UPD-037 / UPD-046 tenant-scoped) — UPD-048 reads `email` and `tenant_id` for the cross-tenant memberships JOIN; no schema change.
- **`oauth_providers`** (UPD-046 migration 102 added `tenant_id`) — the signup page surfaces only providers configured for the resolved tenant; no schema change.
- **`mfa_enrollments`** — first-admin setup requires a verified row; no schema change.
- **`workspaces`** — auto-created on verify-email; only the new `workspaces_user_default_unique` index is added.
- **`subscriptions`** (UPD-047) — auto-provisioned for the new default workspace via `SubscriptionService.provision_for_default_workspace`; no schema change.

## Kafka events emitted

Topic: `accounts.events` (existing — UPD-016). Additive event types:

- `accounts.signup.completed` — emitted post-verification when the default workspace and Free subscription are provisioned. Payload: `user_id`, `email`, `workspace_id`, `subscription_id`, `signup_method` (email/oauth-google/oauth-github), `tenant_id` (always default).
- `accounts.first_admin_invitation.issued` — emitted when super admin provisions an Enterprise tenant. Payload: `tenant_id`, `target_email`, `expires_at`, `super_admin_id`.
- `accounts.first_admin_invitation.resent` — emitted on resend. Payload: `tenant_id`, `target_email`, `prior_token_invalidated_at`, `super_admin_id`.
- `accounts.setup.step_completed` — emitted per setup step. Payload: `tenant_id`, `step` (`tos|password|mfa|workspace|invitations|done`), `user_id`.
- `accounts.cross_tenant_invitation.accepted` — emitted when a user with an existing default-tenant identity accepts an Enterprise invitation. Payload: `default_tenant_user_id`, `enterprise_tenant_id`, `enterprise_user_id`, `email`.
- `accounts.onboarding.step_advanced` — emitted on each wizard step advance. Payload: `user_id`, `tenant_id`, `from_step`, `to_step`.
- `accounts.onboarding.dismissed` — emitted when user dismisses. Payload: `user_id`, `tenant_id`, `dismissed_at_step`.
- `accounts.onboarding.relaunched` — emitted when user re-launches from Settings. Payload: `user_id`, `tenant_id`.

All events follow the canonical `EventEnvelope` shape (UPD-013) with `tenant_id` for partitioning per UPD-046 R7.

## End of data model.
