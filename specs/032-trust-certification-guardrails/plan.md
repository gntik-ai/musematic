# Implementation Plan: Trust, Certification, and Guardrails

**Branch**: `032-trust-certification-guardrails` | **Date**: 2026-04-12 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `specs/032-trust-certification-guardrails/spec.md`

## Summary

Implement the `trust/` bounded context in the Python control plane: certification lifecycle (pending/active/expired/revoked/superseded) with evidence binding and proof chain; 6-layer synchronous guardrail pipeline (input sanitization → prompt injection → output moderation → tool control → memory write → action commit); rule-based SafetyPreScreener (<10ms, Redis-cached compiled patterns, hot-reloadable); configurable Observer-Judge-Enforcer pipeline; recertification triggers (Kafka-driven); Redis sliding-window circuit breaker (Lua EVALSHA); ATE via SimulationControlService gRPC; event-driven trust score and tier computation; privacy impact assessment delegating to PolicyGovernanceEngine. Uses PostgreSQL (12 tables, Alembic migration 032), Redis, Kafka (`trust.events`), MinIO (`trust-evidence` bucket), gRPC to SimulationControlService + RuntimeControlService.

## Technical Context

**Language/Version**: Python 3.12+ (async throughout)  
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, aiokafka 0.11+, redis-py 5.x async, httpx 0.27+ (output moderation), grpcio 1.65+ (SimulationController + RuntimeController), APScheduler 3.x, aioboto3 latest, ruff 0.7+, mypy 1.11+ strict  
**Storage**: PostgreSQL 16 (12 tables), Redis 7 Cluster (circuit breaker sorted sets + pre-screener cache), MinIO (trust-evidence bucket for ATE payloads + pre-screener rule files), Kafka `trust.events` (produce), `registry.events` / `policy.events` / `workflow.runtime` / `simulation.events` (consume)  
**Testing**: pytest + pytest-asyncio 8.x, ≥95% line coverage  
**Target Platform**: Python control plane (modular monolith), `api` + `worker` + `trust-certifier` runtime profiles  
**Performance Goals**: Pre-screener <10ms (SC-004); guardrail pipeline <500ms end-to-end (SC-003); circuit breaker activation <5s (SC-006); trust score update <30s (SC-007)  
**Constraints**: SQLAlchemy async only; no cross-boundary DB access; all hot state in Redis; guardrail pipeline must fail-closed when layer unavailable; Kafka for all async coordination; no PostgreSQL polling  
**Scale/Scope**: 7 user stories, 44 FRs, 13 SCs, 12 PostgreSQL tables, 12 source files, ~8 service classes, 20 REST endpoints, 4 Kafka topics consumed, 10 event types produced

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Gate | Principle | Status | Notes |
|---|---|---|---|
| G-I Modular monolith | `trust/` bounded context in control plane monolith | PASS | No new service — all in `apps/control-plane/src/platform/trust/` |
| G-III-PostgreSQL | Relational data in PostgreSQL only | PASS | All 12 tables in PostgreSQL; no relational data in Redis or ClickHouse |
| G-III-Redis | Hot state (circuit breaker counters, pre-screener cache) in Redis only | PASS | `trust:cb:{agent_id}` sorted set; `trust:prescreener:rules:{v}` string |
| G-III-Kafka | Async event coordination via Kafka | PASS | Consumes registry/policy/workflow events; produces on `trust.events` |
| G-III-ClickHouse | No time-series analytics computed in PostgreSQL | PASS | No ClickHouse needed — trust scores are relational aggregation, not OLAP |
| G-III-Neo4j | No graph queries needed | PASS | Proof chain is a shallow 2-level DAG — PostgreSQL FK joins sufficient |
| G-III-MinIO | Large payloads in object storage | PASS | ATE evidence payloads + pre-screener rule files in `trust-evidence` bucket |
| G-IV No cross-boundary DB | No direct table access across bounded contexts | PASS | All inter-context calls via internal service interfaces (PolicyGovernanceEngine) or Kafka |
| G-VI Policy machine-enforced | Tool gateway + memory write gate enforced by policies/ | PASS | Guardrail pipeline delegates tool control and memory write checks to PolicyGovernanceEngine |
| G-VII Simulation isolation | ATE uses SimulationController in `platform-simulation` namespace | PASS | No direct pod creation from control plane; SimulationControlService gRPC used |
| G-VIII FQN addressing | OJE agents addressed by FQN | PASS | `observer_fqns`, `judge_fqns`, `enforcer_fqns` are FQN arrays in OJEPipelineConfig |
| G-XI Secrets not in LLM context | Output sanitization precedes context delivery | PASS | OutputSanitizer (feature 028) runs before output moderation; guardrail pipeline enforces |

