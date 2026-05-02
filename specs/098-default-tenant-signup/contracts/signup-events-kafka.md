# Contract — Signup / Onboarding Kafka Events

**Topic**: `accounts.events` (existing — UPD-016). UPD-048 adds 8 new event types additively.
**Owner**: `apps/control-plane/src/platform/accounts/events.py`
**Producers**: `AccountsService`, `TenantFirstAdminInviteService`, `OnboardingWizardService`.
**Consumers**: `audit/projection.py`, `notifications/consumers/accounts.py`, `analytics/consumers/accounts.py`.
**Partition key**: `tenant_id` (per UPD-046 R7).

## Envelope

The canonical `EventEnvelope` (UPD-013), with `tenant_id` and per-event payload:

```jsonc
{
  "event_id": "uuid",
  "event_type": "accounts.signup.completed",
  "schema_version": 1,
  "occurred_at": "2026-05-02T10:30:00Z",
  "tenant_id": "uuid",
  "correlation_id": "uuid",
  "actor": { "user_id": "uuid", "role": "user" },
  "trace_id": "32-char-otel-id",
  "payload": { ... }
}
```

## New event types

### `accounts.signup.completed`

Emitted post-verification when default workspace + Free subscription are provisioned.

```jsonc
{
  "user_id": "uuid",
  "email": "alice@example.com",
  "workspace_id": "uuid",
  "subscription_id": "uuid",
  "signup_method": "email"                       // or "oauth-google" | "oauth-github"
}
```

### `accounts.first_admin_invitation.issued`

Emitted when super admin provisions an Enterprise tenant and the first-admin invitation is created.

```jsonc
{
  "tenant_id": "uuid",
  "target_email": "cto@acme.test",
  "expires_at": "2026-05-09T10:00:00Z",
  "super_admin_id": "uuid"
}
```

### `accounts.first_admin_invitation.resent`

```jsonc
{
  "tenant_id": "uuid",
  "target_email": "cto@acme.test",
  "prior_token_invalidated_at": "2026-05-04T14:00:00Z",
  "super_admin_id": "uuid",
  "new_invitation_id": "uuid"
}
```

### `accounts.setup.step_completed`

Emitted per setup step.

```jsonc
{
  "tenant_id": "uuid",
  "step": "tos",                                 // or "credentials" | "mfa" | "workspace" | "invitations" | "done"
  "user_id": "uuid"
}
```

### `accounts.setup.completed`

Emitted on `POST /api/v1/setup/complete`.

```jsonc
{
  "tenant_id": "uuid",
  "user_id": "uuid",
  "first_workspace_id": "uuid",
  "invitations_sent_count": 2
}
```

### `accounts.cross_tenant_invitation.accepted`

Emitted when a user with an existing default-tenant identity accepts an Enterprise invitation.

```jsonc
{
  "default_tenant_user_id": "uuid",
  "enterprise_tenant_id": "uuid",
  "enterprise_user_id": "uuid",
  "email": "juan@acme.com"
}
```

The `tenant_id` in the envelope is the Enterprise tenant; the `default_tenant_user_id` lets analytics track conversion.

### `accounts.onboarding.step_advanced`

```jsonc
{
  "user_id": "uuid",
  "from_step": "workspace_named",                // or "invitations" | "first_agent" | "tour"
  "to_step": "invitations"
}
```

### `accounts.onboarding.dismissed`

```jsonc
{
  "user_id": "uuid",
  "dismissed_at_step": "first_agent"
}
```

### `accounts.onboarding.relaunched`

```jsonc
{
  "user_id": "uuid",
  "from_step": "first_agent"                     // the step where dismissal occurred
}
```

## Idempotency

All consumers MUST be idempotent on `event_id` per UPD-013 pattern.

## Audit-chain integration

Every event in this contract corresponds to a hash-linked audit-chain entry written via `AuditChainService.append`. The `tenant_id` is included in the chain hash per UPD-046 R7. The `audit_event_source` is `accounts` and the `event_type` mirrors the Kafka envelope's `event_type`.
