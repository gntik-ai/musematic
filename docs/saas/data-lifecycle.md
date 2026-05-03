# Data Lifecycle (UPD-051)

The Data Lifecycle bounded context owns workspace- and tenant-scoped data export, two-phase deletion with grace, DPA management, the public sub-processors page, GDPR Article 28 evidence packages, and 30-day backup-purge separation for deleted tenants.

The implementation follows the spec at `specs/104-data-lifecycle/spec.md`. This page covers the user-facing capability set and the operator surface.

## Capability map

| Capability | Tier | UI surface | API surface |
|---|---|---|---|
| Workspace data export | Free, Pro | `/workspaces/{id}/data-export` | `POST /api/v1/workspaces/{id}/data-export` |
| Workspace deletion (two-phase) | Free, Pro | `/workspaces/{id}/settings/delete` + cancel link | `POST /api/v1/workspaces/{id}/deletion-jobs` + `POST /api/v1/workspaces/cancel-deletion/{token}` |
| Tenant data export | Enterprise | `/admin/tenants/{id}/data-export` | `POST /api/v1/admin/tenants/{id}/data-export` |
| Tenant deletion (two-phase) | Enterprise | `/admin/tenants/{id}/delete` (2PA-gated) | `POST /api/v1/admin/tenants/{id}/deletion-jobs` |
| DPA management | Enterprise | `/admin/dpa` | `POST /api/v1/admin/tenants/{id}/dpa` (multipart) |
| Public sub-processors page | Public | `https://musematic.ai/legal/sub-processors` | `GET /api/v1/public/sub-processors{,.rss}` |
| Article 28 evidence package | Enterprise | `/admin/tenants/{id}/article28-evidence` | `POST /api/v1/admin/tenants/{id}/article28-evidence` |

## Workspace export (US1)

A workspace owner navigates to `/workspaces/{id}/data-export`, clicks Request export, and receives a notification email when the async job completes. The email contains a presigned URL with a 7-day TTL.

The ZIP layout is:

```
metadata.json            # workspace identity + export timestamp
agents/                  # one JSON per registered agent + index
executions/              # execution records + task plans
audit/                   # workspace-scoped audit chain (JSONL)
costs/                   # daily/monthly cost rollups
members/                 # workspace member roster (privacy-redacted)
README.md                # how to read the archive
```

Member email addresses are redacted by default per FR-751.4. Cross-workspace email exposure is prohibited; opt-in disclosure is a forthcoming enhancement.

Rate limit: at most 5 export requests per workspace per 24 hours. Concurrent requests against an in-flight job return the existing job (idempotency).

## Workspace deletion (US2)

Two-phase: phase_1 marks `pending_deletion` with a 7-day cancel link emailed to the owner. Phase_2, after grace expires, runs the cross-store cascade and transitions the workspace to `deleted`.

The cancel link is anti-enumeration (R10): visiting it always returns the same message regardless of token validity. Server-side audit records distinguish `token_unknown`, `token_expired`, `token_already_used`, and `cancelled`.

Per-tenant grace overrides live in `tenants.contract_metadata_json.deletion_grace_period_days` (Enterprise contract option). Default 7 days, bounded between 7 and 90.

A 90-day audit tombstone is retained after cascade. After 90 days, the tombstone is reduced to a hash-anchor entry preserving chain integrity.

## Tenant cancellation (US3)

Super admin opens `/admin/tenants/{id}/delete`, types `delete tenant {slug}`, and approves a fresh 2PA challenge. The platform refuses if any subscription is in `trial`, `active`, or `past_due` (FR-754.2 — cancel via UPD-052 first).

Phase_1 enqueues a final tenant export (encrypted, 30-day signed-URL TTL, OOB password). Default grace is 30 days, bounded by per-contract overrides up to 90.

Phase_2 cascade walks every tenant-scoped data plane (PostgreSQL, Qdrant, Neo4j, ClickHouse, OpenSearch, S3) through the privacy_compliance `CascadeOrchestrator`, then runs the DNS/TLS teardown leg (UPD-053, feature-flagged), then schedules the 30-day backup-purge via key-destruction (FR-759).

Audit-chain history is moved to the cold-storage bucket `platform-audit-cold-storage` (S3 Object Lock COMPLIANCE, 7-year retention, separate KMS key). The active chain receives an anchor entry preserving the running hash.

## Public sub-processors page (US4)

