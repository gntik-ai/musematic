# Data Model — UPD-051 Data Lifecycle

**Phase 1 output.** Defines the new entities, brownfield additions to existing tables, RLS policies, and the Alembic migration shape.

Migration id: `111_data_lifecycle` (32-char limit OK; 18 chars).

---

## Brownfield findings

The audit on `main` (2026-05-03) shows:

- `tenants` ALREADY has `dpa_signed_at`, `dpa_version`, `dpa_artifact_uri`, `dpa_artifact_sha256` columns. **No new tenant DPA columns are needed.** The DPA service writes to these existing columns.
- `tenants.status` ALREADY accepts `pending_deletion` via the `ck_tenants_status` CHECK constraint with a partial index on `status='pending_deletion'`. **No tenant enum change.**
- `WorkspaceStatus` enum is `active`/`archived`/`deleted` — DOES NOT include `pending_deletion`. Migration MUST add `pending_deletion` to the `workspaces_workspace_status` PostgreSQL enum AND update `apps/control-plane/src/platform/workspaces/models.py:WorkspaceStatus` enum class.
- `tenants.settings_json` JSONB column exists — used to store per-Enterprise-tenant `deletion_grace_period_days` overrides per R6 (no new column needed).
- `audit_chain_entries` table from UPD-024 is the audit emission target — NEVER write rows directly (rule 9).
- `entity_tags` polymorphic table from UPD-082 is the tag attachment point for new entities (rule 14).
- `outbound_webhooks` from UPD-077 is the producer for sub-processors change subscriptions (rule 17).

---

## New tables (3)

### 1. `data_export_jobs`

Workspace and tenant export job ledger. Append-only state machine (`pending` → `processing` → `completed`/`failed`).

| Column | Type | Notes |
|---|---|---|
| `id` | `UUID` PK | `gen_random_uuid()` |
| `tenant_id` | `UUID NOT NULL` | FK → `tenants.id`; RLS pivot |
| `scope_type` | `VARCHAR(16) NOT NULL` | `CHECK (scope_type IN ('workspace','tenant'))` |
| `scope_id` | `UUID NOT NULL` | workspace_id when scope_type='workspace'; tenant_id when scope_type='tenant' (must equal `tenant_id`) |
| `requested_by_user_id` | `UUID NOT NULL` | actor; logged by audit chain |
| `status` | `VARCHAR(32) NOT NULL` | `CHECK (status IN ('pending','processing','completed','failed'))` |
| `started_at` | `TIMESTAMPTZ NULL` | set when worker picks up |
| `completed_at` | `TIMESTAMPTZ NULL` | set on success or failure |
| `output_url` | `TEXT NULL` | signed S3 URL; set on success only |
| `output_size_bytes` | `BIGINT NULL` | uncompressed total |
| `output_expires_at` | `TIMESTAMPTZ NULL` | signed-URL TTL endpoint (7d for workspace, 30d for tenant) |
| `error_message` | `TEXT NULL` | redacted; no PII or secrets |
| `correlation_id` | `UUID NULL` | propagated from request ContextVar |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |

**Indexes**:
- `(tenant_id, status, created_at DESC)` — admin queue queries
- `(scope_type, scope_id, created_at DESC)` — owner status checks
- partial: `(status) WHERE status IN ('pending','processing')` — worker-poll fast path

**RLS**: `ENABLE ROW LEVEL SECURITY; CREATE POLICY tenant_isolation USING (tenant_id = current_setting('app.tenant_id', true)::uuid);`. Super admins use the BYPASSRLS staff role.

**State transitions**: see [contracts/data-lifecycle-events-kafka.md](./contracts/data-lifecycle-events-kafka.md) for the matching event lifecycle.

---

### 2. `deletion_jobs`

Append-only deletion-job ledger. Phases never mutate; abort writes a new logical state via `phase='aborted'` + `abort_reason`. The grace clock is `grace_ends_at`.

