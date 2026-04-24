# Tasks: Security Compliance and Supply Chain

**Input**: Design documents from `/specs/074-security-compliance/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Tests**: Required (CI coverage gate ≥ 95%); every contract lists named test IDs (AC1-7, SB1-4, VS1-5, SR1-6, JT1-7, PT1-6, CE1-5) that are generated as explicit tasks.

**Organization**: Tasks are grouped by user story. US2 (audit chain) ships before US1 (SBOM / vuln gating) because US1 writes chain entries via `AuditChainService.append()` — the chain service must be operational first. The core `audit/` BC service skeleton lives in Phase 2 (Foundational); US2's own phase finishes the chain with integrity-check, attestation, and BC-integration hooks.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: User story label [US1]–[US6]

---

## Phase 1: Setup

**Purpose**: Scaffold BC directories, ensure deps, and stub CI normaliser scripts.

- [X] T001 Create the new bounded-context directories: `apps/control-plane/src/platform/audit/` (with `__init__.py`, empty `models.py`, `schemas.py`, `service.py`, `repository.py`, `signing.py`, `events.py`, `router.py`, `exceptions.py`) and `apps/control-plane/src/platform/security_compliance/` (same skeleton set plus `services/`, `providers/`, `frameworks/`, `workers/` sub-packages each with an `__init__.py`).
- [X] T002 [P] Verify `cryptography` and `pyyaml` are already in `apps/control-plane/pyproject.toml`; if not, add them. Both are expected (used by auth/ and accounts/ today) — this task exists as a defensive check.
- [X] T003 [P] Create `ci/normalize_scan_results.py` and `ci/normalize_sbom.py` stubs at repo root with argparse entry points and `NotImplementedError` bodies; implementations come in T041 / T043 respectively. Also create `ci/tests/__init__.py` and placeholder test files.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Alembic migration 058, config, event registry, and the `audit/` BC primitive (`AuditChainService` skeleton + Ed25519 signing) that every subsequent user story depends on.

**⚠️ CRITICAL**: No user story (Phase 3–8) can begin until Phase 2 is complete.

### 2A — Migration + config + event registry

- [X] T004 Write Alembic migration `apps/control-plane/migrations/versions/058_security_compliance.py` creating all 13 new tables per `data-model.md` §1–§2, seeding `pentest_sla_policies` (4 rows), `jit_approver_policies` (4 rows), and `compliance_controls` + `compliance_evidence_mappings` from the YAML frameworks in `security_compliance/frameworks/`. Split into logical functions (`_create_audit_chain_table`, `_create_sbom_table`, etc.) as shown in the data-model.md §6 outline. Include the `BEFORE UPDATE OR DELETE` trigger on `audit_chain_entries` and the role-level revocation of `UPDATE`/`DELETE` for the application DB role.
- [X] T005 [P] Extend `apps/control-plane/src/platform/common/config.py` with two new Pydantic settings models: `AuditSettings` (fields: `signing_key_hex`, `verifying_key_hex`, `fail_closed_on_append_error: bool = True`) and `SecurityComplianceSettings` (fields: `vuln_gate_enabled: bool = True`, `rotation_scheduler_interval_seconds: int = 300`, `rotation_overlap_min_hours: int = 24`, `rotation_overlap_max_hours: int = 168`, `pentest_overdue_scan_cron: str`, `manual_evidence_bucket: str = "compliance-evidence"`, `jit_max_expiry_minutes_floor: int = 1440`). Attach as `PlatformSettings.audit` and `PlatformSettings.security_compliance`. Every field carries `Field(description=...)` (constitution rule 37).
- [X] T006 [P] Create YAML seed files in `apps/control-plane/src/platform/security_compliance/frameworks/`: `soc2.yaml` (SOC2 CC1–CC9), `iso27001.yaml` (ISO 27001:2022 Annex A controls), `hipaa.yaml` (HIPAA Security Rule §164.308–§164.314), `pci_dss.yaml` (PCI-DSS v4.0 Requirements 1–12), `mappings.yaml` (evidence_type → control_ids per research.md D-011). These are loaded by T004's seeder.
- [X] T007 [P] Register the 7 new Kafka topics in `apps/control-plane/src/platform/security_compliance/events.py` (following the `auth/events.py:publish_auth_event` pattern): `security.sbom.published`, `security.scan.completed`, `security.pentest.finding.raised`, `security.secret.rotated`, `security.jit.issued`, `security.jit.revoked`. Plus a sibling `apps/control-plane/src/platform/audit/events.py` for `security.audit.chain.verified`. Both modules expose typed Pydantic payload schemas + `publish_*_event` helpers and call `event_registry.register(...)` for each type.

### 2B — `audit/` BC primitive (unblocks every user story)

- [X] T008 [P] Implement SQLAlchemy model `AuditChainEntry` in `apps/control-plane/src/platform/audit/models.py` matching `data-model.md` §1.1 (columns: id, sequence_number BIGSERIAL, previous_hash VARCHAR(64), entry_hash VARCHAR(64) UNIQUE, audit_event_id UUID NULL, audit_event_source VARCHAR(64), canonical_payload_hash VARCHAR(64), created_at). Declare `__table_args__` with the UNIQUE constraints + indexes from §1.1.
- [X] T009 [P] Implement `AuditChainSigning` in `apps/control-plane/src/platform/audit/signing.py`: load Ed25519 keypair from settings; expose `sign(document: bytes) -> bytes` (64-byte signature) and `verify(document: bytes, signature: bytes, public_key_hex: str) -> bool`. Use `cryptography.hazmat.primitives.asymmetric.ed25519`. The module MUST NOT log key material (constitution rule 40); a unit test asserts no log emissions touching the private seed.
- [X] T010 Implement `AuditChainRepository` in `apps/control-plane/src/platform/audit/repository.py` with async methods: `insert_entry`, `get_latest_entry`, `get_by_sequence_range`, `get_by_sequence`. Repository is `INSERT, SELECT` only; the `update`/`delete` methods explicitly raise `NotImplementedError` to prevent accidental misuse (append-only enforcement beyond the DB trigger).
- [X] T011 Implement `AuditChainService` in `apps/control-plane/src/platform/audit/service.py` exposing `append(audit_event_id, audit_event_source, canonical_payload)`, `verify(start_seq=None, end_seq=None)`, `export_attestation(start_seq, end_seq)`, `get_public_verifying_key()` per `contracts/audit-chain-service.md`. Append computes the hash per the data-model.md §1.1 formula, inserts the row, and emits `security.audit.chain.verified` (only on integrity-check — NOT on append; name is slightly misleading — see research.md D-011 for event-shape note). Depends on T008, T009, T010.

### 2C — Stub the existing-BC audit chain hooks (enables US1 without blocking)

- [X] T012 [P] Add a thin `audit_chain_hook` helper function in `apps/control-plane/src/platform/common/audit_hook.py` that existing BCs call immediately after writing their own audit row: `await audit_chain_hook(service, audit_event_id, source, row_as_dict)`. This helper canonicalises the dict to sorted-key JSON and delegates to `AuditChainService.append`. Provides a single choke point for downstream integration in T021 / T022 / T023 / T024.

**Checkpoint**: Foundation complete — migration 058 applied; `AuditChainService.append()` is callable from any BC; 7 Kafka topics registered; YAML framework catalogues seeded. User stories can begin.

---

## Phase 3: User Story 2 — Cryptographic Audit Chain (Priority: P1)

**Goal**: Every existing audit-emitting BC writes a chain entry; integrity-check and attestation endpoints live at `/api/v1/security/audit-chain/*`; tamper detection works.

**Independent Test**: Write 1,000 audit entries; run integrity check; assert valid. Corrupt one row; re-run; assert broken_at = corrupted sequence number. Export a time-window attestation; verify its signature externally with the public key.

### Tests for User Story 2

- [X] T013 [P] [US2] Unit tests AC1–AC6 in `apps/control-plane/tests/unit/audit/test_audit_chain_service.py` per `contracts/audit-chain-service.md`: single-entry hash formula, three sequential entries chain intact, corrupt row detection, RTBF cascade leaves chain valid, attestation signature verifies with external Ed25519, concurrent append produces unique sequence numbers.
- [X] T014 [P] [US2] Performance test AC7 in `apps/control-plane/tests/integration/audit/test_audit_chain_perf.py`: insert 1,000,000 entries; assert `verify()` returns in ≤ 60 s (SC-005).
- [X] T015 [P] [US2] Integration test in `apps/control-plane/tests/integration/audit/test_audit_chain_rtbf.py`: produce an audit row referencing a user; delete the user via RTBF cascade; run verify; assert chain still valid and the referenced `audit_event_id` is NULL per AD-17.

### Implementation for User Story 2

- [X] T016 [US2] Add Pydantic schemas in `apps/control-plane/src/platform/audit/schemas.py`: `VerifyResult`, `SignedAttestation`, `PublicKeyResponse`.
- [X] T017 [US2] Implement the admin router in `apps/control-plane/src/platform/audit/router.py` with three endpoints: `GET /api/v1/security/audit-chain/verify` (query params: `start_seq`, `end_seq`), `POST /api/v1/security/audit-chain/attestations` (body: `{start_seq, end_seq}`), `GET /api/v1/security/audit-chain/public-key` (public per constitution rule 49). Every method depends on `require_superadmin` OR `require_auditor` except the public-key endpoint. Tag with `['admin', 'audit-chain']`.
- [X] T018 [US2] Register the audit router in `apps/control-plane/src/platform/main.py` alongside existing routers. Add `/api/v1/security/audit-chain/public-key` to `auth_middleware.py` `EXEMPT_PATHS` (public endpoint).
- [X] T019 [US2] Integration-hook: extend `apps/control-plane/src/platform/auth/repository_oauth.py` `_create_audit_entry` path to call `audit_chain_hook(service, entry.id, 'auth', entry_as_dict)` immediately after the existing `OAuthAuditEntry` insert. No behavioural change on success; append failure propagates per `fail_closed_on_append_error` setting.
- [X] T020 [US2] Integration-hook in `apps/control-plane/src/platform/a2a_gateway/server_service.py` `_create_audit` method: call `audit_chain_hook` with `source='a2a_gateway'` after the `A2AAuditRecord` insert.
- [X] T021 [US2] Integration-hook in `apps/control-plane/src/platform/registry/` wherever `insert_lifecycle_audit` is called: add `audit_chain_hook` with `source='registry'`.
- [X] T022 [US2] Integration-hook in `apps/control-plane/src/platform/mcp/` wherever `create_audit_record` is called: add `audit_chain_hook` with `source='mcp'`.

**Checkpoint**: US2 complete. Every existing audit write is now chained; tamper detection works end-to-end.

---

## Phase 4: User Story 1 — SBOM + Vulnerability Gating (Priority: P1) 🎯 MVP

**Goal**: Every tagged release generates SPDX + CycloneDX SBOMs, runs the full scanner matrix, gates on severity, and persists evidence.

**Independent Test**: Trigger a release; confirm both SBOMs are attached to the GitHub release AND ingested into the platform. Inject a stub critical CVE; confirm the release workflow fails at the gate. Remove the CVE; confirm the release proceeds.

### Tests for User Story 1

- [X] T023 [P] [US1] Unit tests SB1–SB4 in `apps/control-plane/tests/unit/security_compliance/test_sbom_service.py` per `contracts/sbom-generation.md`.
- [X] T024 [P] [US1] Unit tests VS1–VS5 in `apps/control-plane/tests/unit/security_compliance/test_vuln_scan_service.py` per `contracts/vuln-scan-pipeline.md`.
- [X] T025 [P] [US1] Tests in `ci/tests/test_normalize_scan_results.py` covering the normaliser logic: input from each scanner, output shape, severity resolution, exception lookup.

### Implementation for User Story 1

- [X] T026 [P] [US1] SQLAlchemy models `SoftwareBillOfMaterials`, `VulnerabilityScanResult`, `VulnerabilityException` in `apps/control-plane/src/platform/security_compliance/models.py` (start the file with these three) matching `data-model.md` §2.1–§2.3.
- [X] T027 [P] [US1] Pydantic schemas in `security_compliance/schemas.py` for the SBOM + scan + exception admin endpoints.
- [X] T028 [US1] Implement `SbomService` in `security_compliance/services/sbom_service.py`: `ingest(release_version, format, content)` computes SHA-256, persists, publishes `security.sbom.published`, and writes an audit chain entry.
- [X] T029 [US1] Implement `VulnScanService` in `security_compliance/services/vuln_scan_service.py`: `ingest_scan(release_version, scanner, findings, max_severity)`, `evaluate_gating(release_version)` (aggregates all scanners' results + consults `VulnerabilityException` table), `create_exception(...)` with 2PA server-side enforcement (rule 33). Emits `security.scan.completed`.
- [X] T030 [US1] Extend `security_compliance/router.py` with SBOM + scan + exception endpoints per `contracts/admin-api.md` + `contracts/sbom-generation.md` + `contracts/vuln-scan-pipeline.md`. Every method gates via `require_admin`/`require_superadmin`/`require_release_publisher`. Tag routes with `['admin', 'security', 'sbom' | 'scans' | 'exceptions']`.
- [X] T031 [US1] Implement `ci/normalize_scan_results.py` (replacing the T003 stub): reads scanner outputs (SARIF, JSON) from `scan-results/`, normalises to the shape in `contracts/vuln-scan-pipeline.md`, consults `scan-metadata.json` for dev-only markings, POSTs to `/api/v1/security/scans/{release_version}/results` using a GitHub-OIDC → platform JWT exchange, exits non-zero if any `gating_result = 'blocked'`.
- [X] T032 [US1] Extend `.github/workflows/ci.yml` with five new parallel scanner jobs (`pip-audit`, `govulncheck`, `bandit`, `gosec`, `npm audit`) per `contracts/vuln-scan-pipeline.md` + a final `upload-security-artefacts` job that runs `ci/normalize_scan_results.py`. Use `actions/cache` aggressively to keep CI time bounded.
- [X] T033 [US1] Extend `.github/workflows/deploy.yml` — duplicate the existing `anchore/sbom-action` step to emit both `cyclonedx-json` and `spdx-json` formats; add a POST step that uploads each format to `/api/v1/security/sbom` using a GitHub-OIDC → platform JWT exchange.
- [X] T034 [US1] Implement `ci/normalize_sbom.py` (replacing the T003 stub): canonicalises SBOM JSON (sorted keys, deterministic output) so `content_sha256` is reproducible across runs.

**Checkpoint**: US1 complete. CI gates releases on CVE severity; SBOMs persisted; audit chain entries written for every ingest.

---

## Phase 5: User Story 3 — Zero-Downtime Secret Rotation (Priority: P2)

**Goal**: Scheduled + emergency rotations with a 24-h overlap window produce zero request failures for compliant validators.

**Independent Test**: Configure a test credential, trigger rotation, drive 100 req/s, assert zero failures; verify state machine transitions via chain entries; trigger emergency rotation with 2PA.

### Tests for User Story 3

- [X] T035 [P] [US3] Unit tests SR1–SR5 in `apps/control-plane/tests/unit/security_compliance/test_secret_rotation.py` per `contracts/secret-rotation-service.md`.
- [X] T036 [P] [US3] Integration test SR6 in `apps/control-plane/tests/integration/security_compliance/test_rotation_zero_failure.py`: drive 100 req/s against a validator during a full rotation cycle; assert zero auth failures (SC-007).

### Implementation for User Story 3

- [X] T037 [P] [US3] Add `SecretRotationSchedule` SQLAlchemy model to `security_compliance/models.py` per `data-model.md` §2.7.
- [X] T038 [P] [US3] Implement `RotatableSecretProvider` in `security_compliance/providers/rotatable_secret_provider.py` with `get_current`, `get_previous`, `validate_either` per `contracts/secret-rotation-service.md`. Back it with the existing `VaultResolver` (from `connectors/security.py`) for `vault` mode; fall back to env-var read for `mock` mode. Cached in Redis at `rotation:state:{secret_name}` with 60 s TTL. Hard dependency noted: real Vault implementation arrives with UPD-040; for now, `mock` + env-var is acceptable.
- [X] T039 [P] [US3] Pydantic schemas in `security_compliance/schemas.py` for the rotation admin API (ScheduleCreate, ScheduleResponse, TriggerRequest).
- [X] T040 [US3] Implement `SecretRotationService` in `security_compliance/services/secret_rotation_service.py`: state machine transitions per `contracts/secret-rotation-service.md`, Vault state updates, `security.secret.rotated` events at each transition, audit chain entries at each transition, 2PA enforcement for emergency-skip-overlap (rule 33). Never echoes the new secret in responses (rule 44).
- [X] T041 [US3] Implement `rotation_scheduler.py` worker in `security_compliance/workers/`: APScheduler job that scans `WHERE rotation_state='idle' AND next_rotation_at < now()` every `rotation_scheduler_interval_seconds` and triggers rotations. Register at app-factory lifespan.
- [X] T042 [US3] Implement `overlap_expirer.py` worker in `security_compliance/workers/`: APScheduler job that scans `WHERE rotation_state='overlap' AND overlap_ends_at < now()` every 30 s and advances to `finalising`. Register at lifespan.
- [X] T043 [US3] Extend `security_compliance/router.py` with rotation endpoints per `contracts/secret-rotation-service.md` — GET, POST, PATCH, trigger, history — all admin-gated.

**Checkpoint**: US3 complete. Rotation works with zero downtime; state machine visible via audit chain.

---

## Phase 6: User Story 4 — JIT Credentials (Priority: P2)

**Goal**: Peer-approved, time-bounded credentials for privileged operations with full usage audit.

**Independent Test**: Request → self-approval rejected → peer approval → JWT issued → JWT used (usage audited) → revoked → JWT rejected.

### Tests for User Story 4

- [X] T044 [P] [US4] Unit tests JT1–JT7 in `apps/control-plane/tests/unit/security_compliance/test_jit_service.py` per `contracts/jit-service.md`: request→approve→issued, self-approval rejected, wrong-role approval rejected, post-expiry JWT rejected, revoked JWT rejected, usage audit populated, customer_data operation requires 2 approvers.

### Implementation for User Story 4

- [X] T045 [P] [US4] Add `JitCredentialGrant` + `JitApproverPolicy` SQLAlchemy models to `security_compliance/models.py` per `data-model.md` §2.8–§2.9. The check constraint `CHECK (approved_by IS NULL OR approved_by != user_id)` goes in __table_args__.
- [X] T046 [P] [US4] Pydantic schemas in `security_compliance/schemas.py` for JIT grant lifecycle + approval + revocation + usage.
- [X] T047 [US4] Implement `JitService` in `security_compliance/services/jit_service.py`: `request_grant`, `approve_grant` (2PA + role check + min-approvers enforcement — rule 33), `reject_grant`, `revoke_grant`, `record_usage` per `contracts/jit-service.md`. On approval, issue a short-lived JWT via the existing `auth/services/auth_service.py` with `jti=grant_id` + `purpose` claim. Emits `security.jit.issued` / `security.jit.revoked` + audit chain entry for each.
- [X] T048 [US4] Extend the JWT validator in `apps/control-plane/src/platform/common/auth_middleware.py` to perform an additional Redis denylist lookup `jit:revoked:{jti}` when the JWT has a `jti` claim pointing to a known JIT grant. Revocation takes effect on the next request.
- [X] T049 [US4] Extend `security_compliance/router.py` with the 8 JIT endpoints per `contracts/admin-api.md`. The `/request` endpoint is authenticated-user (not admin) per `contracts/jit-service.md`; all others are admin-gated. Tag routes with `['admin', 'security', 'jit']`.

**Checkpoint**: US4 complete. JIT grants issued + used + revoked; audit trail + Kafka events; 2PA enforced server-side.

---

## Phase 7: User Story 5 — Pentest Tracking (Priority: P3)

**Goal**: Pentest scheduling, import, SLA-driven due-dates, overdue surfacing, and history export.

**Independent Test**: Schedule, execute, import 3 findings (critical/medium/low) with SLA-computed due dates; advance clock; overdue finding appears; mark remediated; history export complete.

### Tests for User Story 5

- [X] T050 [P] [US5] Unit tests PT1–PT6 in `apps/control-plane/tests/unit/security_compliance/test_pentest_service.py` per `contracts/pentest-tracking.md`.

### Implementation for User Story 5

- [X] T051 [P] [US5] Add `PenetrationTest`, `PentestFinding`, `PentestSlaPolicy` SQLAlchemy models to `security_compliance/models.py` per `data-model.md` §2.4–§2.6.
- [X] T052 [P] [US5] Pydantic schemas in `security_compliance/schemas.py` for pentest CRUD + findings import + overdue view.
- [X] T053 [US5] Implement `PentestService` in `security_compliance/services/pentest_service.py`: `schedule`, `execute` (computes attestation_hash = sha256(report_pdf || metadata_canonical_json)), `import_findings` (rejects missing severity, computes due_date from SLA policy), `update_finding_status`, `list_overdue`, `export_history`. Emits `security.pentest.finding.raised` + audit chain entry.
- [X] T054 [US5] Implement `pentest_overdue_scanner.py` worker in `security_compliance/workers/`: daily APScheduler job that scans open findings past their due date, emits `security.pentest.finding.raised` with `overdue: true`, and sends notifications.
- [X] T055 [US5] Extend `security_compliance/router.py` with the 8 pentest endpoints per `contracts/pentest-tracking.md`. Override due-date endpoint validates floor against `pentest_sla_policies.ceiling_days`. All admin-gated. Tag `['admin', 'security', 'pentest']`.

**Checkpoint**: US5 complete. Pentest lifecycle tracked; overdue findings surfaced automatically.

---

## Phase 8: User Story 6 — Compliance Evidence Substrate (Priority: P3)

**Goal**: Auto-association of security events to framework controls; manual uploads; signed evidence bundle export.

**Independent Test**: After US1-US5 have produced events, SOC2 framework view shows controls with evidence counts; upload manual evidence to a gap; export signed bundle; verify hashes externally.

### Tests for User Story 6

- [X] T056 [P] [US6] Unit tests CE1–CE5 in `apps/control-plane/tests/unit/security_compliance/test_compliance_service.py` per `contracts/compliance-evidence.md`.

### Implementation for User Story 6

- [X] T057 [P] [US6] Add `ComplianceControl`, `ComplianceEvidenceMapping`, `ComplianceEvidence` SQLAlchemy models to `security_compliance/models.py` per `data-model.md` §2.10–§2.12.
- [X] T058 [P] [US6] Pydantic schemas in `security_compliance/schemas.py` for framework view, manual upload, bundle export.
- [X] T059 [US6] Implement `ComplianceService` in `security_compliance/services/compliance_service.py`: `on_security_event` (Kafka consumer handler that walks mappings and inserts evidence rows), `list_framework_controls_with_evidence`, `upload_manual_evidence` (S3 PUT to `compliance-evidence/{framework}/{control_id}/...`), `generate_bundle` (collects evidence refs + hashes, signs the manifest with the audit BC's Ed25519 key, returns a pre-signed S3 URL). Unmapped-event-type metric emitted.
- [X] T060 [US6] Register a Kafka consumer in the `worker` runtime profile that subscribes to all 7 security topics + `security.audit.chain.verified` and dispatches to `ComplianceService.on_security_event`. Use the existing aiokafka consumer pattern from `common/events/consumer.py`.
- [X] T061 [US6] Extend `security_compliance/router.py` with the 6 compliance endpoints per `contracts/compliance-evidence.md`. Manual-upload endpoint accepts multipart/form-data and writes to S3 via the platform's generic S3 provider. Tag `['admin', 'security', 'compliance']`.

**Checkpoint**: US6 complete. Framework views show auto-collected evidence; bundle export is externally verifiable.

---

## Phase 9: Polish & Cross-Cutting Concerns

- [X] T062 Write regression test `apps/control-plane/tests/unit/audit/test_append_only.py` asserting the `audit_chain_entries` DB trigger raises on any `UPDATE` or `DELETE` attempt; also asserts the `AuditChainRepository.update` / `.delete` methods raise `NotImplementedError`.
- [X] T063 [P] Add per-BC append-latency assertion to each audit-hook integration test (T019–T022): assert `audit_chain_hook` call completes in ≤ 5 ms p99 under isolated conditions (SC-005 derivative, Complexity Item #1).
- [X] T064 [P] Update the feature-catalogue page `docs/features/074-security-compliance.md` (generated on the docs branch) with grounded content — replace the 7 `TODO(andrea)` placeholders.
- [X] T065 Update `docs/administration/audit-and-compliance.md` to reference the new chain + attestation endpoints (supersedes the current "planned for UPD-024" note).
- [X] T066 Run the six quickstart walkthroughs (Q1–Q6 in `quickstart.md`) against a local `make dev-up` cluster; fix any divergence before marking the feature complete.

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: depends on Phase 1 — **BLOCKS all user stories**.
- **US2 (Phase 3)**: depends on Phase 2. **Must ship before US1** (US1 writes chain entries via `AuditChainService`, which is scaffolded in Phase 2 and finished in US2).
- **US1 (Phase 4)**: depends on Phase 2's `audit/` scaffold being operational (T011 complete). Can run in parallel with US2's completion tasks IF T011 is on `main`.
- **US3 (Phase 5)**: depends on Phase 2. Independent of US1/US2/US4/US5/US6 once foundation lands.
- **US4 (Phase 6)**: depends on Phase 2. Independent.
- **US5 (Phase 7)**: depends on Phase 2. Independent.
- **US6 (Phase 8)**: depends on Phase 2 AND depends on at least one of US1–US5 having produced some events (Kafka consumer wouldn't have anything to map otherwise). Practically, US6 lands after US1–US5 OR runs in parallel against a test fixture stream.
- **Polish (Phase 9)**: depends on US1–US6 complete.

### Within Phase 2

- T004 (migration) can start with T005, T006, T007 in parallel (different files).
- T008, T009, T012 all `[P]` (different files).
- T010 depends on T008.
- T011 depends on T008, T009, T010.

### Within each user story

- Models / schemas / repository / worker modules all `[P]` where they touch different files.
- Services depend on models + schemas.
- Router tasks depend on service.
- CI workflow tasks (T031–T034) can run in parallel with Python-side US1 work.

### Parallel execution opportunities

```bash
# Phase 1 — 3 parallel:
Task: "Create BC dirs (T001)"
Task: "Verify deps (T002)"
Task: "ci/ stubs (T003)"

# Phase 2 — 6 parallel after T004 starts:
Task: "Migration 058 (T004)"
Task: "Config extensions (T005)"
Task: "Framework YAMLs (T006)"
Task: "Kafka event registry (T007)"
Task: "AuditChainEntry model (T008)"
Task: "Ed25519 signing (T009)"
Task: "audit_chain_hook helper (T012)"
# T010, T011 serialise after T008.

# Phase 3 US2 — tests parallel, then sequential impl:
Task: "Unit tests AC1-6 (T013)"
Task: "Perf test AC7 (T014)"
Task: "RTBF test (T015)"
# T016–T018 sequential (same files)
# T019–T022 parallel (different BC files)

# Phase 4 US1 — tests + implementation parallel:
Task: "SBOM service tests (T023)"
Task: "Vuln scan service tests (T024)"
Task: "Normaliser tests (T025)"
Task: "Models (T026)"
Task: "Schemas (T027)"
# T028–T030 sequential (same router/service files)
# T031–T034 CI workflow parallel with Python side

# Phase 5 US3, Phase 6 US4, Phase 7 US5, Phase 8 US6:
# All can start simultaneously once Phase 2 + US2 complete.
# Within each, models/schemas [P], then service, then router.

# Polish:
Task: "Append-only regression test (T062)"
Task: "Append-latency assertions (T063)"
Task: "Feature-catalogue doc (T064)"
Task: "Admin docs update (T065)"
```

---

## Implementation Strategy

### MVP scope (US1 + US2)

Both are P1. Minimum shippable increment:

1. Complete Phase 1: Setup (T001–T003).
2. Complete Phase 2: Foundational (T004–T012).
3. Complete Phase 3: US2 audit chain (T013–T022).
4. Complete Phase 4: US1 SBOM + vuln gating (T023–T034).
5. **STOP and VALIDATE**: release workflow gates on CVE severity; chain integrity verifiable; attestations exportable. Two enterprise-compliance P1 claims ship simultaneously.

### Incremental delivery

1. Phase 2 + US2 → foundational compliance primitive.
2. **+ US1 (SBOM + vuln gating)** → release supply-chain hygiene.
3. **+ US3 (rotation)** → operational credential hygiene.
4. **+ US4 (JIT)** → privilege-elevation hygiene.
5. **+ US5 (pentest tracking)** → pentest governance loop.
6. **+ US6 (compliance evidence)** → consolidated evidence export for SOC2 / ISO27001 / HIPAA / PCI-DSS.
7. Polish (T062–T066).

### Parallel team strategy (5 developers)

- **Dev A**: Phase 2 (all, T004–T012) → lead integrator for US2 completion.
- **Dev B**: US1 CI path (T031–T034) + SBOM service (T023, T026, T028) → release engineer.
- **Dev C**: US1 vuln scan service (T024, T029), US1 router (T030).
- **Dev D**: US3 rotation (T035–T043) → ownership of Vault integration.
- **Dev E**: US4 JIT (T044–T049) + US5 pentest (T050–T055).
- Dev A again on US6 (T056–T061) once US1–US5 land.
- All devs on Polish (T062–T066) concurrently.

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks in the same phase.
- [Story] label maps each task to its user story for traceability.
- **Tests are part of each user story's phase** per the constitution's 95% coverage gate.
- Every v1.3.0 constitution rule the plan flagged load-bearing has a corresponding task: rule 9 → T011 + T012 + T019–T022; rule 10 → T038 + T040; rule 33 → T029 + T040 + T047; rule 40 → T009; rule 44 → T040; AD-17 → T015; AD-18 → T008–T011.
- Migration 058 (T004) is the single largest task; budget 3–4 hours including the seed-data loading from YAML.
- `main.py` is edited by T018, T041, T042, T054 (APScheduler registration), T060 (Kafka consumer). Serialise these edits under one integration commit or use a shared `lifespan_registrations.py` helper.
- The feature implements constitution rules that are themselves load-bearing; the constitution amendment already happened (v1.3.0) and this feature makes them enforceable in code.
