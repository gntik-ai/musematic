# Tasks: Trust, Certification, and Guardrails

**Input**: Design documents from `specs/032-trust-certification-guardrails/`  
**Feature**: 032-trust-certification-guardrails  
**Branch**: `032-trust-certification-guardrails`

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US7)
- Exact file paths included in every task description

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create all trust/ module files and shared exception/DI scaffolding.

- [x] T001 Create `apps/control-plane/src/platform/trust/` directory with all empty module stubs: `__init__.py`, `models.py`, `schemas.py`, `repository.py`, `service.py`, `guardrail_pipeline.py`, `prescreener.py`, `trust_tier.py`, `recertification.py`, `circuit_breaker.py`, `oje_pipeline.py`, `ate_service.py`, `privacy_assessment.py`, `router.py`, `events.py`, `exceptions.py`, `dependencies.py`; create `apps/control-plane/src/platform/trust/lua/` subdirectory
- [x] T002 [P] Implement `apps/control-plane/src/platform/trust/exceptions.py` — `TrustError` base class, `CertificationNotFoundError`, `CertificationStateError`, `InvalidStateTransitionError`, `GuardrailBlockedError`, `CircuitBreakerTrippedError`, `ATERunError`, `OJEConfigError`, `PreScreenerError` — all inherit from `PlatformError` per common/exceptions.py conventions
- [x] T003 [P] Implement `apps/control-plane/src/platform/trust/dependencies.py` — FastAPI DI providers: `get_certification_service`, `get_guardrail_pipeline_service`, `get_prescreener_service`, `get_oje_service`, `get_recertification_service`, `get_circuit_breaker_service`, `get_ate_service`, `get_trust_tier_service`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: All 12 SQLAlchemy models, Pydantic schemas, repository layer, Kafka event types, and Alembic migration 032.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T004 Implement `apps/control-plane/src/platform/trust/models.py` — all 12 SQLAlchemy models per data-model.md: `TrustCertification`, `TrustCertificationEvidenceRef`, `TrustTier`, `TrustSignal`, `TrustProofLink`, `TrustRecertificationTrigger`, `TrustBlockedActionRecord`, `TrustATEConfiguration`, `TrustGuardrailPipelineConfig`, `TrustOJEPipelineConfig`, `TrustCircuitBreakerConfig`, `TrustSafetyPreScreenerRuleSet`; all enums (`CertificationStatus`, `EvidenceType`, `TrustTierName`, `RecertificationTriggerType`, `RecertificationTriggerStatus`, `GuardrailLayer`, `OJEVerdictType`); all indexes and unique constraints per data-model.md
- [x] T005 [P] Implement `apps/control-plane/src/platform/trust/schemas.py` — all Pydantic v2 schemas per data-model.md: `CertificationCreate`, `CertificationRevoke`, `CertificationResponse`, `EvidenceRefCreate`, `EvidenceRefResponse`, `TrustTierResponse`, `GuardrailEvaluationRequest`, `GuardrailEvaluationResponse`, `BlockedActionResponse`, `BlockedActionsListResponse`, `PreScreenRequest`, `PreScreenResponse`, `RecertificationTriggerResponse`, `ATEConfigCreate`, `ATERunRequest`, `ATERunResponse`, `OJEPipelineConfigCreate`, `OJEPipelineConfigResponse`, `JudgeVerdictEvent`, `CircuitBreakerConfigCreate`, `CircuitBreakerStatusResponse`, `PreScreenerRuleSetCreate`, `PreScreenerRuleSetResponse`, `PrivacyAssessmentRequest`, `PrivacyAssessmentResponse`
- [x] T006 Implement `apps/control-plane/src/platform/trust/repository.py` — async SQLAlchemy query methods for all 12 models: CRUD operations per model; bulk queries (list_certifications_for_agent, list_blocked_actions_paginated, list_trust_signals_for_agent); upsert_trust_tier; get_active_prescreener_rule_set; get_guardrail_config(workspace_id, fleet_id); get_oje_config(workspace_id, fleet_id)
- [x] T007 [P] Implement `apps/control-plane/src/platform/trust/events.py` — Kafka event type string constants for all 10 trust event types; `TrustEventPublisher` class wrapping `EventPublisher` from `common/events/producer.py` with typed publish methods per event type (publish_certification_created, publish_certification_activated, publish_guardrail_blocked, publish_circuit_breaker_activated, etc.)
- [x] T008 Create `apps/control-plane/migrations/versions/032_trust_certifications.py` — Alembic migration creating all 12 tables in dependency order: trust_certifications → trust_certification_evidence_refs → trust_tiers → trust_signals → trust_proof_links → trust_recertification_triggers → trust_blocked_action_records → trust_ate_configurations → trust_guardrail_pipeline_configs → trust_oje_pipeline_configs → trust_circuit_breaker_configs → trust_prescreener_rule_sets; all indexes, unique constraints, and foreign keys per data-model.md

