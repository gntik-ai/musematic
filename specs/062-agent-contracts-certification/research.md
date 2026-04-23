# Research: Agent Contracts and Certification Enhancements

**Feature**: 062-agent-contracts-certification  
**Date**: 2026-04-19  
**Next migration**: 049 (latest is 048_governance_pipeline.py)

---

## Decision 1: Trust bounded context is flat — no `models/` or `services/` subdirectory

**Decision**: New model classes extend `trust/models.py` directly. New service files are placed flat in `trust/` as `trust/contract_service.py`, `trust/contract_monitor.py`, `trust/surveillance_service.py`.

**Rationale**: The existing `trust/` directory is flat (models.py, schemas.py, service.py, router.py, events.py, etc.). Brownfield Rule 4 requires using existing patterns. Creating subdirectories would require refactoring all existing imports from `trust.models` to `trust.models.*`, which violates Brownfield Rule 1.

**Alternatives considered**: `trust/models/contract.py` (as per user input) — rejected because it requires import refactoring of the entire trust module.

---

## Decision 2: `expires_at` already exists — do not add `expiry_date`

**Decision**: The `trust_certifications` table already has `expires_at: Mapped[datetime | None]`. Do NOT add `expiry_date` as the user input DDL suggested. Use the existing `expires_at` column for all expiry logic.

**Rationale**: Brownfield Rule 1 (never rewrite) + Rule 7 (backward-compatible). Adding a duplicate `expiry_date` column alongside the existing `expires_at` would create confusion and require migration of existing data. The existing column serves the same purpose.

**Alternatives considered**: Adding both columns — rejected. Renaming `expires_at` to `expiry_date` — rejected (breaking change, requires migration and code updates across all callers).

---

## Decision 3: `CertificationStatus` enum — add `expiring` and `suspended` values

**Decision**: Add two values to the existing `CertificationStatus` enum: `expiring` (BEFORE `expired`) and `suspended` (AFTER `revoked`). Migration 049 includes `ALTER TYPE certification_status ADD VALUE 'expiring' BEFORE 'expired'; ALTER TYPE certification_status ADD VALUE 'suspended';`.

**Rationale**: Brownfield Rule 6 (additive enum values). Existing values `pending`, `active`, `expired`, `revoked`, `superseded` are preserved. New lifecycle: `active → expiring → expired` (time-based) and `active/expiring → suspended → revoked` (material-change path).

**Alternatives considered**: String column instead of enum — rejected, inconsistent with existing pattern. New enum type — rejected (violates additive rule).

---

## Decision 4: Contract snapshot stored inline on interactions/executions

**Decision**: Add both `contract_id UUID` FK and `contract_snapshot JSONB` to both `interactions` and `executions` tables. The snapshot is captured at attachment time by `ContractService.attach_to_*()`.

**Rationale**: FR-004 requires a snapshot to be captured at attachment time. Storing inline (alongside the FK on the same row) is simpler than a join table, avoids an extra query at monitor time, and fits the existing pattern where all relevant data is on the target row.

**Alternatives considered**: Separate `contract_attachments` join table — rejected as over-engineering for a 1:1 relationship.

---

## Decision 5: `agent_id` on AgentContract stored as string FQN (not FK)

**Decision**: `AgentContract.agent_id` is `VARCHAR(512)` (FQN string), not a UUID FK to the agents table. Same pattern as `TrustCertification.agent_id` and `TrustCertification.agent_fqn`.

**Rationale**: Preserves the audit trail if an agent is deleted; follows the existing trust pattern; contracts reference the FQN conceptually rather than a mutable registry entry.

**Alternatives considered**: UUID FK to `registry_agent_profiles` — rejected because deletion of the agent would cascade or block, and the existing trust pattern already uses string FQNs.

---

## Decision 6: Compliance KPI query uses PostgreSQL aggregation

**Decision**: Compliance-rate queries (`GET /compliance/rates`) aggregate `contract_breach_events` + `interactions`/`executions` in PostgreSQL via the repository layer. Do NOT route to ClickHouse.

**Rationale**: Breach events and contract attachments are stored in PostgreSQL. The query joins data already in PostgreSQL; routing to ClickHouse would require a parallel pipeline. Volume is low (compliance queries, not operational hot path). SC-009 (3s p95) is achievable with proper indexes on `contract_breach_events(target_id, created_at)` and `executions(contract_id, created_at)`. The Constitution Principle III prohibits PostgreSQL for time-series analytics rollups — this is a compliance aggregation query, not a rollup pipeline.

