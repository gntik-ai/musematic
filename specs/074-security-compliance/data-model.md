# Phase 1 Data Model: Security Compliance and Supply Chain

**Feature**: 074-security-compliance
**Date**: 2026-04-23

## Overview

Thirteen new Postgres tables across two new bounded contexts
(`audit/` + `security_compliance/`), three new Redis key patterns,
seven new Kafka topics, and one new S3 bucket. Migration 058
creates every table and seeds the four framework catalogues.

---

## 1. PostgreSQL — `audit/` BC (1 table)

### 1.1 `audit_chain_entries`

Every audit event across the platform adds one row here.

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID (PK) | `DEFAULT gen_random_uuid()` |
| `sequence_number` | BIGSERIAL | `NOT NULL UNIQUE` — monotonic |
| `previous_hash` | VARCHAR(64) | `NOT NULL` — hex SHA-256 |
| `entry_hash` | VARCHAR(64) | `NOT NULL UNIQUE` — hex SHA-256 |
| `audit_event_id` | UUID | `NULL` — FK-like reference (not enforced; `ON DELETE SET NULL` semantics via RTBF logic). Points to the producing BC's audit row |
| `audit_event_source` | VARCHAR(64) | `NOT NULL` — the producing BC (`auth`, `a2a_gateway`, `registry`, `mcp`, `security_compliance`) |
| `canonical_payload_hash` | VARCHAR(64) | `NOT NULL` — SHA-256 of canonical payload |
| `created_at` | TIMESTAMPTZ | `NOT NULL DEFAULT now()` |

**Constraints**:
- `UNIQUE (sequence_number)` — monotonic ordering.
- **DB trigger**: `BEFORE UPDATE OR DELETE` raises exception (append-only).
- The application DB role is granted `INSERT, SELECT` only; `UPDATE, DELETE` revoked.

**Hash construction** (per research.md D-002):
```
entry_hash = sha256_hex(
    previous_hash.encode()           # 64 bytes ASCII hex
    + sequence_number.to_bytes(8, 'big')
    + canonical_payload_hash.encode() # 64 bytes ASCII hex
)
```

`audit_event_id` is intentionally excluded from the immutable hash input so RTBF
logic can set it to `NULL` without breaking the chain. The producing BC remains
responsible for including any stable non-PII event identifier in the canonical
payload before `canonical_payload_hash` is computed.

**Indexes**:
- `PRIMARY KEY (id)`
- `UNIQUE (sequence_number)`
- `UNIQUE (entry_hash)`
- `ix_audit_chain_source_time` on `(audit_event_source, created_at)` — for per-BC querying.

---

## 2. PostgreSQL — `security_compliance/` BC (12 tables)

### 2.1 `software_bills_of_materials`

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID (PK) | `DEFAULT gen_random_uuid()` |
| `release_version` | VARCHAR(64) | `NOT NULL` |
| `format` | VARCHAR(32) | `NOT NULL CHECK (IN ('spdx', 'cyclonedx'))` |
| `content` | TEXT | `NOT NULL` — full SBOM as JSON string |
| `content_sha256` | VARCHAR(64) | `NOT NULL` — integrity hash |
| `generated_at` | TIMESTAMPTZ | `NOT NULL DEFAULT now()` |

**Indexes**: `UNIQUE (release_version, format)`.

### 2.2 `vulnerability_scan_results`

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID (PK) | `DEFAULT gen_random_uuid()` |
| `scanner` | VARCHAR(64) | `NOT NULL CHECK (IN ('trivy', 'grype', 'pip_audit', 'npm_audit', 'govulncheck', 'bandit', 'gosec', 'gitleaks'))` |
| `release_version` | VARCHAR(64) | `NOT NULL` |
| `findings` | JSONB | `NOT NULL` — normalised per D-005 |
| `max_severity` | VARCHAR(32) | `NULL CHECK (IN ('critical','high','medium','low','info',NULL))` |
| `scanned_at` | TIMESTAMPTZ | `NOT NULL DEFAULT now()` |
| `gating_result` | VARCHAR(16) | `NOT NULL CHECK (IN ('passed','blocked'))` |

