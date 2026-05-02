# Contract — Marketplace Lifecycle Kafka Events

**Topic**: `marketplace.events` (existing) — UPD-049 adds 8 new event types additively. Plus one new event on `tenants.lifecycle` (`tenants.feature_flag_changed`).
**Owner**: `apps/control-plane/src/platform/registry/events.py` (marketplace events flow through the registry events module per current architecture) + `apps/control-plane/src/platform/tenants/events.py`.
**Producers**: `RegistryService` (lifecycle transitions), `MarketplaceAdminService` (review actions), `TenantsService` (feature flag changes).
**Consumers**: `audit/projection.py`, `notifications/consumers/marketplace.py` (review-rejection + source-updated fan-out), `analytics/consumers/marketplace.py` (commercial KPI dashboard), `marketplace/search_service.py` (OpenSearch index update).
**Partition key**: `tenant_id` (per UPD-046 R7).

## Envelope

Canonical `EventEnvelope` (UPD-013) with `tenant_id` and event-specific payload.

## New event types

### `marketplace.scope_changed`

```jsonc
{ "agent_id": "uuid", "from_scope": "workspace", "to_scope": "tenant", "actor_user_id": "uuid" }
```

### `marketplace.submitted`

```jsonc
{
  "agent_id": "uuid",
  "submitter_user_id": "uuid",
  "category": "data-extraction",
  "tags": ["pdf"],
  "marketing_description_hash": "sha256-..."
}
```

### `marketplace.approved`

```jsonc
{ "agent_id": "uuid", "reviewer_user_id": "uuid", "approval_notes": "..." }
```

### `marketplace.rejected`

```jsonc
{ "agent_id": "uuid", "reviewer_user_id": "uuid", "rejection_reason": "Marketing description too vague." }
```

### `marketplace.published`

```jsonc
{ "agent_id": "uuid", "published_at": "2026-05-02T10:30:00Z" }
```

### `marketplace.deprecated`

```jsonc
{ "agent_id": "uuid", "actor_user_id": "uuid", "deprecation_reason": "Superseded by v2." }
```

### `marketplace.forked`

```jsonc
{
  "source_agent_id": "uuid",
  "fork_agent_id": "uuid",
  "target_scope": "tenant",
  "consumer_user_id": "uuid",
  "consumer_tenant_id": "uuid"
}
```

The envelope's `tenant_id` is the **consumer**'s tenant (the fork lives there); the `source_agent_id` and `consumer_tenant_id` payload fields preserve the cross-tenant linkage.

### `marketplace.source_updated`

Emitted when a published public source is updated and re-approved. Consumed by `notifications/consumers/marketplace.py` to fan out to fork owners.

```jsonc
{ "source_agent_id": "uuid", "new_version_id": "uuid", "diff_summary_hash": "sha256-..." }
```

### `tenants.feature_flag_changed`

On the `tenants.lifecycle` topic (UPD-046's existing topic).

```jsonc
{
  "tenant_id": "uuid",
  "flag_name": "consume_public_marketplace",
  "from_value": false,
  "to_value": true,
  "super_admin_user_id": "uuid"
}
```

## Idempotency

All consumers MUST be idempotent on `event_id` per UPD-013.

## Audit-chain integration

Every event in this contract corresponds to a hash-linked audit-chain entry written via `AuditChainService.append`. The `tenant_id` is included in the chain hash per UPD-046 R7. The `audit_event_source` is `marketplace` and the `event_type` mirrors the Kafka envelope's `event_type`.
