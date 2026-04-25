# Tasks: Privacy Compliance (GDPR / CCPA)

**Input**: Design documents from `/specs/076-privacy-compliance/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Tests**: Required (CI coverage ≥ 95%); every contract lists named test IDs (DSR1–DSR9, CO1–CO9, DLP1–DLP9, RE1–RE8, PIA1–PIA8, consent CO1–CO9) that are generated as explicit tasks.

**Organization**: Tasks are grouped by user story. US1 (erasure + cascade + tombstone) is the MVP; US2 (consent) is P1 and ships alongside. US3–US6 are independent extensions on top of the shared foundation.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: User story label [US1]–[US6]

---

## Phase 1: Setup

**Purpose**: BC scaffolding and CI helper stubs.

- [X] T001 Create bounded-context directory `apps/control-plane/src/platform/privacy_compliance/` with `__init__.py`, empty `models.py`, `schemas.py`, `repository.py`, `events.py`, `router.py`, `router_self_service.py`, `exceptions.py`, plus `services/`, `cascade_adapters/`, `dlp/`, `workers/` sub-packages each with `__init__.py`.
- [X] T002 [P] Create `apps/control-plane/src/platform/privacy_compliance/cascade_adapters/base.py` with the `CascadeAdapter` ABC, `CascadePlan`, and `CascadeResult` dataclasses per `contracts/cascade-orchestrator.md`. Other adapters (T017–T022) subclass from here.
- [X] T003 [P] Create `ci/lint_privacy_cascade_coverage.py` stub at repo root (executable) that will grep for `ForeignKey("users.id")` across `apps/control-plane/src/platform/` and diff against the declared `USER_IDENTITY_COLUMNS` map in the PG adapter. Implementation lands in T057 (polish); this task creates the file with a `NotImplementedError` body.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Migration 060, config, events, models, repository, audit chain + Vault wiring, orchestrator skeleton.

**⚠️ CRITICAL**: No user story (Phase 3–8) can start until Phase 2 completes.

### 2A — Migration + role enum + ClickHouse extension

- [X] T004 Write Alembic migration `apps/control-plane/migrations/versions/060_privacy_compliance.py` creating all 7 tables per `data-model.md` §1: `privacy_dsr_requests`, `privacy_deletion_tombstones`, `privacy_residency_configs`, `privacy_dlp_rules`, `privacy_dlp_events`, `privacy_impact_assessments`, `privacy_consent_records`. Include the tombstones `BEFORE UPDATE OR DELETE` trigger, CHECK constraints (approved_by != submitted_by for PIA per rule 33), and `UNIQUE (user_id, consent_type)` on consent records. Seed ≥ 10 DLP patterns per `research.md` D-009 with `seeded=true`. Add `privacy_officer` to the `RoleType` enum. Include a `_alter_clickhouse_rollups_add_is_deleted()` function that uses `common/clients/clickhouse.py` to ALTER the PII-bearing analytics rollup tables adding `is_deleted UInt8 DEFAULT 0`.
- [X] T005 [P] Extend `apps/control-plane/src/platform/auth/schemas.py` `RoleType` StrEnum with `privacy_officer = "privacy_officer"`. Also seed permissions for the new role in a same-migration Alembic operation: privacy_officer can `read/write` on `dsr`, `pia`, `consent`, `dlp`, and `read` on `audit`, `tombstone`. Migration-referenced scope matches research.md D-015.

### 2B — Config + events + models

- [X] T006 [P] Extend `apps/control-plane/src/platform/common/config.py` with `PrivacyComplianceSettings` (fields: `dsr_enabled: bool = False`, `erasure_hold_hours_default: int = 0`, `erasure_hold_hours_max: int = 72`, `dlp_enabled: bool = False`, `residency_enforcement_enabled: bool = False`, `dlp_event_retention_days: int = 90`, `consent_propagator_interval_seconds: int = 60`, `salt_vault_path: str`, `clickhouse_pii_tables: list[str]`). Attach as `PlatformSettings.privacy_compliance`. `Field(description=...)` on every field (rule 37).
- [X] T007 [P] Register 5 new Kafka topics in `apps/control-plane/src/platform/privacy_compliance/events.py` (and derived `.rejected` / `.superseded` / `.scheduled_with_hold` / `.residency.configured` / `.residency.violated` / `.consent.revoked`) following the `auth/events.py:publish_auth_event` pattern. Typed Pydantic payloads + `publish_*_event` helpers + `event_registry.register(...)`.
- [X] T008 [P] Implement all 7 SQLAlchemy models in `apps/control-plane/src/platform/privacy_compliance/models.py` per `data-model.md` §1.1–§1.7 with all check/unique constraints + indexes.
- [X] T009 [P] Implement `apps/control-plane/src/platform/privacy_compliance/repository.py` with async query methods for each entity: DSR CRUD, tombstone CRUD (insert-only), residency CRUD, DLP rule + event CRUD, PIA CRUD with state transitions, consent record upsert + revoke + history.

### 2C — Vault salt provider + orchestrator skeleton

- [X] T010 Implement `apps/control-plane/src/platform/privacy_compliance/services/salt_history.py` `SaltHistoryProvider`: loads `secret/data/musematic/{env}/privacy/subject-hash-salt` from Vault (via UPD-040's `SecretProvider`, env-var fallback if UPD-040 not yet live); exposes `get_current_salt()`, `get_current_version()`, `get_salt(version)`. Handles the history array per `data-model.md` §5.
- [X] T011 Implement `apps/control-plane/src/platform/privacy_compliance/services/cascade_orchestrator.py` `CascadeOrchestrator` per `contracts/cascade-orchestrator.md`: constructor accepts a list of `CascadeAdapter` instances, sorts by `STORE_ORDER`, `run(dsr_id, subject_user_id, *, dry_run)` walks adapters with try/except per-store, builds tombstone, invokes signer. Depends on T002, T008, T009, T010.
- [X] T012 Register integration with UPD-024: `AuditChainService` + Ed25519 signer via DI from `app.state.clients`. Add a tiny `apps/control-plane/src/platform/privacy_compliance/services/tombstone_signer.py` that delegates signing to UPD-024's `AuditChainSigning.sign(...)` — single trust anchor (research.md D-006).

**Checkpoint**: Migration applied; models + repository + orchestrator skeleton in place; Vault salt provider wired; 5 Kafka topics registered.

---

## Phase 3: User Story 1 — Erasure + Cascade + Tombstone (Priority: P1) 🎯 MVP

**Goal**: Privacy officer opens erasure DSR; cascade runs across all 6 data stores; tombstone produced with SHA-256 `proof_hash`; signed attestation exportable; external verification succeeds.

**Independent Test**: Provision test subject with data across all 6 stores. Open erasure DSR. Verify: zero rows remain referencing subject, tombstone row exists with non-null `proof_hash`, DSR → `completed`, chain entry written, signed export verifies externally.

### Tests for User Story 1

- [X] T013 [P] [US1] Unit tests CO1–CO7 + DSR1–DSR9 in `apps/control-plane/tests/unit/privacy_compliance/test_cascade_orchestrator.py` per `contracts/cascade-orchestrator.md` + `contracts/dsr-handling.md`: orchestrator walks adapters in order, dry_run no mutation, partial failure, retry idempotent, `users` last, proof_hash matches canonical payload, subject_user_id_hash uses current salt, 6 DSR lifecycle scenarios.
- [X] T014 [P] [US1] Integration test `test_erasure_e2e.py` running against docker-compose with all 6 data stores: provisions subject data, runs erasure DSR, asserts zero residual rows, verifies tombstone + signed export.
- [X] T015 [P] [US1] CI coverage-check test `ci/tests/test_cascade_adapter_coverage.py`: diffs `USER_IDENTITY_COLUMNS` against `grep ForeignKey("users.id")` output; asserts no undeclared PII-bearing tables exist (CO9 from contracts/cascade-orchestrator.md).

### Implementation for User Story 1

- [X] T016 [P] [US1] Pydantic schemas in `apps/control-plane/src/platform/privacy_compliance/schemas.py` for DSR endpoints: `DSRCreateRequest`, `DSRResponse`, `DSRCancelRequest`, `SignedTombstoneResponse`, `CascadePlanResponse`.
- [X] T017 [P] [US1] Implement `cascade_adapters/postgresql_adapter.py` with the 38-table `USER_IDENTITY_COLUMNS` map per `contracts/cascade-orchestrator.md`. Executes DELETEs in a single transaction, ordered child-before-parent with `users` row last. Non-PK columns (e.g. `created_by`) are NULLified to a sentinel `DELETED_SUBJECT_UUID`; PK-bearing rows (credentials, memberships, etc.) are deleted.
- [X] T018 [P] [US1] Implement `cascade_adapters/qdrant_adapter.py` using `AsyncQdrantClient.delete(collection_name="*", points_selector=Filter(...))` with payload `user_id` match. Iterates all known collections (list from existing `common/clients/qdrant.py` helpers).
- [X] T019 [P] [US1] Implement `cascade_adapters/opensearch_adapter.py` using `AsyncOpenSearchClient.delete_by_query(index="*", body={"query":{"term":{"user_id":...}}})`.
- [X] T020 [P] [US1] Extend `apps/control-plane/src/platform/common/clients/object_storage.py` with `async def delete_objects_matching_prefix(bucket: str, prefix: str) -> int`. Then implement `cascade_adapters/s3_adapter.py` that iterates every configured bucket with `prefix=f"users/{subject_user_id}/"`.
- [X] T021 [P] [US1] Implement `cascade_adapters/clickhouse_adapter.py`: for each PII-bearing rollup table listed in `PrivacyComplianceSettings.clickhouse_pii_tables`, issues `ALTER TABLE {table} UPDATE is_deleted = 1 WHERE user_id = %(uid)s`. Emits a tombstone log entry per table.
- [X] T022 [P] [US1] Implement `cascade_adapters/neo4j_adapter.py`: uses the PostgreSQL fallback path (`graph_nodes`, `graph_edges` tables) — issues `DELETE FROM graph_edges WHERE source_node_id IN (SELECT id FROM graph_nodes WHERE owner_user_id = :uid) OR target_node_id IN (…); DELETE FROM graph_nodes WHERE owner_user_id = :uid;`. When the platform adopts a real Neo4j driver later, adapter signature stays the same.
- [X] T023 [US1] Add a ClickHouse tombstone-aware query-rewrite helper to `apps/control-plane/src/platform/common/clients/clickhouse.py`: wraps `execute_query` so queries against registered tables automatically get `AND NOT is_deleted` appended. The wrapper consults `PrivacyComplianceSettings.clickhouse_pii_tables`.
- [X] T024 [US1] Implement `DSRService` in `apps/control-plane/src/platform/privacy_compliance/services/dsr_service.py` with six handler methods (`_handle_access`, `_handle_rectification`, `_handle_erasure`, `_handle_portability`, `_handle_restriction`, `_handle_objection`). Erasure invokes `CascadeOrchestrator.run(...)`; others ship functional skeletons matching `contracts/dsr-handling.md`. Every state transition writes an audit chain entry (UPD-024) + emits the appropriate Kafka event.
- [X] T025 [US1] Implement admin DSR router in `apps/control-plane/src/platform/privacy_compliance/router.py` with endpoints per `contracts/dsr-handling.md` §Admin REST endpoints (POST, GET, GET/{id}, cancel, retry, tombstone, tombstone/signed, export). Every method gates on `privacy_officer` / `platform_admin` / `superadmin` (per role catalogue from T005). Tagged `['admin', 'privacy', 'dsr']`.
- [X] T026 [US1] Implement self-service DSR router in `apps/control-plane/src/platform/privacy_compliance/router_self_service.py` with `POST/GET /api/v1/me/dsr` endpoints per rule 46 (scoped to `current_user`, no `user_id` parameter).
- [X] T027 [US1] Implement `hold_window_releaser.py` worker in `apps/control-plane/src/platform/privacy_compliance/workers/`: APScheduler job (30s cadence) that transitions `status='scheduled' AND scheduled_release_at < now()` rows to `in_progress` and kicks off the cascade. Registered under `scheduler` runtime profile.
- [X] T028 [US1] Register both DSR routers + hold-window worker in `apps/control-plane/src/platform/main.py` alongside existing routers. Add `/api/v1/me/dsr` to auth middleware exempt path catalogue? No — it's authenticated — just route.

**Checkpoint**: US1 complete. Erasure + cascade + tombstone + signed export end-to-end. Rule 15, 16, AD-17 satisfied.

---

## Phase 4: User Story 2 — AI Disclosure + Consent (Priority: P1)

**Goal**: First-time conversation triggers HTTP 428 Precondition Required; user records three consent choices; revocation propagates to training + analytics within 5 minutes.

**Independent Test**: New user attempts conversation → 428. Records consents → conversation proceeds. Revokes `training_use` → `revoked_at` populated; worker propagates; subsequent training jobs exclude user.

### Tests for User Story 2

- [X] T029 [P] [US2] Unit tests (consent CO1–CO9) in `apps/control-plane/tests/unit/privacy_compliance/test_consent_service.py` per `contracts/consent-service.md`: 428 without consents, 428 with partial consents, revocation timestamps, propagator worker enqueues, snapshot isolation for training, admin history query, cross-user access rejected.
- [X] T030 [P] [US2] Integration test `test_consent_propagation.py`: revoke `training_use`; wait ≤ 60 s; assert user is in Redis `privacy:revoked_training_users`; simulate a training job composition and verify the user's messages are excluded.

### Implementation for User Story 2

- [X] T031 [P] [US2] Implement `ConsentService` in `apps/control-plane/src/platform/privacy_compliance/services/consent_service.py` per `contracts/consent-service.md` API: `get_state`, `require_or_prompt` (raises `ConsentRequired`), `record_consents`, `revoke`, `history`.
- [X] T032 [US2] Add consent endpoints to `router_self_service.py`: `GET/PUT /api/v1/me/consents`, `POST /api/v1/me/consents/{type}/revoke`, `GET /api/v1/me/consents/history`, `GET /api/v1/me/consents/disclosure`. Add admin query endpoint `GET /api/v1/privacy/consents?user_id=` to `router.py`.
- [X] T033 [US2] Extend `apps/control-plane/src/platform/interactions/service.py` `create_conversation` method (around line 123) with the consent pre-flight per `contracts/consent-service.md`: call `consent_service.require_or_prompt(user_id, workspace_id)`; catch `ConsentRequired` and raise `HTTPException(status_code=428, detail=...)` with the missing consent types + disclosure reference.
- [X] T034 [US2] Implement `consent_propagator.py` worker in `privacy_compliance/workers/`: APScheduler job (60 s cadence) that reads `privacy_consent_records WHERE revoked_at > (now() - '2 minutes')` and updates the `privacy:revoked_training_users` Redis set. Emits `privacy.consent.revoked` Kafka event.
- [X] T035 [US2] Extend `apps/control-plane/src/platform/composition/` training corpus composition path (exact file per composition BC's structure) to consult `privacy:revoked_training_users` Redis set and exclude those users' messages when composing training corpora. Honours the snapshot-isolation semantics from research.md D-014 (in-flight jobs that already snapshotted proceed).
- [X] T036 [US2] Extend analytics event-emission path in `apps/control-plane/src/platform/analytics/` (exact file TBD during implementation; grep for `analytics_event.emit` usages) to skip events for users with `data_collection=false` consent; uses the same Redis set pattern.

**Checkpoint**: US2 complete. First-interaction gate in place; consent revocation propagates to training + analytics.

---

## Phase 5: User Story 3 — PIA Workflow (Priority: P2)

**Goal**: Creator submits PIA; privacy officer reviews + approves/rejects; approval unblocks certification; material data-category change supersedes prior PIA.

**Independent Test**: Submit PIA for agent with `pii` data category; attempt cert → blocked; approve PIA; cert proceeds. Update agent's categories materially; prior PIA → superseded.

### Tests for User Story 3

- [X] T037 [P] [US3] Unit tests PIA1–PIA8 in `apps/control-plane/tests/unit/privacy_compliance/test_pia_service.py` per `contracts/pia-workflow.md`: submit draft, missing-field rejection, 2PA enforcement, approve, reject with feedback, cert blocked without PIA, cert proceeds with PIA, material-change supersede.

### Implementation for User Story 3

- [X] T038 [P] [US3] Implement `PIAService` in `apps/control-plane/src/platform/privacy_compliance/services/pia_service.py` per `contracts/pia-workflow.md` API. State machine enforcement in service layer (draft → under_review → approved/rejected; approved → superseded on material change).
- [X] T039 [US3] Add PIA endpoints to `router.py`: `POST /api/v1/privacy/pia`, `GET`, `GET/{id}`, `POST /{id}/submit`, `POST /{id}/approve`, `POST /{id}/reject`, `GET /subject/{type}/{id}/active`. Approver must differ from submitter (rule 33) — enforced server-side.
- [X] T040 [US3] Extend `apps/control-plane/src/platform/trust/services/certification_service.py` `request_certification` method: if agent's declared `data_categories` intersects `DATA_CATEGORIES_REQUIRING_PIA`, call `pia_service.get_approved_pia("agent", agent_id)` and raise `CertificationBlocked(reason="pia_required")` on None. Coordinate with feature 075's existing extension to this file.
- [X] T041 [US3] Extend `apps/control-plane/src/platform/registry/service.py` agent-update path: when declared `data_categories` set changes, call `pia_service.check_material_change("agent", agent_id, new_categories)` which supersedes any existing approved PIA for that agent, emits `privacy.pia.superseded`, and notifies the submitter.

**Checkpoint**: US3 complete. PIAs gate certification; material changes invalidate.

---

## Phase 6: User Story 4 — Data Residency Enforcement (Priority: P2)

**Goal**: Workspace admin sets region config; cross-region queries are rejected at query time with structured error; config changes propagate ≤ 60 s.

**Independent Test**: Set region=`eu-central-1` with no transfer allowlist. Query from `us-east-1` → 403 residency_violation. Query from `eu-central-1` → success. Add `eu-west-1` to allowlist → query from `eu-west-1` succeeds.

### Tests for User Story 4

- [X] T042 [P] [US4] Unit tests RE1–RE8 in `apps/control-plane/tests/unit/privacy_compliance/test_residency_service.py` per `contracts/residency-enforcer.md`.

### Implementation for User Story 4

- [X] T043 [P] [US4] Implement `ResidencyService` in `apps/control-plane/src/platform/privacy_compliance/services/residency_service.py` per contract: CRUD + `get_cached` (60 s Redis cache) + in-process LRU.
- [X] T044 [US4] Extend `apps/control-plane/src/platform/policies/gateway.py` visibility resolution (around lines 45–68) with the residency gate per `contracts/residency-enforcer.md` §Enforcement point. Raises `ResidencyViolation` (new exception) → HTTP 403 with structured payload. Emits audit chain entry + `privacy.residency.violated` Kafka event on violation.
- [X] T045 [US4] Add residency endpoints to `router.py`: `GET /api/v1/privacy/residency/{ws_id}`, `PUT`, `DELETE`. DELETE requires `superadmin` + 2PA (residency removal is significant). Every change emits `privacy.residency.configured`/`.removed` Kafka event + audit chain entry.
- [X] T046 [US4] Derive `origin_region` in the request context: extract `X-Origin-Region` header in auth_middleware (or a new middleware), fall back to JWT `region_hint` claim, then `"unknown"`. Attach to `request.state.origin_region` for downstream consumers.

**Checkpoint**: US4 complete. Residency enforced at query time; config changes propagate in under a minute.

---

## Phase 7: User Story 5 — DLP Scanning (Priority: P2)

**Goal**: DLP rules scan tool outputs + agent outputs with actions (redact/block/flag); events recorded with classification-label summary only; seeded patterns cover common PII/financial/confidential categories.

**Independent Test**: Create workspace-scoped rule matching "Project Alpha" with action `block`. Drive agent execution producing a tool output with the match. Verify 403 / blocked; DLP event persisted with `match_summary="confidential:internal_project_alpha"` (label only).

### Tests for User Story 5

- [X] T047 [P] [US5] Unit tests DLP1–DLP9 in `apps/control-plane/tests/unit/privacy_compliance/test_dlp_pipeline.py` per `contracts/dlp-pipeline.md`: seeded SSN pattern redacts, credit card Luhn validation, block raises, flag records only, workspace-scoped augments platform, seeded rule deletion 403, `match_summary` never contains raw text, integration with gateway, integration with guardrail pipeline.

### Implementation for User Story 5

- [X] T048 [P] [US5] Implement `DLPScanner` in `apps/control-plane/src/platform/privacy_compliance/dlp/scanner.py` per `contracts/dlp-pipeline.md`: regex-compiled rule cache (60 s TTL), `scan(text, workspace_id) -> list[DLPMatch]`, `apply_actions(text, matches) -> DLPScanResult`. Rules loaded from `privacy_dlp_rules` filtered by workspace + `enabled=true`.
- [X] T049 [P] [US5] Implement `DLPService` in `apps/control-plane/src/platform/privacy_compliance/services/dlp_service.py`: `scan_and_apply(text, workspace_id)` wraps scanner, `emit_event(match, execution_id)` persists + publishes `privacy.dlp.event` Kafka event. CRUD on rules with seeded-rule delete rejection.
- [X] T050 [US5] Extend `apps/control-plane/src/platform/policies/gateway.py` `ToolGatewayService.sanitize_tool_output()` (around lines 187–206) with the DLP insertion per `contracts/dlp-pipeline.md` §Point 1. On `block` action → raise `ToolOutputBlocked`.
- [X] T051 [US5] Extend `apps/control-plane/src/platform/trust/guardrail_pipeline.py` `GuardrailLayer` StrEnum with `dlp_scan = "dlp_scan"`; insert into `LAYER_ORDER` after `output_moderation` per `contracts/dlp-pipeline.md` §Point 2. The layer calls `dlp_service.scan_and_apply(...)`.
- [X] T052 [US5] Add DLP admin endpoints to `router.py`: `GET/POST/PATCH/DELETE /api/v1/privacy/dlp/rules` (seeded rules reject delete), `GET /api/v1/privacy/dlp/events`, `GET /api/v1/privacy/dlp/events/aggregate`.
- [X] T053 [US5] Implement `dlp_event_aggregator.py` worker in `workers/` (APScheduler daily): aggregates DLP event counts into ClickHouse via analytics BC's interface; purges full-fidelity events older than 90 days.

**Checkpoint**: US5 complete. DLP scans outputs at two pipeline points; events logged with classification-only summaries.

---

## Phase 8: User Story 6 — External Tombstone Verification (Priority: P3)

**Goal**: External assessor can verify a signed tombstone independently using only the public key + documented canonicalisation rules.

**Independent Test**: Run erasure (via US1). Fetch signed tombstone. On external client: (a) recompute SHA-256 of canonical payload → matches `proof_hash`; (b) verify Ed25519 signature with public key → valid.

### Tests for User Story 6

- [X] T054 [P] [US6] Integration test `test_signed_tombstone_external_verify.py` in `apps/control-plane/tests/integration/privacy_compliance/`: runs erasure, fetches signed tombstone, re-implements canonicalisation from scratch (not using platform helpers), re-verifies hash + Ed25519 signature. Fails the build if either check is wrong — catches canonicalisation drift.

### Implementation for User Story 6

- [X] T055 [US6] Ship `tests/e2e/scripts/verify_signed_tombstone.py` as a standalone script (no platform imports) demonstrating external verification. Uses only `cryptography` + `json` + `hashlib` stdlib. Referenced by the quickstart Q6 walkthrough.
- [X] T056 [US6] Document canonicalisation rules in `apps/control-plane/src/platform/privacy_compliance/services/cascade_orchestrator.py` module docstring: JSON with `sort_keys=True, separators=(",", ":")`; field list; subject_hash construction; salt-version tracking. Any future change to canonicalisation requires a new `tombstone_version` field and backward-compat support for the prior version.

**Checkpoint**: US6 complete. Signed tombstones are self-contained compliance attestations, verifiable without platform access.

---

## Phase 9: Polish & Cross-Cutting Concerns

- [X] T057 Implement `ci/lint_privacy_cascade_coverage.py` (replaces the T003 stub): greps Python source for `ForeignKey("users.id")` references, parses the table class name, diffs against the declared `USER_IDENTITY_COLUMNS` in `cascade_adapters/postgresql_adapter.py`. Exits non-zero on drift. Add as a CI gate in `.github/workflows/ci.yml`.
- [X] T058 [P] Chaos test `apps/control-plane/tests/integration/privacy_compliance/test_cascade_chaos.py`: for each of the 6 adapters, inject a runtime failure (connection refused, timeout, auth error) and assert: DSR → `failed`, cascade_log captures the specific failure, retry after fix succeeds idempotently.
- [X] T059 [P] Update feature-catalogue page `docs/features/076-privacy-compliance.md` (generated on the docs branch): replace seven `TODO(andrea)` placeholders with grounded content.
- [X] T060 [P] Update `docs/administration/audit-and-compliance.md` to reference the new DSR / tombstone / PIA / DLP / residency / consent endpoints and the cross-audit-chain linkage.
- [X] T061 Run the six quickstart walkthroughs (Q1–Q6 in `quickstart.md`) against a local `make dev-up` cluster; fix any divergence.

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: no deps.
- **Foundational (Phase 2)**: depends on Phase 1 — **BLOCKS all user stories**.
- **US1 (Phase 3)**: depends on Phase 2. MVP.
- **US2 (Phase 4)**: depends on Phase 2. Independent of US1.
- **US3 (Phase 5)**: depends on Phase 2. Independent of US1/US2/US4/US5/US6.
- **US4 (Phase 6)**: depends on Phase 2. Independent.
- **US5 (Phase 7)**: depends on Phase 2. Independent.
- **US6 (Phase 8)**: depends on US1 (signed tombstone export in T025).
- **Polish (Phase 9)**: depends on US1–US6.

### Within Phase 2

- T004 (migration) can start with T005 in parallel.
- T006–T009 all `[P]` (different files).
- T010–T012 sequential (salt provider → orchestrator skeleton → signer wiring).

### Within US1

- Tests T013–T015 parallel with implementation.
- T016 (schemas) parallel with cascade-adapter tasks.
- T017–T022 all `[P]` (each in its own adapter file).
- T023 depends on T006 (config for `clickhouse_pii_tables`).
- T024 depends on T011 + cascade adapters.
- T025, T026 serialise (same router module — or could split to two files as planned).
- T027, T028 sequential.

### Parallel execution opportunities

```bash
# Phase 1 — 3 parallel:
Task: "BC scaffold (T001)"
Task: "CascadeAdapter ABC (T002)"
Task: "CI script stub (T003)"

