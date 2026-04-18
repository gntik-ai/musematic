# Research: Judge/Enforcer Governance Pipeline

**Feature**: 061-judge-enforcer-governance  
**Date**: 2026-04-18  
**Phase**: 0 — Resolve unknowns before design

---

## Decision 1: AgentRoleType.judge/enforcer — Already Exist

**Decision**: Do NOT add a new migration for the role_type enum. The values `judge` and `enforcer` are already present in `AgentRoleType` at `registry/models.py:31-32`.

```python
class AgentRoleType(StrEnum):  # registry/models.py:26
    executor = "executor"
    planner = "planner"
    orchestrator = "orchestrator"
    observer = "observer"
    judge = "judge"       # line 31 — ALREADY PRESENT
    enforcer = "enforcer" # line 32 — ALREADY PRESENT
    custom = "custom"
```

**Rationale**: Dependency UPD-001 is confirmed complete. FR-001 is satisfied without any code change to the enum itself. Chain role-eligibility checks (`FR-011`) can use `AgentRoleType.judge` / `AgentRoleType.enforcer` comparisons directly against agent profile `role_types`.

**Alternatives considered**: Adding them again (would violate Brownfield Rule 6 — additive enum values). No action needed.

---

## Decision 2: Fleet Governance Chain — Already Implemented (Additive Only)

**Decision**: The `FleetGovernanceChain` model, `fleet_governance_chains` table, `FleetGovernanceChainService`, and fleet router endpoints already exist. This feature makes two additive changes: (a) adds `verdict_to_action_mapping` JSONB column to `fleet_governance_chains`; (b) wires `JudgeService` as the `oje_service` in `FleetGovernanceChainService`.

**Existing fleet governance chain assets**:
- `fleets/models.py:178-223` — `FleetGovernanceChain` model with `observer_fqns`, `judge_fqns`, `enforcer_fqns`, `policy_binding_ids`, `is_current`, `version`
- `fleets/governance.py` — `FleetGovernanceChainService` with `get_chain()`, `update_chain()`, `get_chain_history()`, `trigger_oje_pipeline()` (stub)
- `fleets/schemas.py:166-195` — `FleetGovernanceChainUpdate`, `FleetGovernanceChainResponse`
- `fleets/router.py:311-341` — `GET/PUT /{fleet_id}/governance-chain`, `GET /{fleet_id}/governance-chain/history`

**What is missing**: `verdict_to_action_mapping` field (the enforcement config, e.g. `{"VIOLATION": "block"}`). Will be added as a new JSONB column with `default '{}'`.

**Rationale**: Reusing the existing versioned chain table maintains consistency. The `trigger_oje_pipeline()` stub is the integration point — the new `JudgeService` implements the `process_fleet_anomaly_signal(fleet_id, chain, signal)` interface.

---

## Decision 3: Workspace Governance Chain — New Versioned Table

**Decision**: Create `workspace_governance_chains` table mirroring `fleet_governance_chains` exactly (same columns, same indexing pattern). Add `WorkspaceGovernanceChain` model to `workspaces/models.py`. Add `WorkspaceGovernanceChainService` in new `workspaces/governance.py`. Add endpoints to `workspaces/router.py`.

**Rationale**: The spec requires workspace-level chains with fleet-level fallback (FR-013). A simple JSONB column on `workspaces` (as stated in the user input) cannot support the versioning, history, and `is_current` tracking that the existing fleet chain model uses. Mirroring `fleet_governance_chains` gives consistent audit trail, history, and future extensibility.

**Alternatives considered**:
- JSONB column on `workspaces` — simpler but loses versioning and chain history for audit
- Single shared table with `scope_type` discriminator — adds complexity to existing fleet code

---

## Decision 4: GovernanceVerdict / EnforcementAction — FQN Strings, Not FK to Agents

**Decision**: Store `judge_agent_fqn VARCHAR(512)` and `enforcer_agent_fqn VARCHAR(512)` as strings (not FK to `agents(id)`) in `governance_verdicts` and `enforcement_actions`. Store `target_agent_fqn VARCHAR(512)` similarly.

**Rationale**: Verdicts and enforcement actions are immutable audit records. If a judge, enforcer, or target agent is deleted from the registry, the audit record MUST remain readable (spec edge case: "target deleted mid-pipeline"). A hard FK would require `ON DELETE SET NULL` which loses the identity. FQNs preserve human-readable identity in the audit trail even after agent deletion.

**Exception**: `verdict_id` in `enforcement_actions` is a real FK with `ON DELETE CASCADE` because enforcement actions cannot outlive their parent verdicts (FR-016, SC-010).

**Alternatives considered**: FK with SET NULL — would lose agent identity in audit; storing both FK and FQN — redundant and harder to maintain.

---

## Decision 5: Observer Signal Input Channel — monitor.alerts (Existing Topic)

**Decision**: The governance pipeline consumes observer signals from the existing `monitor.alerts` Kafka topic. A new `ObserverSignalConsumer` in `governance/consumers.py` subscribes with consumer group `governance-observer-signals`.

**Rationale**: `monitor.alerts` is the platform's existing alert channel (confirmed in `execution/events.py:149`, `ws_hub/subscription.py:35`). Observer agents already emit to this topic. The spec says "observer agents continue to emit signals through existing mechanisms." No new topic is needed for the input side.

