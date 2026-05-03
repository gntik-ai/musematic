# Research — UPD-051 Data Lifecycle

**Phase 0 output.** Resolves all NEEDS CLARIFICATION items and documents the major design decisions before Phase 1 (data-model + contracts).

The user input had no NEEDS CLARIFICATION markers; this research is therefore organised around the 10 highest-risk design questions surfaced by the brownfield audit.

---

## R1 — Cross-store cascade: extend `CascadeOrchestrator` or build parallel?

**Decision**: Extend `privacy_compliance/services/cascade_orchestrator.CascadeOrchestrator` and `privacy_compliance/cascade_adapters/base.CascadeAdapter` with scope-level methods. Do NOT create a parallel cascade engine in `data_lifecycle/`.

**Rationale**: Rule 15 mandates a single cascade implementation for right-to-be-forgotten. The existing class operates on `subject_user_id`; the audit shows neither `execute_workspace_cascade(workspace_id)` nor `execute_tenant_cascade(tenant_id)` exists. Building a second engine in `data_lifecycle/` would fork the cascade logic and is a constitution violation. Extending in place keeps a single source of truth and lets the audit-pass invariant (rule 9 + AD-18) hold across user-DSR, workspace-deletion, and tenant-deletion code paths.

**Alternatives considered**:
- *Parallel engine in `data_lifecycle/`*: Rejected. Violates rule 15. Introduces a long-tail risk that user-DSR cascade and workspace-deletion cascade drift apart over time.
- *Inline SQL cascade in `data_lifecycle/`*: Rejected. Misses Qdrant/Neo4j/ClickHouse/OpenSearch/S3 cleanup, which is exactly what the existing `CascadeAdapter` polymorphism handles.

**How to apply**: In Phase 2 implementation, add three methods to `CascadeAdapter`:
1. `async def dry_run_for_workspace(self, workspace_id: UUID) -> CascadePlan`
2. `async def execute_for_workspace(self, workspace_id: UUID) -> CascadeResult`
3. `async def execute_for_tenant(self, tenant_id: UUID) -> CascadeResult`

Each adapter implementation (`postgresql_adapter`, `qdrant_adapter`, etc.) writes the scope-appropriate WHERE clause (e.g., `WHERE workspace_id = ?` for tables that have it; `WHERE tenant_id = ?` for tenant-scoped tables; collection-prefix scan for Qdrant; node-property filter for Neo4j). The orchestrator gains `execute_workspace_cascade(...)` / `execute_tenant_cascade(...)` driver methods that loop adapters in deterministic order. Unit tests live in `tests/unit/privacy_compliance/`, not `tests/unit/data_lifecycle/` — the cascade is privacy-compliance's responsibility.

---

## R2 — Export ZIP layout, streaming, and resume

**Decision**:
- Layout: top-level `metadata.json` + per-resource directories (`agents/`, `executions/`, `audit/`, `costs/`, `members/` for workspace; add `workspaces/`, `users/`, `subscriptions/`, `tenant_settings/` for tenant).
- Streaming: write the ZIP to a S3 multi-part upload via `aioboto3.S3.create_multipart_upload`, holding ≤ 8 MB chunks in memory, writing parts as the streaming `zipfile` produces them.
- Resume: track `last_part_number` and `last_resource_emitted` on `data_export_jobs`. On worker crash, the next worker resumes from the last completed part — no duplicate parts (multi-part assembler dedupes on `PartNumber`).
- Compression: `ZIP_DEFLATED` level 6 (default) — beats no-compression on observed JSON-heavy export fixtures by ~3.5×.

**Rationale**: 100 GB tenant exports cannot fit in worker RAM and a single-shot upload would re-do the entire 60-minute job on retry. Multi-part + per-resource streaming is the only design that meets SC-002 (≤ 60 min p95) within the worker memory budget.

**Alternatives considered**:
- *Build full ZIP on local disk before upload*: Rejected. 100 GB temp space per worker is a hard provisioning ask; concurrent jobs would multiply the requirement.
- *Direct S3 SELECT-style streaming without ZIP*: Rejected. Spec FR-751.3 requires a ZIP with structured layout.
- *Server-side recompression to BZIP2*: Rejected. ~10× CPU cost for ~10 % size win.