| Column | Type | Notes |
|---|---|---|
| `id` | `UUID` PK | |
| `tenant_id` | `UUID NOT NULL` | FK → `tenants.id`; RLS pivot |
| `scope_type` | `VARCHAR(16) NOT NULL` | `CHECK (scope_type IN ('workspace','tenant'))` |
| `scope_id` | `UUID NOT NULL` | workspace_id or tenant_id (must equal `tenant_id` when tenant scope) |
| `phase` | `VARCHAR(16) NOT NULL` | `CHECK (phase IN ('phase_1','phase_2','completed','aborted'))` |
| `requested_by_user_id` | `UUID NOT NULL` | actor |
| `two_pa_token_id` | `UUID NULL` | required when scope_type='tenant'; nullable when 'workspace' |
| `grace_period_days` | `INTEGER NOT NULL` | resolved at request time per R6 |
| `grace_ends_at` | `TIMESTAMPTZ NOT NULL` | `created_at + grace_period_days::interval` |
| `cancel_token_hash` | `BYTEA NOT NULL` | SHA-256 of the cancel-link token (anti-enumeration: no plaintext stored) |
| `cancel_token_expires_at` | `TIMESTAMPTZ NOT NULL` | typically equals `grace_ends_at` |
| `cascade_started_at` | `TIMESTAMPTZ NULL` | set when phase transitions to `phase_2` |
| `cascade_completed_at` | `TIMESTAMPTZ NULL` | set when cascade finishes |
| `tombstone_id` | `UUID NULL` | FK → `privacy_compliance_tombstones.id` (UPD-023) |
| `final_export_job_id` | `UUID NULL` | FK → `data_export_jobs.id` for the phase-1 final export (tenant only) |
| `abort_reason` | `TEXT NULL` | non-null iff `phase='aborted'`; logged but not displayed to non-superadmin |
| `correlation_id` | `UUID NULL` | |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |

**Indexes**:
- `(tenant_id, scope_type, scope_id, created_at DESC)` — list jobs for a scope
- partial: `(grace_ends_at) WHERE phase = 'phase_1'` — grace-monitor cron scan
- `(cancel_token_hash)` UNIQUE — token lookup
- `(scope_type, scope_id) WHERE phase IN ('phase_1','phase_2')` — uniqueness guard via partial UNIQUE index

**Constraint** (uniqueness):
```sql
CREATE UNIQUE INDEX uq_deletion_jobs_active_per_scope
  ON deletion_jobs (scope_type, scope_id)
  WHERE phase IN ('phase_1', 'phase_2');
```
Prevents two concurrent active deletion jobs against the same workspace or tenant.

**RLS**: same pattern as `data_export_jobs`.

---

### 3. `sub_processors`

Public-readable, admin-writable. NOT tenant-scoped (this is platform-level data). RLS disabled for this table; access is via service-layer policy (router gates).

