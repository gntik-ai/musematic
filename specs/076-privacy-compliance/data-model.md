# Phase 1 Data Model: Privacy Compliance

**Feature**: 076-privacy-compliance
**Date**: 2026-04-25

## Overview

7 new Postgres tables, 5 new Kafka topics, 2 Redis key patterns, 1
Vault path, + ClickHouse `is_deleted BOOLEAN` column added to PII-
bearing rollup tables. Migration 060 creates Postgres tables + seeds
DLP patterns; an accompanying ClickHouse migration (invoked from
within 060) adds tombstone columns.

---

## 1. PostgreSQL tables

### 1.1 `privacy_dsr_requests`

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID (PK) | `DEFAULT gen_random_uuid()` |
| `subject_user_id` | UUID | `NOT NULL REFERENCES users(id)` |
| `request_type` | VARCHAR(32) | `NOT NULL CHECK (IN ('access','rectification','erasure','portability','restriction','objection'))` |
| `requested_by` | UUID | `NOT NULL REFERENCES users(id)` |
| `status` | VARCHAR(32) | `NOT NULL DEFAULT 'received' CHECK (IN ('received','scheduled','in_progress','completed','failed','cancelled'))` |
| `legal_basis` | VARCHAR(256) | `NULL` |
| `scheduled_release_at` | TIMESTAMPTZ | `NULL` — for optional hold window per research.md D-013 |
| `requested_at` | TIMESTAMPTZ | `NOT NULL DEFAULT now()` |
| `completed_at` | TIMESTAMPTZ | `NULL` |
| `completion_proof_hash` | VARCHAR(64) | `NULL` — SHA-256 of canonical completion payload |
| `failure_reason` | TEXT | `NULL` |
| `tombstone_id` | UUID | `NULL REFERENCES privacy_deletion_tombstones(id)` — set for erasure DSRs on completion |

**Indexes**: `ix_dsr_subject_status` on `(subject_user_id, status)`;
`ix_dsr_scheduled_release` on `(status, scheduled_release_at)` filtered
`WHERE status = 'scheduled'`.

### 1.2 `privacy_deletion_tombstones`

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID (PK) | |
| `subject_user_id_hash` | VARCHAR(64) | `NOT NULL` — SHA-256 hash of subject_user_id + platform_salt (never stores raw UUID per AD-17) |
| `salt_version` | INTEGER | `NOT NULL DEFAULT 1` — allows verifying against a salt-history |
| `entities_deleted` | JSONB | `NOT NULL` — `{store_name: count}` map |
| `cascade_log` | JSONB | `NOT NULL` — list of per-stage outcomes |
| `proof_hash` | VARCHAR(64) | `NOT NULL UNIQUE` — SHA-256 of canonical tombstone payload |
| `created_at` | TIMESTAMPTZ | `NOT NULL DEFAULT now()` |

**Indexes**: `UNIQUE (proof_hash)`; `ix_tombstone_subject_hash` on
`(subject_user_id_hash, salt_version)`.

