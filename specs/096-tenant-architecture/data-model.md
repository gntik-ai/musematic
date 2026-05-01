# Phase 1 — Data Model

**Feature**: UPD-046 — Tenant Architecture
**Date**: 2026-05-01

This document specifies the database schema introduced or modified by UPD-046. Concrete column types, indexes, constraints, and RLS policies are listed at a level sufficient for `/speckit-tasks` to derive Alembic migration tasks. The corresponding Python SQLAlchemy models are produced in Track A.

## Entity 1 — `Tenant`

**Owning bounded context**: `apps/control-plane/src/platform/tenants/`
**Table**: `tenants`
**Owner**: `tenants/models.py`
**Migration**: `096_tenant_table_and_seed.py`

### Columns

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK, `DEFAULT gen_random_uuid()` | The default tenant uses the hardcoded UUID `00000000-0000-0000-0000-000000000001`. |
| `slug` | `VARCHAR(32)` | `NOT NULL UNIQUE`, `CHECK (slug ~ '^[a-z][a-z0-9-]{0,30}[a-z0-9]$')` | URL-safe; first char lowercase letter; cannot end with hyphen; max 32 chars. |
| `kind` | `VARCHAR(16)` | `NOT NULL`, `CHECK (kind IN ('default', 'enterprise'))` | Constitutional rule SaaS-2. |
| `subdomain` | `VARCHAR(64)` | `NOT NULL UNIQUE` | The subdomain piece used by the hostname resolver. The default tenant's subdomain is `app`. |
| `display_name` | `VARCHAR(128)` | `NOT NULL` | Human-readable name shown in `/admin/tenants` and in branding fallback. |
| `region` | `VARCHAR(32)` | `NOT NULL` | Region label for residency policies (FR-468 carryover). |
| `data_isolation_mode` | `VARCHAR(8)` | `NOT NULL DEFAULT 'pool'`, `CHECK (data_isolation_mode IN ('pool', 'silo'))` | `pool` means shared physical infrastructure (this feature); `silo` is reserved for future per-tenant cluster. |
| `branding_config_json` | `JSONB` | `NOT NULL DEFAULT '{}'::jsonb` | See `TenantBrandingConfiguration` shape below. |
| `subscription_id` | `UUID` | `NULL` | FK added later in UPD-047; nullable here because UPD-046 must land before UPD-047. |
| `status` | `VARCHAR(24)` | `NOT NULL DEFAULT 'active'`, `CHECK (status IN ('active', 'suspended', 'pending_deletion'))` | Lifecycle state. |
| `scheduled_deletion_at` | `TIMESTAMPTZ` | `NULL` | Set when status transitions to `pending_deletion`; the deletion job runs at or after this time. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT now()` | |
| `created_by_super_admin_id` | `UUID` | `NULL`, FK `users.id` | NULL for the default tenant (seeded). |
| `dpa_signed_at` | `TIMESTAMPTZ` | `NULL` | NULL for the default tenant; required for `enterprise` kind. |
| `dpa_version` | `VARCHAR(32)` | `NULL` | DPA template version recorded at upload. |
| `dpa_artifact_uri` | `VARCHAR(512)` | `NULL` | S3 URI in `tenant-dpas` bucket. Path scheme: `s3://tenant-dpas/{tenant_slug}/{dpa_version}-{timestamp}.pdf`. |
| `dpa_artifact_sha256` | `VARCHAR(64)` | `NULL` | Hex-encoded SHA-256 of the uploaded DPA, recorded at upload. |
| `contract_metadata_json` | `JSONB` | `NOT NULL DEFAULT '{}'::jsonb` | Free-form: contract number, signed-by, expiry, etc. |
| `feature_flags_json` | `JSONB` | `NOT NULL DEFAULT '{}'::jsonb` | Per-tenant feature flag overrides. |

### Indexes & constraints

- `tenants_pkey` on `(id)` (implicit).
- `tenants_slug_key` UNIQUE on `(slug)` (implicit).
- `tenants_subdomain_key` UNIQUE on `(subdomain)` (implicit).
- `tenants_one_default` UNIQUE partial on `(kind)` `WHERE kind = 'default'` — enforces "exactly one default tenant".
- `tenants_kind_status_idx` on `(kind, status)` — for `/admin/tenants` filtering.
- `tenants_scheduled_deletion_at_idx` partial on `(scheduled_deletion_at)` `WHERE status = 'pending_deletion'` — for the deletion-cascade scheduler.