**Signal envelope**: Standard `EventEnvelope` format. The payload's `correlation_context.fleet_id` and `correlation_context.workspace_id` identify which governance chain to resolve.

**Alternatives considered**: New `observer.signals` topic — creates a parallel channel when `monitor.alerts` already serves this purpose; would require observer agents to emit to two topics.

---

## Decision 6: Governance Kafka Topics — New Event Definitions

**Decision**: Create `GovernanceEventType(StrEnum)` in `governance/events.py` with two values: `verdict_issued` and `enforcement_executed`. The two Kafka topics are `governance.verdict.issued` and `governance.enforcement.executed` (already registered in the constitution).

**Publisher functions**:
- `publish_verdict_issued(producer, verdict, correlation_ctx)` → topic `governance.verdict.issued`, key = `str(verdict.fleet_id or verdict.workspace_id)`
- `publish_enforcement_executed(producer, action, correlation_ctx)` → topic `governance.enforcement.executed`, key = `str(action.verdict_id)`

**Event registry**: Both event types registered in `register_governance_event_types()` called from `main.py` lifespan startup.

---

## Decision 7: Certificate Revocation Interface

**Decision**: The `revoke_cert` enforcement action calls `CertificationService.revoke(cert_id, reason, actor_id)` from `trust/service.py:122-152`.

**Signature**: `async def revoke(self, cert_id: UUID, reason: str, actor_id: str) -> CertificationResponse`

**EnforcerService dependency**: `EnforcerService` receives a `CertificationService` injected in `dependencies.py` (or lazily imported) to avoid cross-boundary DB access. The certification service is called via its service interface, not via direct DB access from governance.

**Rationale**: `CertificationService.revoke()` already handles status validation, event publishing (`certification.revoked`), and response. No re-implementation needed.

---

## Decision 8: Audit Query Role — AUDITOR

**Decision**: Governance audit queries (`FR-017`, `FR-018`) require `RoleType.AUDITOR`. The spec says "compliance-viewing role" — this maps to the existing `AUDITOR` role in `auth/schemas.py:20`. No new role needed.

**Rationale**: `AUDITOR` is the closest existing role. Introducing a new `COMPLIANCE_VIEWER` role would require auth + RBAC changes (out of scope per spec Out of Scope section which excludes role changes).

---

## Decision 9: Rate Limiting — Existing Redis Pattern

**Decision**: Per-observer rate limiting (`FR-024`) uses the existing `redis_client.check_rate_limit("governance", f"{observer_fqn}:{fleet_or_workspace_id}", limit, 60_000)` pattern from `common/clients/redis.py`.

**Config field**: `GovernanceSettings.rate_limit_per_observer_per_minute: int = 100` (configurable, not hardcoded per FR-024 "configured threshold").

**Where enforced**: In `JudgeService.process_signal()` before any evaluation. Excess signals: drop + log incident (spec edge case: "observer flood").

---

## Decision 10: Retention GC — APScheduler + CASCADE Delete

**Decision**: Retention GC is an APScheduler job in `main.py` (`governance-retention-gc`, interval `settings.governance.gc_interval_hours * 3600`). The job calls `governance_repo.delete_expired_verdicts(retention_days)`. `enforcement_actions.verdict_id` FK has `ON DELETE CASCADE` so actions are removed with their parent verdicts.

**Config**: `GovernanceSettings.retention_days: int = 90`.

**Rationale**: CASCADE ensures SC-010 ("enforcement actions cannot outlive their parent verdicts") is enforced at the DB level — no application-level enforcement of cascade ordering needed.

---

## Decision 11: JudgeService as oje_service for FleetGovernanceChainService

**Decision**: `FleetGovernanceChainService.trigger_oje_pipeline()` (fleets/governance.py:113) accepts `oje_service: Any | None`. The new `JudgeService` implements `async def process_fleet_anomaly_signal(fleet_id, chain, signal)` as a method. In `main.py` lifespan, `FleetGovernanceChainService` is instantiated with `oje_service=judge_service`.

**Rationale**: The stub was designed for exactly this integration. Wiring preserves backward compatibility (if `oje_service is None`, the stub returns `"status": "skipped"`) and requires no changes to `FleetGovernanceChainService` itself.

---

## Decision 12: Next Alembic Migration Number — 048

**Decision**: Migration file is `048_governance_pipeline.py` with `revision="048_governance_pipeline"` and `down_revision="047_notifications_alerts"`.

**Confirmed**: Scan of `apps/control-plane/migrations/versions/` shows 047 is the latest.

---

## Summary of Resolved Unknowns

| Unknown | Resolution |
|---|---|
| Does role_type have judge/enforcer? | YES — `registry/models.py:31-32`, no migration needed |
| Does fleet governance chain exist? | YES — table + service + router already in `fleets/`. Add `verdict_to_action_mapping` column only |
| Does workspace governance chain exist? | NO — new `workspace_governance_chains` table + service + router in `workspaces/` |
| Do verdict/action tables exist? | NO — created in migration 048 |
| Observer signal input channel? | `monitor.alerts` (existing) |
| Certification revocation interface? | `CertificationService.revoke(cert_id, reason, actor_id)` in `trust/service.py:122` |
| Audit role? | `RoleType.AUDITOR` (existing) |
| Next migration number? | 048 |
| Rate limiting pattern? | `redis_client.check_rate_limit()` from `common/clients/redis.py` |