**Checkpoint**: Foundation ready — user story implementation can begin.

---

## Phase 3: User Story 1 — Certification Lifecycle (Priority: P1) 🎯 MVP

**Goal**: Full certification state machine with evidence binding, audit trail, supersession, and automatic expiry.

**Independent Test**: `POST /trust/certifications` → add evidence → `POST /certifications/{id}/activate` verifies pending→active transition; second activation supersedes first cert; `POST /certifications/{id}/revoke` verifies revocation with reason; APScheduler expire_stale transitions expired certs automatically.

- [x] T009 [P] [US1] Implement `CertificationService` in `apps/control-plane/src/platform/trust/service.py` — `create` (initial PENDING state, publishes `certification.created`); `get` (raises CertificationNotFoundError); `list_for_agent`; `activate` (validates PENDING→ACTIVE transition, finds and supersedes any existing ACTIVE cert for same agent, publishes `certification.activated` + `certification.superseded`); `revoke` (validates ACTIVE→REVOKED, stores reason, publishes `certification.revoked`); `add_evidence` (creates CertificationEvidenceRef linked to cert); `expire_stale` (SELECT certs with expires_at < now() and status=ACTIVE, batch-transition to EXPIRED, publish `certification.expired` per cert)
- [x] T010 [P] [US1] Implement `TrustTierService` stub in `apps/control-plane/src/platform/trust/trust_tier.py` — `get_tier(agent_id)` (returns existing TrustTier or creates untrusted default with score=0); `upsert_tier(agent_id, tier, score, components)` (write to trust_tiers table) — full weighted score computation added in Phase 9 (US7)
- [x] T011 [US1] Add certification and trust tier REST endpoints to `apps/control-plane/src/platform/trust/router.py`: `POST /certifications` (require trust_certifier role); `GET /certifications/{id}`; `GET /agents/{agent_id}/certifications`; `POST /certifications/{id}/activate` (trust_certifier); `POST /certifications/{id}/revoke` (trust_certifier); `POST /certifications/{id}/evidence` (trust_certifier); `GET /agents/{agent_id}/tier`; `GET /agents/{agent_id}/signals` (paginated)
- [x] T012 [US1] Register `expire_stale` APScheduler hourly job in `apps/control-plane/entrypoints/api_main.py` under the `trust-certifier` runtime profile conditional block (check `RUNTIME_PROFILE == "trust-certifier"`)

**Checkpoint**: US1 complete — create, activate, revoke, add evidence, and auto-expire certifications are all functional.

---

## Phase 4: User Story 2 — Layered Guardrail Pipeline (Priority: P1)

**Goal**: Synchronous 6-layer guardrail pipeline executing in order with fail-closed behavior and durable blocked action records.

**Independent Test**: `POST /trust/guardrails/evaluate` with layer=`prompt_injection` and known injection string → `allowed: false`, `BlockedActionRecord` created in DB, `guardrail.blocked` event on Kafka; mock one layer to raise exception → still returns `allowed: false` (fail-closed).