**How to apply**: New `ExportArchiver` helper in `data_lifecycle/services/export_service.py` wraps `aioboto3.MultipartUploader`. Per-resource serializers go in `apps/control-plane/src/platform/data_lifecycle/serializers/{workspace,tenant}/{agents,executions,audit,...}.py` — each serializer is an async generator yielding `(filepath, bytes_chunk)` tuples that the archiver streams.

---

## R3 — DPA virus-scan: ClamAV in-cluster vs. external

**Decision**: Ship a Helm sub-chart `deploy/helm/clamav/` running Bitnami ClamAV (latest mainline) as a single-replica StatefulSet with a 2 GiB PVC for the signature database. Daily signature update via initContainer + sidecar `freshclam`. The DPA service connects via the official `clamd` Python client over a plain TCP socket on port 3310 (cluster-internal Service, no Ingress).

**Rationale**: External providers (VirusTotal, Cloudflare Sandbox) are commercial, expose the DPA bytes off-cluster (data-residency violation per rule 18), and add per-scan latency that pushes p95 over the 30 s SC-007 budget. ClamAV in-cluster is the standard pattern, free, and keeps DPA bytes on-platform.

**Alternatives considered**:
- *VirusTotal*: Rejected. Sends DPA off-platform; cross-region transfer; commercial.
- *No virus scan*: Rejected. Spec edge case explicitly requires it; legal risk for shipping infected PDFs to the tenant admin.
- *MaxMind ClamAV-as-a-service*: Rejected. Same data-egress issue.

**How to apply**: New env vars `DATA_LIFECYCLE_CLAMAV_HOST` (default `clamav.platform-data:3310`), `DATA_LIFECYCLE_CLAMAV_PORT` (default 3310), `DATA_LIFECYCLE_CLAMAV_TIMEOUT_SECONDS` (default 25). Failure mode: if ClamAV is unreachable, return 503 `dpa_scan_unavailable` (fail-safe). Retries: 3 attempts with exponential backoff; the upload UI shows a single banner and a Retry button.

---

## R4 — Backup separation + 30-day purge approach

**Decision**: Encrypted-key-destruction. Each tenant's backup objects encrypted with a tenant-specific KMS data key. On tenant deletion phase-2 + 30 days, the key is destroyed (key-shred). The cipher-text remains on tape/cold-storage, satisfying regulatory retention, but is unrecoverable — meeting the GDPR right-to-be-forgotten standard accepted by GDPR practitioners as "logical deletion".

**Rationale**: Hard-deleting a tenant's backup data within 30 days conflicts with regulatory retention obligations (financial: 7 years for accounting trail; HIPAA-adjacent: 6 years). Key-destruction is the standard reconciliation. We keep the cold-storage proof-of-archival while making the data cryptographically unrecoverable.

**Alternatives considered**:
- *Hard delete from backup object store*: Rejected. Some regulatory regimes (EU finance for invoices, US HIPAA-adjacent for health) require multi-year retention. Removing the backup object violates the underlying contract and tenant DPAs.
- *Retain backup in plaintext for 7 years*: Rejected. Violates GDPR right-to-be-forgotten — the data IS recoverable.

**How to apply**: New `backup_purge_service.py` enqueues a key-destruction request to the existing KMS adapter (per UPD-040 `SecretRotationService` pattern) at `phase_2_completed_at + 30 days`. The audit chain records the key id, key-version, and key-destruction-timestamp as a tombstone (rule 16 + AD-17).

---

## R5 — Sub-processors public page: independent deployment vs. shared

**Decision**: Ship a separate Helm release `deploy/helm/public-pages/` that runs the same Next.js image with the `(public)` route group only, behind its own Ingress and 2-replica Deployment. This deliberately mirrors the rule-49 status-page pattern.

**Rationale**: A control-plane outage (database down, auth service down) MUST NOT hide the sub-processors page — it's a regulatory artifact a customer reads when evaluating Trust & Compliance. A shared Deployment with the main `/api/v1/*` stack would couple the page's availability to the platform's. The page is read-mostly (regenerated on data change via cron), so duplication of route serving is essentially free.