**All applicable gates PASS.** No constitution violations.

## Project Structure

### Documentation (this feature)

```text
specs/032-trust-certification-guardrails/
├── plan.md              # This file
├── research.md          # Phase 0 output — 15 decisions
├── data-model.md        # Phase 1 output — SQLAlchemy models, Pydantic schemas, service interfaces
├── quickstart.md        # Phase 1 output — 20 test scenarios
├── contracts/
│   └── trust-api.md     # Phase 1 output — REST API, Kafka events, internal service interfaces
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code

```text
apps/control-plane/src/platform/trust/
├── __init__.py
├── models.py                    # 12 SQLAlchemy models + enums
├── schemas.py                   # All Pydantic request/response schemas
├── repository.py                # Async SQLAlchemy queries
├── service.py                   # CertificationService, TrustTierService
├── guardrail_pipeline.py        # GuardrailPipelineService (6 layers, fail-closed)
├── prescreener.py               # SafetyPreScreenerService (rule-based, <10ms, Redis hot-cache)
├── trust_tier.py                # TrustTierService score computation (weighted formula)
├── recertification.py           # RecertificationService + Kafka handlers (revision/policy triggers)
├── circuit_breaker.py           # CircuitBreakerService (Redis sorted set + Lua EVALSHA)
├── oje_pipeline.py              # OJEPipelineService (Observer-Judge-Enforcer)
├── ate_service.py               # ATEService (SimulationControlService gRPC + Kafka result handler)
├── privacy_assessment.py        # PrivacyAssessmentService (delegates to policies/)
├── router.py                    # FastAPI router — all trust endpoints
├── events.py                    # Kafka event types and publisher (10 event types on trust.events)
├── exceptions.py                # TrustError hierarchy
└── dependencies.py              # FastAPI dependency injection