The page lists every active third-party sub-processor with category, location, data categories, and links to their privacy policy and DPA. The route is operationally independent of the main control plane (rule 49) — it serves from a dedicated `public-pages` Helm release with a regenerator-snapshot ConfigMap fallback.

RSS feed at `/legal/sub-processors.rss`. Email subscription endpoint accepts any address with anti-enumeration (always 202).

Operator changes (add / modify / remove) propagate to the live page within 5 minutes (FR-757.5) via the regenerator cron. Every change emits an audit chain entry and a Kafka event that the notifications BC fans out to subscribed endpoints with HMAC-signed webhooks.

## DPA management (US5)

Super admin uploads a tenant-specific DPA PDF at `/admin/dpa`. Upload limits: 50 MB, must start with `%PDF-` magic bytes, version must match `v[0-9]+(\.[0-9]+){0,2}`.

Every upload is virus-scanned by the in-cluster ClamAV daemon. On detection: 422 + `dpa_virus_detected`; on scanner unreachable: 503 + `dpa_scan_unavailable`. Both modes emit audit entries and are visible on the Grafana `Data Lifecycle - UPD-051` dashboard.

The PDF bytes are stored encrypted in Vault at `secret/data/musematic/{env}/tenants/{slug}/dpa/dpa-{version}.pdf` (base64-encoded `value` + metadata). The tenant row records `dpa_signed_at`, `dpa_version`, `dpa_artifact_uri`, `dpa_artifact_sha256`.

Versioning is append-only. Older versions remain addressable until the tenant cascade.

Tenant admins can view their own active DPA metadata at `/api/v1/me/tenant/dpa` (rule 46 — no `tenant_id` parameter, operates on the JWT principal's tenant).

## Article 28 evidence

The endpoint composes a single ZIP containing the active DPA + sub-processors snapshot + audit-chain extract (last 12 months) + residency config + maintenance history + a signed manifest with SHA-256 per file. Delivery uses the standard tenant-export job machinery; the resulting URL has a 30-day TTL.

## Backup separation (FR-759)

After phase_2 cascade completion, the platform schedules a key-destruction operation 30 days out. The tenant's encrypted backup segment is re-keyed and the prior key destroyed, leaving the data unrecoverable while preserving the cryptographic tombstone for regulatory retention.

## Operator runbooks

- `deploy/runbooks/data-lifecycle/tenant-deletion-failed-cascade.md`
- `deploy/runbooks/data-lifecycle/export-job-stuck.md`
- `deploy/runbooks/data-lifecycle/dpa-virus-scan-unavailable.md`
- `deploy/runbooks/data-lifecycle/dns-teardown-manual.md`
- `deploy/runbooks/data-lifecycle/cold-storage-retention-restore.md`

## Constitution mapping

| Rule | How this BC honours it |
|---|---|
| 9 + AD-18 (audit chain) | Every operation emits a hash-linked entry via `audit/service.AuditChainService` |
| 14 (tags/labels) | New entities register with `entity_tags`/`entity_labels` polymorphic substrate |
| 15 (cascade) | Delegates to `privacy_compliance/services/cascade_orchestrator.CascadeOrchestrator` (extended with workspace/tenant scope methods) |
| 16 + AD-17 (tombstones) | Cascade emits a tombstone before reporting complete |
| 24, 27 (dashboards) | `deploy/helm/observability/templates/dashboards/data-lifecycle.yaml` |
| 25 (BC E2E + journey) | `tests/e2e/suites/data_lifecycle/` + J27 Tenant Lifecycle Cancellation |
| 29-30 (admin segregation + role gate) | All admin routes under `/api/v1/admin/*` with `require_superadmin` |
| 33 (2PA server-side) | Tenant deletion validates a fresh 2PA challenge id |
| 35 (anti-enumeration) | Cancel-deletion + sub-processor subscribe return identical responses regardless of outcome |
| 46 (`/api/v1/me/*`) | Tenant DPA self-service operates on the JWT principal's tenant only |
| 49 (operationally independent public pages) | Sub-processors page ships in `public-pages` Helm release |

## Configuration reference

See `docs/configuration/environment-variables.md` for the auto-generated reference. The `DATA_LIFECYCLE_*` and `FEATURE_UPD05{3,7}_*` env vars control export bucket, DPA Vault path, ClamAV host/port, grace defaults, and DNS-teardown / SMS-password feature flags.
