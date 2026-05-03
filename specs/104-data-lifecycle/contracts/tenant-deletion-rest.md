# Contract — Tenant Deletion REST

**Phase 1 output.** Routes under `/api/v1/admin/tenants/{tenant_id}/deletion-jobs/*` and `/api/v1/admin/data-lifecycle/deletion-jobs/{id}/abort`. Gated by `require_superadmin` AND a fresh 2PA token on every state-changing call (rule 33).

Two-phase workflow with a 30-day default grace, per R6 / spec.

---

## `POST /api/v1/admin/tenants/{tenant_id}/deletion-jobs`

Schedule tenant deletion. Phase 1 starts immediately upon successful 2PA validation.

**Headers**:
- `X-2PA-Token: <token>` — fresh 2PA token (per UPD-039 / feature 086 primitives)

**Request body**:

```json
{
  "typed_confirmation": "delete tenant acme",
  "reason": "...required free text...",
  "include_final_export": true,
  "grace_period_days": 30
}
```

**Behaviour**:
- Validates the 2PA token freshly server-side.
- Validates `tenants.subscription_status` is NOT `active` (UPD-052 hard prerequisite). If active, returns 409 `subscription_active_cancel_first`.
- Validates `typed_confirmation` matches `delete tenant {slug}`.
- Validates `7 ≤ grace_period_days ≤ 90`.
- Creates `deletion_jobs` row in `phase_1`. Tenant status flips to `pending_deletion`.
- If `include_final_export=true`, creates a `data_export_jobs` row and links via `final_export_job_id`.
- Audits `data_lifecycle.tenant_deletion_phase_1` with the actor + 2PA token id.
- Emits `data_lifecycle.deletion.requested` Kafka event.

**Response 202**:

```json
{
  "id": "uuid",
  "scope_type": "tenant",
  "scope_id": "uuid",
  "phase": "phase_1",
  "grace_period_days": 30,
  "grace_ends_at": "2026-06-02T10:00:00Z",
  "final_export_job_id": "uuid"
}
```

**Errors**:

| Status | Code |
|---|---|
| 400 | `typed_confirmation_mismatch` |
| 403 | `not_superadmin` / `2pa_token_required` / `2pa_token_invalid` |
| 404 | `tenant_not_found` |
| 409 | `subscription_active_cancel_first` |
| 409 | `deletion_job_already_active` |
| 422 | `grace_period_out_of_range` |

---

## `GET /api/v1/admin/tenants/{tenant_id}/deletion-jobs/{job_id}`

Returns deletion job state including cascade progress per store (when phase ≥ 2).

**Response 200**:

```json
{
  "id": "uuid",
  "phase": "phase_2",
  "grace_ends_at": "...",
  "cascade_started_at": "...",
  "cascade_completed_at": null,
  "tombstone_id": null,
  "final_export_job_id": "uuid",
  "two_pa_token_id": "uuid",
  "store_progress": [
    { "store": "postgresql", "status": "completed", "rows_affected": 12345 },
    { "store": "qdrant",     "status": "in_progress", "rows_affected": 800 },
    { "store": "neo4j",      "status": "pending",  "rows_affected": null },
    { "store": "clickhouse", "status": "pending",  "rows_affected": null },
    { "store": "opensearch", "status": "pending",  "rows_affected": null },
    { "store": "s3",         "status": "pending",  "rows_affected": null }
  ]
}
```

`store_progress` entries are populated by the `CascadeOrchestrator.execute_tenant_cascade` extension as each adapter reports.

---

## `POST /api/v1/admin/data-lifecycle/deletion-jobs/{id}/abort`

Super-admin abort. Works for both workspace and tenant scopes; permitted ONLY in `phase_1`.

**Headers**:
- `X-2PA-Token: <token>` (required for tenant-scope; optional for workspace-scope)

**Request body**:

```json
{
  "abort_reason": "False alarm — tenant requested rollback within hours."
}
```

**Behaviour**:
- Validates phase ∈ {`phase_1`}; returns 409 `cascade_in_progress` otherwise.
- Restores workspace/tenant prior status (`active` for workspace; previous status for tenant — typically `active` or `suspended`).
- Audits `data_lifecycle.{workspace,tenant}_deletion_aborted`.
- Emits `data_lifecycle.deletion.aborted` Kafka event.
- Final-export job (if any) is left in its current state — operators may delete the partial export manually or wait for its TTL to expire.

**Errors**:

| Status | Code |
|---|---|
| 403 | `not_superadmin` / `2pa_token_required` |
| 409 | `cascade_in_progress` |
| 410 | `deletion_job_already_finalised` |

---

## `POST /api/v1/admin/tenants/{tenant_id}/deletion-jobs/{job_id}/extend-grace`

Operator-initiated grace extension (US3 acceptance #4 mid-sentence: "configurable per contract"). Only in `phase_1`.

**Headers**: `X-2PA-Token: <token>` (required)

**Request body**:

```json
{
  "additional_days": 14,
  "reason": "Acme legal requested extra review window."
}
```

Validates `additional_days >= 1` and that `new grace_ends_at` ≤ `created_at + 90 days` (upper bound from R6).

Audits `data_lifecycle.tenant_deletion_grace_extended`.