- [x] T013 [P] [US2] Implement `GuardrailPipelineService` in `apps/control-plane/src/platform/trust/guardrail_pipeline.py` — `evaluate_full_pipeline(request)`: calls layers in order; short-circuits on first block; Layer 1 `_layer_input_sanitization`: compile-time regex scan for forbidden patterns; Layer 2 `_layer_prompt_injection`: pattern matching for injection signatures (ignore/bypass/jailbreak patterns); Layer 3 `_layer_output_moderation`: regex stage + optional `httpx` async LLM moderation call if `OUTPUT_MODERATION_URL` configured; Layer 4 `_layer_tool_control`: await `policy_engine.evaluate_tool_access(agent_id, tool_id, workspace_id)` via injected PolicyGovernanceEngine interface; Layer 5 `_layer_memory_write`: await `policy_engine.evaluate_memory_write(agent_id, namespace, workspace_id)`; Layer 6 `_layer_action_commit`: configurable per workspace GuardrailPipelineConfig; fail-closed wrapper: each layer in `try/except Exception` — on exception, block with `policy_basis="guardrail_layer_unavailable:{layer_name}"`; `record_blocked_action`: SHA-256 hash of full payload + store first 500 chars preview in PostgreSQL; publish `guardrail.blocked` event post-commit
- [x] T014 [P] [US2] Add `GuardrailPipelineConfig` CRUD to `apps/control-plane/src/platform/trust/repository.py` (get_guardrail_config, upsert_guardrail_config) and add `GuardrailPipelineConfigService` methods to `apps/control-plane/src/platform/trust/service.py` (get_config, update_config)
- [x] T015 [US2] Add guardrail pipeline endpoints to `apps/control-plane/src/platform/trust/router.py`: `POST /guardrails/evaluate` (service account only); `GET /guardrails/blocked-actions` (paginated, filterable by agent_id, layer, date range); `GET /guardrails/blocked-actions/{id}`; `GET /guardrails/config` (workspace + optional fleet_id query params); `PUT /guardrails/config` (workspace_admin or platform_admin)

**Checkpoint**: US2 complete — all 6 guardrail layers enforce synchronously; blocked actions are audited.

---

## Phase 5: User Story 3 — Safety Pre-Screening (Priority: P2)

**Goal**: In-process rule-based pre-screener (<10ms), Redis hot-cache, versioned rules, hot-reload without platform restart.

**Independent Test**: `POST /trust/prescreener/screen` with known jailbreak phrase → `blocked: true`, elapsed <10ms; upload new rule set, activate it, wait ≤60s, screen new pattern → blocked (Kafka hot-reload verified).

- [x] T016 [P] [US3] Implement `SafetyPreScreenerService` in `apps/control-plane/src/platform/trust/prescreener.py` — in-process `_compiled_patterns: dict[str, re.Pattern]` cache; `screen(content, context_type)`: iterate compiled patterns, first match → `PreScreenResponse(blocked=True, matched_rule=name, passed_to_full_pipeline=False)`; no match → `PreScreenResponse(blocked=False, passed_to_full_pipeline=True)`; `load_active_rules()`: GET `trust:prescreener:active_version` from Redis → if set, fetch rules JSON from MinIO `trust-evidence/prescreener/{version}/rules.json` → compile each pattern → store in `_compiled_patterns`; `activate_rule_set(rule_set_id)`: validate rule set exists, serialize rules JSON → upload to MinIO, update `is_active=True` in PostgreSQL (and `is_active=False` for previous active), SET `trust:prescreener:active_version` in Redis, publish `prescreener.rule_set.activated` Kafka event
- [x] T017 [P] [US3] Add `SafetyPreScreenerRuleSet` CRUD to `apps/control-plane/src/platform/trust/repository.py` (list_rule_sets, get_rule_set, get_active_rule_set, create_rule_set, set_active_rule_set) and expose from `apps/control-plane/src/platform/trust/service.py`
- [x] T018 [US3] Add pre-screener endpoints to `apps/control-plane/src/platform/trust/router.py`: `POST /prescreener/screen` (service account); `GET /prescreener/rule-sets` (platform_admin); `POST /prescreener/rule-sets` (platform_admin, accepts `PreScreenerRuleSetCreate`, uploads to MinIO, creates DB record); `POST /prescreener/rule-sets/{id}/activate` (platform_admin)
- [x] T019 [US3] Register `prescreener.rule_set.activated` Kafka consumer in `apps/control-plane/entrypoints/worker_main.py` (consumer calls `prescreener_service.load_active_rules()` on each event); add startup lifespan hook in API startup to call `prescreener_service.load_active_rules()` on boot in `apps/control-plane/src/platform/main.py`

