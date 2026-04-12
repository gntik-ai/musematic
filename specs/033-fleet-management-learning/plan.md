# Implementation Plan: Fleet Management and Learning

**Branch**: `033-fleet-management-learning` | **Date**: 2026-04-12 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `specs/033-fleet-management-learning/spec.md`

## Summary

Implement the `fleets/` and `fleet_learning/` bounded contexts in the Python control plane: fleet domain model (Fleet, FleetMember, FleetTopology, FleetPolicyBinding, ObserverAssignment, FleetGovernanceChain, FleetOrchestrationRules) with workspace-scoped CRUD and immutable versioning; Redis-backed health projection with quorum tracking (Kafka-driven via `runtime.lifecycle`); Observer-Judge-Enforcer chain configuration delegating OJE execution to `trust/OJEPipelineService`; fleet performance profiles aggregated from ClickHouse (APScheduler daily job); adaptation engine (condition-action rules evaluated after profile computation, with revert); cross-fleet knowledge transfer (propose/approve/apply/revert state machine); fleet personality profiles as advisory orchestration modifiers. Uses PostgreSQL (12 tables, Alembic migration 033), Redis, Kafka (`fleet.events` + `fleet.health`), MinIO (`fleet-patterns` bucket for large transfer patterns), ClickHouse (read-only for performance metrics).

## Technical Context

**Language/Version**: Python 3.12+ (async throughout)  
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, aiokafka 0.11+, redis-py 5.x async, clickhouse-connect 0.8+, APScheduler 3.x, aioboto3 latest (MinIO fleet-patterns bucket), grpcio 1.65+ (RuntimeControllerClient — called by FleetService.record_member_failure), ruff 0.7+, mypy 1.11+ strict  
**Storage**: PostgreSQL 16 (12 tables), Redis 7 Cluster (`fleet:health:{id}` JSON TTL 90s, `fleet:member:avail:{fleet_id}:{fqn}` TTL 120s), ClickHouse (read from analytics execution_metrics table), MinIO (`fleet-patterns` bucket for large transfer pattern payloads)  
**Testing**: pytest + pytest-asyncio 8.x, ≥95% line coverage  
**Target Platform**: Python control plane (modular monolith), `api` + `worker` + `scheduler` runtime profiles  
**Performance Goals**: Fleet health projection update <30s of member change (SC-008); observer events within 2s (SC-006); governance chain 15s detection→enforcement (SC-007); fleet coordination within 5s of task submission (SC-001); member failure recovery within 10s (SC-002); performance profile query <2s (SC-003)  
**Constraints**: SQLAlchemy async only; no cross-boundary DB access (ClickHouse shared OLAP read is permitted); health projection hot state in Redis; Kafka for all async coordination; no PostgreSQL polling; `fleet.health` and `fleet.events` are the two produced topics  
**Scale/Scope**: 8 user stories, 40 FRs, 10 SCs, 12 PostgreSQL tables, 23 source files, ~10 service classes, 38 REST endpoints, 2 Kafka topics produced (`fleet.events`, `fleet.health`), 2 consumed (`runtime.lifecycle`, `workflow.runtime`), 10 event types produced

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Gate | Principle | Status | Notes |
|---|---|---|---|
| G-I Modular monolith | `fleets/` + `fleet_learning/` bounded contexts in control plane monolith | PASS | No new service — all in `apps/control-plane/src/platform/fleets/` and `fleet_learning/` |
| G-III-PostgreSQL | Fleet domain, topology, orchestration rules, governance chains in PostgreSQL | PASS | All 12 tables in PostgreSQL; no relational data in Redis |
| G-III-Redis | Fleet health projection and member availability in Redis | PASS | `fleet:health:{id}` JSON blob; `fleet:member:avail:{fleet_id}:{fqn}` TTL keys |
| G-III-ClickHouse | Performance profile metrics aggregated from ClickHouse analytics tables | PASS | `FleetPerformanceProfileService` queries ClickHouse directly; no PostgreSQL aggregation |
| G-III-Kafka | Async event coordination via Kafka | PASS | Consumes `runtime.lifecycle` + `workflow.runtime`; produces `fleet.events` + `fleet.health` |
| G-III-Neo4j | No graph queries needed | PASS | Fleet topology and member relationships fit in PostgreSQL FK joins (shallow hierarchy) |
| G-III-MinIO | Large transfer pattern payloads in object storage | PASS | `fleet-patterns/{transfer_id}/pattern.json` for payloads >50KB |
| G-IV No cross-boundary DB | No direct table access across bounded contexts | PASS | All inter-context calls via internal service interfaces (trust/OJEPipelineService) or Kafka |
| G-VIII FQN addressing | Fleet member FQNs and OJE agent FQNs | PASS | `agent_fqn`, `observer_fqn`, `observer_fqns`, `judge_fqns`, `enforcer_fqns` are FQN strings |
| G-IX Zero-trust | Fleet member visibility follows workspace zero-trust | PASS | All fleet queries are workspace-scoped; no cross-workspace fleet access |
| G-XIII Attention pattern | Quorum violation notifies via `interaction.attention` | PASS | `FleetHealthProjectionService` publishes to `interaction.attention` on quorum breach |