**Alternatives considered**:
- *Same Deployment as `apps/web`*: Rejected. Couples to control-plane. Outages hide the page.
- *Static-site generation deployed to GitHub Pages*: Rejected. Diverges from the in-cluster operational model and complicates CI.

**How to apply**: The `public-pages/` chart's Deployment runs `pnpm start` with an env var `NEXT_PUBLIC_ROUTE_GROUP=public` that the App Router uses to short-circuit non-`(public)` matchers. Sub-processors data fetched at SSR-time from the shared sub-processors REST GET (cached via ETag); on cache miss, fall back to a baked-in JSON snapshot regenerated by `sub_processors_regenerator` cron (snapshot lives in a `ConfigMap` mounted into the public pod).

---

## R6 — Grace period: per-tenant override mechanism

**Decision**: Default grace = 7 days for workspace deletion, 30 days for tenant deletion. Per-Enterprise-tenant override stored on `tenants.settings_json.deletion_grace_period_days` (existing JSON column). Validation: 7 ≤ override ≤ 90.

**Rationale**: Spec assumption A2 explicitly states grace days are bounded. Storing as JSON on `tenants` reuses the existing settings mechanism (avoids an explicit column). Validation at the upper bound avoids indefinite-grace abuse.

**Alternatives considered**:
- *Hardcoded constants*: Rejected. Spec calls out per-contract overrides for Enterprise.
- *New first-class column `tenants.deletion_grace_days`*: Rejected. Adds DDL for a single feature; the JSON column is the documented extension point.

**How to apply**: New helper `data_lifecycle/services/grace_calculator.py:resolve(scope_type, scope_id) -> int` reads from `settings_json` with fallback to defaults. Audit logs the resolved value on every deletion request.

---

## R7 — Recovery-during-grace: privileged restoration semantics

**Decision**: A super admin (and only a super admin) can issue `POST /api/v1/admin/data-lifecycle/deletion-jobs/{id}/abort` during phase-1. The deletion job transitions to `aborted`; the workspace/tenant returns to its prior status; an audit chain entry records actor + reason. After phase-2 dispatch begins, abort is no longer permitted (returns 409 `cascade_in_progress`).

**Rationale**: Spec US3 acceptance #4 calls out super-admin recovery during grace. After phase-2 starts, hot-store deletion has begun — partial undo would leave inconsistent state.

**Alternatives considered**:
- *Allow workspace owner to self-abort*: Permitted only via the cancel-link in the confirmation email (phase-1 only); does NOT include rescuing a tenant deletion.
- *Allow abort during phase-2*: Rejected. Cascade is irreversible by store-level design.

**How to apply**: `DeletionService.abort(job_id, actor, reason)` validates phase ∈ {`phase_1`}, flips state, restores prior workspace/tenant status, emits `deletion_job.aborted` event + audit entry. After-phase-2 state returns 409.

---

## R8 — DNS/TLS teardown coupling to UPD-053

**Decision**: Soft prerequisite — feature-flagged behind `FEATURE_UPD053_DNS_TEARDOWN` (default `false` until UPD-053 ships). When false, phase-2 logs a structured `dns_teardown_skipped: tenant_id=...` warning and proceeds with the data-store cascade. When true, phase-2 calls `tenant_cascade.py:teardown_dns(tenant_slug)` which delegates to the UPD-053 service.

**Rationale**: Wave 26 places UPD-053 alongside UPD-051. If UPD-053 slips, UPD-051 can ship — the data-store cascade is the regulatory-critical path; DNS records leaking for an extra week is an operational issue, not a compliance one. Hard-coupling would block UPD-051 on UPD-053 readiness.

**Alternatives considered**:
- *Hard prerequisite (block UPD-051 until UPD-053 ships)*: Rejected. Couples regulatory delivery to ops automation.
- *Inline DNS calls in `data_lifecycle/`*: Rejected. Violates the BC boundary; UPD-053 owns DNS.

**How to apply**: Phase-2 cascade wrapper checks the feature flag. The journey test J27 enables the flag in CI to assert the full cascade. Manual ops cleanup runbook published at `deploy/runbooks/data-lifecycle/dns-teardown-manual.md` for the flag-off path.

---

## R9 — Tenant-export password delivery (out-of-band)

