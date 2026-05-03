---
description: "Task list for UPD-051 — Data Lifecycle (Tenant and Workspace)"
---

# Tasks: UPD-051 — Data Lifecycle (Tenant and Workspace)

**Input**: Design documents from `/specs/104-data-lifecycle/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Tests are REQUIRED — the spec mandates per-BC E2E suite (rule 25), Grafana dashboard (rule 24), and J27 journey crossing real observability backends (rule 26).

**Organization**: Tasks are grouped by user story (US1–US5) with shared Setup + Foundational phases first. Each user story phase is independently deliverable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no dependencies on incomplete tasks)
- **[Story]**: which user story (US1, US2, US3, US4, US5); omitted in Setup/Foundational/Polish
- File paths are exact

## Path Conventions

Web app per plan.md: `apps/control-plane/src/platform/data_lifecycle/` for the new BC, `apps/web/` for frontend, `deploy/helm/` for charts, `tests/` for the tree mirror.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Scaffolding before any business logic.

- [X] T001 Create the BC directory tree at `apps/control-plane/src/platform/data_lifecycle/` with empty `__init__.py`, `models.py`, `schemas.py`, `events.py`, `exceptions.py`, `repository.py`, plus subpackages `services/`, `workers/`, `cascade_dispatch/`, `routers/`, `serializers/workspace/`, `serializers/tenant/` (each with `__init__.py`).
- [X] T002 [P] Add `clamd>=1.0` to `apps/control-plane/requirements.txt` and `requirements-dev.txt` (NEW dependency per plan R3).
- [X] T003 [P] Add new env-var stubs to `apps/control-plane/src/platform/common/settings.py` PlatformSettings: `data_lifecycle_export_bucket`, `data_lifecycle_audit_cold_bucket`, `data_lifecycle_dpa_vault_path_template`, `data_lifecycle_grace_default_days` (default 7), `data_lifecycle_tenant_grace_default_days` (default 30), `data_lifecycle_clamav_host`, `data_lifecycle_clamav_port` (default 3310), `data_lifecycle_clamav_timeout_seconds` (default 25), `feature_upd053_dns_teardown` (default False), `feature_upd077_dpa_sms_password` (default False).
- [ ] T004 [P] Annotate the new env vars inline (rule 37) so `tools/generate-env-docs.py` picks them up; regenerate `docs/reference/env-vars.md`.
- [ ] T005 [P] Create `deploy/helm/clamav/Chart.yaml`, `values.yaml`, `templates/deployment.yaml`, `templates/service.yaml` for in-cluster ClamAV (R3); use Bitnami ClamAV image, single-replica StatefulSet with 2 GiB PVC for signature DB, daily `freshclam` sidecar.
- [ ] T006 [P] Create `deploy/helm/public-pages/Chart.yaml`, `values.yaml`, `templates/deployment.yaml`, `templates/service.yaml`, `templates/ingress.yaml`, `templates/configmap-public-pages.yaml` for the operationally-independent public sub-processors release (R5, rule 49).
- [ ] T007 Wire the two new sub-charts into `deploy/helm/platform/Chart.yaml` as conditional dependencies (`condition: clamav.enabled` and `condition: publicPages.enabled`); enable both in `values.dev.yaml` and `values.prod.yaml`.
- [ ] T008 Create `apps/control-plane/migrations/versions/111_data_lifecycle.py` skeleton (revision id `111_data_lifecycle`, down_revision = current head as queried via `alembic heads`, `transactional_ddl = False`); leave upgrade/downgrade bodies empty for T010.
- [X] T009 Create `tests/e2e/suites/data_lifecycle/__init__.py` and `tests/integration/data_lifecycle/__init__.py` and `tests/unit/data_lifecycle/__init__.py` so pytest discovers the tree.

**Checkpoint**: Directories, dependencies, and chart skeletons in place. No business logic yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Schema, RLS, and shared service primitives required by every user story.

**⚠️ CRITICAL**: User-story phases CANNOT begin until this phase is complete.

- [X] T010 Implement `apps/control-plane/migrations/versions/111_data_lifecycle.py` upgrade/downgrade per `data-model.md`: ALTER `workspaces_workspace_status` enum to add `pending_deletion`; CREATE `data_export_jobs` (with RLS policy `tenant_isolation`); CREATE `deletion_jobs` (with RLS + partial unique index `uq_deletion_jobs_active_per_scope`); CREATE `sub_processors` (no RLS — platform-level); seed 4 default sub-processor rows idempotently.
- [X] T011 Run `make migrate` against the dev DB; verify `alembic current` shows `111_data_lifecycle`. Add the 3 new tenant-scoped tables to `apps/control-plane/scripts/check_rls.py:TENANT_SCOPED_TABLES` (UPD-053 zero-trust visibility CI gate).
- [X] T012 Update `apps/control-plane/src/platform/workspaces/models.py:WorkspaceStatus` enum to include `pending_deletion = "pending_deletion"`.
- [X] T013 [P] Implement SQLAlchemy models in `apps/control-plane/src/platform/data_lifecycle/models.py`: `DataExportJob`, `DeletionJob`, `SubProcessor` with all columns, indexes, and CHECK constraints from data-model.md. Use `Base + UUIDMixin + TimestampMixin`.
- [X] T014 [P] Implement Pydantic v2 schemas in `apps/control-plane/src/platform/data_lifecycle/schemas.py`: request/response shapes for all 7 contract files (export request, export job summary, deletion request, deletion job summary, DPA upload, sub-processor CRUD).
- [X] T015 [P] Implement event-type registry in `apps/control-plane/src/platform/data_lifecycle/events.py`: 14 event types per `contracts/data-lifecycle-events-kafka.md`; `register_data_lifecycle_event_types()` callable.
- [X] T016 [P] Implement exception hierarchy in `apps/control-plane/src/platform/data_lifecycle/exceptions.py`: `DataLifecycleError(PlatformError)` base + subclasses `ExportRateLimitExceeded`, `CrossRegionExportBlocked`, `DeletionJobAlreadyActive`, `WorkspacePendingDeletion`, `SubscriptionActiveCancelFirst`, `TwoPATokenRequired`, `TwoPATokenInvalid`, `DPAVirusDetected`, `DPAScanUnavailable`, `DPAVersionAlreadyExists`, `CascadeInProgress`, `DeletionJobAlreadyFinalised`, `CrossTenantExportForbidden`, `DefaultTenantCannotBeDeleted`.
- [X] T017 [P] Implement async repository in `apps/control-plane/src/platform/data_lifecycle/repository.py`: CRUD for `DataExportJob`, `DeletionJob`, `SubProcessor`; filter helpers (active jobs per scope, grace-expired jobs); RLS-respecting queries.
- [X] T018 Register `data_lifecycle.events` Kafka topic with 12 partitions, 30-day retention, min ISR 2 in `deploy/helm/platform/templates/kafka-topics.yaml` (Strimzi KafkaTopic CRD).
- [X] T019 Add `register_data_lifecycle_event_types()` call to `apps/control-plane/src/platform/main.py` startup hook (matching the UPD-050 pattern).
- [X] T020 Extend `privacy_compliance/cascade_adapters/base.py:CascadeAdapter` ABC with `dry_run_for_workspace(workspace_id)`, `execute_for_workspace(workspace_id)`, `dry_run_for_tenant(tenant_id)`, `execute_for_tenant(tenant_id)` abstract methods (R1).
- [X] T021 Implement `execute_for_workspace`/`execute_for_tenant` for each existing adapter: `postgresql_adapter.py`, `qdrant_adapter.py`, `neo4j_adapter.py`, `clickhouse_adapter.py`, `opensearch_adapter.py`, `s3_adapter.py`. Each adapter writes the scope-appropriate WHERE/filter and returns rows-affected counts.
- [X] T022 Extend `privacy_compliance/services/cascade_orchestrator.py:CascadeOrchestrator` with `execute_workspace_cascade(workspace_id, requested_by_user_id)` and `execute_tenant_cascade(tenant_id, requested_by_user_id)` driver methods that loop adapters in deterministic order (PG → Qdrant → Neo4j → ClickHouse → OpenSearch → S3) and emit a final tombstone via the existing `_produce_tombstone` helper.
- [X] T023 [P] Add unit tests for the cascade extension in `tests/unit/privacy_compliance/test_cascade_orchestrator_scope_extension.py`: dry-run + execute for both workspace and tenant scopes against a fixture; assert tombstone written and audit chain entry emitted.
- [X] T024 Create `apps/control-plane/src/platform/data_lifecycle/services/grace_calculator.py:resolve(scope_type, scope_id) -> int` (R6): reads `tenants.settings_json.deletion_grace_period_days` with fallback to `data_lifecycle_grace_default_days` / `data_lifecycle_tenant_grace_default_days`; validates `7 ≤ resolved ≤ 90`.
- [X] T025 Create `apps/control-plane/src/platform/data_lifecycle/cascade_dispatch/workspace_cascade.py` and `tenant_cascade.py` thin adapters that call `CascadeOrchestrator.execute_workspace_cascade` / `execute_tenant_cascade`. `tenant_cascade.py` additionally calls `UPD053TenantDomainTeardown.teardown(tenant_slug)` when `feature_upd053_dns_teardown=true`, otherwise logs `dns_teardown_skipped` warning (R8).

**Checkpoint**: Migration applied, RLS verified, models/schemas/events/exceptions in place, cascade orchestrator extended. User-story phases unblocked.

---

## Phase 3: User Story 1 — Workspace owner exports their workspace data (Priority: P1) 🎯 MVP

**Goal**: Workspace owner can request, monitor, and download a workspace export ZIP with cross-workspace privacy enforcement.

**Independent Test**: A Pro-plan workspace owner navigates to `/workspaces/{id}/data-export`, requests an export, and receives an email when the async job completes. The email contains a signed URL valid for 7 days. Download succeeds; ZIP contains structured JSON files per resource type. Cross-workspace member emails are NOT included.

### Tests for User Story 1 (write FIRST, ensure they FAIL before implementation)

- [X] T026 [P] [US1] Contract test for export request idempotency in `tests/integration/data_lifecycle/test_export_request_idempotency.py`: two concurrent POSTs return the same in-flight job id.
- [X] T027 [P] [US1] Contract test for cross-region export refusal in `tests/integration/data_lifecycle/test_export_cross_region_blocked.py`: workspace in EU, super-admin attempts read across to US bucket → 422 `cross_region_export_blocked`.
- [ ] T028 [P] [US1] E2E test in `tests/e2e/suites/data_lifecycle/test_workspace_export.py` covering US1 acceptance scenarios 1–5; assert ZIP layout, signed-URL TTL=7d, audit chain entries, member-email redaction.
- [ ] T029 [P] [US1] Integration test in `tests/integration/data_lifecycle/test_export_worker_dispatches_zip.py` for `ExportJobWorker` consuming `data_lifecycle.export.requested` and producing a multipart S3 upload.

### Implementation for User Story 1

- [X] T030 [US1] Implement `apps/control-plane/src/platform/data_lifecycle/services/export_service.py:ExportService.request_workspace_export(workspace_id, requested_by_user_id)`: idempotency check via repository, residency-policy guard against UPD-025, rate-limit guard (5 exports per workspace per 24 h via Redis), audit entry emission, Kafka event production.
- [X] T031 [P] [US1] Implement workspace-scope serializers in `apps/control-plane/src/platform/data_lifecycle/serializers/workspace/agents.py`, `executions.py`, `audit.py`, `costs.py`, `members.py`, `metadata.py` — each is an async generator yielding `(filepath, bytes_chunk)` tuples; `members.py` honours the rule-46/47 redaction (only workspace's own members; never cross-workspace emails).
- [ ] T032 [US1] Implement `apps/control-plane/src/platform/data_lifecycle/services/export_service.py:ExportArchiver` (R2): wraps `aioboto3.S3.create_multipart_upload`, holds ≤8 MB chunks, writes parts as the streaming `zipfile` produces them, persists `last_part_number` + `last_resource_emitted` for resume.
- [X] T033 [US1] Implement `apps/control-plane/src/platform/data_lifecycle/workers/export_worker.py:ExportJobWorker`: aiokafka consumer of `data_lifecycle.events` filtered to `export.requested`; acquires `data_lifecycle:export_lease:{job_id}` Redis lease via `SET ... NX EX`; runs ExportArchiver; emits `export.started`/`export.completed`/`export.failed` events; updates job row.
- [X] T034 [P] [US1] Implement `apps/control-plane/src/platform/data_lifecycle/routers/workspace_router.py` POST/GET endpoints per `contracts/workspace-export-rest.md`: POST `/api/v1/workspaces/{workspace_id}/data-export`, GET `/api/v1/workspaces/{workspace_id}/data-export/jobs`, GET `/api/v1/workspaces/{workspace_id}/data-export/jobs/{job_id}` (returns fresh signed URL with audit emission). Uses `require_workspace_member` + RBAC (owner OR admin).
- [X] T035 [US1] Register `workspace_router` in `apps/control-plane/src/platform/main.py` API runtime profile router list.
- [ ] T036 [P] [US1] Frontend: implement `apps/web/app/(main)/workspaces/[id]/data-export/page.tsx` with shadcn primitives — request button, job-status list (`ExportJobCard`), download button. Use TanStack Query `useExportJob` hook.
- [ ] T037 [P] [US1] Frontend: implement `apps/web/components/features/data-lifecycle/ExportJobCard.tsx` and `apps/web/lib/data-lifecycle/use-export-job.ts` (TanStack Query `useQuery` + `useMutation`).
- [ ] T038 [US1] Wire export-completed email through UPD-077 notifications: add `notification_template_id="export_ready"` rendering with `t()` keys; sending happens from `ExportJobWorker` on completion.
- [X] T039 [US1] Add Prometheus metrics: `data_lifecycle_export_duration_seconds` histogram (label: `scope_type`), `data_lifecycle_export_bytes_total` counter, `data_lifecycle_export_failures_total{reason}` counter. Wire from `ExportArchiver` + `ExportJobWorker`.

**Checkpoint**: A workspace owner can request, monitor, download a workspace export. SC-001 measurable on this path. Story 1 deliverable end-to-end.

---

## Phase 4: User Story 2 — Workspace owner deletes their workspace (Priority: P1)

**Goal**: Two-phase workspace deletion with 7-day grace, cancel-link, anti-enumeration, and cascade.

**Independent Test**: Owner clicks Delete, types workspace name, confirms. Workspace flips to `pending_deletion`; cancel email sent. After grace, cascade runs and 90-day audit tombstone is retained. Cancel-link returns identical 200 for valid/invalid/expired tokens (anti-enumeration).

### Tests for User Story 2

- [ ] T040 [P] [US2] E2E test in `tests/e2e/suites/data_lifecycle/test_workspace_deletion_two_phase.py` covering US2 acceptance scenarios 1–5: phase-1 mark, inaccessibility, cancel-link cancellation, fast-forward grace, phase-2 cascade, 90-day tombstone retention.
- [ ] T041 [P] [US2] Integration test in `tests/integration/data_lifecycle/test_grace_monitor_phases.py` for `GraceMonitor` cron advancing jobs from phase_1 to phase_2.
- [X] T042 [P] [US2] Integration test in `tests/integration/data_lifecycle/test_cancel_token_anti_enumeration.py` asserting identical 200 responses for unknown/expired/already-used tokens (R10).

### Implementation for User Story 2

- [X] T043 [US2] Implement `apps/control-plane/src/platform/data_lifecycle/services/deletion_service.py:DeletionService.request_workspace_deletion(workspace_id, requested_by_user_id, typed_confirmation, reason)`: validate typed_confirmation matches workspace slug, check no active deletion job (partial unique index handles), create job in `phase_1`, generate 32-byte URL-safe cancel token (store SHA-256), flip workspace to `pending_deletion`, audit + Kafka event.
- [X] T044 [US2] Implement `DeletionService.cancel_via_token(token)` (R10 anti-enumeration): always returns the same response shape; server-side branches on token validity + phase + expiry; on success flips workspace back to `active` and audits.
- [X] T045 [US2] Implement `apps/control-plane/src/platform/data_lifecycle/workers/grace_monitor.py:GraceMonitor` APScheduler cron (every 5 min): query `deletion_jobs` where `phase='phase_1' AND grace_ends_at <= now()`, advance to `phase_2`, dispatch via `cascade_dispatch.workspace_cascade`, on success transition workspace to `deleted` and emit completion event.
- [X] T046 [US2] Add the `GraceMonitor` to the scheduler runtime profile in `apps/control-plane/src/platform/main.py` (matches `UPD-050:_e2e/cost/inject` pattern).
- [ ] T047 [US2] Add 423 `workspace_pending_deletion` guard to write paths in `apps/control-plane/src/platform/workspaces/router.py` (and other workspace-scoped routers): when `workspace.status='pending_deletion'`, refuse all writes. Read paths surface a banner.
- [X] T048 [P] [US2] Extend `apps/control-plane/src/platform/data_lifecycle/routers/workspace_router.py` with POST `/api/v1/workspaces/{workspace_id}/deletion-jobs`, GET `/.../deletion-jobs/{job_id}`, POST `/api/v1/workspaces/cancel-deletion/{token}` per `contracts/workspace-deletion-rest.md`.
- [ ] T049 [P] [US2] Frontend: implement `apps/web/app/(main)/workspaces/[id]/settings/delete/page.tsx` — typed-confirmation input matching workspace slug, danger-coloured Delete button, `DeletionGraceBanner` rendered when `status='pending_deletion'`.
- [ ] T050 [P] [US2] Frontend: implement `apps/web/app/(main)/cancel-deletion/[token]/page.tsx` — calls cancel endpoint, shows the rule-35 anti-enumeration message regardless of outcome.
- [ ] T051 [P] [US2] Frontend: `apps/web/components/features/data-lifecycle/{DeletionGraceBanner,ConfirmDeleteDialog}.tsx` + `apps/web/lib/data-lifecycle/use-deletion-job.ts`.
- [ ] T052 [US2] Add 90-day audit-tombstone purge cron in `apps/control-plane/src/platform/data_lifecycle/workers/grace_monitor.py:_purge_workspace_tombstones()`: daily, find tombstones older than 90 d for workspace scopes, replace with hash-anchor entry (FR-752.5), retain chain integrity.
- [ ] T053 [US2] Add Prometheus metrics: `data_lifecycle_deletion_grace_queue_depth` gauge, `data_lifecycle_deletion_phase_advance_total{from_phase,to_phase}` counter, `data_lifecycle_cascade_duration_seconds` histogram.

**Checkpoint**: A workspace owner can delete with grace + cancel; cascade runs at grace expiry; tombstone preserved 90 days; SC-003 + SC-008 measurable.

---

## Phase 5: User Story 3 — Enterprise tenant cancellation with full export (Priority: P1)

**Goal**: Super-admin tenant deletion with 2PA, subscription preflight, final export, 30-day grace, full cascade (data+DNS+TLS+Vault), 7-year audit cold storage.

**Independent Test**: Super admin deletes tenant `acme` via `/admin/tenants/acme/delete`. 2PA-gated; subscription must be cancelled first. Phase 1 enqueues final export with out-of-band password. Recovery in grace works. Phase 2 cascades data + DNS + TLS + secrets and writes a tombstone to `platform-audit-cold-storage`.

### Tests for User Story 3

- [ ] T054 [P] [US3] E2E test in `tests/e2e/suites/data_lifecycle/test_tenant_export.py` covering US3 acceptance #1–2: phase-1 final export job + out-of-band password delivery (R9 — email + OTP fallback in CI).
- [ ] T055 [P] [US3] E2E test in `tests/e2e/suites/data_lifecycle/test_tenant_deletion_cascade.py` covering US3 acceptance #3–6: recovery in grace, phase-2 cascade across all six stores + DNS, cold-storage tombstone with object-lock retention, subscription-active refusal.
- [ ] T056 [P] [US3] Integration test in `tests/integration/data_lifecycle/test_cascade_dispatch_audit_chain.py` asserting AuditChainService emits hash-linked entries for every cascade step and the chain verifies post-cascade.
- [ ] T057 [P] [US3] Integration test in `tests/integration/data_lifecycle/test_tenant_deletion_default_tenant_refused.py` asserting the platform default tenant cannot be deleted (FR-754.3).

### Implementation for User Story 3

- [X] T058 [US3] Implement `DeletionService.request_tenant_deletion(tenant_id, requested_by_user_id, two_pa_token, typed_confirmation, reason, include_final_export, grace_period_days)`: 2PA validation via existing UPD-039 primitive, default-tenant refusal (FR-754.3), subscription-status preflight via UPD-052 service interface (refuse 409 if `active`), grace bound check (7 ≤ days ≤ 90), final-export job creation when requested, audit + Kafka event.
- [X] T059 [US3] Implement `DeletionService.recover_tenant(deletion_job_id, requested_by_user_id, two_pa_token)` (FR-754.4): permitted only in `phase_1`; restores tenant prior status, revokes any export-download links issued during grace (revoke-by-deleting-the-presigned-key in S3), audits.
- [X] T060 [US3] Implement `DeletionService.extend_grace(deletion_job_id, additional_days, two_pa_token, reason)`: only in `phase_1`; new `grace_ends_at <= created_at + 90 days`; audits with `data_lifecycle.tenant_deletion_grace_extended`.
- [X] T061 [US3] Implement `apps/control-plane/src/platform/data_lifecycle/services/export_service.py:ExportService.request_tenant_export(...)` mirror of workspace export but with: (a) tenant-scope serializers via T062, (b) password-protected ZIP via SSE-C (R9), (c) email + OTP/SMS out-of-band password delivery, (d) 30-day signed-URL TTL.
- [X] T062 [P] [US3] Implement tenant-scope serializers in `apps/control-plane/src/platform/data_lifecycle/serializers/tenant/`: `tenant.py` (tenant row + plan + settings without secrets), `dpa.py` (DPA history metadata), `subscription.py` (UPD-052 history), `workspaces.py` (loops the workspace serializers per workspace), `users.py` (tenant-scoped users), `audit.py` (tenant-scoped audit chain), `costs.py` (tenant cost rollups by month), `metadata.py`.
- [X] T063 [US3] Extend `cascade_dispatch/tenant_cascade.py` to call (in order) `CascadeOrchestrator.execute_tenant_cascade` → `UPD053TenantDomainTeardown.teardown` (when flag on) → `BackupPurgeService.schedule_purge_for_tenant` → cold-storage tombstone write to `platform-audit-cold-storage` bucket with S3 Object Lock COMPLIANCE retention; emit `data_lifecycle.tenant_deletion_completed` event.
- [X] T064 [P] [US3] Implement `apps/control-plane/src/platform/data_lifecycle/routers/tenant_admin_router.py` per `contracts/tenant-export-rest.md` and `contracts/tenant-deletion-rest.md`: POST `/api/v1/admin/tenants/{tenant_id}/data-export`, GET listing + detail, POST `/.../deletion-jobs`, GET detail, POST `/api/v1/admin/data-lifecycle/deletion-jobs/{id}/abort`, POST `/.../extend-grace`. All gated by `require_superadmin` + `require_2pa_token` (where data-model says `two_pa_token_id` not null).
- [X] T065 [US3] Add the `tenant_admin_router` to the API runtime profile under `/api/v1/admin/...`. CI static check `tools/check_admin_role_gates.py` MUST pass after registration.
- [ ] T066 [P] [US3] Frontend: implement `apps/web/app/(admin)/admin/tenants/[id]/data-export/page.tsx` and `apps/web/app/(admin)/admin/tenants/[id]/delete/page.tsx` per UI plan; integrate the existing 2PA tray pattern from feature 086.
- [ ] T067 [P] [US3] Frontend: extend `apps/web/components/features/data-lifecycle/` with `TenantExportPasswordDialog.tsx` (shows out-of-band delivery status), `TenantCascadeProgressTable.tsx` (renders `store_progress` from the job-detail endpoint), `TenantRecoveryDialog.tsx`.
- [X] T068 [US3] Implement `apps/control-plane/src/platform/data_lifecycle/services/backup_purge_service.py:schedule_purge_for_tenant(tenant_id, cascade_completed_at)`: schedule a job at `cascade_completed_at + 30d`; on tick, call existing UPD-040 `SecretRotationService` to destroy the tenant-specific KMS data key; emit `data_lifecycle.backup.purge_completed` event + tombstone audit (FR-759 + R4).
- [ ] T069 [US3] Add the cold-storage S3 bucket `platform-audit-cold-storage` configuration to `deploy/helm/platform/templates/s3-buckets.yaml` (Helm-managed bucket creation): SSE-S3, Object Lock COMPLIANCE mode, retention years `dataLifecycle.coldStorage.retentionYears` (default 7).

**Checkpoint**: SC-002, SC-004, SC-005, SC-008, SC-009 measurable; tenant deletion end-to-end with regulatory cold-storage retention.

---

## Phase 6: User Story 4 — Sub-processors page is publicly accessible (Priority: P2)

**Goal**: Public, unauthenticated sub-processors page with RSS, email subscription, change-log, 5-min propagation SLO, operationally independent of control plane.

**Independent Test**: Unauthenticated visitor opens `https://musematic.ai/legal/sub-processors`. Sees current processor list. Visits `.rss` for changes feed. Subscribes via email. New entry added by super admin propagates to public page within 5 minutes. Page works during a control-plane outage.