**Checkpoint**: US3 complete — pre-screener blocks obvious violations in <10ms and hot-reloads rules within 60s.

---

## Phase 6: User Story 4 — Observer-Judge-Enforcer Pipeline (Priority: P2)

**Goal**: Configurable OJE pipeline per workspace/fleet; observer signals → judge verdicts → enforcer actions (quarantine, escalate, warn) with full audit trail.

**Independent Test**: Configure OJE pipeline, simulate VIOLATION verdict → mock `RuntimeControllerClient.stop_runtime` called; simulate ESCALATE_TO_HUMAN → `interaction.attention` Kafka event published; verdict stored in trust_signals + trust_proof_links.

- [x] T020 [P] [US4] Implement `OJEPipelineService` in `apps/control-plane/src/platform/trust/oje_pipeline.py` — `configure_pipeline(data)`: validate all observer/judge/enforcer FQNs exist via registry service interface; save `TrustOJEPipelineConfig`; `get_pipeline_config(workspace_id, fleet_id)`; `process_observation(signal, config_id)`: load judge agent FQNs from config, invoke judge via interactions service internal interface with `trust_pipeline_context=True` flag, parse response JSON as `JudgeVerdictEvent`; `execute_enforcement(verdict)`: VIOLATION → `await runtime_controller_client.stop_runtime(runtime_id, reason=verdict.reasoning)`; ESCALATE_TO_HUMAN → publish to `interaction.attention` Kafka topic per §XIII; WARNING → publish warning event to `trust.events`; COMPLIANT → log only; store all verdicts as `TrustSignal` + `TrustProofLink` records regardless of type
- [x] T021 [P] [US4] Add `TrustOJEPipelineConfig` CRUD to `apps/control-plane/src/platform/trust/repository.py` (create_oje_config, get_oje_config, list_oje_configs, deactivate_oje_config) and expose from service layer
- [x] T022 [US4] Add OJE pipeline endpoints to `apps/control-plane/src/platform/trust/router.py`: `GET /oje-configs` (workspace_admin, filter by workspace_id + fleet_id); `POST /oje-configs` (workspace_admin or platform_admin); `GET /oje-configs/{id}`; `DELETE /oje-configs/{id}` (deactivate, workspace_admin or platform_admin)

**Checkpoint**: US4 complete — OJE pipeline is configurable per workspace/fleet and enforces verdicts with audit trail.

---

## Phase 7: User Story 5 — Recertification Triggers (Priority: P2)

**Goal**: Automatic recertification triggers on revision change, policy update, expiry approach, and conformance failure; deduplication prevents duplicate workflows.

**Independent Test**: Publish mock `agent_revision.published` Kafka event → one `RecertificationTrigger` created + new pending Certification; publish same event again within window → second trigger is silently deduplicated (ON CONFLICT DO NOTHING).