**All applicable gates PASS.** No constitution violations.

## Project Structure

### Documentation (this feature)

```text
specs/033-fleet-management-learning/
├── plan.md              # This file
├── research.md          # Phase 0 output — 15 decisions
├── data-model.md        # Phase 1 output — SQLAlchemy models, Pydantic schemas, service interfaces
├── quickstart.md        # Phase 1 output — 20 test scenarios
├── contracts/
│   └── fleet-api.md     # Phase 1 output — REST API, Kafka events, internal service interfaces
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code

```text
apps/control-plane/src/platform/fleets/
├── __init__.py
├── models.py            # 7 SQLAlchemy models + FleetStatus, FleetTopologyType, FleetMemberRole, FleetMemberAvailability enums
├── schemas.py           # All Pydantic request/response schemas for fleets/ context
├── repository.py        # Async SQLAlchemy queries for all fleets/ tables
├── service.py           # FleetService + FleetOrchestrationModifierService
├── health.py            # FleetHealthProjectionService (Redis TTL keys + quorum logic + Kafka consumer handler)
├── governance.py        # FleetGovernanceChainService (chain CRUD, default chain creation, OJE delegation)
├── router.py            # FastAPI router — all 21 fleets/ REST endpoints
├── events.py            # fleet.events + fleet.health event types and publisher
├── exceptions.py        # FleetError, FleetNotFoundError, FleetStateError, QuorumNotMetError, FleetNameConflictError
└── dependencies.py      # get_fleet_service, get_health_service FastAPI dependencies

apps/control-plane/src/platform/fleet_learning/
├── __init__.py
├── models.py            # 5 SQLAlchemy models + 5 enums (TransferRequestStatus, CommunicationStyle, DecisionSpeed, RiskTolerance, AutonomyLevel)
├── schemas.py           # All Pydantic request/response schemas for fleet_learning/ context
├── repository.py        # Async SQLAlchemy queries for all fleet_learning/ tables
├── performance.py       # FleetPerformanceProfileService (ClickHouse aggregation + PostgreSQL storage + APScheduler job)
├── adaptation.py        # FleetAdaptationEngineService (rule evaluation, orchestration update, log, revert)
├── transfer.py          # CrossFleetTransferService (propose/approve/apply/reject/revert state machine + MinIO)
├── personality.py       # FleetPersonalityProfileService (CRUD, versioning, OrchestrationModifier computation)
├── service.py           # FleetLearningService (coordinator, wires together learning services)
├── router.py            # FastAPI router — all 17 fleet_learning/ REST endpoints
├── events.py            # fleet_learning event types and publisher (reuses fleet.events topic)
├── exceptions.py        # FleetLearningError, AdaptationError, TransferError, IncompatibleTopologyError
└── dependencies.py      # get_fleet_learning_service FastAPI dependencies