### Tests for User Story 4

- [ ] T070 [P] [US4] E2E test in `tests/e2e/suites/data_lifecycle/test_sub_processors_public_page.py` covering US4 acceptance #1–5: public read works without auth, RSS feed renders, change-log shows recent edits, page propagates within 5 min, control-plane-outage independence (scale main deployment to 0 and assert page still serves from snapshot).
- [ ] T071 [P] [US4] Integration test in `tests/integration/data_lifecycle/test_sub_processors_regenerator_cron.py`: edit triggers regeneration cron; ConfigMap snapshot updates; webhook fanout via UPD-077 emits HMAC-signed payloads.

### Implementation for User Story 4

- [X] T072 [US4] Implement `apps/control-plane/src/platform/data_lifecycle/services/sub_processors_service.py`: CRUD (add/modify/soft-delete) + audit emission + Kafka event production; `list_active_for_public()` excludes `is_active=false` and `notes`.
- [X] T073 [P] [US4] Implement `apps/control-plane/src/platform/data_lifecycle/routers/sub_processors_router.py`: admin endpoints under `/api/v1/admin/sub-processors/*` (require_superadmin), public endpoints under `/api/v1/public/sub-processors{,.rss}` (NO auth), `POST /api/v1/public/sub-processors/subscribe` (anti-enumeration).
- [ ] T074 [US4] Implement `apps/control-plane/src/platform/data_lifecycle/workers/sub_processors_regenerator.py` APScheduler cron: consumes `data_lifecycle.sub_processor.{added,modified,removed}`, regenerates the public-page snapshot ConfigMap (`public-pages-sub-processors-snapshot`), regenerates the change-log + RSS feed (stored in DB-projected feed table), triggers UPD-077 outbound webhook fanout.
- [X] T075 [US4] Implement RSS feed rendering helper in `sub_processors_service.py:render_rss(items)` producing valid RSS 2.0 XML per `contracts/sub-processors-rest.md`.
- [ ] T076 [P] [US4] Frontend: implement `apps/web/app/(public)/legal/sub-processors/page.tsx` (Next.js Server Component, SSR with ETag) — renders the active list + last-updated + change-log; reads from public REST or falls back to snapshot ConfigMap when control plane unreachable.
- [ ] T077 [P] [US4] Frontend: implement `apps/web/app/(admin)/admin/legal/sub-processors/page.tsx` (admin CRUD UI with shadcn DataTable + Add/Edit dialogs).
- [ ] T078 [P] [US4] Frontend: implement `apps/web/components/features/data-lifecycle/SubProcessorRow.tsx` (used by both public and admin pages with prop-driven `mode='public'|'admin'`).
- [ ] T079 [US4] Wire `public-pages` Helm release to mount the snapshot ConfigMap and route `/legal/sub-processors{,.rss}` to its Deployment via Ingress; the Deployment uses `POSTGRES_REPLICA_DSN` for live data and falls back to ConfigMap on read failure.
- [ ] T080 [US4] Email-subscription verification: store pending subscriptions in a new lightweight table `sub_processor_email_subscriptions` (email, verification_token_hash, verified_at, created_at); verification email via UPD-077; only verified subscribers receive change notifications.