**Constraint**: DB trigger `BEFORE UPDATE OR DELETE` raises (tombstones
are immutable, same pattern as UPD-024's audit chain).

### 1.3 `privacy_residency_configs`

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID (PK) | |
| `workspace_id` | UUID | `NOT NULL UNIQUE REFERENCES workspaces(id) ON DELETE CASCADE` |
| `region_code` | VARCHAR(32) | `NOT NULL` — e.g. `eu-central-1`, `us-east-1` |
| `allowed_transfer_regions` | JSONB | `NOT NULL DEFAULT '[]'::jsonb` — list of allowed foreign regions |
| `created_at` | TIMESTAMPTZ | `NOT NULL DEFAULT now()` |
| `updated_at` | TIMESTAMPTZ | `NOT NULL DEFAULT now()` |

### 1.4 `privacy_dlp_rules`

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID (PK) | |
| `workspace_id` | UUID | `NULL REFERENCES workspaces(id) ON DELETE CASCADE` — NULL for platform-seeded |
| `name` | VARCHAR(256) | `NOT NULL` |
| `classification` | VARCHAR(32) | `NOT NULL CHECK (IN ('pii','phi','financial','confidential'))` |
| `pattern` | TEXT | `NOT NULL` — regex |
| `action` | VARCHAR(32) | `NOT NULL CHECK (IN ('redact','block','flag'))` |
| `enabled` | BOOLEAN | `NOT NULL DEFAULT true` |
| `seeded` | BOOLEAN | `NOT NULL DEFAULT false` — TRUE for migration-seeded; cannot be deleted, but can be disabled per-workspace |

**Indexes**: `ix_dlp_rule_ws_enabled` on `(workspace_id, enabled)`.

### 1.5 `privacy_dlp_events`

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID (PK) | |
| `rule_id` | UUID | `NOT NULL REFERENCES privacy_dlp_rules(id) ON DELETE CASCADE` |
| `workspace_id` | UUID | `NULL REFERENCES workspaces(id) ON DELETE CASCADE` |
| `execution_id` | UUID | `NULL` |
| `match_summary` | VARCHAR(128) | `NOT NULL` — CLASSIFICATION LABEL ONLY; never raw PII |
| `action_taken` | VARCHAR(32) | `NOT NULL CHECK (IN ('redact','block','flag'))` |
| `created_at` | TIMESTAMPTZ | `NOT NULL DEFAULT now()` |

**Indexes**: `ix_dlp_events_by_rule_time` on `(rule_id, created_at)`;
`ix_dlp_events_by_execution` on `(execution_id)` filtered `WHERE
execution_id IS NOT NULL`.

**Retention**: 90 days full fidelity (daily purge job); aggregated
counts pushed to ClickHouse analytics BC.

### 1.6 `privacy_impact_assessments`

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID (PK) | |
| `subject_type` | VARCHAR(32) | `NOT NULL CHECK (IN ('agent','workspace','workflow'))` |
| `subject_id` | UUID | `NOT NULL` |
| `data_categories` | JSONB | `NOT NULL` — array of `pii`/`phi`/`financial`/`confidential`/`behavioral`/`other` |
| `legal_basis` | TEXT | `NOT NULL CHECK (length(legal_basis) >= 10)` |
| `retention_policy` | TEXT | `NULL` |
| `risks` | JSONB | `NULL` |
| `mitigations` | JSONB | `NULL` |
| `status` | VARCHAR(32) | `NOT NULL DEFAULT 'draft' CHECK (IN ('draft','under_review','approved','rejected','superseded'))` |
| `submitted_by` | UUID | `NOT NULL REFERENCES users(id)` |
| `approved_by` | UUID | `NULL REFERENCES users(id)` |
| `approved_at` | TIMESTAMPTZ | `NULL` |
| `rejection_feedback` | TEXT | `NULL` |
| `superseded_by_pia_id` | UUID | `NULL REFERENCES privacy_impact_assessments(id)` |
| `created_at` | TIMESTAMPTZ | `NOT NULL DEFAULT now()` |
| `updated_at` | TIMESTAMPTZ | `NOT NULL DEFAULT now()` |

**Indexes**: `ix_pia_by_subject` on `(subject_type, subject_id, status)`.

**Constraint**: `CHECK (approved_by IS NULL OR approved_by != submitted_by)` — 2PA per rule 33.

### 1.7 `privacy_consent_records`

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID (PK) | |
| `user_id` | UUID | `NOT NULL REFERENCES users(id) ON DELETE CASCADE` |
| `consent_type` | VARCHAR(64) | `NOT NULL CHECK (IN ('ai_interaction','data_collection','training_use'))` |
| `granted` | BOOLEAN | `NOT NULL` |
| `granted_at` | TIMESTAMPTZ | `NOT NULL DEFAULT now()` |
| `revoked_at` | TIMESTAMPTZ | `NULL` |
| `workspace_id` | UUID | `NULL REFERENCES workspaces(id) ON DELETE CASCADE` — for per-workspace consent in v1.x |

**Indexes**: `UNIQUE (user_id, consent_type)` (only one active row per
user + type; revocation sets `revoked_at`; granting again inserts a new
row via delete-and-re-insert pattern OR updates `revoked_at = NULL` +
increments a `revision`); `ix_consent_user_type_revoked` on `(user_id,
consent_type, revoked_at)` for the propagation worker.

---

## 2. ClickHouse (existing DB; new columns)

Migration 060 ALTERs PII-bearing ClickHouse rollup tables to add:

```sql
ALTER TABLE execution_metrics ADD COLUMN is_deleted UInt8 DEFAULT 0;
ALTER TABLE agent_performance ADD COLUMN is_deleted UInt8 DEFAULT 0;
ALTER TABLE token_usage ADD COLUMN is_deleted UInt8 DEFAULT 0;
-- plus other rollups per analytics BC's table list
```

Downstream queries get auto-filtered by a query-rewrite helper in
`common/clients/clickhouse.py` (a thin wrapper that adds `AND NOT
is_deleted` when hitting a registered table). A monthly compactor
(follow-up work — not in this feature) hard-deletes rows where
`is_deleted=1` and `created_at < now() - INTERVAL 30 DAY`.

---

## 3. Redis

| Key pattern | Purpose | TTL |
|---|---|---|
| `privacy:consent:{user_id}:{workspace_id}` | Cached consent state (3 rows collapsed into one JSON hash) | 30 s read-through |
| `privacy:residency:{workspace_id}` | Cached residency config | 60 s read-through |
| `privacy:revoked_training_users` | Denormalised set of user IDs that revoked `training_use` consent | Indefinite (refreshed by worker every 60 s) |

---

## 4. Kafka — 5 new topics (per constitution §7)

| Topic | Producer | Consumer(s) |
|---|---|---|
| `privacy.dsr.received` | `privacy_compliance/dsr_service` | audit chain, notifications, admin dashboard |
| `privacy.dsr.completed` | `privacy_compliance/dsr_service` | audit chain, notifications, compliance_service |
| `privacy.deletion.cascaded` | `privacy_compliance/cascade_orchestrator` | audit chain, compliance_service |
| `privacy.dlp.event` | `privacy_compliance/dlp_service` (emitted from `policies/gateway` + `trust/guardrail_pipeline` via service call) | security_compliance, audit chain, operator dashboard |
| `privacy.pia.approved` | `privacy_compliance/pia_service` | trust, registry, compliance_service |

Plus derived `privacy.pia.rejected` and `privacy.pia.superseded`
following the same pattern.

All payloads carry a `CorrelationContext` envelope (correlation_id,
workspace_id where applicable).

---

## 5. Vault

Path: `secret/data/musematic/{env}/privacy/subject-hash-salt`

Value:

```json
{
  "current_salt": "<hex 32 bytes>",
  "salt_version": 1,
  "rotated_at": "<ISO8601>",
  "history": [
    {"salt": "<hex>", "salt_version": 1, "rotated_at": "..."},
    ...
  ]
}
```

A `SaltHistoryProvider` (new class in
`privacy_compliance/services/salt_history.py`) exposes
`get_salt(version: int) -> bytes` so tombstone verification uses the
salt version recorded on the tombstone (not the current salt).

---

## 6. Migration 060 shape

```python
# apps/control-plane/migrations/versions/060_privacy_compliance.py
revision = "060"
down_revision = "059"

def upgrade() -> None:
    _create_dsr_requests_table(op)                # §1.1
    _create_deletion_tombstones_table(op)         # §1.2
    _create_residency_configs_table(op)           # §1.3
    _create_dlp_rules_table(op)                   # §1.4
    _create_dlp_events_table(op)                  # §1.5
    _create_pia_table(op)                         # §1.6
    _create_consent_records_table(op)             # §1.7
    _install_tombstone_trigger(op)                # append-only enforcement
    _seed_dlp_patterns(op)                        # ≥ 10 platform floor patterns
    _extend_role_type_enum_with_privacy_officer(op)  # adds value
    _alter_clickhouse_rollups_add_is_deleted()    # out-of-band ClickHouse alters
```

Total migration ≈ 500 lines including seed data; split into logical
functions for reviewability.