- [x] T023 [P] [US5] Implement `RecertificationService` in `apps/control-plane/src/platform/trust/recertification.py` — `create_trigger(agent_id, revision_id, trigger_type, originating_event)`: INSERT with PostgreSQL unique constraint deduplication (ON CONFLICT DO NOTHING on pending trigger); if row inserted: create new pending `TrustCertification` linked to trigger, publish `recertification.triggered` event; `handle_revision_published(event)`: extract agent_id, revision_id from `registry.events` payload, call `create_trigger(type=REVISION_CHANGED)`; `handle_policy_updated(event)`: query agents with this policy_id attached (via registry service interface), for each agent call `create_trigger(type=POLICY_CHANGED)`; `scan_expiry_approaching(threshold_days)`: query `trust_certifications` where `expires_at < now() + threshold` and status=ACTIVE, call `create_trigger(type=EXPIRY_APPROACHING)` for each; `mark_conformance_failed(agent_id, revision_id, execution_id)`: call `create_trigger(type=CONFORMANCE_FAILED, originating_event_id=execution_id)`
- [x] T024 [P] [US5] Add `TrustRecertificationTrigger` CRUD to `apps/control-plane/src/platform/trust/repository.py` (create_trigger with upsert deduplication, get_trigger, list_triggers_for_agent, mark_trigger_processed)
- [x] T025 [US5] Add recertification trigger read endpoints to `apps/control-plane/src/platform/trust/router.py`: `GET /recertification-triggers` (trust_certifier/platform_admin, query param agent_id, paginated); `GET /recertification-triggers/{id}`
- [x] T026 [US5] Register `registry.events` (event_type `agent_revision.published`) and `policy.events` (event_type `policy.updated`) Kafka consumers in `apps/control-plane/entrypoints/worker_main.py`; register `scan_expiry_approaching(threshold_days=30)` APScheduler daily job in `apps/control-plane/entrypoints/api_main.py` under trust-certifier profile

**Checkpoint**: US5 complete — recertification triggers fire automatically and are deduplicated.

---

## Phase 8: User Story 6 — Accredited Testing Environments (Priority: P3)

**Goal**: Workspace-scoped versioned ATE configs; ATE runs via SimulationControlService gRPC; structured evidence linked to certifications; timeout handling.

**Independent Test**: Create ATE config, `POST /trust/ate/runs` with certification_id → mock SimulationControlService.CreateSimulation called; simulate `simulation.completed` Kafka event → CertificationEvidenceRef entries created, evidence linked to cert; timeout mock → partial results with "timed_out" status.

- [x] T027 [P] [US6] Implement `ATEService` in `apps/control-plane/src/platform/trust/ate_service.py` — `create_config(workspace_id, data)`: validate, store `TrustATEConfiguration`, upload optional golden_dataset to MinIO `trust-evidence/ate-configs/{id}/golden_dataset`; `run(request)`: load ATEConfiguration, call `await simulation_controller_client.create_simulation(config=ate_config_payload)`, store `simulation_id → {certification_id, ate_config_id, started_at}` mapping in Redis key `trust:ate:run:{simulation_id}` with TTL=`timeout_seconds + 300`; return `ATERunResponse`; `handle_simulation_completed(event)`: retrieve cert mapping from Redis by `simulation_id`, parse `result_payload` (list of scenario results), create one `TrustCertificationEvidenceRef` per scenario result with `evidence_type=ATE_RESULTS`, write full result JSON to MinIO `trust-evidence/ate-results/{simulation_id}/result.json`, publish `certification.evidence_added` sub-event; `scan_timed_out_runs()`: APScheduler job — scan Redis for ATE run keys older than timeout, mark evidence as `summary="timed_out"` with partial results
- [x] T028 [P] [US6] Add `TrustATEConfiguration` CRUD to `apps/control-plane/src/platform/trust/repository.py` (create_ate_config, get_ate_config, list_ate_configs_for_workspace, list_ate_config_versions) and expose from service
- [x] T029 [US6] Add ATE endpoints to `apps/control-plane/src/platform/trust/router.py`: `GET /ate/configs` (workspace member, filter by workspace_id); `POST /ate/configs` (workspace_admin or platform_admin); `GET /ate/configs/{id}`; `POST /ate/runs` (trust_certifier, body: ATERunRequest); `GET /ate/runs/{simulation_id}` (trust_certifier — returns status from Redis + evidence refs if completed)
- [x] T030 [US6] Register `simulation.events` Kafka consumer filtering `event_type == "simulation.completed"` in `apps/control-plane/entrypoints/worker_main.py`; register `scan_timed_out_runs` APScheduler job (every 5 minutes) in `apps/control-plane/entrypoints/api_main.py` under trust-certifier profile