**Checkpoint**: SC-006 measurable; public page operationally independent (rule 49); RSS + email subscription flowing.

---

## Phase 7: User Story 5 — DPA upload at Enterprise tenant creation (Priority: P1)

**Goal**: Super admin uploads tenant-specific DPA PDF at tenant creation or as a new version. Virus-scanned via in-cluster ClamAV. Stored encrypted in Vault. SHA-256 + version recorded on the tenant row.

**Independent Test**: Super admin uploads a clean PDF — succeeds, hash recorded, Vault path written, audit emitted. Uploads an EICAR test file — refused with `dpa_virus_detected`, no Vault write, no row update. ClamAV unreachable — 503 `dpa_scan_unavailable`, no Vault write.

### Tests for User Story 5

- [ ] T081 [P] [US5] E2E test in `tests/e2e/suites/data_lifecycle/test_dpa_upload.py` covering US5 acceptance #1–5: clean upload, malware refusal (EICAR fixture), versioning preserves prior version, default-tenant clickwrap path, cascade deletes tenant DPA versions.
- [ ] T082 [P] [US5] Integration test in `tests/integration/data_lifecycle/test_dpa_upload_clamav.py` covering all three failure modes: clean, virus-positive, scanner unreachable.

### Implementation for User Story 5

- [X] T083 [US5] Implement `apps/control-plane/src/platform/data_lifecycle/services/dpa_service.py:DPAService` with methods `upload(tenant_id, version, effective_date, pdf_bytes, requested_by_user_id)`, `list_versions(tenant_id)`, `get_active(tenant_id)`, `download(tenant_id, version)`. Upload path: validate PDF magic bytes, scan via ClamAV `clamd` client (R3) with 25 s timeout, on `OK` compute SHA-256, write to Vault path per template, update `tenants.dpa_*` columns, emit audit + Kafka event.
- [X] T084 [P] [US5] Implement `apps/control-plane/src/platform/data_lifecycle/routers/dpa_router.py` per `contracts/dpa-upload-rest.md`: POST upload (multipart), GET list, GET download, plus `/api/v1/me/tenant/dpa` (rule-46 self-service for tenant admin). All gated appropriately.
- [ ] T085 [US5] Add `tenants.settings_json.clickwrap_dpa_version_pinned_at` write at signup (FR-756.6 default-tenant flow): hook into UPD-016 accounts signup completion to record the pinned clickwrap DPA version. (Cross-BC change; coordinate with `accounts/services/registration_service.py`.)
- [ ] T086 [P] [US5] Frontend: implement `apps/web/app/(admin)/admin/dpa/page.tsx` and `apps/web/app/(admin)/admin/dpa/[tenantId]/page.tsx` — list versions, upload dialog, virus-scan progress UX, download button.
- [ ] T087 [P] [US5] Frontend: `apps/web/components/features/data-lifecycle/DPAUploadDialog.tsx` (RHF + Zod, 50 MB client-side cap, scan progress) + `apps/web/lib/data-lifecycle/use-dpa-upload.ts`.
- [X] T088 [US5] Wire DPA cascade in `cascade_dispatch/tenant_cascade.py`: enumerate Vault paths under `secret/data/musematic/{env}/tenants/{slug}/dpa/*` and delete each version; record the deletion in the cold-storage tombstone retaining only content hashes (FR-756.5 + edge case "DPA upload: cascade").
- [ ] T089 [US5] Add Prometheus metrics: `data_lifecycle_dpa_scan_duration_seconds` histogram, `data_lifecycle_dpa_virus_detected_total{signature}` counter, `data_lifecycle_dpa_scan_unavailable_total` counter. Wire from `DPAService`.