**Alternatives considered**: ClickHouse — rejected (no existing breach-event pipeline into ClickHouse; compliance queries are pull-based low-frequency).

---

## Decision 7: ContractMonitorConsumer subscribes to `workflow.runtime` and `runtime.lifecycle`

**Decision**: `ContractMonitorConsumer` subscribes to:
- `workflow.runtime` (token usage, step completion events from Runtime Controller)  
- `runtime.lifecycle` (execution lifecycle events: started, completed, timed-out)

Consumer group: `{settings.kafka.consumer_group}.trust-contract-monitor`

**Rationale**: These topics are already produced by the Runtime Controller (feature 009) and contain the telemetry needed to evaluate cost (token counts), time (start/elapsed), and completion status against contract terms.

**Alternatives considered**: Subscribing to `evaluation.events` for quality metrics — deferred. Quality threshold evaluation requires the evaluation engine to produce quality scores; this consumer will emit a "not evaluated" breach status for quality when scores are unavailable, consistent with the spec edge case.

---

## Decision 8: SurveillanceConsumer subscribes to `policy.events` and `trust.events` for material changes

**Decision**: `SurveillanceConsumer` subscribes to:
- `policy.events` — for policy attachment/detachment changes on agents
- `trust.events` — for agent revision deployment signals (assumed to be emitted by registry on new revision)

Consumer group: `{settings.kafka.consumer_group}.trust-surveillance-material-change`

**Rationale**: `policy.events` already exists (feature 028). Agent revision events are assumed emitted on `trust.events` per spec Assumption 4 ("upstream systems emit change signals on existing event channels"). If the registry emits revision signals on a different topic (e.g., `registry.events`), this integration point requires coordination with the registry team and can be updated without changing the consumer architecture.

**Alternatives considered**: New dedicated `agent.events` or `registry.events` topic — rejected (should not create new topics when existing channels are sufficient; deferred to registry team if needed).

---

## Decision 9: `TrustRecertificationRequest` is a new table distinct from existing `recertification_triggers`

**Decision**: Create `trust_recertification_requests` table (new). The existing `trust/recertification.py` service manages `recertification_triggers` (expiry-approach triggers). The new table handles material-change suspension tracking.

**Rationale**: The existing `recertification_triggers` model tracks upcoming expiry events (expiry approach). The new `TrustRecertificationRequest` tracks material-change events that suspend certifications and require recertification within a grace period. Semantically different, different lifecycle states, different triggers.

**Alternatives considered**: Reusing `recertification_triggers` — rejected (different semantics; would require adding columns and changing existing behavior, violating Brownfield Rule 1).

---

## Decision 10: Certifiers are platform-level (no workspace scope)

**Decision**: `Certifier` model does NOT include `WorkspaceScopedMixin`. Certifiers are registered at the platform level and are visible across workspaces.

**Rationale**: External certifier organizations (ACME Labs, industry bodies) are platform-level entities, not workspace-specific. A certifier registered by an admin should be reusable across any workspace's agents.

**Alternatives considered**: Workspace-scoped certifiers — rejected (would require per-workspace certifier management, not matching the enterprise pattern where certifier credentials are platform-wide).

---

## Decision 11: `ContractBreachEvent.contract_snapshot` carries attachment-time snapshot

**Decision**: The `contract_snapshot JSONB` field on `ContractBreachEvent` stores the full contract terms as captured at attachment time (copied from `interactions.contract_snapshot` / `executions.contract_snapshot`). This is redundant but ensures complete breach audit trail even if the attachment record is modified.

**Rationale**: FR-008 requires every enforcement action to be auditable with the contract reference. If the attachment snapshot is later updated (edge case), the breach event's own snapshot provides the authoritative view of what terms governed the execution at breach time.

---

## Decision 12: `SurveillanceService.run_surveillance_cycle()` is APScheduler interval job (hourly)

**Decision**: The APScheduler job runs every 1 hour (consistent with the existing `trust-expire-stale` job pattern). A separate cron-based reassessment dispatcher evaluates per-certification `reassessment_schedule` cron expressions to determine which certifications need a reassessment job triggered.

**Rationale**: The existing `trust-expire-stale` job already runs hourly. SC-004 requires expired certifications to be transitioned within 24 hours, which hourly satisfies. SC-005 requires expiring certifications to be caught within one surveillance cycle. SC-006 requires material-change suspension within 1 hour — handled by the Kafka consumer (near-real-time), not the scheduler.

**Job IDs**:
- `trust-surveillance-cycle` (hourly, expiry + reassessment checks)
- `trust-grace-period-check` (hourly, suspended → revoked timeout check)

---