**Indexes**: `ix_vuln_scan_release` on `(release_version, scanned_at)`; `ix_vuln_scan_severity` on `(max_severity, gating_result)`.

### 2.3 `vulnerability_exceptions` (NEW per D-014)

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID (PK) | |
| `scanner` | VARCHAR(64) | `NOT NULL` |
| `vulnerability_id` | VARCHAR(128) | `NOT NULL` — e.g. `CVE-2025-12345` |
| `component_pattern` | VARCHAR(256) | `NOT NULL` — glob / regex pattern |
| `justification` | TEXT | `NOT NULL CHECK (length(justification) >= 20)` |
| `approved_by` | UUID | `NOT NULL REFERENCES users(id)` |
| `expires_at` | TIMESTAMPTZ | `NOT NULL CHECK (expires_at > now())` |
| `created_at` | TIMESTAMPTZ | `NOT NULL DEFAULT now()` |

**Indexes**: `ix_vuln_exception_active` on `(scanner, vulnerability_id, expires_at)`.

### 2.4 `penetration_tests`

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID (PK) | |
| `scheduled_for` | DATE | `NOT NULL` |
| `executed_at` | TIMESTAMPTZ | `NULL` |
| `firm` | VARCHAR(256) | `NULL` |
| `report_url` | TEXT | `NULL` |
| `attestation_hash` | VARCHAR(64) | `NULL` — SHA-256 of report + metadata at import time |
| `created_at` | TIMESTAMPTZ | `NOT NULL DEFAULT now()` |

### 2.5 `pentest_findings`

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID (PK) | |
| `pentest_id` | UUID | `NOT NULL REFERENCES penetration_tests(id) ON DELETE CASCADE` |
| `severity` | VARCHAR(16) | `NOT NULL CHECK (IN ('critical','high','medium','low'))` |
| `title` | VARCHAR(512) | `NOT NULL` |
| `description` | TEXT | `NULL` |
| `remediation_status` | VARCHAR(32) | `NOT NULL DEFAULT 'open' CHECK (IN ('open','in_progress','remediated','accepted','wont_fix'))` |
| `remediation_due_date` | DATE | `NOT NULL` |
| `remediated_at` | TIMESTAMPTZ | `NULL` |
| `remediation_notes` | TEXT | `NULL` |

**Indexes**: `ix_pentest_overdue` on `(remediation_status, remediation_due_date)` filtered `WHERE remediation_status = 'open'`.

### 2.6 `pentest_sla_policies` (NEW per D-007)

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID (PK) | |
| `severity` | VARCHAR(16) | `NOT NULL UNIQUE CHECK (IN ('critical','high','medium','low'))` |
| `max_days` | INTEGER | `NOT NULL CHECK (max_days > 0)` |
| `ceiling_days` | INTEGER | `NOT NULL` — constitutional floor (operators cannot widen above this) |

**Seed rows**:
- `('critical', 7, 7)`
- `('high', 30, 30)`
- `('medium', 90, 90)`
- `('low', 180, 180)`

### 2.7 `secret_rotation_schedules`

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID (PK) | |
| `secret_name` | VARCHAR(256) | `NOT NULL UNIQUE` |
| `secret_type` | VARCHAR(64) | `NOT NULL` — e.g. `db_password`, `jwt_signing_key`, `oauth_client_secret` |
| `rotation_interval_days` | INTEGER | `NOT NULL DEFAULT 90 CHECK (> 0 AND <= 365)` |
| `overlap_window_hours` | INTEGER | `NOT NULL DEFAULT 24 CHECK (>= 24 AND <= 168)` |
| `last_rotated_at` | TIMESTAMPTZ | `NULL` |
| `next_rotation_at` | TIMESTAMPTZ | `NULL` |
| `rotation_state` | VARCHAR(32) | `NOT NULL DEFAULT 'idle' CHECK (IN ('idle','rotating','overlap','finalising','failed'))` |
| `vault_path` | VARCHAR(512) | `NOT NULL` — e.g. `secret/data/musematic/prod/rotating/db-password` |