| Column | Type | Notes |
|---|---|---|
| `id` | `UUID` PK | |
| `name` | `VARCHAR(128) NOT NULL` | display name |
| `category` | `VARCHAR(64) NOT NULL` | e.g., `LLM provider`, `Infrastructure`, `Billing`, `Email`, `Fraud` |
| `location` | `VARCHAR(64) NOT NULL` | e.g., `Germany`, `USA`, `Ireland` |
| `data_categories` | `TEXT[] NOT NULL` | e.g., `{"prompts","outputs"}` |
| `privacy_policy_url` | `TEXT NULL` | |
| `dpa_url` | `TEXT NULL` | |
| `is_active` | `BOOLEAN NOT NULL DEFAULT true` | |
| `started_using_at` | `DATE NULL` | first day platform began using this processor |
| `notes` | `TEXT NULL` | operator-facing notes; not rendered on public page |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |
| `updated_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |
| `updated_by_user_id` | `UUID NULL` | last admin to edit; FK → `users.id` |

**Indexes**:
- `(is_active, category)` — public-page filtering

**Seed data** (idempotent — see migration's `op.execute(... ON CONFLICT (name) DO NOTHING)`):
- Anthropic, PBC — LLM provider — USA — `{"prompts","outputs"}`
- OpenAI — LLM provider — USA — `{"prompts","outputs"}`
- Hetzner Online GmbH — Infrastructure — Germany — `{"all_platform_data_at_rest"}`
- Stripe Payments Europe Ltd — Billing — Ireland — `{"payment_method_metadata","invoices"}`

---

## Brownfield ALTERs (1)

### `workspaces_workspace_status` enum

Add `'pending_deletion'` value. Migration:

```python
op.execute("ALTER TYPE workspaces_workspace_status ADD VALUE IF NOT EXISTS 'pending_deletion'")
```

This is a non-transactional Alembic operation and MUST be in its own migration if other transactional steps exist (Postgres limitation). Migration `111_data_lifecycle.py` declares `transactional_ddl = False` and bundles only the enum addition + the 3 new tables (3 tables are also enum-free pure DDL, safe outside a transaction). All other DDL goes in a follow-up migration if needed; in practice, none is needed.

Update `apps/control-plane/src/platform/workspaces/models.py:WorkspaceStatus` to include `pending_deletion = "pending_deletion"`.

---

## Vault paths (1 family)

`secret/data/musematic/{env}/tenants/{slug}/dpa/dpa-v{n}.pdf` — accessed only by `dpa_service.py`. Stored as KV v2 with `data` field = base64-encoded PDF bytes. Metadata fields: `dpa_version`, `uploaded_by_user_id`, `uploaded_at`, `sha256`, `clamav_signature_version`.

The Vault path mirror in PostgreSQL is `tenants.dpa_artifact_uri` (already exists). The `dpa_artifact_sha256` column already exists for content-hash verification.

---

## S3 buckets (2)

Both accessed via `common/clients/s3.S3Client` (Principle XVI — generic-S3, MinIO optional).

### `data-lifecycle-exports`
- Per-region (UPD-025 residency). Bucket name suffix: `-{region}`.
- SSE-S3 default. Optional SSE-C for tenant exports per R9.
- Lifecycle: objects under `archive/` prefix expire 7 days after creation (workspace exports); 30 days after creation (tenant exports under `tenant/` prefix).
- Public access blocked. Access only via signed URL.

### `platform-audit-cold-storage`
- Single global bucket (audit chain is platform-level).
- S3 Object Lock COMPLIANCE mode. Retention = `dataLifecycle.coldStorage.retentionYears` Helm value (default 7).
- Separate KMS key reference from the live audit chain — protects historical tombstones from accidental key destruction.
- Used by `backup_purge_service.py` for tenant deletion tombstone evidence.

---

## Redis keys (1 family)

`data_lifecycle:export_lease:{job_id}` — TTL = max-export-duration (60 min) + 5 min grace. Acquired by export workers via `SET ... NX EX`. Prevents duplicate dispatch on rebalance.

---

## Kafka topics (1)

`data_lifecycle.events` — single topic, partitioned by `tenant_id`. Event type registry lives in `apps/control-plane/src/platform/data_lifecycle/events.py`. See [contracts/data-lifecycle-events-kafka.md](./contracts/data-lifecycle-events-kafka.md).

Event types:
- `data_lifecycle.export.requested`
- `data_lifecycle.export.started`
- `data_lifecycle.export.completed`
- `data_lifecycle.export.failed`
- `data_lifecycle.deletion.requested`
- `data_lifecycle.deletion.phase_advanced`
- `data_lifecycle.deletion.aborted`
- `data_lifecycle.deletion.completed`
- `data_lifecycle.dpa.uploaded`
- `data_lifecycle.dpa.removed`
- `data_lifecycle.sub_processor.added`
- `data_lifecycle.sub_processor.modified`
- `data_lifecycle.sub_processor.removed`
- `data_lifecycle.backup.purge_completed`

---

## Audit-chain entry types (delegated to UPD-024)

This BC emits — never writes — audit chain entries. Entry `event_type` strings used:

- `data_lifecycle.export_requested`
- `data_lifecycle.export_completed`
- `data_lifecycle.export_failed`
- `data_lifecycle.workspace_deletion_phase_1`
- `data_lifecycle.workspace_deletion_phase_2`
- `data_lifecycle.workspace_deletion_aborted`
- `data_lifecycle.workspace_deletion_completed`
- `data_lifecycle.tenant_deletion_phase_1`
- `data_lifecycle.tenant_deletion_phase_2`
- `data_lifecycle.tenant_deletion_aborted`
- `data_lifecycle.tenant_deletion_completed`
- `data_lifecycle.dpa_uploaded`
- `data_lifecycle.dpa_removed`
- `data_lifecycle.sub_processor_change`
- `data_lifecycle.backup_purge_completed`
- `data_lifecycle.cancel_token_used`
- `data_lifecycle.cancel_token_invalid` (anti-enumeration: written but never returned to caller)

---

## Polymorphic tag/label attachments (rule 14)

`entity_tags` and `entity_labels` extensions:
- `entity_type='data_export_job'`, `entity_id=jobs.id`
- `entity_type='deletion_job'`, `entity_id=jobs.id`
- `entity_type='sub_processor'`, `entity_id=sub_processors.id`

Frontend filtering uses these via the standard tag-filter components (UPD-082 substrate).

---

## Migration shape (`111_data_lifecycle.py`)

```python
"""data_lifecycle: export jobs, deletion jobs, sub_processors

Revision ID: 111_data_lifecycle
Revises: 110_marketplace_scope
Create Date: 2026-05-03 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "111_data_lifecycle"
down_revision = "110_marketplace_scope"
branch_labels = None
depends_on = None

# Non-transactional because ALTER TYPE ... ADD VALUE cannot run in a transaction
# block prior to PostgreSQL 12. Helm targets PG 16, so this is safe today, but we
# keep transactional_ddl = False for portability.
transactional_ddl = False


def upgrade() -> None:
    # 1. enum extension
    op.execute("ALTER TYPE workspaces_workspace_status ADD VALUE IF NOT EXISTS 'pending_deletion'")

    # 2. data_export_jobs
    op.create_table("data_export_jobs", ...)  # see column spec above
    op.create_index(...)  # 3 indexes per spec
    op.execute("ALTER TABLE data_export_jobs ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY tenant_isolation ON data_export_jobs USING (tenant_id = current_setting('app.tenant_id', true)::uuid)")

    # 3. deletion_jobs
    op.create_table("deletion_jobs", ...)
    op.create_index(...)  # 4 indexes including the partial unique
    op.execute("ALTER TABLE deletion_jobs ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY tenant_isolation ON deletion_jobs USING (tenant_id = current_setting('app.tenant_id', true)::uuid)")

    # 4. sub_processors (no RLS — platform-level)
    op.create_table("sub_processors", ...)
    op.create_index("ix_sub_processors_active_category", "sub_processors", ["is_active", "category"])
    op.bulk_insert(...)  # 4 default rows; ON CONFLICT-style guard via WHERE NOT EXISTS in raw SQL


def downgrade() -> None:
    op.drop_table("sub_processors")
    op.drop_table("deletion_jobs")
    op.drop_table("data_export_jobs")
    # NOTE: ALTER TYPE ... DROP VALUE is not supported by PostgreSQL.
    # The 'pending_deletion' enum value remains. Acceptable for downgrade.
```

---

## RLS verification

After migration, the existing `tools/check_rls_coverage.py` (per UPD-053 zero-trust visibility) MUST be re-run; new tables `data_export_jobs` and `deletion_jobs` MUST appear in `TENANT_SCOPED_TABLES`. The framework-glue check `apps/control-plane/scripts/check_rls.py` verifies the policy is `tenant_isolation` with the canonical USING clause.

---

## Coverage map: spec → schema

| Spec FR | Schema element |
|---|---|
| FR-751 (workspace export) | `data_export_jobs` (scope_type='workspace'), `data-lifecycle-exports` bucket |
| FR-752 (workspace deletion) | `deletion_jobs` (scope_type='workspace'), `WorkspaceStatus.pending_deletion` |
| FR-753 (tenant export) | `data_export_jobs` (scope_type='tenant'), tenant-scoped lifecycle |
| FR-754 (tenant deletion cascade) | `deletion_jobs` (scope_type='tenant'), 2PA via `two_pa_token_id`, `tombstone_id` |
| FR-755 (DPA) | `tenants.dpa_*` (existing), Vault path family |
| FR-756 (sub-processors) | `sub_processors` table + `outbound_webhooks` (UPD-077) |
| FR-757 (GDPR Article 28 evidence) | Composite read across `tenants` + `data_export_jobs` + `deletion_jobs` + audit chain |
| FR-758 (backup separation) | `platform-audit-cold-storage` bucket + `backup_purge_service` |
| FR-759 (audit-chain integrity) | Delegation to `audit/service.AuditChainService` |
| FR-760 (cascade orchestrator extension) | R1 — extend `CascadeOrchestrator`/`CascadeAdapter`, no new table |