**Checkpoint**: US6 complete — ATE runs produce structured evidence automatically linked to certifications.

---

## Phase 9: User Story 7 — Circuit Breaker and Trust Signals (Priority: P3)

**Goal**: Redis sliding-window circuit breaker (Lua EVALSHA); weighted trust score computation; Kafka-driven tier updates; marketplace visibility.

**Independent Test**: Simulate 5 `workflow.runtime` failure events → circuit breaker trips (Redis tripped flag set, `circuit_breaker.activated` event); trust score recomputed after `certification.activated` event within 30s; `GET /agents/{id}/tier` shows updated score and tier.

- [x] T031 [P] [US7] Create `apps/control-plane/src/platform/trust/lua/circuit_breaker_check.lua` — Lua script taking args `{agent_id_key, tripped_key, threshold, window_seconds, tripped_ttl}`: `ZADD key timestamp timestamp_as_member`; `ZREMRANGEBYSCORE key 0 (now - window_seconds)`; `local count = ZCARD key`; `if count >= threshold then SETEX tripped_key tripped_ttl "1" end`; `return {count, count >= threshold and 1 or 0}` — script loaded via `SCRIPT LOAD` on startup, EVALSHA on each failure
- [x] T032 [P] [US7] Implement `CircuitBreakerService` in `apps/control-plane/src/platform/trust/circuit_breaker.py` — on startup: `SCRIPT LOAD` lua script → store SHA; `record_failure(agent_id, workspace_id)`: EVALSHA with `trust:cb:{agent_id}` sorted set key + `trust:cb:tripped:{agent_id}` flag key; if tripped: publish `circuit_breaker.activated` event on `trust.events`, publish to `interaction.attention` topic with urgency=HIGH, call `runtime_controller_client.pause_workflow(execution_id, reason)` if execution_id available; `is_tripped(agent_id)`: GET `trust:cb:tripped:{agent_id}` → return bool; `reset(agent_id)`: DEL both Redis keys; add `CircuitBreakerConfig` CRUD to service + repository
- [x] T033 [P] [US7] Implement full `TrustTierService.recompute(agent_id)` in `apps/control-plane/src/platform/trust/trust_tier.py` — fetch data: (1) latest certification status for agent from PostgreSQL; (2) guardrail pass rate = 1 - (blocked_actions_last_30d / max(total_guardrail_evaluations, 1)); (3) behavioral_component = avg score_contribution from trust_signals of type `behavioral_conformance` last 30 days; apply weighted formula: `score = cert_component * 0.50 + guardrail_component * 0.35 + behavioral_component * 0.15`; map to tier: ≥0.80 → CERTIFIED, ≥0.50 → PROVISIONAL, else UNTRUSTED; upsert `trust_tiers` table; publish `trust_tier.updated` event; implement `handle_trust_event(event)`: route by event_type to trigger `recompute(agent_id)` for all relevant event types (`certification.activated`, `certification.revoked`, `certification.expired`, `guardrail.blocked`, `circuit_breaker.activated`)
- [x] T034 [US7] Add circuit breaker and trust score endpoints to `apps/control-plane/src/platform/trust/router.py`: `GET /circuit-breaker/{agent_id}/status`; `POST /circuit-breaker/{agent_id}/reset` (platform_admin); `GET /circuit-breaker/configs`; `POST /circuit-breaker/configs` (workspace_admin or platform_admin)
- [x] T035 [US7] Register `trust.events` Kafka consumer (call `trust_tier_service.handle_trust_event(event)`) in `apps/control-plane/entrypoints/worker_main.py`; register `workflow.runtime` Kafka consumer filtering `event_type == "execution.guardrail_failed"` (call `circuit_breaker_service.record_failure(agent_id, workspace_id)`)

