# Implementation Plan: UPD-051 — Data Lifecycle (Tenant and Workspace)

**Branch**: `104-data-lifecycle` | **Date**: 2026-05-03 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/104-data-lifecycle/spec.md`

## Summary

Adds tenant- and workspace-scoped data lifecycle: async ZIP exports, two-phase deletion with operator-recoverable grace, per-Enterprise-tenant DPA management, public sub-processors page, GDPR Article 28 evidence package, and 30-day backup-purge separation for deleted tenants. Hot-store cascade is **delegated** to the existing `privacy_compliance/services/cascade_orchestrator.CascadeOrchestrator` (PostgreSQL/Qdrant/Neo4j/ClickHouse/OpenSearch/S3 adapters from UPD-023). Audit emission is **delegated** to `audit/service.AuditChainService` (UPD-024 hash-linked chain). Tenant subscription cancellation is **gated** on UPD-052 (hard prerequisite at phase-1). DNS/TLS teardown is **gated** on UPD-053 (soft prerequisite — feature-flagged so deletion still proceeds against data planes if DNS automation is absent). The new BC owns only the data-lifecycle workflow (request, grace, dispatch, evidence) — it never reimplements deletion or audit primitives.

## Technical Context

**Language/Version**: Python 3.12+ (control plane), TypeScript 5.x strict (Next.js 14+ App Router) — no Go work.
**Primary Dependencies (existing)**: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, Alembic 1.13+, aiokafka 0.11+, redis-py 5.x async, aioboto3 (MinIO), httpx 0.27+, APScheduler 3.x, opentelemetry-sdk 1.27+, shadcn/ui, TanStack Query v5, React Hook Form + Zod 3.x.
**Primary Dependencies (NEW)**: `clamd 1.0+` (Python ClamAV daemon client) — virus-scan for DPA uploads. Helm sub-chart `deploy/helm/clamav/` (Bitnami ClamAV image). Optional: signed-URL packing handled by existing `aioboto3`; multi-part upload via existing `S3Client` wrapper.
**Storage**:
- PostgreSQL — 3 new tables (`data_export_jobs`, `deletion_jobs`, `sub_processors`); **brownfield finding**: DPA columns (`dpa_signed_at`, `dpa_version`, `dpa_artifact_uri`, `dpa_artifact_sha256`) ALREADY exist on `tenants` and `tenants.status` ALREADY accepts `pending_deletion` via CHECK constraint, so no DDL change there. The only enum gap is `WorkspaceStatus` (currently `active`/`archived`/`deleted`); migration adds `pending_deletion` to the `workspaces_workspace_status` PostgreSQL enum and updates the SQLAlchemy `WorkspaceStatus` enum class. Alembic migration **111** (32-char id: `111_data_lifecycle`).
- S3-compatible — 2 new buckets via the generic-S3 client (Principle XVI): `data-lifecycle-exports` (export ZIPs, SSE-S3 + 7-day lifecycle expiry on objects under `archive/` prefix) and `platform-audit-cold-storage` (audit-chain tombstones for deleted tenants, S3 Object Lock COMPLIANCE mode, 7-year retention, separate KMS key reference per spec SC-009).
- Vault — 1 path family: `secret/data/musematic/{env}/tenants/{slug}/dpa/dpa-v{n}.pdf` (raw PDF KV v2, accessed only by DPA service).
- Redis — 1 new key namespace: `data_lifecycle:export_lease:{job_id}` (TTL = max-export-duration + grace; deduplicates concurrent dispatch on the export Kafka consumer).
- Kafka — 1 new topic `data_lifecycle.events` (export request/complete/fail, deletion phase transitions, DPA upload, sub-processors change, backup purge).
**Testing**: pytest 8.x + pytest-asyncio (per-BC unit + integration), tests/e2e/suites/data_lifecycle/ (rule 25: 6 e2e tests + J27 journey), Playwright + axe (rule 28 a11y), Vitest + RTL (frontend).
**Target Platform**: Existing Helm umbrella chart at `deploy/helm/platform/`; new sub-chart `deploy/helm/public-pages/` for operationally-independent public sub-processors page (rule 49 status-page-style independence); new sub-chart `deploy/helm/clamav/` for DPA virus-scan daemon.
**Project Type**: Web service (Python control plane + Next.js frontend + new Helm sub-charts).
**Performance Goals**:
- Workspace export ≤ 10 minutes p95 for ≤ 5 GB workspace (SC-001).
- Tenant export ≤ 60 minutes p95 for ≤ 100 GB tenant (SC-002).
- Cascade delete ≤ 30 minutes p95 for ≤ 100 GB tenant (SC-005, plus the cross-store CascadeOrchestrator budget UPD-023 already meets).
- Sub-processors public page TTFB ≤ 2 s p95 (SC-008) — server-rendered + ETag-cached.
- DPA upload virus-scan + Vault store ≤ 30 s p95 for ≤ 50 MB PDF (SC-007).
**Constraints**:
- Audit chain integrity preserved across all cascade phases (rule 9 + AD-18) — every step emits a chain entry, tombstone written **before** the cascade completes.
- 30-day backup purge for deleted tenants (SC-010) — encrypted-key-destruction approach (key shred makes the data unrecoverable while preserving cold-archive proof) honors regulatory retention without violating GDPR.
- Two-person authorization required to schedule tenant deletion phase-1 (rule 33; uses existing 2PA primitives from UPD-039 / feature 086).
- Anti-enumeration on the recovery-link form (rule 35 family — even though target is workspace/tenant not email, return identical responses for valid + invalid + expired tokens).
- DPA virus-scan failure-mode = explicit reject (no silent storage); ClamAV unreachable = explicit 503 with `dpa_scan_unavailable` (per UPD-024 fail-safe pattern).
- Cross-store cascade is delegated, NEVER reimplemented (rule 15) — `data_lifecycle/` calls `cascade_orchestrator.execute_workspace_cascade(workspace_id)` and `cascade_orchestrator.execute_tenant_cascade(tenant_id)`. If those entrypoints don't exist on `main`, R3 (Phase 0) extends `CascadeOrchestrator` with the missing scope-level methods rather than building a parallel cascade engine here.
**Scale/Scope**:
- ~6 admin REST endpoints + ~6 self-service REST endpoints + 1 public read-only endpoint.
- 1 new BC (`data_lifecycle/`, ~18 modules: routers, services, repositories, workers, schemas, events, exceptions).
- 7 new frontend pages spread across `(main)`, `(admin)`, `(public)` route groups.
- 1 Grafana dashboard (rule 24: `data-lifecycle.yaml` ConfigMap).
- 6 e2e tests + 1 journey (J27 Tenant Lifecycle Cancellation, rule 25).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Reviewed against constitution v1.3.0 (50 domain rules + 16 core principles + 7 architecture decisions). All checks **PASS**:

- **Rules 1–8 (brownfield baseline)**: Spec / plan exist; no scope creep beyond UPD-051 (sub-processors RSS, billing notification copy delegated to UPD-052/077); migrations are additive (migration 111, no destructive ALTERs); UPD-023/024/052/053/077 boundaries declared in Summary above.
- **Rule 9 + AD-18 (audit chain)**: Every export request/complete, deletion phase transition, DPA upload, sub-processor list change, and backup purge call emits an `AuditChainEntry` via `AuditChainService` — never written directly to `audit_chain_entries`.
- **Rule 10 + 39–41 (Vault)**: DPA PDFs stored in Vault via `SecretProvider` (existing `RotatableSecretProvider` pattern); no plaintext DPA bytes in PostgreSQL or logs; Vault-down on DPA upload returns 503 with no fallback.
- **Rule 11 (model router)**: This feature does not invoke an LLM — N/A.
- **Rule 12 (cost attribution)**: Export jobs may incur S3 storage cost; the export worker writes a `cost_governance.attribution_service.record_step()` entry with `category="data_lifecycle.export"` (UPD-027 BC).
- **Rule 13 (i18n)**: Every user-facing string in new pages goes through `t()`; no hardcoded JSX strings (CI gate `apps/web/eslint/no-hardcoded-jsx-strings.js`).
- **Rule 14 (tags/labels)**: New entities `data_export_jobs`, `deletion_jobs`, `sub_processors` register with `entity_tags` polymorphic relation per UPD-082 substrate.
- **Rule 15 (cascade delegation)**: `data_lifecycle/` NEVER writes cascade adapters. It calls `CascadeOrchestrator` only. If a scope-level method is missing on `main`, R3 documents the additive extension to `CascadeOrchestrator` (still owned by `privacy_compliance/`).
- **Rule 16 + AD-17 (tombstone)**: Phase-2 cascade emits a deletion tombstone (immutable audit row) before the cascade reports complete.
- **Rule 17 (HMAC webhooks)**: Sub-processor change subscribers receive HMAC-signed outbound webhooks via UPD-077's `outbound_webhooks` infrastructure — this BC is a producer, not a re-implementer.
- **Rule 18 (residency)**: Export ZIPs stored in the workspace/tenant's region per UPD-025 `data_residency_configs`; cross-region copies blocked at S3-bucket-policy + service-layer guard.
- **Rule 19 (maintenance mode)**: Deletion phase-2 dispatch respects maintenance gate (UPD-081). Phase-1 (mark + grace) is a write but not a heavy data operation — gated as a normal write.
- **Rule 20 (structured logs)**: All new modules use `structlog`; no `print()`.
- **Rule 21 (correlation IDs)**: Export and deletion job ids propagate via ContextVars; `tenant_id`/`workspace_id` always set.
- **Rule 22 (Loki labels)**: Job ids and scope ids are JSON-payload fields, not labels. Allowed labels: `service=control-plane`, `bounded_context=data_lifecycle`.
- **Rule 23 (secrets in logs)**: DPA bytes, Vault token, signed-URL signature never logged.
- **Rule 24 (dashboard)**: New dashboard `deploy/helm/observability/templates/dashboards/data-lifecycle.yaml` (export-job duration p50/p95, deletion-grace queue depth, virus-scan reject rate, backup-purge SLO compliance).
- **Rule 25 (BC E2E + journey)**: New suite `tests/e2e/suites/data_lifecycle/` with 6 tests covering each capability block + J27 journey crossing workspaces, registry, audit, S3.
- **Rule 26 (real observability)**: J27 asserts via Loki/Prometheus queries — no mocks.
- **Rule 27 (Helm bundle dashboards)**: Dashboard ships in `deploy/helm/observability/`.
- **Rule 28 (a11y)**: All 7 new frontend pages tested by axe in J15 — zero new WCAG AA violations.
- **Rule 29–30 (admin segregation + role gate)**: Admin endpoints under `/api/v1/admin/data-lifecycle/*` and `/api/v1/admin/dpa/*`; every router method depends on `require_superadmin` (CI static check at `tools/check_admin_role_gates.py`).
- **Rule 32 (idempotent bootstrap)**: Default-tenant seed inserts the standard clickwrap DPA + the 4 default sub-processor rows; running twice does NOT reset versions.
- **Rule 33 (2PA)**: Tenant deletion phase-1 requires fresh 2PA token; server validates on every state-changing call.
- **Rule 34 (impersonation double-audit)**: Operator-during-impersonation requesting export emits dual audit entries (acting + effective).
- **Rule 35 (anti-enumeration)**: Recovery-link endpoint returns identical response for valid/invalid/expired tokens.
- **Rule 36 (FR-with-UX docs)**: All 5 user stories mapped to corresponding doc page under `docs/saas/data-lifecycle.md`.
- **Rule 37 (env var auto-doc)**: New env vars (`DATA_LIFECYCLE_EXPORT_BUCKET`, `DATA_LIFECYCLE_AUDIT_COLD_BUCKET`, `DATA_LIFECYCLE_DPA_VAULT_PATH_TEMPLATE`, `DATA_LIFECYCLE_GRACE_DEFAULT_DAYS`, `DATA_LIFECYCLE_TENANT_GRACE_DEFAULT_DAYS`, `DATA_LIFECYCLE_CLAMAV_HOST`, `DATA_LIFECYCLE_CLAMAV_PORT`, `FEATURE_UPD053_DNS_TEARDOWN`, `FEATURE_UPD077_DPA_SMS_PASSWORD`) annotated inline; `tools/generate-env-docs.py` regenerates `docs/reference/env-vars.md`.
- **Rule 38 (i18n parity)**: New copy added in `en` synchronously; locale-drift CI tracks.
- **Rule 45 (UI for every backend capability)**: All user-facing endpoints have UI surfaces under `(main)/workspaces/{id}/...` (export + delete); admin endpoints have UI surfaces under `(admin)/admin/...`; public sub-processors page under `(public)/legal/...`.
- **Rule 46 (`/api/v1/me/*` scoping)**: This BC has no `me/*` routes; workspace-scoped endpoints under `/api/v1/workspaces/{workspace_id}/...`, tenant-scoped under `/api/v1/admin/tenants/{tenant_id}/...`.
- **Rule 47 (workspace-vs-platform scope)**: Workspace export/deletion is workspace-scoped UI; tenant export/deletion is admin-scoped UI; the two never share a router.
- **Rule 48 (platform state visibility)**: Maintenance-gate denial during phase-2 dispatch surfaces via `<PlatformStatusBanner>` — not as a generic 503.
- **Rule 49 (status-page independence)**: `/legal/sub-processors` ships as the `public-pages` Helm release (separate Deployment + Service + Ingress) so a control-plane outage does not hide it. This is the same operational pattern as the status page.
- **AD-17 / AD-18**: Tombstone + hash-chain integrity verified by an integration test that runs `audit/verify_chain_integrity.py` against a freshly-deleted-then-restored fixture.
- **AD-21 (region)**: Export bucket selection respects `tenants.region`; cross-region attempts return 422 `cross_region_export_blocked`.
- **Core Principle V (append-only journal)**: Deletion job state transitions are append-only — abort emits a new row, never mutates the original.
- **Core Principle VII (simulation isolation)**: Tenant deletion does NOT touch `platform-simulation` namespace pods (out of scope; sandboxes are ephemeral by design).
- **Core Principle XVI (generic S3)**: Both new buckets accessed via existing `S3Client` wrapper in `common/clients/s3.py`. No `boto3.client('s3')` calls outside that module.

**No violations.** No entries needed in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/104-data-lifecycle/
├── plan.md              # this file
├── research.md          # Phase 0 — R1–R10 decisions
├── data-model.md        # Phase 1 — entities + migration 111 + RLS
├── quickstart.md        # Phase 1 — operator + workspace-owner walkthroughs (J27 mapping)
├── contracts/
│   ├── workspace-export-rest.md
│   ├── workspace-deletion-rest.md
│   ├── tenant-export-rest.md
│   ├── tenant-deletion-rest.md
│   ├── dpa-upload-rest.md
│   ├── sub-processors-rest.md
│   └── data-lifecycle-events-kafka.md
├── checklists/
│   └── requirements.md  # already complete
└── tasks.md             # Phase 2 — generated by /speckit-tasks
```

### Source Code (repository root)

```text
apps/control-plane/src/platform/data_lifecycle/         # NEW BC
├── __init__.py
├── models.py                          # SQLAlchemy: DataExportJob, DeletionJob, SubProcessor
├── schemas.py                         # Pydantic v2 request/response + event payloads
├── events.py                          # Kafka event-type registry for data_lifecycle.events
├── exceptions.py                      # PlatformError subclasses
├── repository.py                      # async SQLAlchemy queries (RLS-respecting)
├── services/
│   ├── export_service.py              # request_workspace_export, request_tenant_export
│   ├── deletion_service.py            # request_workspace_deletion, request_tenant_deletion, abort, recover
│   ├── dpa_service.py                 # upload (ClamAV scan + Vault store), get, list, hash-verify
│   ├── sub_processors_service.py      # CRUD + public read + change-feed
│   ├── backup_purge_service.py        # 30-day key-destruction logic + cold-storage retention
│   └── grace_calculator.py            # per-tenant grace overrides (Enterprise contract reads)
├── workers/
│   ├── export_worker.py               # Kafka consumer of data_lifecycle.events:export_requested
│   ├── grace_monitor.py               # APScheduler cron: tick deletion jobs through phases
│   └── sub_processors_regenerator.py  # APScheduler cron: re-render static page on changes
├── cascade_dispatch/
│   ├── workspace_cascade.py           # adapter: calls CascadeOrchestrator.execute_workspace_cascade
│   └── tenant_cascade.py              # adapter: calls CascadeOrchestrator + UPD-053 DNS removal
├── routers/
│   ├── workspace_router.py            # /api/v1/workspaces/{id}/data-export, /delete
│   ├── tenant_admin_router.py         # /api/v1/admin/tenants/{id}/data-export, /delete (require_superadmin + 2PA)
│   ├── dpa_router.py                  # /api/v1/admin/dpa/* (require_superadmin)
│   └── sub_processors_router.py       # /api/v1/admin/sub-processors/* (admin) + /api/v1/public/sub-processors (no auth)
└── README.md

apps/web/app/(main)/workspaces/[id]/                    # Workspace owner UI
├── data-export/page.tsx               # request export + view job status
└── settings/delete/page.tsx           # delete workspace + cancel-link page

apps/web/app/(admin)/admin/                             # Super admin UI
├── tenants/[id]/data-export/page.tsx
├── tenants/[id]/delete/page.tsx       # 2PA-gated delete flow
├── dpa/page.tsx                       # per-tenant DPA list + upload
└── legal/sub-processors/page.tsx      # CRUD + change feed

apps/web/app/(public)/legal/                            # Public route group
└── sub-processors/page.tsx            # SSR + ETag, served by public-pages release

apps/web/components/features/data-lifecycle/            # Shared components
├── ExportJobCard.tsx
├── DeletionGraceBanner.tsx            # uses <PlatformStatusBanner> pattern
├── DPAUploadDialog.tsx
├── SubProcessorRow.tsx
└── ConfirmDeleteDialog.tsx

apps/web/lib/data-lifecycle/                            # Hooks
├── use-export-job.ts                  # TanStack Query
├── use-deletion-job.ts
├── use-dpa-upload.ts
└── use-sub-processors.ts

deploy/helm/public-pages/                               # NEW sub-chart (rule 49)
├── Chart.yaml
├── values.yaml                        # separate ingress + replicas + image
└── templates/
    ├── deployment.yaml                # Next.js public route group only
    ├── service.yaml
    ├── ingress.yaml                   # /legal/sub-processors → this release
    └── configmap-public-pages.yaml

deploy/helm/clamav/                                     # NEW sub-chart for DPA virus-scan
├── Chart.yaml
├── values.yaml
└── templates/
    ├── deployment.yaml
    └── service.yaml

deploy/helm/observability/templates/dashboards/
└── data-lifecycle.yaml                # NEW Grafana dashboard ConfigMap (rule 24, 27)

deploy/runbooks/
└── data-lifecycle/
    ├── tenant-deletion-failed-cascade.md
    ├── export-job-stuck.md
    └── dpa-virus-scan-unavailable.md

tests/
├── unit/data_lifecycle/                       # mirrors apps/control-plane/.../data_lifecycle/
│   ├── test_export_service.py
│   ├── test_deletion_service.py
│   ├── test_dpa_service.py
│   ├── test_sub_processors_service.py
│   ├── test_backup_purge_service.py
│   └── test_grace_calculator.py
├── integration/data_lifecycle/                # live-DB + Kafka
│   ├── test_export_worker_dispatches_zip.py
│   ├── test_grace_monitor_phases.py
│   ├── test_cascade_dispatch_audit_chain.py
│   └── test_dpa_upload_clamav.py
└── e2e/suites/data_lifecycle/                 # rule 25
    ├── test_workspace_export.py
    ├── test_workspace_deletion_two_phase.py
    ├── test_tenant_export.py
    ├── test_tenant_deletion_cascade.py
    ├── test_dpa_upload.py
    └── test_sub_processors_public_page.py

tests/e2e/journeys/
└── j27_tenant_lifecycle_cancellation.py       # rule 25 + 26 (real observability)

apps/control-plane/migrations/
└── versions/111_data_lifecycle.py             # ≤ 32 chars: '111_data_lifecycle'

docs/
├── saas/data-lifecycle.md                     # rule 36 — FR + UX docs
├── runbooks/data-lifecycle-deletion.md
└── reference/env-vars.md                      # rule 37 — auto-regenerated
```

**Structure Decision**: Web service with new bounded context `data_lifecycle/` under `apps/control-plane/src/platform/`, frontend across three Next.js route groups (`(main)`, `(admin)`, `(public)`), and two new Helm sub-charts (`public-pages/` for rule-49 independence, `clamav/` for DPA virus-scan). The BC layout follows the standard pattern (`models.py`, `schemas.py`, `services/`, `repository.py`, `routers/`, `workers/`, `events.py`, `exceptions.py`). Cascade dispatch is a thin adapter package (`cascade_dispatch/`) that calls `CascadeOrchestrator` — this BC owns no cross-store deletion logic.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations. Section intentionally empty.