### Triggers

- `tenants_reserved_slug_check` BEFORE INSERT OR UPDATE — refuses if `slug IN ('api', 'grafana', 'status', 'www', 'admin', 'platform', 'webhooks', 'public', 'docs', 'help')` AND `kind != 'default'`.
- `tenants_default_immutable` BEFORE UPDATE OR DELETE — refuses any update that changes `slug`, `subdomain`, `kind`, or `status` of the row where `kind='default'`, and refuses any delete of that row. Constitutional rule SaaS-9; FR-002.

### Row Level Security

The `tenants` table is itself NOT under RLS (it is the source of truth for tenant identity and is read by the resolver via the regular role). The default-tenant-immutable trigger and the `tenants_one_default` index are sufficient guards. Cross-tenant browsing of the `tenants` table is restricted to `/api/v1/admin/tenants/*` (super admin) and `/api/v1/platform/tenants/*` (platform staff) at the routing layer.

## Entity 2 — `TenantBrandingConfiguration` (JSONB shape inside `tenants.branding_config_json`)

```jsonc
{
  "logo_url": "https://...",        // optional; renders default Musematic logo if absent
  "accent_color_hex": "#0078d4",     // optional; renders default accent if absent
  "display_name_override": null,     // optional; falls back to tenants.display_name
  "favicon_url": null,               // optional
  "support_email": "support@acme.com", // optional; rendered in footer
  "_reserved": {}                    // forward-compatible extension point
}
```

The default tenant's `branding_config_json` is `{}` and stays empty (rule FR-038).

## Entity 3 — `Tenant` lifecycle audit chain entries

The existing `audit_chain_entries` table (owner: `audit/models.py`) gains a `tenant_id` column (see "Modifications to existing tables" below). Each tenant lifecycle action emits an entry of the following shape via `AuditChainService.append()`:

| Field | Notes |
|---|---|
| `audit_event_source` | Constant `tenants` |
| `event_type` | One of `tenants.created`, `tenants.suspended`, `tenants.reactivated`, `tenants.scheduled_for_deletion`, `tenants.deletion_cancelled`, `tenants.deleted` (tombstone) |
| `actor_role` | `super_admin` or `platform_staff` |
| `tenant_id` | The subject tenant's UUID |
| `canonical_payload` | JSON containing slug, display_name, kind, status_before, status_after, dpa_version (for create), scheduled_deletion_at (for schedule), and operation-specific details |
| `previous_hash`, `entry_hash` | Inherited from the chain |

The deletion-tombstone entry's payload includes a cryptographic proof field `cascade_complete: true` and a digest of the row counts cleared per BC.

## Modifications to existing tables — add `tenant_id`

The migration suite 097→100 adds `tenant_id UUID NOT NULL` to every table in the catalogue below. Each table also gets a per-table index `<table>_tenant_id_idx` (migration 099) and an RLS policy `tenant_isolation` (migration 100). The catalogue is derived from the Phase 0 inventory of 35 bounded contexts × the SQLAlchemy models in each.

### Catalogue of tenant-scoped tables

> The catalogue is grouped by owning bounded context; the table list within each BC is the comprehensive set of tables managed by that BC's `models.py`. Approximately **41 tables** in total — this matches the spec's "~40" estimate.