**Checkpoint**: US7 complete — circuit breaker activates on threshold, trust scores update within 30s of signal changes.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Privacy assessment, router registration, Kafka consumer consolidation, APScheduler jobs, test coverage, linting, type checking.

- [x] T036 [P] Implement `PrivacyAssessmentService` in `apps/control-plane/src/platform/trust/privacy_assessment.py` — `assess(request)`: call `await policy_governance_engine.check_privacy_compliance(context_assembly_id=request.context_assembly_id, workspace_id=request.workspace_id)` via injected `PolicyGovernanceEngine` interface; map result to `PrivacyAssessmentResponse(compliant=..., violations=[...], blocked=...)`
- [x] T037 [P] Add privacy assessment endpoint to `apps/control-plane/src/platform/trust/router.py`: `POST /privacy/assess` (service account)
- [x] T038 Register trust router in `apps/control-plane/src/platform/main.py`: `app.include_router(trust_router, prefix="/api/v1/trust", tags=["trust"])` in the router registration section
- [x] T039 Consolidate and verify all Kafka consumer registrations in `apps/control-plane/entrypoints/worker_main.py` — ensure all consumers are registered: `registry.events` (recertification), `policy.events` (recertification), `workflow.runtime` (circuit breaker + recertification conformance_failed), `simulation.events` (ATE result handler), `trust.events` (trust tier recomputation), `prescreener.rule_set.activated` (pre-screener hot-reload)
- [x] T040 Consolidate and verify all APScheduler job registrations in `apps/control-plane/entrypoints/api_main.py` under trust-certifier runtime profile: `expire_stale` (hourly), `scan_expiry_approaching` (daily, threshold=30 days), `scan_timed_out_runs` (every 5 minutes)
- [x] T041 [P] Create `apps/control-plane/tests/unit/trust/` with unit test files: `test_certification_service.py` (state machine transitions, supersession logic, expire_stale), `test_guardrail_pipeline.py` (each layer, fail-closed behavior, blocked action record), `test_prescreener.py` (pattern matching, hot-reload, <10ms timing), `test_circuit_breaker.py` (Lua script logic, trip threshold, reset), `test_trust_tier.py` (weighted formula, tier mapping, recompute), `test_recertification.py` (trigger creation, deduplication, Kafka handlers)
- [x] T042 [P] Create `apps/control-plane/tests/integration/trust/` with integration test files covering all 20 quickstart scenarios: `test_certification_lifecycle.py` (scenarios 1-4), `test_guardrail_pipeline.py` (scenarios 5-6), `test_prescreener.py` (scenarios 7-9), `test_oje_pipeline.py` (scenarios 10-11), `test_recertification.py` (scenarios 12-13), `test_ate.py` (scenarios 14-15), `test_circuit_breaker.py` (scenarios 16-17), `test_trust_signals.py` (scenario 18), `test_privacy.py` (scenario 19)
- [x] T043 Update `apps/control-plane/tests/conftest.py` — add trust-specific fixtures: `mock_policy_governance_engine` (AsyncMock with evaluate_tool_access, evaluate_memory_write, check_privacy_compliance), `mock_runtime_controller_client` (AsyncMock with stop_runtime, pause_workflow), `mock_simulation_controller_client` (AsyncMock with create_simulation), `mock_minio_trust` (aioboto3 mock for trust-evidence bucket), trust Redis test client (REDIS_TEST_MODE=standalone)
- [x] T044 Validate test coverage ≥95%: `pytest apps/control-plane/tests/ --cov=platform.trust --cov-report=term-missing --cov-fail-under=95` — fix any gaps
- [x] T045 [P] Run ruff: `ruff check apps/control-plane/src/platform/trust/ --fix` — resolve all lint issues
- [x] T046 [P] Run mypy: `mypy apps/control-plane/src/platform/trust/ --strict` — fix all type errors

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Foundational — no other story dependencies
- **US2 (Phase 4)**: Depends on Foundational; guardrail blocks feed into US7 trust score
- **US3 (Phase 5)**: Depends on Foundational; runs before US2 guardrail pipeline in execution
- **US4 (Phase 6)**: Depends on US1 (certifications) + US2 (guardrail outcomes); FQN from §VIII
- **US5 (Phase 7)**: Depends on US1 (certifications)
- **US6 (Phase 8)**: Depends on US1 (evidence refs)
- **US7 (Phase 9)**: Depends on US1 + US2 + US5 (all signal sources)
- **Polish (Phase 10)**: Depends on all user stories

