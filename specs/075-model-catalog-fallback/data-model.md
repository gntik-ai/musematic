# Phase 1 Data Model: Model Catalog and Fallback

**Feature**: 075-model-catalog-fallback
**Date**: 2026-04-23

## Overview

5 new Postgres tables (4 from spec DDL + 1
`injection_defense_patterns`), 1 new Redis key pattern, 4 new Kafka
topics, 1 new Vault path scheme. Migration 059 creates every table and
seeds 6 catalogue entries + ≥ 20 injection patterns.

---

## 1. PostgreSQL tables

### 1.1 `model_catalog_entries`

Matches user-provided DDL.

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID (PK) | `DEFAULT gen_random_uuid()` |
| `provider` | VARCHAR(64) | `NOT NULL` |
| `model_id` | VARCHAR(256) | `NOT NULL` |
| `display_name` | VARCHAR(256) | `NULL` |
| `approved_use_cases` | JSONB | `NULL` |
| `prohibited_use_cases` | JSONB | `NULL` |
| `context_window` | INTEGER | `NOT NULL CHECK (> 0)` |
| `input_cost_per_1k_tokens` | NUMERIC(10, 6) | `NOT NULL CHECK (>= 0)` |
| `output_cost_per_1k_tokens` | NUMERIC(10, 6) | `NOT NULL CHECK (>= 0)` |
| `quality_tier` | VARCHAR(16) | `NOT NULL CHECK (IN ('tier1', 'tier2', 'tier3'))` |
| `approved_by` | UUID | `NOT NULL REFERENCES users(id)` |
| `approved_at` | TIMESTAMPTZ | `NOT NULL DEFAULT now()` |
| `approval_expires_at` | TIMESTAMPTZ | `NOT NULL CHECK (approval_expires_at > approved_at)` |
| `status` | VARCHAR(32) | `NOT NULL DEFAULT 'approved' CHECK (IN ('approved', 'deprecated', 'blocked'))` |
| `created_at` | TIMESTAMPTZ | `NOT NULL DEFAULT now()` |
| `updated_at` | TIMESTAMPTZ | `NOT NULL DEFAULT now()` |

**Indexes**: `UNIQUE (provider, model_id)`; `ix_model_catalog_status_expires`
on `(status, approval_expires_at)` for the auto-deprecation scanner.

### 1.2 `model_cards`

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID (PK) | |
| `catalog_entry_id` | UUID | `NOT NULL UNIQUE REFERENCES model_catalog_entries(id) ON DELETE CASCADE` |
| `capabilities` | TEXT | `NULL` |
| `training_cutoff` | DATE | `NULL` |
| `known_limitations` | TEXT | `NULL` |
| `safety_evaluations` | JSONB | `NULL` |
| `bias_assessments` | JSONB | `NULL` |
| `card_url` | TEXT | `NULL` |
| `revision` | INTEGER | `NOT NULL DEFAULT 1` |
| `created_at` | TIMESTAMPTZ | `NOT NULL DEFAULT now()` |
| `updated_at` | TIMESTAMPTZ | `NOT NULL DEFAULT now()` |

**Material-change detection**: an update to `safety_evaluations` or
`bias_assessments` increments `revision` AND emits
`model.card.published` event with `material: true`; updates to other
fields increment `revision` with `material: false`. The trust BC
listens for `material: true` events and flags affected agent
certifications for re-review.

### 1.3 `model_fallback_policies`

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID (PK) | |
| `name` | VARCHAR(128) | `NOT NULL` |
| `scope_type` | VARCHAR(16) | `NOT NULL CHECK (IN ('global', 'workspace', 'agent'))` |
| `scope_id` | UUID | `NULL` — NULL iff scope_type='global' |
| `primary_model_id` | UUID | `NOT NULL REFERENCES model_catalog_entries(id)` |
| `fallback_chain` | JSONB | `NOT NULL` — array of UUIDs referencing model_catalog_entries |
| `retry_count` | INTEGER | `NOT NULL DEFAULT 3 CHECK (> 0 AND <= 10)` |
| `backoff_strategy` | VARCHAR(32) | `NOT NULL DEFAULT 'exponential' CHECK (IN ('fixed', 'linear', 'exponential'))` |
| `acceptable_quality_degradation` | VARCHAR(16) | `NOT NULL DEFAULT 'tier_plus_one' CHECK (IN ('tier_equal', 'tier_plus_one', 'tier_plus_two'))` |
| `recovery_window_seconds` | INTEGER | `NOT NULL DEFAULT 300 CHECK (>= 30)` |
| `created_at` | TIMESTAMPTZ | `NOT NULL DEFAULT now()` |

**Check constraints**:
- `CHECK ((scope_type = 'global' AND scope_id IS NULL) OR (scope_type != 'global' AND scope_id IS NOT NULL))`

**Indexes**:
- `ix_fallback_scope` on `(scope_type, scope_id)` for resolution lookup.
- `ix_fallback_primary` on `(primary_model_id)` for chain-side joins.