| BC | Tables |
|---|---|
| `accounts` | `users`, `user_profiles`, `organizations`, `invitations`, `approval_queue` |
| `auth` | `user_credentials`, `mfa_enrollments`, `auth_attempts`, `password_reset_tokens`, `oauth_providers` (also Track E composite uniqueness change), `oauth_links`, `oauth_provider_rate_limits`, `ibor_syncs`, `ibor_group_mappings` |
| `audit` | `audit_chain_entries` (also: hash function update — see R7) |
| `workspaces` | `workspaces`, `memberships`, `workspace_settings`, `workspace_goals`, `workspace_agent_decision_configs` |
| `registry` | `agent_namespaces`, `agent_profiles`, `agent_revisions`, `capability_models` |
| `execution` | `execution_records`, `execution_steps`, `approval_requests`, `compensation_records`, `scheduled_triggers` |
| `cost_governance` | `cost_attributions`, `workspace_budgets`, `budget_alerts`, `cost_forecasts`, `cost_anomalies` |
| `interactions` | `interactions`, `messages`, `participant_mappings`, `branches`, `attention_items` |
| `governance` | `governance_verdicts`, `enforcement_actions` |
| `policies` | `policy_policies`, `policy_versions`, `policy_attachments`, `policy_blocked_action_records` |
| `composition` | `composition_requests`, `composition_audit_events`, `composition_topologies` |
| `connectors` | `connector_instances`, `connector_health_records`, `connector_invocations`, `dead_letter_records` |
| `context_engineering` | `context_sources`, `profile_assignments`, `ab_tests`, `correlation_profiles`, `compaction_logs` |
| `discovery` | `discovery_sessions`, `hypotheses`, `embedding_results`, `tournament_rounds`, `governance_signals` |
| `evaluation` | `eval_sets`, `eval_runs`, `verdicts`, `experiments`, `ate_runs` |
| `fleets` | `fleets`, `fleet_members`, `fleet_metrics`, `fleet_edges` |
| `fleet_learning` | `adaptation_signals`, `performance_metrics` |
| `incident_response` | `incident_integrations`, `incidents`, `incident_external_alerts`, `runbooks`, `post_mortems` |
| `marketplace` | `marketplace_agent_ratings`, `marketplace_quality_aggregates`, `marketplace_recommendations`, `marketplace_trending_snapshots` |
| `memory` | `memory_entries`, `evidence_conflicts`, `embedding_jobs`, `embedding_patterns`, `retention_policies` |
| `model_catalog` | `model_catalog_entries`, `model_cards`, `model_fallback_policies`, `model_provider_credentials`, `injection_defense_patterns` |
| `multi_region_ops` | `region_configs`, `replication_statuses`, `failover_plans`, `failover_plan_runs`, `maintenance_windows` |
| `notifications` | `user_alert_settings`, `user_alerts`, `alert_delivery_outcomes`, `notification_channel_configs`, `outbound_webhooks` |
| `privacy_compliance` | `privacy_dsr_requests`, `consent_audit_logs`, `dlp_policies`, `privacy_impact_assessments` |
| `security_compliance` | `software_bills_of_materials`, `vulnerability_scan_results`, `vulnerability_exceptions`, `penetration_tests`, `pentest_findings`, `pentest_sla_policies`, `secret_rotation_schedules`, `jit_credential_grants` |
| `simulation` | `simulation_scenarios`, `simulation_runs`, `simulation_metrics`, `simulation_traces` |
| `status_page` | `platform_status_snapshots`, `status_subscriptions`, `subscription_dispatches` |
| `testing` | `generated_test_suites`, `adversarial_test_cases`, `coordination_test_results`, `drift_alerts` |
| `trust` | `trust_certifications`, `guardrail_behaviors`, `oje_verdicts`, `recertification_schedules` |
| `two_person_approval` | `two_person_approval_challenges`, `approval_responses` |
| `workflows` | `workflow_definitions`, `workflow_versions`, `workflow_trigger_definitions`, `workflow_executions` |
| `agentops` | `baseline_metrics`, `regression_alerts`, `canary_deployments`, `retirement_workflows` |
| `analytics` | `cost_models`, `embedding_metrics` |
| `localization` | `user_preferences`, `locale_files` |
| `a2a_gateway` | `a2a_tasks`, `a2a_external_endpoints`, `a2a_audit_records` |

> **Out of scope for `tenant_id`** (platform-wide): platform metadata tables in `multi_region_ops` that describe regions themselves; tables in `model_catalog` that describe globally-approved models (with the model_provider_credentials table being the exception — those are tenant-scoped because Enterprise tenants supply their own provider credentials); cert-manager and observability tables are platform-scoped and do not appear in any BC. The exact carve-outs are confirmed with each BC owner during Track C.

### Per-table changes (applied in migration suite)

For every table in the catalogue:

```text
ALTER TABLE <table> ADD COLUMN tenant_id UUID NULL;            -- 097
UPDATE <table> SET tenant_id = '00000000-0000-0000-0000-000000000001'; -- 098 (with checkpoint table marking)
ALTER TABLE <table> ALTER COLUMN tenant_id SET NOT NULL;        -- 099
CREATE INDEX <table>_tenant_id_idx ON <table> (tenant_id);     -- 099
ALTER TABLE <table> ENABLE ROW LEVEL SECURITY;                  -- 100
CREATE POLICY tenant_isolation ON <table>
  USING (tenant_id = current_setting('app.tenant_id', true)::uuid); -- 100
ALTER TABLE <table> FORCE ROW LEVEL SECURITY;                   -- 100 — forces RLS on table owners too
```