# Phase 2 — 5 parallel after T004:
Task: "Migration 060 (T004)"
Task: "privacy_officer role enum (T005)"
Task: "PrivacyComplianceSettings (T006)"
Task: "Kafka topics (T007)"
Task: "SQLAlchemy models (T008)"
Task: "Repository (T009)"
# T010–T012 sequential

# Phase 3 US1 — heavy parallel:
Task: "Unit tests CO/DSR (T013)"
Task: "Integration test (T014)"
Task: "CI coverage test (T015)"
Task: "Schemas (T016)"
Task: "PG adapter (T017)"
Task: "Qdrant adapter (T018)"
Task: "OpenSearch adapter (T019)"
Task: "S3 adapter + helper (T020)"
Task: "ClickHouse adapter (T021)"
Task: "Neo4j adapter (T022)"
# T023–T028 sequential

# Phase 4 US2:
Task: "Consent unit tests (T029)"
Task: "Propagation integration test (T030)"
Task: "ConsentService (T031)"
# T032–T036 sequential

# Phase 5-7 (US3, US4, US5): all three phases can run in parallel once Phase 2 + US1 land (different services, different files).

# Polish — 3 parallel:
Task: "Feature catalogue doc (T059)"
Task: "Admin docs update (T060)"
Task: "Chaos test (T058)"
# T057 (CI script impl) + T061 (quickstart smoke) sequential
```

---

## Implementation Strategy

### MVP scope (US1 only)

1. Complete Phase 1 (T001–T003).
2. Complete Phase 2 (T004–T012).
3. Complete US1 (T013–T028).
4. **STOP and VALIDATE**: Erasure DSR runs end-to-end; tombstone produced with valid proof_hash; signed export externally verifiable. GDPR Article 17 + CCPA §1798.105 compliance story shippable.

### Incremental delivery

1. US1 → erasure + cascade + tombstone.
2. **+ US2** → AI disclosure + consent; first-interaction gate.
3. **+ US3** → PIA workflow + cert gating.
4. **+ US4** → residency enforcement.
5. **+ US5** → DLP scanning.
6. **+ US6** → external verification script + docs.
7. Polish (T057–T061).

### Parallel team strategy (3 developers, over 2.5 days)

- **Dev A**: Phase 2 + US1 (T001–T028) — lead integrator; owns cascade orchestrator.
- **Dev B**: US2 + US3 (T029–T041) — consent + PIA.
- **Dev C**: US4 + US5 + US6 (T042–T056) — residency + DLP + verify-script.
- All devs on Polish (T057–T061).

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks.
- [Story] label maps each task to its user story for traceability.
- **Tests are part of each user story's phase** per the constitution's 95% coverage gate.
- Every v1.3.0 constitution rule flagged load-bearing has a corresponding task:
  - Rule 9 (audit chain entries) → T024 + T044 + PIA transitions in T038 + consent transitions in T031
  - Rule 15 (cascade deletion) → T011 + T017–T022
  - Rule 16 (DSR tombstones) → T011 + T024
  - Rule 18 (residency at query time) → T044
  - Rule 33 (2PA) → T039 (PIA approver ≠ submitter) + T025 (DSR cancel 2PA)
  - AD-17 (tombstone RTBF proof) → T010 (subject hash with salt) + T011 (tombstone never contains PII)
- **Principle IV exception** (cross-BC PG adapter) is explicitly owned by `privacy_compliance/`; no target BC queries across.
- Migration 060 (T004) is the single largest task; budget 4–5 hours including ClickHouse alters + DLP seed + role enum extension.
- `main.py` is edited by T028 (routers), T027 (worker), T034 (worker), T053 (worker), T046 (middleware). Serialise these edits under one developer or use a shared lifespan-registrations module.
- **UPD-024 dependency** is load-bearing: audit chain entries (every state transition) and Ed25519 signing of tombstones. If UPD-024 is not yet live, env-var fallbacks are acceptable per UPD-024's transitional design.
- **UPD-040 dependency** for the Vault subject-hash salt; env-var fallback accepted during rollout.
