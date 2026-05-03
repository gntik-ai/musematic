# Contract — Data Lifecycle Kafka Events

**Phase 1 output.** All events are produced on the `data_lifecycle.events` topic, partitioned by `tenant_id` (key = `tenant_id` UUID bytes).

The canonical envelope is the platform `EventEnvelope` from `common/events/envelope.py`. Required envelope fields: `event_id`, `event_type`, `event_version`, `occurred_at`, `correlation_id`, `tenant_id`, `actor` block, `payload`.

`actor.role` MAY be one of `workspace_owner`, `workspace_admin`, `tenant_admin`, `super_admin`, `system`.

---

## Topic configuration

- Name: `data_lifecycle.events`
- Partitions: 12 (matches existing high-fanout topics; tenant_id keys distribute evenly).
- Retention: 30 days (audit chain is the durable record; topic is for projection + fanout).
- Cleanup policy: `delete`.
- Min ISR: 2.

Registered in `apps/control-plane/src/platform/data_lifecycle/events.py:register_data_lifecycle_event_types()` called at startup from `main.py` (matches the UPD-050 pattern).

---

## Event types

### `data_lifecycle.export.requested`

Emitted on every successful POST to a data-export endpoint. Triggers the `ExportJobWorker` consumer.

```json
{
  "event_type": "data_lifecycle.export.requested",
  "event_version": 1,
  "payload": {
    "job_id": "uuid",
    "scope_type": "workspace | tenant",
    "scope_id": "uuid",
    "requested_at": "...",
    "estimated_size_bytes_lower_bound": 0
  }
}
```

### `data_lifecycle.export.started`

Emitted by the worker as it acquires the Redis lease.

```json
{
  "event_type": "data_lifecycle.export.started",
  "event_version": 1,
  "payload": {
    "job_id": "uuid",
    "worker_id": "control-plane-worker-3",
    "started_at": "..."
  }
}
```

### `data_lifecycle.export.completed`

```json
{
  "event_type": "data_lifecycle.export.completed",
  "event_version": 1,
  "payload": {
    "job_id": "uuid",
    "output_size_bytes": 12345,
    "output_url_expires_at": "...",
    "completed_at": "..."
  }
}
```

### `data_lifecycle.export.failed`

```json
{
  "event_type": "data_lifecycle.export.failed",
  "event_version": 1,
  "payload": {
    "job_id": "uuid",
    "failure_reason_code": "s3_unreachable | source_query_timeout | partial_success",
    "retries_remaining": 2,
    "failed_at": "..."
  }
}
```

`failure_reason_code` is a redacted enum; raw error messages do NOT appear in the event (they live in `data_export_jobs.error_message`, also redacted, accessible only to operators).

---

### `data_lifecycle.deletion.requested`

```json
{
  "event_type": "data_lifecycle.deletion.requested",
  "event_version": 1,
  "payload": {
    "job_id": "uuid",
    "scope_type": "workspace | tenant",
    "scope_id": "uuid",
    "grace_period_days": 30,
    "grace_ends_at": "...",
    "two_pa_token_id": "uuid | null",
    "final_export_job_id": "uuid | null"
  }
}
```

### `data_lifecycle.deletion.phase_advanced`

Emitted by `grace_monitor` cron when phase transitions phase_1 → phase_2.

```json
{
  "event_type": "data_lifecycle.deletion.phase_advanced",
  "event_version": 1,
  "payload": {
    "job_id": "uuid",
    "from_phase": "phase_1",
    "to_phase": "phase_2",
    "advanced_at": "..."
  }
}
```

### `data_lifecycle.deletion.aborted`

```json
{
  "event_type": "data_lifecycle.deletion.aborted",
  "event_version": 1,
  "payload": {
    "job_id": "uuid",
    "scope_type": "workspace | tenant",
    "scope_id": "uuid",
    "abort_source": "owner_cancel_link | superadmin",
    "aborted_at": "..."
  }
}
```

`abort_reason` is NOT in the event payload — only in the audit chain.

### `data_lifecycle.deletion.completed`

Emitted by `cascade_worker` when all adapter executions finish.

```json
{
  "event_type": "data_lifecycle.deletion.completed",
  "event_version": 1,
  "payload": {
    "job_id": "uuid",
    "scope_type": "workspace | tenant",
    "scope_id": "uuid",
    "tombstone_id": "uuid",
    "store_results": [
      { "store": "postgresql", "rows_affected": 12345 },
      { "store": "qdrant",     "rows_affected": 800 }
    ],
    "cascade_started_at": "...",
    "cascade_completed_at": "..."
  }
}
```

---

### `data_lifecycle.dpa.uploaded`

```json
{
  "event_type": "data_lifecycle.dpa.uploaded",
  "event_version": 1,
  "payload": {
    "tenant_id": "uuid",
    "dpa_version": "v3.0",
    "sha256": "abcdef...",
    "effective_date": "2026-05-03",
    "vault_path_redacted": "secret/data/musematic/{env}/tenants/{slug}/dpa/dpa-v3.0.pdf"
  }
}
```

The Vault path is template-redacted; consumers cannot reconstruct the literal path from the event alone.

### `data_lifecycle.dpa.removed`

Reserved for future use (current implementation never removes DPAs; revocation is via uploading a superseding version).

---

### `data_lifecycle.sub_processor.added` / `.modified` / `.removed`

```json
{
  "event_type": "data_lifecycle.sub_processor.added",
  "event_version": 1,
  "payload": {
    "sub_processor_id": "uuid",
    "name": "MaxMind, Inc.",
    "category": "Fraud",
    "is_active": true,
    "changed_at": "..."
  }
}
```

Consumed by:
- `sub_processors_regenerator` cron — re-renders the public-page snapshot ConfigMap.
- `notifications/` BC — fans out to RSS feed + email subscribers (UPD-077 producer wrapper).

---

### `data_lifecycle.backup.purge_completed`

```json
{
  "event_type": "data_lifecycle.backup.purge_completed",
  "event_version": 1,
  "payload": {
    "tenant_id": "uuid",
    "purge_method": "key_destruction",
    "kms_key_id": "...",
    "kms_key_version": 7,
    "purge_completed_at": "...",
    "cold_storage_objects_retained": 1234
  }
}
```

Emitted by `backup_purge_service.py` 30 days after `deletion.completed`. The audit chain receives a parallel entry with the same payload.

---

## Idempotency + ordering

- All events carry `event_id` (UUIDv7); consumers MUST dedupe by event_id over a 30-day window.
- Per-tenant ordering guaranteed via tenant-id partition key.
- Cross-tenant ordering is NOT guaranteed; consumers that need a global order MUST use `occurred_at`.

## Schema evolution

Each event type bumps `event_version` on breaking change. Consumers SHOULD accept version `n` and `n-1` simultaneously during a deploy window. The registry in `events.py` enforces the version policy.