Each step in the suite writes a row to the `_alembic_tenant_backfill_checkpoint(table_name TEXT PRIMARY KEY, completed_phase TEXT NOT NULL, completed_at TIMESTAMPTZ NOT NULL DEFAULT now())` table; resumption skips already-completed phases.

## Modifications to specific existing tables

### `oauth_providers` (Track E, migration 102)

Replace existing `UNIQUE (provider_type)` with `UNIQUE (tenant_id, provider_type)`. Backfill `tenant_id = default tenant UUID` (already done by 098 + 099). All other OAuth columns unchanged.

### `audit_chain_entries` (R7)

In addition to the standard `tenant_id` column added by 097→099, the canonical-payload hashing function in `audit/service.py` is updated to include `tenant_id` in the hashed bytes. A schema-version-boundary entry is inserted as the first new-format entry (its `previous_hash` is the last v1 entry's hash; its `event_type` is `audit.schema.tenant_id_added`).

## Database role and connection-pool segregation

### Migration 101 — `musematic_platform_staff` role

```sql
-- Run as a database superuser (privileged install/upgrade context).
CREATE ROLE musematic_platform_staff LOGIN BYPASSRLS;
ALTER ROLE musematic_platform_staff SET search_path = public;
GRANT USAGE ON SCHEMA public TO musematic_platform_staff;
GRANT SELECT, INSERT, UPDATE, DELETE
  ON ALL TABLES IN SCHEMA public TO musematic_platform_staff;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO musematic_platform_staff;
```

The application's regular role (`musematic_app`, already exists) remains without `BYPASSRLS`.

### Application engine segregation

`common/database.py` exposes two async engines and two session factories:

- `regular_engine` / `get_session()` — `musematic_app` role; default for routes outside `/api/v1/platform/*`.
- `platform_staff_engine` / `get_platform_staff_session()` — `musematic_platform_staff` role; only used in `tenants/platform_router.py` and other routes under `/api/v1/platform/*`.

A FastAPI dependency-tree segregation enforces this at runtime; CI rule (FR-042) enforces it statically.

## State transitions for `Tenant.status`

```text
                      ┌──── reactivate ────┐
                      ↓                    │
   (insert) → active ──→ suspended ────────┘
              │  ↑           │
              │  │           ├──── (super admin schedules deletion) ──→ pending_deletion
              │  │                                                          │  │
              │  │             (cancel deletion before grace expires)       │  │
              │  └──────────────────────────────────────────────────────────┘  │
              │                                                                │
              │                       (grace period elapsed; cascade job runs) │
              └────────────────────── (delete + tombstone) ───────────────────┘
                                              │
                                              ↓
                                     (row deleted; audit-chain tombstone persists)
```

`tenants_default_immutable` trigger refuses any transition where the row's `kind='default'`.

## Kafka events emitted by tenant lifecycle

Topic: `tenants.lifecycle` (additive — new topic owned by this feature; partition key = `tenant_id`).

Event types: `tenants.created`, `tenants.suspended`, `tenants.reactivated`, `tenants.scheduled_for_deletion`, `tenants.deletion_cancelled`, `tenants.deleted`, `tenants.branding_updated`. Envelope follows the canonical EventEnvelope shape (UPD-013); detailed payload schema in `contracts/tenant-events-kafka.md`.

## Reserved slug list

```text
api, grafana, status, www, admin, platform, webhooks, public, docs, help
```

This list lives in three places (constitutional defense-in-depth, FR-003):

1. `apps/web/components/features/admin/TenantProvisionForm.tsx` (Zod schema, client-side validation).
2. `apps/control-plane/src/platform/tenants/service.py:RESERVED_SLUGS` (server-side service validation).
3. `tenants_reserved_slug_check` PostgreSQL trigger (database guard).

All three are kept in sync via a CI check that compares the three sources to a single source-of-truth file `apps/control-plane/src/platform/tenants/reserved_slugs.py`.

## End of data model.