**Indexes**: `ix_rotation_due` on `(next_rotation_at)` filtered `WHERE rotation_state = 'idle'`.

### 2.8 `jit_credential_grants`

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID (PK) | |
| `user_id` | UUID | `NOT NULL REFERENCES users(id) ON DELETE CASCADE` |
| `operation` | VARCHAR(256) | `NOT NULL` |
| `purpose` | TEXT | `NOT NULL CHECK (length(purpose) >= 20)` |
| `status` | VARCHAR(32) | `NOT NULL DEFAULT 'pending' CHECK (IN ('pending','approved','rejected','expired','revoked'))` |
| `approved_by` | UUID | `NULL REFERENCES users(id)` |
| `requested_at` | TIMESTAMPTZ | `NOT NULL DEFAULT now()` |
| `approved_at` | TIMESTAMPTZ | `NULL` |
| `issued_at` | TIMESTAMPTZ | `NULL` |
| `expires_at` | TIMESTAMPTZ | `NULL CHECK (expires_at IS NULL OR expires_at <= issued_at + INTERVAL '24 hours')` |
| `revoked_at` | TIMESTAMPTZ | `NULL` |
| `revoked_by` | UUID | `NULL REFERENCES users(id)` |
| `usage_audit` | JSONB | `NOT NULL DEFAULT '[]'::jsonb` |

**Constraint**: `CHECK (approved_by IS NULL OR approved_by != user_id)` — 2PA.

**Indexes**:
- `ix_jit_user_status` on `(user_id, status, expires_at)`
- `ix_jit_pending` on `(status, requested_at)` filtered `WHERE status = 'pending'`.

### 2.9 `jit_approver_policies` (NEW per D-010)

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID (PK) | |
| `operation_pattern` | VARCHAR(256) | `NOT NULL UNIQUE` — glob (e.g. `db:prod:*`) |
| `required_roles` | JSONB | `NOT NULL` — array of role names |
| `min_approvers` | INTEGER | `NOT NULL DEFAULT 1 CHECK (> 0 AND <= 5)` |
| `max_expiry_minutes` | INTEGER | `NOT NULL CHECK (> 0 AND <= 1440)` — upper bound on grant lifetime |

**Seed rows** (from D-010): `db:prod:*`, `infra:prod:*`, `customer_data:*`, `*` (fallback).

### 2.10 `compliance_controls`

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID (PK) | |
| `framework` | VARCHAR(32) | `NOT NULL CHECK (IN ('soc2','iso27001','hipaa','pci_dss'))` |
| `control_id` | VARCHAR(64) | `NOT NULL` |
| `description` | TEXT | `NOT NULL` |
| `evidence_requirements` | JSONB | `NULL` |

**Indexes**: `UNIQUE (framework, control_id)`.

**Seeded** from YAML files in
`apps/control-plane/src/platform/security_compliance/frameworks/`.

### 2.11 `compliance_evidence_mappings` (NEW per D-011)

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID (PK) | |
| `evidence_type` | VARCHAR(64) | `NOT NULL` — e.g. `sbom_generated`, `vulnerability_scan_completed` |
| `control_id` | UUID | `NOT NULL REFERENCES compliance_controls(id) ON DELETE CASCADE` |
| `filter_expression` | TEXT | `NULL` — optional JSONPath filter on the event payload |

**Indexes**: `ix_mapping_by_evidence` on `(evidence_type)`.

### 2.12 `compliance_evidence`

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID (PK) | |
| `control_id` | UUID | `NOT NULL REFERENCES compliance_controls(id) ON DELETE CASCADE` |
| `evidence_type` | VARCHAR(64) | `NOT NULL` |
| `evidence_ref` | TEXT | `NOT NULL` — opaque pointer (e.g. `sbom:<sbom_id>`, `scan:<scan_id>`, `pentest:<finding_id>`, `s3://compliance-evidence/<path>`) |
| `evidence_hash` | VARCHAR(64) | `NULL` — SHA-256 of referenced artefact |
| `collected_at` | TIMESTAMPTZ | `NOT NULL DEFAULT now()` |
| `collected_by` | UUID | `NULL REFERENCES users(id)` — NULL for auto-collected |