**Decision**: Generate a 32-char URL-safe password, encrypt the ZIP with it (AES-256 via `aioboto3.S3 SSE-C` header), then deliver the password via TWO out-of-band channels: (a) an authenticated email to the tenant admin's verified email (existing UPD-077 email channel) and (b) optionally an SMS via UPD-077 SMS adapter when `FEATURE_UPD077_DPA_SMS_PASSWORD=true` AND `tenants.contact_phone_e164` is populated.

**Rationale**: Phase-1 final export contains every tenant's data. Sending the signed download URL and the password in the same email is a single-channel-compromise risk. Two-channel delivery is the GDPR-recommended pattern for sensitive data egress.

**Alternatives considered**:
- *Single-email delivery*: Rejected. Single channel = single compromise.
- *Hand-deliver via tenant admin's existing OAuth provider*: Rejected. Not all tenant admins have OAuth set up; would block on identity coverage.

**How to apply**: When SMS flag is off OR phone is empty, fall back to email + a temporary 6-digit OTP that the tenant admin must enter on the download page (effectively a second authentication factor). Audit chain records both deliveries.

---

## R10 — Anti-enumeration on the cancel-deletion link

**Decision**: The workspace/tenant cancel-deletion link returns identical 200 responses for: (a) valid + unused token, (b) valid + already-used token, (c) invalid token, (d) expired token. Server-side branches on the actual case to either honour the cancel or do nothing. The UI says "If the link was valid, deletion has been cancelled — check your email for confirmation."

**Rationale**: Rule 35's anti-enumeration intent applies generally: don't leak whether a token is "real". Emitting a 404 for invalid tokens leaks token validity to a guesser; leaking workspace existence is a tenant-isolation hole.

**Alternatives considered**:
- *404 on invalid token*: Rejected. Leaks valid-token shape and existence.
- *302 to login page*: Rejected. Adds a friction step for legitimate users without improving the security posture.

**How to apply**: `WorkspaceRouter.cancel_deletion(token)` and `TenantAdminRouter.cancel_deletion(token)` both share the same `Response(status_code=200, body={"message": "If the link was valid, deletion has been cancelled."})` template. Server-side audit logs include the actual outcome (`cancel_succeeded` / `token_already_used` / `token_invalid` / `token_expired`) so operators can see real signal.

---

## Open follow-ups (not blocking Phase 1)

- **Sub-processor RSS**: Spec calls for an RSS feed (US4 acceptance #5); detailed XML schema is deferred to contract `sub-processors-rest.md` Phase 1. RSS is read-only public, served by the public-pages release.
- **Cold-storage object-lock duration**: 7 years per regulatory baseline. Configurable via Helm value `dataLifecycle.coldStorage.retentionYears` defaulting to 7, capped at 10 (S3 Object Lock COMPLIANCE mode). Confirm with legal before first prod release.
- **DPA versioning model**: Append-only — every upload bumps `dpa_version` and writes a new Vault path `dpa-v{n}.pdf`. Old versions retained for 7 years per regulatory baseline (separate KMS key from the live DPA so revocation flows can't accidentally destroy historical evidence).

---

## Decisions summary

| ID | Decision | Risk if reversed |
|---|---|---|
| R1 | Extend `CascadeOrchestrator` (no parallel engine) | Drift between user-DSR and tenant-deletion cascade |
| R2 | S3 multi-part streaming ZIP | OOM crashes on large tenant exports |
| R3 | In-cluster ClamAV via Helm sub-chart | Data-residency violation if external scanner used |
| R4 | Encrypted-key-destruction for backup purge | Regulatory retention vs GDPR conflict unresolved |
| R5 | `public-pages` Helm release for sub-processors | Outage hides regulatory artifact |
| R6 | Per-tenant grace via `tenants.settings_json` | Avoids new column; uses documented extension point |
| R7 | Abort permitted only in phase-1 | Inconsistent state if phase-2 partially undone |
| R8 | DNS teardown feature-flagged on UPD-053 | UPD-051 ship blocked on UPD-053 readiness |
| R9 | Two-channel password delivery for tenant export | Single-channel compromise risk |
| R10 | Anti-enumeration on cancel-deletion links | Token-validity leak to guessers |
