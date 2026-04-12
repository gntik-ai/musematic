# Research: Fleet Management and Learning

**Feature**: 033-fleet-management-learning  
**Date**: 2026-04-12  
**Phase**: 0 — Architecture decisions before design

---

## Decision 1: Two bounded contexts — `fleets/` and `fleet_learning/`

**Decision**: Split fleet concerns across two contexts per the constitution's repository structure:
- `fleets/` — domain model (Fleet, FleetMember), topology, orchestration rules, observer assignments, governance chain configuration, health projections
- `fleet_learning/` — performance profiles, adaptation engine, cross-fleet transfer, personality profiles

**Rationale**: The constitution explicitly names both `fleets/` and `fleet_learning/` as distinct paths in `apps/control-plane/src/platform/`. Fleet domain (CRUD, membership, topology, orchestration) is operationally critical and P1; learning features (performance profiles, adaptation, transfer) are P2/P3 and evolve independently. Separating them avoids coupling a fast-changing, ML-adjacent context (`fleet_learning/`) with a stable domain context (`fleets/`).

**Alternatives considered**: Single `fleets/` context. Rejected — would create a megamodule mixing CRUD with analytics aggregation (ClickHouse reads), scheduler jobs, and MinIO storage.

---

## Decision 2: Fleet health projection in Redis (not PostgreSQL)

**Decision**: Fleet health state (`available members`, `quorum_met`, `health_pct`, `status`) is stored as a JSON blob in Redis key `fleet:health:{fleet_id}` (TTL 90s, refreshed by the heartbeat consumer). Member availability is tracked in `fleet:member:avail:{fleet_id}:{agent_fqn}` keys (TTL = 2 × heartbeat interval = 120s).