**Indexes**: `ix_evidence_by_control` on `(control_id, collected_at)`.

---

## 3. Redis

| Key pattern | Purpose | TTL |
|---|---|---|
| `jit:revoked:{grant_id}` | Denylist for revoked JIT grants (JWT validators check) | = remaining grant lifetime |
| `rotation:state:{secret_name}` | Cached `current`/`previous`/`overlap_ends_at` | 60 s |
| `chain:last_seq` | Monotonic counter optimisation (always falls back to DB on miss) | 5 s |

---

## 4. Kafka — 7 new topics (per constitution §7)

| Topic | Producer | Consumer(s) |
|---|---|---|
| `security.sbom.published` | `security_compliance/sbom_service` | compliance_service (evidence), registry, audit |
| `security.scan.completed` | `security_compliance/vuln_scan_service` | release pipeline, audit, compliance_service |
| `security.pentest.finding.raised` | `security_compliance/pentest_service` | trust, notifications, compliance_service |
| `security.secret.rotated` | `security_compliance/secret_rotation_service` | all credential consumers, audit, compliance_service |
| `security.jit.issued` | `security_compliance/jit_service` | audit, compliance_service |
| `security.jit.revoked` | `security_compliance/jit_service` | audit, compliance_service |
| `security.audit.chain.verified` | `audit/audit_chain_service` | compliance dashboard, compliance_service |

All events carry a `CorrelationContext` envelope (correlation_id,
workspace_id where applicable) consistent with constitution rule 21.

---

## 5. S3

New bucket `compliance-evidence` (generic S3 via existing provider
per principle XVI). Holds manual evidence uploads (PDFs, policies).
Object keys: `{framework}/{control_id}/{timestamp}-{filename}`.

Access: only `compliance_officer` + `platform_admin` roles can
read/write; bucket policy enforces IAM.

---

## 6. Alembic migration 058 shape

```python
# apps/control-plane/migrations/versions/058_security_compliance.py
"""security_compliance: hash chain + sbom + scan + pentest + rotation + jit + compliance evidence"""

revision = "058"
down_revision = "057"
create_date = "2026-04-23"

def upgrade() -> None:
    _create_audit_chain_table(op)              # §1.1
    _create_sbom_table(op)                     # §2.1
    _create_vuln_scan_tables(op)               # §2.2 + §2.3
    _create_pentest_tables(op)                 # §2.4 + §2.5 + §2.6
    _create_rotation_table(op)                 # §2.7
    _create_jit_tables(op)                     # §2.8 + §2.9
    _create_compliance_tables(op)              # §2.10 + §2.11 + §2.12
    _install_audit_chain_trigger(op)           # BEFORE UPDATE/DELETE raise
    _revoke_mutation_perms(op)                 # GRANT INSERT, SELECT only
    _seed_pentest_sla_policies(op)             # §2.6 seed
    _seed_jit_approver_policies(op)            # §2.9 seed
    _seed_compliance_frameworks(op)            # §2.10 + §2.11 from YAML
```

Each `_create_*` function is ≤ 30 lines. Total migration ≈ 400
lines; reviewable in a single PR.

---

## 7. Chain hash signing schema

Ed25519 keypair lives in Vault at `secret/data/musematic/{env}/
audit/signing-key` with keys:

```json
{
  "public_key": "<64 hex chars (32-byte raw)>",
  "private_key": "<64 hex chars (32-byte seed)>",
  "key_version": 1,
  "created_at": "<ISO8601>"
}
```

Attestation document shape (signed):

```json
{
  "platform": "musematic",
  "env": "prod",
  "start_seq": 12345,
  "end_seq": 67890,
  "start_entry_hash": "<64 hex>",
  "end_entry_hash": "<64 hex>",
  "window_start_time": "<ISO8601>",
  "window_end_time": "<ISO8601>",
  "chain_entries_count": 55546,
  "key_version": 1,
  "signature": "<128 hex chars — Ed25519 over the document minus signature>"
}
```