apps/control-plane/migrations/versions/
└── 032_trust_certifications.py  # Alembic migration — all 12 tables
```

## Implementation Phases

### Phase 1 — Core Data Layer (Foundational)

**Goal**: Migration 032, models, schemas, repository, events, DI skeleton.

**Tasks**:
- Alembic migration `032_trust_certifications.py`: all 12 tables in dependency order
- `models.py`: 12 SQLAlchemy models + all enums (CertificationStatus, EvidenceType, TrustTierName, etc.)
- `schemas.py`: all Pydantic schemas
- `repository.py`: async CRUD for all models
- `events.py`: Kafka event type constants + publisher using existing `EventPublisher` from common
- `exceptions.py`: `TrustError`, `CertificationNotFoundError`, `CertificationStateError`, `GuardrailBlockedError`, `CircuitBreakerTrippedError`
- `dependencies.py`: `get_trust_service`, `get_guardrail_service`, `get_prescreener` FastAPI dependencies

### Phase 2 — Certification Lifecycle (US1: P1)

**Goal**: Full certification state machine with evidence binding, audit trail, and trust tier event.

**Tasks**:
- `service.py` `CertificationService`: `create`, `get`, `list_for_agent`, `activate`, `revoke`, `add_evidence`, `expire_stale`
- State machine guard: validate allowed transitions, raise `CertificationStateError` on invalid
- Supersede logic: on activation, find and supersede existing active cert for same agent
- Auto-expire: APScheduler job calling `expire_stale()` hourly in `trust-certifier` profile
- Publish Kafka events for all state transitions
- `router.py`: 6 certification + 2 trust tier endpoints
- `trust_tier.py` `TrustTierService`: stub for `get_tier` (full computation in Phase 8)

### Phase 3 — Guardrail Pipeline (US2: P1)

**Goal**: Synchronous 6-layer guardrail pipeline with fail-closed behavior and blocked action audit.

**Tasks**:
- `guardrail_pipeline.py` `GuardrailPipelineService`:
  - `evaluate_full_pipeline`: calls layers in order; short-circuits on first block
  - Layer 1 `input_sanitization`: regex scan for forbidden input patterns
  - Layer 2 `prompt_injection`: pattern matching for injection signatures
  - Layer 3 `output_moderation`: regex stage + optional httpx LLM moderation call (configurable)
  - Layer 4 `tool_control`: calls `PolicyGovernanceEngine.evaluate_tool_access()` (feature 028 internal interface)
  - Layer 5 `memory_write`: calls `PolicyGovernanceEngine.evaluate_memory_write()` (feature 028)
  - Layer 6 `action_commit`: final commit gate (configurable per workspace)
  - Fail-closed: each layer wrapped in try/except; exception → block + record `guardrail_layer_unavailable`
- `record_blocked_action`: SHA-256 hash of full input + first 500 chars preview; write to PostgreSQL; publish `guardrail.blocked` event
- `router.py`: add `/trust/guardrails/evaluate`, blocked-actions list/get, config GET/PUT endpoints
- `GuardrailPipelineConfig` CRUD in service + repository

### Phase 4 — Safety Pre-Screener (US3: P2)

**Goal**: In-process rule-based pre-screener, Redis hot-cache, versioned rule sets, hot-reload via Kafka.

**Tasks**:
- `prescreener.py` `SafetyPreScreenerService`:
  - In-process compiled pattern cache (dict of {rule_name: compiled_regex})
  - `screen(content, context_type)`: iterate compiled patterns; return first match or pass
  - `load_active_rules()`: read active version pointer from Redis (`trust:prescreener:active_version`); fetch rules JSON from MinIO; compile and cache
  - `activate_rule_set(rule_set_id)`: write rules JSON to MinIO; update PostgreSQL; set Redis pointer; publish `prescreener.rule_set.activated` Kafka event
- Kafka consumer (in `trust-certifier` profile): `prescreener.rule_set.activated` → reload rules in each worker
- `router.py`: add 4 pre-screener endpoints (screen, list rule sets, upload rule set, activate)
- Worker startup hook: call `load_active_rules()` on startup

### Phase 5 — Observer-Judge-Enforcer Pipeline (US4: P2)

**Goal**: Configurable OJE pipeline with verdict storage and enforcer actions (quarantine, notify, revoke, recertify).

**Tasks**:
- `oje_pipeline.py` `OJEPipelineService`:
  - `configure_pipeline`: validate FQNs exist in registry (call registry service interface); save OJEPipelineConfig
  - `process_observation(signal, config_id)`: find judge agents; invoke via interactions service (feature 024 internal interface) with `trust_pipeline_context=True`; parse verdict JSON
  - `execute_enforcement(verdict)`: route by `verdict.verdict` type:
    - `VIOLATION` → call `RuntimeControllerClient.stop_runtime()` for quarantine
    - `ESCALATE_TO_HUMAN` → publish to `interaction.attention` Kafka topic (§XIII)
    - `WARNING` → publish `trust.events` warning event
    - `COMPLIANT` → log only
  - Store verdict in `trust_signals` + `trust_proof_links` tables
- `router.py`: add OJE config endpoints (list, create, get, deactivate)

### Phase 6 — Recertification Triggers (US5: P2)

**Goal**: Kafka-driven recertification on revision/policy/conformance changes; expiry via APScheduler; deduplication.

**Tasks**:
- `recertification.py` `RecertificationService`:
  - `create_trigger`: insert with `ON CONFLICT DO NOTHING` (PostgreSQL unique constraint for deduplication); if inserted, create new pending certification; publish `recertification.triggered`
  - `handle_revision_published(event)`: extract agent_id, revision_id from registry event; call `create_trigger(type=REVISION_CHANGED)`
  - `handle_policy_updated(event)`: look up agents with this policy attached; for each, call `create_trigger(type=POLICY_CHANGED)`
  - `scan_expiry_approaching(threshold_days)`: APScheduler job; query certifications expiring within threshold; call `create_trigger(type=EXPIRY_APPROACHING)` for each
- Register Kafka consumers in `worker` entrypoint: `registry.events` + `policy.events`
- Register APScheduler job in `trust-certifier` entrypoint: daily expiry scan
- `router.py`: add recertification trigger list/get endpoints

### Phase 7 — ATE Integration (US6: P3)

**Goal**: Workspace-scoped ATE configurations, ATE runs via SimulationControlService gRPC, evidence linking.

**Tasks**:
- `ate_service.py` `ATEService`:
  - `create_config`: validate + store `TrustATEConfiguration`; MinIO key for golden_dataset if provided
  - `run(request)`: call `SimulationControllerClient.create_simulation()` with ATE config as payload; store `simulation_id → certification_id` mapping in Redis (TTL = timeout_seconds + 300s); return ATERunResponse
  - `handle_simulation_completed(event)`: retrieve certification_id from Redis by simulation_id; parse result JSON; create `CertificationEvidenceRef` entries; write full result payload to MinIO (`trust-evidence/ate/{simulation_id}/result.json`); publish `certification.evidence_added` event (sub-event of trust.events)
  - Timeout: APScheduler scans in-progress ATE runs (Redis keys); on timeout, record partial evidence with `timed_out` status
- Register Kafka consumer in `worker` entrypoint: `simulation.events` with event_type filter `simulation.completed`
- `router.py`: add ATE config endpoints + ATE run endpoints

### Phase 8 — Circuit Breaker and Trust Score (US7: P3)

**Goal**: Redis sliding-window circuit breaker, trust score weighted computation, Kafka-driven tier updates.

**Tasks**:
- `circuit_breaker.py` `CircuitBreakerService`:
  - `record_failure(agent_id, workspace_id)`: EVALSHA Lua script on `trust:cb:{agent_id}` sorted set (ZADD current timestamp; ZREMRANGEBYSCORE below window; ZCARD; compare to threshold; if tripped: SETEX `trust:cb:tripped:{agent_id}`)
  - Lua script stored in `apps/control-plane/src/platform/trust/lua/circuit_breaker_check.lua`
  - `is_tripped(agent_id)`: check Redis `trust:cb:tripped:{agent_id}`
  - On trip: publish `circuit_breaker.activated`; call RuntimeControllerClient to pause workflow; send attention notification
  - `reset(agent_id)`: DEL both Redis keys; optionally via POST admin endpoint
- `trust_tier.py` `TrustTierService`:
  - `recompute(agent_id)`: fetch last N certifications (PostgreSQL), recent blocked actions count (PostgreSQL), behavioral signals (PostgreSQL); apply weighted formula (certification 0.50, guardrail 0.35, behavioral 0.15); update `trust_tiers` table
  - `handle_trust_event(event)`: Kafka consumer handler — routes event_type to appropriate recompute trigger
- Register `trust.events` consumer in `worker` profile for trust tier recomputation
- Register `workflow.runtime` consumer in `worker` profile for circuit breaker failure recording
- `router.py`: add circuit breaker status/reset + config endpoints

### Phase 9 — Privacy Assessment + Polish (Cross-Cutting)

**Goal**: Privacy assessment, ARIA audit, coverage validation, ruff, mypy strict.

**Tasks**:
- `privacy_assessment.py` `PrivacyAssessmentService`:
  - `assess(request)`: call `PolicyGovernanceEngine.check_privacy_compliance(context_assembly_id, workspace_id)` via internal service interface; map result to `PrivacyAssessmentResponse`
  - `router.py`: add `/trust/privacy/assess` endpoint
- Register `router.py` in `apps/control-plane/src/platform/main.py` (`app.include_router(trust_router, prefix="/api/v1/trust")`)
- Register all Kafka consumers in `apps/control-plane/entrypoints/worker_main.py`
- Register APScheduler jobs in `apps/control-plane/entrypoints/api_main.py` (trust-certifier profile)
- `tests/conftest.py`: fixtures for trust services with mocked PolicyGovernanceEngine, RuntimeControllerClient, SimulationControllerClient, Redis, MinIO
- Validate ≥95% coverage: `pytest --cov=platform.trust`
- ruff: `ruff check apps/control-plane/src/platform/trust/`
- mypy: `mypy apps/control-plane/src/platform/trust/ --strict`

## Complexity Tracking

No constitution violations — no entries required.