**Rationale**: Health projection is hot read state, not a system-of-record. SC-008 requires updates within 30s of a member availability change — a PostgreSQL polling approach would add 15-30s latency. Redis TTL-based availability tracking (borrowed from the reasoning engine's budget design) gives sub-second updates. PostgreSQL rows remain for auditable history (status change events via `fleet.events`).

**Alternatives considered**: Updating a PostgreSQL `fleet_health_projections` table directly. Rejected — introduces a write hot path per heartbeat and violates §III (Redis for hot state).

---

## Decision 3: Member availability via `runtime.lifecycle` Kafka consumer

**Decision**: The fleet worker consumes `runtime.lifecycle` (produced by the Runtime Controller, §009) to detect member availability changes. On each event, it maps `runtime.agent_fqn` to fleet membership, updates the Redis key, re-evaluates quorum, and publishes `fleet.health` if status changed.

**Rationale**: The Runtime Controller already tracks pod heartbeats and emits `runtime.lifecycle` events for startup/shutdown/heartbeat-missed. Re-using this stream avoids a second heartbeat mechanism. No PostgreSQL polling; Kafka for all async coordination per §III.

**Alternatives considered**: gRPC call to Runtime Controller on each dispatch to check availability. Rejected — synchronous coupling on the critical dispatch path; adds latency.

---

## Decision 4: Orchestration rules stored as versioned JSONB in PostgreSQL

**Decision**: `fleet_orchestration_rules` table stores delegation, aggregation, escalation, conflict, and retry rules as separate JSONB columns. Each change creates a new row (immutable versioning, same pattern as `fleet_topology_versions`). `is_current = true` marks the active version; a partial unique index enforces one current version per fleet.

**Rationale**: Orchestration rules are relational configuration data (owned by a fleet, workspace-scoped, referenced by adaptation logs). JSONB is appropriate for the semi-structured rule payloads. Immutable versions enable revert without soft-delete complexity. PostgreSQL JSONB operations (jsonb_set, → operators) are sufficient for the read/write patterns here.

**Alternatives considered**: Storing rules as a single JSONB blob per fleet. Rejected — loses granular versioning. Storing in MinIO. Rejected — disproportionate for <1KB rule configs.

---

## Decision 5: Governance chain stores FQNs in PostgreSQL; OJE execution delegates to `trust/` service interface

**Decision**: `fleet_governance_chains` stores observer/judge/enforcer FQNs as JSONB arrays in PostgreSQL, versioned alongside topology. Execution of the OJE pipeline (routing anomaly signals through judge to enforcer) is delegated to `trust/OJEPipelineService` via internal service interface — the fleet governance chain is the configuration, not the executor.

**Rationale**: Feature 032 (`trust/`) already implements OJE pipeline mechanics (verdict processing, enforcer actions). Duplicating that logic in `fleets/` would violate §IV (no cross-boundary duplication) and the DRY principle. The fleet governance chain is purely a configuration artifact that feeds into the trust service's pipeline at runtime.

**Alternatives considered**: Implementing OJE pipeline directly in `fleets/`. Rejected — would duplicate trust certification machinery.

---

## Decision 6: Default governance chain assigned at fleet creation time

**Decision**: When `FleetService.create_fleet()` is called, it inserts a `FleetGovernanceChain` row with `is_default = true` using platform-reserved FQNs: `platform:default-observer`, `platform:default-judge`, `platform:default-enforcer`. These FQNs are documented as assumptions (pre-registered in every workspace per spec assumption §8).

**Rationale**: FR-015 requires automatic default chain assignment. Doing this at creation time (not lazily) ensures the fleet is always governance-ready. The platform FQNs follow §VIII (FQN addressing) convention.

**Alternatives considered**: Lazy default assignment (create chain only when OJE pipeline first triggers). Rejected — creates a window where a fleet has no governance chain.

---

## Decision 7: Observer execution stream routing via fleet-tagged `fleet.events`

**Decision**: The fleet worker consumes `workflow.runtime` events (produced by Runtime Controller for all executions). For each execution event, it checks if the executing agent FQN is a fleet member. If yes, it re-publishes the event to `fleet.events` with `fleet_id` in the envelope. Observer agents (identified by FQN in `observer_assignments`) receive execution events via the WS gateway's `fleet` channel, filtered by `fleet_id`.

**Rationale**: Observers are platform agents, not Kafka consumers. The WS gateway already delivers fleet-channel events to connected agents (per §019 WebSocket gateway, which supports fleet channel type). The fleet worker acts as a router/filter — no direct Kafka access for observer agents required.

**Alternatives considered**: Direct Kafka consumer per observer agent. Rejected — observers are agents, not services; they consume via the agent interaction model (WS/interactions), not direct Kafka.

---

## Decision 8: Performance metrics sourced from ClickHouse via direct client queries

**Decision**: `FleetPerformanceProfileService` queries ClickHouse directly using the `ClickHouseClient` wrapper (`common/clients/clickhouse.py`). It reads execution metrics (completion time, success/failure, cost) from the same ClickHouse materialized views created by feature 020's Kafka→ClickHouse pipeline, filtered by `agent_fqn IN (fleet member FQNs)`.

**Rationale**: ClickHouse is the shared OLAP store (§III), not a bounded-context-private database. Feature 020 created the materialized views for this exact purpose. Reading them directly follows the same pattern as analytics/ itself. Computing aggregations in PostgreSQL is explicitly prohibited by §III.

**Alternatives considered**: Internal service interface to `AnalyticsService`. Rejected — adds a synchronous in-process call chain just to reach the same ClickHouse client; over-abstracted for a read-only query path. Storing raw metrics in PostgreSQL and aggregating there. Rejected — violates §III.

---

## Decision 9: Adaptation engine runs as APScheduler job after profile computation

**Decision**: `FleetAdaptationEngineService.evaluate_all_rules()` is scheduled by APScheduler immediately after `FleetPerformanceProfileService.compute_all_profiles()` completes (daily job in `scheduler` runtime profile). Evaluation is fleet-by-fleet: for each active fleet, load the latest performance profile, evaluate all active adaptation rules in priority order, apply the first matching rule (no multi-rule batching in v1).

**Rationale**: SC-004 requires adaptation fires within one computation interval. APScheduler chaining guarantees this. Priority ordering resolves conflicting rules per FR-031. Restricting to one rule per evaluation cycle prevents cascading oscillations.

**Alternatives considered**: Kafka-event-triggered adaptation (adapt on every `fleet.health` change). Rejected — health events are too frequent and noisy for stable rule evaluation; performance profiles are computed at a controlled interval.

---

## Decision 10: Cross-fleet transfer pattern stored inline (JSONB) or in MinIO

**Decision**: `cross_fleet_transfer_requests.pattern_definition` (JSONB) stores the pattern inline for payloads ≤ 50KB. For larger payloads, `pattern_minio_key` stores a reference to the `fleet-patterns` MinIO bucket; `pattern_definition` is NULL. The service checks payload size at proposal time and routes accordingly.

**Rationale**: Most orchestration pattern definitions are small (<5KB). JSONB is sufficient. MinIO is reserved for edge cases (e.g., patterns with embedded golden datasets). This follows the same tiered approach used in trust/ (ATE evidence payloads).

**Alternatives considered**: Always store in MinIO. Rejected — adds object storage round-trip for every transfer read; wasteful for small patterns.

---

## Decision 11: Personality profile is an advisory modifier, not a rule override

**Decision**: `FleetPersonalityProfileService.get_orchestration_modifier(fleet_id)` returns a modifier struct consumed by `FleetOrchestrationService` during task dispatch. Personality adjusts defaults (e.g., `decision_speed=fast` sets `max_wait_ms=0` on delegation), but any explicit orchestration rule config overrides the personality modifier. This is enforced by applying personality modifiers first, then applying explicit rules as overrides.

**Rationale**: FR-040 requires orchestration rules to take precedence. Implementing personality as a modifier (applied at dispatch, not stored as rules) cleanly separates the two concepts while making the influence mechanical (not just advisory documentation).

**Alternatives considered**: Personality stored as a special-priority orchestration rule. Rejected — conflates the two concepts; makes rule versioning and revert more complex.

---

## Decision 12: Fleet lifecycle state machine

**Decision**: `FleetStatus` enum has 4 states: `active → degraded → paused → archived`. Transitions:
- `active → degraded`: quorum met but one or more members unavailable
- `degraded → active`: all members available again
- `degraded → paused`: quorum no longer met (too many members unavailable)
- `paused → degraded`: quorum recovered but not all members back
- `any → archived`: admin action, irreversible

State transitions are enforced by `FleetService` with a guard function. Illegal transitions raise `FleetStateError`.

**Rationale**: The spec (FR-006) defines 4 states. The transitions above map directly to the degraded operation user story (US4). The guard pattern (same as trust/ certification state machine) prevents invalid state transitions.

**Alternatives considered**: Simple boolean `is_active/is_archived` flags. Rejected — loses degraded/paused distinction needed for SC-002 and US4 acceptance scenarios.

---

## Decision 13: Alembic migration 033 — all 12 tables in one migration

**Decision**: Single migration file `033_fleet_management.py` creates all 12 tables (7 in `fleets/` schema, 5 in `fleet_learning/` schema) in dependency order: `fleets` first, then `fleet_members`, then tables that FK to `fleets`.

**Rationale**: All tables are co-created as part of one feature. A single migration is atomic and easier to roll back if needed. The 12-table count is comparable to feature 032 (12 tables). Splitting across two migrations would add complexity without benefit.

---

## Decision 14: Kafka topics

**Decision**:
- Produce to `fleet.events` (fleet CRUD, topology, governance chain, orchestration rule, adaptation, transfer status events) — all event types on one topic per topic-per-domain pattern
- Produce to `fleet.health` (health projection updates when quorum or member availability changes) — already in the Kafka registry as `fleet.health | fleet_id | fleet observers | fleet learning`
- Consume from `runtime.lifecycle` (member availability changes from Runtime Controller)
- Consume from `workflow.runtime` (execution events for observer routing)

**Rationale**: The constitution's Kafka registry already defines `fleet.health`. One additional `fleet.events` topic follows the per-domain pattern (e.g., `trust.events`, `analytics.events`). Consuming `runtime.lifecycle` and `workflow.runtime` avoids new topics for existing event streams.

---

## Decision 15: Runtime profiles

**Decision**:
- `api` profile: fleets and fleet_learning routers registered, FleetHealthProjectionService reads from Redis
- `worker` profile: Kafka consumers for `runtime.lifecycle` (health tracking) and `workflow.runtime` (observer routing)
- `scheduler` profile: APScheduler daily jobs for performance profile computation and adaptation rule evaluation
- No new runtime profile needed (both contexts fit in existing profiles)

**Rationale**: Fleet concerns naturally split across api (REST), worker (event consumers), and scheduler (background jobs) — exactly the existing profile split. No dedicated `fleet-orchestrator` profile needed in v1.