apps/control-plane/migrations/versions/
└── 033_fleet_management.py  # Alembic migration — all 12 tables in dependency order
```

## Implementation Phases

### Phase 1 — Core Data Layer (Foundational)

**Goal**: Migration 033, models, schemas, repositories, events, exceptions, DI skeletons for both bounded contexts.

**Tasks**:
- Alembic migration `033_fleet_management.py`: all 12 tables in dependency order (fleets → fleet_members → fleet_topology_versions → fleet_policy_bindings → observer_assignments → fleet_governance_chains → fleet_orchestration_rules → fleet_performance_profiles → fleet_adaptation_rules → fleet_adaptation_log → cross_fleet_transfer_requests → fleet_personality_profiles)
- `fleets/models.py`: 7 SQLAlchemy models + 4 enums (FleetStatus, FleetTopologyType, FleetMemberRole, FleetMemberAvailability)
- `fleet_learning/models.py`: 5 SQLAlchemy models + 5 enums
- `fleets/schemas.py` + `fleet_learning/schemas.py`: all Pydantic schemas
- `fleets/repository.py` + `fleet_learning/repository.py`: async CRUD for all models
- `fleets/events.py` + `fleet_learning/events.py`: event type constants + publisher using `EventPublisher` from common
- `fleets/exceptions.py` + `fleet_learning/exceptions.py`: domain exception hierarchies
- `fleets/dependencies.py` + `fleet_learning/dependencies.py`: FastAPI DI stubs

### Phase 2 — Fleet Domain and Topology (US1: P1)

**Goal**: Fleet CRUD with topology versioning, member management, policy binding, default governance chain creation.

**Tasks**:
- `fleets/service.py` `FleetService`: `create_fleet` (with initial members, default topology version, default governance chain, default orchestration rules), `get_fleet`, `list_fleets`, `update_fleet`, `archive_fleet`, `add_member`, `remove_member`, `update_member_role`, `list_members`, `update_topology` (immutable version), `get_topology_history`, `bind_policy`, `unbind_policy`, `assign_observer`, `remove_observer`
- State machine guard: `archive` only from `active`/`degraded`/`paused`; raise `FleetStateError` on invalid
- Unique name validation: `(workspace_id, name)` constraint → `FleetNameConflictError` → 409
- Topology version: `is_current=True` only on latest; previous versions marked `is_current=False` (PostgreSQL partial unique index)
- Default governance chain: insert `FleetGovernanceChain` with platform FQNs (`platform:default-observer`, `platform:default-judge`, `platform:default-enforcer`) and `is_default=True` at `create_fleet` time
- Default orchestration rules: insert `FleetOrchestrationRules` with sensible defaults (round_robin delegation, first_wins aggregation, 300s escalation) at `create_fleet` time
- Publish Kafka events for all state changes
- `fleets/router.py`: 21 endpoints (CRUD + member + topology + policy + observer + rules + chain)

### Phase 3 — Orchestration Rules (US2: P1)

**Goal**: Orchestration rules CRUD and versioning; rules service with delegation/aggregation/escalation/conflict/retry strategies.

**Tasks**:
- `fleets/service.py` `FleetService.get_orchestration_rules` + `update_orchestration_rules` + `get_rules_history`
- `update_orchestration_rules`: create new `FleetOrchestrationRules` row with incremented version, mark old as `is_current=False`; publish `fleet.orchestration_rules.updated`
- `get_rules_history`: return all versions for a fleet ordered by version desc
- `fleets/service.py` `FleetOrchestrationModifierService.get_modifier(fleet_id)`: reads current personality profile (cross-context in-process call to `fleet_learning/personality.py`) and returns `OrchestrationModifier` struct (advisory defaults only)
- `fleets/router.py` rules endpoints already included in Phase 2 router; validate schema on PUT

### Phase 4 — Observer Agents and Governance Chain (US3: P2)

**Goal**: Observer assignment management; governance chain CRUD with versioning; execution event routing to observers; OJE delegation to trust/.

**Tasks**:
- `fleets/governance.py` `FleetGovernanceChainService`: `get_chain`, `update_chain` (new immutable version), `get_chain_history`
- `update_chain`: mark old chain `is_current=False`; publish `fleet.governance_chain.updated`
- Observer routing: `worker` profile Kafka consumer on `workflow.runtime` — for each execution event, look up fleet membership by `agent_fqn`; if member found, republish event to `fleet.events` with `fleet_id` in envelope headers (for WS gateway fleet channel delivery to observer agents)
- OJE delegation stub: `FleetGovernanceChainService.trigger_oje_pipeline(fleet_id, signal)` calls `OJEPipelineServiceInterface.process_fleet_anomaly_signal()` via internal service interface (trust/ context)
- `fleets/router.py` governance endpoints already included in Phase 2 router

### Phase 5 — Fleet Health Projection and Degraded Operation (US4: P2)

**Goal**: Redis-backed health projection, quorum tracking, automatic pause/resume, attention notifications.

**Tasks**:
- `fleets/health.py` `FleetHealthProjectionService`:
  - `get_health(fleet_id)`: read `fleet:health:{fleet_id}` from Redis; deserialize to `FleetHealthProjectionResponse`; fall back to PostgreSQL if Redis miss
  - `handle_member_availability_change(agent_fqn, is_available)`: query `fleet_members` for all fleets containing `agent_fqn`; for each fleet, update `fleet:member:avail:{fleet_id}:{agent_fqn}` Redis key (SET with TTL 120s if available; DEL if unavailable); call `refresh_health(fleet_id)`
  - `refresh_health(fleet_id)`: SCAN all `fleet:member:avail:{fleet_id}:*` keys; count available; compute `health_pct`; determine new `FleetStatus`; write `fleet:health:{fleet_id}` JSON; if status changed, update PostgreSQL fleet status + publish `fleet.status.changed` on `fleet.events` + publish `fleet.health.updated` on `fleet.health`
  - Quorum violation: if `available_count < quorum_min`, set `status=PAUSED`; publish attention notification to `interaction.attention` Kafka topic with `urgency=high`
  - Quorum recovery: if `available_count >= quorum_min` and `status=PAUSED`, set `status=DEGRADED`; if all members available, set `status=ACTIVE`
- `worker` profile: Kafka consumer on `runtime.lifecycle` → `FleetHealthProjectionService.handle_member_availability_change`

### Phase 6 — Fleet Performance Profiles (US5: P2)

**Goal**: ClickHouse-backed performance profile aggregation with daily APScheduler job, queryable profiles.

**Tasks**:
- `fleet_learning/performance.py` `FleetPerformanceProfileService`:
  - `compute_profile(fleet_id, period_start, period_end)`: get member FQNs from `FleetServiceInterface.get_fleet_members(fleet_id)`; execute ClickHouse query over `execution_metrics` table with `agent_fqn IN (...)` and time range filter; compute per-member + fleet-wide aggregates; flag members with deviation > 2 std from mean; insert `FleetPerformanceProfile` row; return response
  - `compute_all_profiles(period_start, period_end)`: query all active fleets workspace-by-workspace; call `compute_profile` for each
  - `get_profile(fleet_id, query)`: query `fleet_performance_profiles` by fleet_id and overlapping time range
  - `get_profile_history(fleet_id)`: query all profiles for fleet ordered by period_end desc
- `scheduler` profile: APScheduler daily job at 01:00 UTC calling `compute_all_profiles(yesterday_start, yesterday_end)`
- `fleet_learning/router.py`: performance profile endpoints (GET + POST compute + GET history)

### Phase 7 — Adaptation Engine (US6: P3)

**Goal**: Rule evaluation against latest profile, orchestration rule updates, adaptation log with revert.

**Tasks**:
- `fleet_learning/adaptation.py` `FleetAdaptationEngineService`:
  - `create_rule`, `list_rules`, `update_rule`, `deactivate_rule`: CRUD for `FleetAdaptationRule`
  - `evaluate_rules_for_fleet(fleet_id)`: load latest `FleetPerformanceProfile` for fleet; load active rules ordered by `priority DESC`; for the first matching rule (condition evaluated against profile metrics): call `FleetServiceInterface.update_orchestration_rules(fleet_id, patched_rules)` with the adaptation action applied; insert `FleetAdaptationLog` row with `before_rules_version`, `after_rules_version`, `performance_snapshot`; publish `fleet.adaptation.applied`
  - `evaluate_all_fleets()`: APScheduler job, runs after daily profile computation; calls `evaluate_rules_for_fleet` for each active fleet with active adaptation rules
  - `revert_adaptation(log_id)`: load log entry; mark old orchestration rules version as `is_current=True`; mark new version as `is_current=False`; update `FleetAdaptationLog.is_reverted=True`; publish `fleet.orchestration_rules.updated` with reverted version number
  - `list_log(fleet_id)`: query `fleet_adaptation_log` for fleet
- `scheduler` profile: APScheduler daily job chained after performance profile job
- `fleet_learning/router.py`: adaptation rules endpoints + log endpoints + revert endpoint

### Phase 8 — Cross-Fleet Knowledge Transfer (US7: P3)

**Goal**: Transfer request state machine, pattern adaptation, MinIO for large payloads.

**Tasks**:
- `fleet_learning/transfer.py` `CrossFleetTransferService`:
  - `propose(source_fleet_id, request, proposed_by)`: validate `target_fleet_id` exists in same workspace (call `FleetServiceInterface.get_fleet`); if `len(json.dumps(pattern_definition)) > 50KB`: write to MinIO `fleet-patterns/{transfer_id}/pattern.json`, store key in `pattern_minio_key`; else: store inline in `pattern_definition`; insert `CrossFleetTransferRequest` with `status=PROPOSED`; publish `fleet.transfer.status_changed`
  - `approve(transfer_id, approved_by)`: validate requester has admin role on `target_fleet`; guard `status=PROPOSED`; update to `APPROVED`; publish event
  - `reject(transfer_id, rejected_by, reason)`: guard `status=PROPOSED`; update to `REJECTED` with reason; publish event
  - `apply(transfer_id)`: guard `status=APPROVED`; load pattern (inline or from MinIO); adapt pattern to target fleet topology (re-map lead FQNs for hierarchical, strip leader-specific config for peer-to-peer); call `FleetServiceInterface.update_orchestration_rules(target_fleet_id, adapted_rules)`; if incompatible → raise `IncompatibleTopologyError` (422); set `status=APPLIED`, `applied_at`; publish event
  - `revert(transfer_id)`: guard `status=APPLIED`; call `FleetServiceInterface` to restore pre-transfer orchestration rules version; set `reverted_at`; publish event
  - `list_for_fleet(fleet_id)`: query by `source_fleet_id` OR `target_fleet_id`
- `fleet_learning/router.py`: transfer request endpoints

### Phase 9 — Fleet Personality Profiles (US8: P3)

**Goal**: Personality CRUD with versioning, orchestration modifier computation.

**Tasks**:
- `fleet_learning/personality.py` `FleetPersonalityProfileService`:
  - `get(fleet_id)`: query current `FleetPersonalityProfile` for fleet; if none exists, return platform defaults (concise, deliberate, moderate, semi_autonomous)
  - `update(fleet_id, request)`: mark old profile `is_current=False`; insert new with `version+1, is_current=True`
  - `get_modifier(fleet_id)`: compute `OrchestrationModifier` from personality attributes:
    - `decision_speed=FAST` → `max_wait_ms=0`
    - `decision_speed=DELIBERATE` → `max_wait_ms=5000`
    - `decision_speed=CONSENSUS_SEEKING` → `require_quorum_for_decision=True`
    - `risk_tolerance=CONSERVATIVE` → `escalate_unverified=True`
    - `autonomy_level=FULLY_AUTONOMOUS` → `auto_approve=True`
- `fleets/service.py` `FleetOrchestrationModifierService.get_modifier(fleet_id)`: delegates to `FleetPersonalityProfileService.get_modifier(fleet_id)` via in-process call
- `fleet_learning/router.py`: personality profile GET + PUT endpoints

### Phase 10 — Polish and Cross-Cutting Concerns

**Goal**: Router registration, Kafka consumer registration, APScheduler job registration, coverage ≥95%, ruff, mypy strict.

**Tasks**:
- Register `fleets_router` and `fleet_learning_router` in `apps/control-plane/src/platform/main.py` (`app.include_router(fleets_router, prefix="/api/v1")` + `app.include_router(fleet_learning_router, prefix="/api/v1")`)
- Register Kafka consumers in `apps/control-plane/entrypoints/worker_main.py`:
  - `runtime.lifecycle` → `FleetHealthProjectionService.handle_member_availability_change`
  - `workflow.runtime` → observer routing (re-publish to `fleet.events` for fleet-member executions)
- Register APScheduler jobs in `apps/control-plane/entrypoints/scheduler_main.py`:
  - Daily at 01:00 UTC: `FleetPerformanceProfileService.compute_all_profiles`
  - Daily at 01:05 UTC: `FleetAdaptationEngineService.evaluate_all_fleets` (after profiles computed)
- `tests/conftest.py`: fixtures for fleet services with mocked `OJEPipelineService`, `FleetServiceInterface`, Redis, ClickHouse, MinIO
- Validate ≥95% coverage: `pytest --cov=platform.fleets --cov=platform.fleet_learning`
- ruff: `ruff check apps/control-plane/src/platform/fleets/ apps/control-plane/src/platform/fleet_learning/`
- mypy: `mypy apps/control-plane/src/platform/fleets/ apps/control-plane/src/platform/fleet_learning/ --strict`
- Update `CLAUDE.md` with feature 033 two-line entries

## Complexity Tracking

No constitution violations — no entries required.