**Application-layer validations (per research.md D-009)**:
- Chain has no cycles.
- Every chain entry's `context_window >= primary.context_window`.
- No chain entry exceeds `acceptable_quality_degradation` below primary.

### 1.4 `model_provider_credentials`

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID (PK) | |
| `workspace_id` | UUID | `NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE` |
| `provider` | VARCHAR(64) | `NOT NULL` |
| `vault_ref` | VARCHAR(256) | `NOT NULL` — e.g. `secret/data/musematic/prod/providers/{workspace_id}/openai` |
| `rotated_at` | TIMESTAMPTZ | `NULL` |
| `rotation_schedule_id` | UUID | `NULL REFERENCES secret_rotation_schedules(id) ON DELETE SET NULL` |
| `created_at` | TIMESTAMPTZ | `NOT NULL DEFAULT now()` |

**Indexes**: `UNIQUE (workspace_id, provider)`.

**Note**: The raw credential is NEVER in this table; only the Vault
path reference. Rotation is delegated to UPD-024's
`secret_rotation_schedules` via `rotation_schedule_id`.

### 1.5 `injection_defense_patterns` (NEW, per research.md D-011)

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID (PK) | |
| `pattern_name` | VARCHAR(128) | `NOT NULL` |
| `pattern_regex` | TEXT | `NOT NULL` |
| `severity` | VARCHAR(16) | `NOT NULL CHECK (IN ('low', 'medium', 'high', 'critical'))` |
| `layer` | VARCHAR(32) | `NOT NULL CHECK (IN ('input_sanitizer', 'output_validator'))` |
| `action` | VARCHAR(32) | `NOT NULL CHECK (IN ('strip', 'quote_as_data', 'reject', 'redact', 'block'))` |
| `seeded` | BOOLEAN | `NOT NULL DEFAULT false` — TRUE for platform-seeded patterns; cannot be deleted |
| `workspace_id` | UUID | `NULL REFERENCES workspaces(id)` — NULL for platform-wide; non-NULL for workspace overrides |
| `created_at` | TIMESTAMPTZ | `NOT NULL DEFAULT now()` |

**Seeded patterns** (partial list, ≥ 20 shipped):
- `role_reversal`: `(?i)ignore\s+(all\s+)?(previous|above)\s+instructions`
- `instruction_injection`: `(?i)you\s+are\s+now\s+`
- `delimiter_confusion`: various delimiter-escape patterns
- `jwt_detection`: `eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+`
- `bearer_token`: `Bearer\s+[A-Za-z0-9_\-.=]+`
- `api_key_prefix`: `msk_[A-Za-z0-9]{32,}`
- `email_exfiltration`: `[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}`
- ... (13+ more covering well-known injection techniques)

**Indexes**: `ix_injection_patterns_layer` on
`(layer, workspace_id, severity)`.

---

## 2. Redis

| Key pattern | Purpose | TTL |
|---|---|---|
| `router:primary_sticky:{workspace_id}:{primary_model_id}` | Sticky cache for fallback recovery (values: `use_primary`, `in_fallback`) | `recovery_window_seconds` (default 300) |
| `router:catalog:{model_id}` | In-process cache of catalogue entry status (application-layer LRU, not Redis) | 60 s |
| `router:credential:{workspace_id}:{provider}` | Cached resolved credential (handled by `RotatableSecretProvider` from UPD-024) | 60 s |

---

## 3. Kafka — 4 new topics (per constitution §7)

| Topic | Producer | Consumer |
|---|---|---|
| `model.catalog.updated` | `model_catalog/catalog_service` | registry, workflow, audit chain, compliance_service |
| `model.card.published` | `model_catalog/model_card_service` | trust, registry, compliance_service |
| `model.fallback.triggered` | `common/clients/model_router` | analytics, cost_governance, operator dashboard |
| `model.deprecated` | `model_catalog/catalog_service` + `workers/auto_deprecation_scanner` | notifications, registry |

---

## 4. Vault

Path scheme: `secret/data/musematic/{env}/providers/{workspace_id}/{provider}`

Value shape (during active rotation, per UPD-024):

```json
{
  "current": "<api_key>",
  "previous": "<api_key>",
  "overlap_ends_at": "<ISO8601>"
}
```

Outside an active rotation, only `current` is present.

---

## 5. Migration 059 shape

```python
# apps/control-plane/migrations/versions/059_model_catalog.py
revision = "059"
down_revision = "058"

def upgrade() -> None:
    _create_catalog_table(op)              # §1.1
    _create_cards_table(op)                # §1.2
    _create_fallback_policies_table(op)    # §1.3
    _create_provider_credentials_table(op) # §1.4
    _create_injection_patterns_table(op)   # §1.5
    _seed_catalogue_entries(op)            # 6 entries per research.md D-006
    _seed_injection_patterns(op)           # ≥ 20 patterns per D-011

def downgrade() -> None:
    op.drop_table("injection_defense_patterns")
    op.drop_table("model_provider_credentials")
    op.drop_table("model_fallback_policies")
    op.drop_table("model_cards")
    op.drop_table("model_catalog_entries")
```

Total migration ≈ 350 lines (mostly seed data).