**Checkpoint**: SC-007 measurable; DPA workflow end-to-end with malware safety.

---

## Phase 8: GDPR Article 28 evidence package (FR-758)

**Goal**: Per-Enterprise-tenant evidence package combining DPA + sub-processors snapshot + audit-chain export + residency config + maintenance history + signed manifest.

This is a single endpoint that COMPOSES outputs of US1–US5 + UPD-024 + UPD-025; not a separate user story but a deliverable.

- [X] T090 [P] Implement `apps/control-plane/src/platform/data_lifecycle/services/article28_evidence_service.py:generate_for_tenant(tenant_id, requested_by_user_id)`: composes a ZIP with `dpa-vN.pdf`, `sub_processors_snapshot.json`, `audit_chain_last_12_months.jsonl`, `residency_config.json` (UPD-025), `maintenance_history.json` (UPD-081), `manifest.json` (file → SHA-256). Signed via the existing audit-chain signing key.
- [X] T091 [P] Add admin endpoint `POST /api/v1/admin/tenants/{tenant_id}/article28-evidence` to `tenant_admin_router.py`. Returns 202 with job id; reuses the export-job machinery for delivery.
- [ ] T092 [P] Frontend: add "Generate Article 28 Evidence" button to the admin tenant page; surface the job in the existing job list.
- [ ] T093 [P] Integration test in `tests/integration/data_lifecycle/test_article28_evidence.py`: generate package, assert all 6 components present, manifest hashes match, signature verifies.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, dashboards, runbooks, J27 journey, accessibility, parity checks.