### User Story Dependencies

- **US1 (P1)**: No story dependencies — implement first
- **US2 (P1)**: No story dependencies — implement in parallel with US1
- **US3 (P2)**: No story dependencies — implement in parallel after Foundational
- **US4 (P2)**: Soft dependency on US1 (needs active certifications for revocation action)
- **US5 (P2)**: Hard dependency on US1 (creates pending certifications)
- **US6 (P3)**: Hard dependency on US1 (links evidence to certifications)
- **US7 (P3)**: Hard dependency on US1 + US2 (consumes certification + guardrail signals)

### Parallel Opportunities

- T002 + T003 (exceptions + DI) can run in parallel
- T005 + T007 (schemas + events) can run in parallel after T004
- T009 + T010 (CertificationService + TrustTierService stub) can run in parallel
- T013 + T014 (GuardrailPipelineService + config CRUD) can run in parallel
- T016 + T017 (SafetyPreScreenerService + rule set CRUD) can run in parallel
- T020 + T021 (OJEPipelineService + config CRUD) can run in parallel
- T023 + T024 (RecertificationService + trigger CRUD) can run in parallel
- T027 + T028 (ATEService + config CRUD) can run in parallel
- T031 + T032 + T033 (Lua script + CircuitBreakerService + TrustTierService) can run in parallel
- T036 + T037 (PrivacyAssessmentService + endpoint) can run in parallel
- T041 + T042 (unit tests + integration tests) can run in parallel
- T045 + T046 (ruff + mypy) can run in parallel

---

## Parallel Example: US1 Certification Lifecycle

```bash
# Phase 3 parallel tasks (launch simultaneously):
Task: "T009 — Implement CertificationService in service.py"
Task: "T010 — Implement TrustTierService stub in trust_tier.py"

# After T009 + T010 complete:
Task: "T011 — Add certification + trust tier endpoints to router.py"
Task: "T012 — Register expire_stale APScheduler job"
```

---

## Implementation Strategy

### MVP First (US1 + US2 only — P1 stories)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 2: Foundational (T004-T008)
3. Complete Phase 3: US1 Certification Lifecycle (T009-T012)
4. Complete Phase 4: US2 Guardrail Pipeline (T013-T015)
5. **STOP and VALIDATE**: Create cert, bind evidence, activate, run guardrail eval — end-to-end
6. Register router in main.py (T038), deploy/demo

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. US1 (P1) → Certification state machine working
3. US2 (P1) → Guardrail enforcement live → MVP!
4. US3 (P2) → Pre-screener reduces latency for obvious violations
5. US4 (P2) → OJE pipeline configurable per workspace
6. US5 (P2) → Recertification triggers automated
7. US6 (P3) → ATE evidence collection formalized
8. US7 (P3) → Circuit breaker + trust scores visible in marketplace
9. Polish → Coverage, linting, mypy clean

### Parallel Team Strategy

With two developers after Foundational is complete:
- Dev A: US1 (P1) → US5 (P2) → US6 (P3)
- Dev B: US2 (P1) → US3 (P2) → US4 (P2) → US7 (P3)

---

## Notes

- [P] tasks target different files — safe to run in parallel without conflicts
- Story labels map to spec.md user stories for full traceability
- Trust score computation (US7 Phase 9) depends on US1 + US2 signal data being present
- Pre-screener Lua is NOT the circuit breaker Lua — two separate scripts
- Guardrail pipeline layers 4 + 5 (tool_control, memory_write) mock PolicyGovernanceEngine in all tests
- Circuit breaker Lua script must be loaded via SCRIPT LOAD on service startup before first EVALSHA call
