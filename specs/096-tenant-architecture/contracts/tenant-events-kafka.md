# Contract — Tenant Lifecycle Kafka Events

**Topic**: `tenants.lifecycle`
**Owner**: `apps/control-plane/src/platform/tenants/events.py`
**Producer**: `TenantsService` (after a successful lifecycle action, post-commit)
**Consumers** (initial set): `audit/projection.py` (audit-chain projection), `notifications/consumers/tenants.py` (operator notification fan-out), `ws_hub/consumers/tenants.py` (admin UI live updates).
**Partition key**: `tenant_id` (UUID string) — guarantees per-tenant ordering.
**Replication / retention**: standard topic config from constitutional defaults.

## Envelope

The canonical `EventEnvelope` from UPD-013, augmented with `tenant_id` per the constitutional Critical Reminder:

```jsonc
{
  "event_id": "uuid",                          // unique per emitted event
  "event_type": "tenants.created",             // see types below
  "schema_version": 1,
  "occurred_at": "2026-05-01T10:00:00Z",
  "tenant_id": "uuid",                         // subject tenant
  "correlation_id": "uuid",                    // request correlation ID
  "actor": {
    "user_id": "uuid",
    "role": "super_admin"                      // or "platform_staff"
  },
  "trace_id": "32-char-otel-id",
  "payload": { ... }                            // type-specific (below)
}
```

## Event types and payload shapes

### `tenants.created`

```jsonc
{
  "slug": "acme",
  "subdomain": "acme",
  "kind": "enterprise",
  "region": "eu-central",
  "display_name": "Acme Corp",
  "first_admin_email": "cto@acme.com",
  "dpa_version": "v3-2026-01",
  "dpa_artifact_sha256": "..."
}
```

### `tenants.suspended`

```jsonc
{ "reason": "Non-payment", "previous_status": "active" }
```

### `tenants.reactivated`

```jsonc
{ "previous_status": "suspended" }   // or "pending_deletion" if reactivated from deletion grace
```

### `tenants.scheduled_for_deletion`

```jsonc
{
  "reason": "End of contract",
  "scheduled_deletion_at": "2026-05-04T10:00:00Z",
  "grace_period_hours": 72,
  "two_pa_principal_secondary": "uuid"          // the second 2PA principal
}
```

### `tenants.deletion_cancelled`

```jsonc
{ "scheduled_deletion_at_was": "2026-05-04T10:00:00Z" }
```

### `tenants.deleted`

The tombstone event. Payload includes proof of cascade completion:

```jsonc
{
  "row_count_digest": {
    "workspaces": 7,
    "users": 42,
    "agents": 11,
    // ... per-BC counts of deleted rows
  },
  "cascade_completed_at": "2026-05-04T10:00:01Z",
  "tombstone_sha256": "...",                    // hash of the canonical cascade summary
  "audit_chain_entry_seq": 123456
}
```

### `tenants.branding_updated`

```jsonc
{
  "fields_changed": ["logo_url", "accent_color_hex"],
  "previous_hash": "...",                       // sha256 of previous branding_config_json
  "new_hash": "..."
}
```

## Idempotency

Events carry `event_id`. Consumers MUST be idempotent on `event_id` (existing pattern from UPD-013).

## Ordering guarantees

Per-tenant ordering is guaranteed via the `tenant_id` partition key. Cross-tenant ordering is not — and is not needed by any consumer.

## Constitutional alignment

- `tenant_id` field is part of the envelope (Critical Reminder: "Audit chain entries must include `tenant_id`").
- Event topic is owned by the `tenants` BC (Core Principle IV — bounded context owns its events).
- Producer publishes after the DB transaction commits (UPD-013 outbox pattern); consumers handle replay safely.