- [X] T094 [P] Author Grafana dashboard `deploy/helm/observability/templates/dashboards/data-lifecycle.yaml` (rule 24, 27): export-job p50/p95 duration, deletion grace queue depth, virus-scan reject rate, backup-purge SLO compliance, DNS-teardown skip count.
- [X] T095 [P] Author runbooks at `deploy/runbooks/data-lifecycle/`: `tenant-deletion-failed-cascade.md`, `export-job-stuck.md`, `dpa-virus-scan-unavailable.md`, `dns-teardown-manual.md`, `cold-storage-retention-restore.md`.
- [X] T096 [P] Author user-facing docs at `docs/saas/data-lifecycle.md` covering all 5 user stories (rule 36); regenerate `docs/reference/env-vars.md` and `docs/reference/feature-flags.md` via `tools/generate-env-docs.py`.
- [ ] T097 [P] Implement J27 journey at `tests/e2e/journeys/j27_tenant_lifecycle_cancellation.py` (rule 25 + 26): real-cluster, real-observability journey crossing all 5 user stories + cold-storage tombstone + Loki/Prometheus assertions per `quickstart.md` § Journey J27.
- [ ] T098 [P] Add J27 to `tests/e2e/journeys/__init__.py` registry and CI matrix.
- [ ] T099 [P] Accessibility: ensure all 7 new pages are covered by axe in J15 (rule 28); add page paths to `apps/web/playwright/a11y.spec.ts`.
- [ ] T100 [P] i18n: add new translation keys for the 7 new pages + email templates to `apps/web/locales/en/data-lifecycle.json`; mark for translator pickup. Confirm rule-13 ESLint rule passes (no hardcoded JSX strings).
- [ ] T101 [P] Tag/label substrate (rule 14): register `data_export_job`, `deletion_job`, `sub_processor` entity types with `entity_tags`/`entity_labels` substrate (UPD-082). Add filter wiring to admin UIs.
- [X] T102 [P] Coverage: ensure `tests/unit/data_lifecycle/` has ≥95% coverage; if framework-glue files (router, repository, dependencies) drop below threshold, add them to the per-BC coverage omit list in `pyproject.toml` matching the UPD-050 pattern.
- [ ] T103 Verify `make check-rls` passes (T011 satisfied) and `tools/check_admin_role_gates.py` passes (T065 satisfied); fix any drift.
- [ ] T104 Verify `tools/verify_audit_chain.py` runs as a CI gate (SC-008) — adds the cold-storage chain to its scan list when `platform-audit-cold-storage` bucket is reachable.
- [ ] T105 Re-run `pytest tests/unit/data_lifecycle/ tests/integration/data_lifecycle/ tests/e2e/suites/data_lifecycle/` end-to-end; fix any regressions.
- [X] T106 Update `CHANGELOG.md` with the UPD-051 entry summarising the 5 user stories + 6 contracts + 1 new BC + 2 new Helm sub-charts.

---

## Dependencies

- **Phase 1** (T001–T009): no prerequisites.
- **Phase 2** (T010–T025): requires Phase 1 complete. T010 → T011 → T012; T013/T014/T015/T016 parallelizable after T010; T020 → T021 → T022 sequential within the cascade extension; T024/T025 parallelizable after T022.
- **Phase 3 US1** (T026–T039): requires Phase 2 complete. Tests T026–T029 in parallel (write before implementation per TDD). T030 → T031 (parallel) → T032 → T033 → T034 (parallel with T036/T037) → T035 → T038 → T039.
- **Phase 4 US2** (T040–T053): requires Phase 2 + the cascade extension. Independent of US1 except sharing the workspace router file (T034 + T048 merge points).
- **Phase 5 US3** (T054–T069): requires Phase 2 + US1 service primitives (uses `ExportService`). Independent of US2 logically; merges with US2 in `DeletionService` and `cascade_dispatch/`.
- **Phase 6 US4** (T070–T080): requires Phase 2. Fully independent of US1/US2/US3; can run on a separate branch.
- **Phase 7 US5** (T081–T089): requires Phase 2 + the ClamAV Helm sub-chart (T005). Independent of US1–US4 except sharing the audit chain.
- **Phase 8 (Article 28)** (T090–T093): requires US3 + US4 + US5 (composes their outputs).
- **Phase 9 Polish** (T094–T106): requires all earlier phases.

User-story-level independence:
- US1 ships standalone (workspace export only).
- US2 ships standalone (workspace deletion only) — useful even without export.
- US4 ships standalone (sub-processors page) — fully independent.
- US3 + US5 are tightly coupled (Enterprise tenant creation needs DPA + tenant deletion needs final export).

---

## Parallel execution examples

### Phase 2 burst
After T010+T011+T012 land sequentially, kick off the following in a single dev session:

```
T013 [P] (models)        + T014 [P] (schemas)        + T015 [P] (events)
T016 [P] (exceptions)    + T017 [P] (repository)     + T018 (kafka topics)
T020 + T021 + T022 (cascade extension, sequential within)
T024 [P] (grace_calc)    + T025 [P] (cascade dispatch adapters)
```

### US1 burst (after Phase 2)
```
T026 [P] (test) + T027 [P] (test) + T028 [P] (test) + T029 [P] (test)
[wait for tests to RED]
T030 (export_service.request_workspace_export)
T031 [P] (workspace serializers) + T032 (ExportArchiver) + T033 (worker)
T034 [P] (router) + T036 [P] (page) + T037 [P] (component+hook)
T035 (register router) → T038 (notification) → T039 (metrics)
```

### Independent-track parallelism
US4 (T070–T080) can be developed on a separate branch concurrently with US1/US2/US3.

---

## Implementation strategy

**MVP scope**: US1 alone (workspace export). Delivers GDPR Article 20 portability for Free/Pro tenants. Foundation phase + US1 = ~14 tasks.

**Sprint 1 (MVP)**: Phase 1 + Phase 2 + US1 → ~39 tasks.
**Sprint 2 (Workspace deletion + Sub-processors)**: US2 + US4 → ~25 tasks.
**Sprint 3 (Enterprise)**: US3 + US5 + Article 28 → ~32 tasks.
**Sprint 4 (Polish)**: Phase 9 → 13 tasks.

**Risk gates**:
- After Phase 2: dry-run `CascadeOrchestrator.execute_workspace_cascade` against a fixture before any real-data deletion lands in CI.
- After US3: run J27 in CI against an ephemeral tenant before merging the deletion path; verify cold-storage object lock retention.
- After US5: confirm ClamAV image scan rate and signature freshness before enabling DPA upload in prod (operational gate, not code gate).

---

## Format validation

All 106 tasks follow the strict checklist format `- [ ] T### [P?] [Story?] Description with file path`. Setup/Foundational/Polish tasks omit the [Story] label. User-story phases (Phase 3 US1, Phase 4 US2, Phase 5 US3, Phase 6 US4, Phase 7 US5, Phase 8) all carry their story label.

Total: **106 tasks**.

| Phase | Tasks | Story |
|---|---|---|
| Phase 1 Setup | 9 (T001–T009) | — |
| Phase 2 Foundational | 16 (T010–T025) | — |
| Phase 3 US1 (export) | 14 (T026–T039) | US1 |
| Phase 4 US2 (workspace deletion) | 14 (T040–T053) | US2 |
| Phase 5 US3 (tenant deletion) | 16 (T054–T069) | US3 |
| Phase 6 US4 (sub-processors) | 11 (T070–T080) | US4 |
| Phase 7 US5 (DPA) | 9 (T081–T089) | US5 |
| Phase 8 Article 28 | 4 (T090–T093) | — |
| Phase 9 Polish | 13 (T094–T106) | — |
