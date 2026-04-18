# Implementation Plan: Judge/Enforcer Governance Pipeline

**Branch**: `061-judge-enforcer-governance` | **Date**: 2026-04-18 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/061-judge-enforcer-governance/spec.md`

## Summary

New `governance/` bounded context that implements the Observer→Judge→Enforcer pipeline. Consumes observer signals from `monitor.alerts`, evaluates them via a configurable judge chain, persists verdicts, and drives enforcement actions (block/quarantine/notify/revoke_cert/log_and_continue). Fleet governance chains already exist (`fleet_governance_chains` table, `FleetGovernanceChainService`); this feature adds `verdict_to_action_mapping` to fleet chains, creates a parallel `workspace_governance_chains` table, creates two new audit tables (`governance_verdicts`, `enforcement_actions`), and wires the full pipeline via Kafka (`governance.verdict.issued`, `governance.enforcement.executed`). Role types `judge` and `enforcer` are already present in `AgentRoleType`.

## Technical Context

**Language/Version**: Python 3.12+  
**Primary Dependencies**: FastAPI 0.115+, aiokafka 0.11+, SQLAlchemy 2.x async, redis-py 5.x async (rate limiting), APScheduler 3.x (retention GC), grpcio 1.65+ (CertificationService call), pytest + pytest-asyncio 8.x — all already in requirements.txt  
**Storage**: PostgreSQL 16 (4 table changes: 2 new tables, 1 new workspace table, 1 additive column); Kafka (2 existing topics from constitution now with producers); Redis (rate limiting, existing pattern)  
**Testing**: pytest + pytest-asyncio 8.x  
**Target Platform**: Linux/Kubernetes (platform-control namespace)  
**Project Type**: Bounded context in the Python control-plane modular monolith  
**Performance Goals**: p95 judge evaluation ≤5s (SC-001), p95 verdict-to-action ≤10s (SC-002)  
**Constraints**: No cross-boundary DB access; existing `FleetGovernanceChainService` must remain unchanged except additive `verdict_to_action_mapping` wiring; `AgentRoleType` unchanged (already has judge/enforcer)  
**Scale/Scope**: One new bounded context (~14 files), migration 048, 4 modified existing files, 1 new workspace governance file

## Constitution Check

| Rule | Status | Notes |
|---|---|---|
| Brownfield Rule 1: Never rewrite | ✅ PASS | `FleetGovernanceChainService`, `workspaces/`, `fleets/` all receive additive changes only |
| Brownfield Rule 2: Alembic migrations | ✅ PASS | Migration 048; no raw DDL |
| Brownfield Rule 3: Preserve existing tests | ✅ PASS | Existing fleet/workspace/registry tests unaffected |
| Brownfield Rule 4: Use existing patterns | ✅ PASS | Follows `fleets/governance.py` pattern for workspace chain service; `EventProducer.publish()` for Kafka; `check_rate_limit()` for rate limiting; `APScheduler` for GC |
| Brownfield Rule 5: Reference exact files | ✅ PASS | All modified files cited below with line references |
| Brownfield Rule 6: Additive enum values | ✅ PASS | `AgentRoleType.judge/enforcer` already present (registry/models.py:31-32); no enum change needed |
| Brownfield Rule 7: Backward-compatible APIs | ✅ PASS | `verdict_to_action_mapping` added as optional with default `{}` to `FleetGovernanceChainUpdate`; existing callers continue working |
| Brownfield Rule 8: Feature flags | ✅ PASS | Default posture is "no chain = no enforcement"; no existing behavior changed |
| Principle I: Modular monolith | ✅ PASS | New bounded context in control plane; no new process |
| Principle IV: No cross-boundary DB access | ✅ PASS | `governance/` reads only its own tables; calls `CertificationService` via in-process service interface for `revoke_cert` |
| Kafka-first for async | ✅ PASS | Judge→Enforcer hand-off via `governance.verdict.issued` Kafka topic; no direct in-process call from judge to enforcer |

**POST-DESIGN RE-CHECK**: All gates pass. No violations.

## Project Structure

### Documentation (this feature)

```text
specs/061-judge-enforcer-governance/
├── plan.md              ← this file
├── research.md          ← Phase 0 output
├── data-model.md        ← Phase 1 output
├── quickstart.md        ← Phase 1 output
├── contracts/
│   └── rest-api.md      ← Phase 1 output
└── tasks.md             ← Phase 2 output (via /speckit.tasks)
```

### Source Code (repository root)

```text
apps/control-plane/src/platform/

# NEW — governance bounded context
governance/
├── __init__.py
├── models.py             ← GovernanceVerdict, EnforcementAction, VerdictType, ActionType
├── schemas.py            ← Pydantic request/response + VerdictListQuery
├── events.py             ← GovernanceEventType, VerdictIssuedPayload, EnforcementExecutedPayload, publish fns
├── exceptions.py         ← GovernanceError, VerdictNotFoundError, ChainConfigError
├── repository.py         ← GovernanceRepository (async SQLAlchemy verdicts + actions)
├── dependencies.py       ← get_governance_service()
├── services/
│   ├── __init__.py
│   ├── pipeline_config.py    ← PipelineConfigService (chain resolution + validation)
│   ├── judge_service.py      ← JudgeService (signal evaluation, verdict issuance, layered chains)
│   └── enforcer_service.py   ← EnforcerService (action dispatch, idempotency)
├── consumers.py          ← ObserverSignalConsumer (monitor.alerts), VerdictConsumer (governance.verdict.issued)
└── router.py             ← Audit query endpoints + governance service class

# MODIFIED — workspaces bounded context (additive)
workspaces/models.py      ← Add WorkspaceGovernanceChain model (append — Brownfield Rule 1)
workspaces/schemas.py     ← Add WorkspaceGovernanceChain schemas (append)
workspaces/governance.py  ← NEW file: WorkspaceGovernanceChainService (mirrors fleets/governance.py)
workspaces/router.py      ← Add 3 workspace governance chain endpoints (additive)

# MODIFIED — fleets bounded context (additive)
fleets/models.py          ← Add verdict_to_action_mapping field to FleetGovernanceChain (line ~222)
fleets/schemas.py         ← Add verdict_to_action_mapping to Update + Response schemas (lines 166, 187)
fleets/governance.py      ← Persist verdict_to_action_mapping in update_chain(); wire oje_service

# MODIFIED — infrastructure
migrations/versions/048_governance_pipeline.py   ← New migration
main.py                        ← Wire ObserverSignalConsumer, VerdictConsumer + APScheduler retention GC
common/config.py               ← Add GovernanceSettings section
```

## Implementation Tasks

### Task 1 — Alembic migration 048
**File**: `apps/control-plane/migrations/versions/048_governance_pipeline.py`  
Create migration with `revision="048_governance_pipeline"`, `down_revision="047_notifications_alerts"`.  
- Create PG enums: `verdicttype` (COMPLIANT/WARNING/VIOLATION/ESCALATE_TO_HUMAN), `enforcementactiontype` (block/quarantine/notify/revoke_cert/log_and_continue).  
- Create table `governance_verdicts` per `data-model.md` Section 1.  
- Create table `enforcement_actions` per `data-model.md` Section 1.  
- Create table `workspace_governance_chains` per `data-model.md` Section 1.  
- Add column `verdict_to_action_mapping JSONB NOT NULL DEFAULT '{}'` to `fleet_governance_chains`.

### Task 2 — GovernanceSettings in config.py
**File**: `apps/control-plane/src/platform/common/config.py`  
Add `GovernanceSettings` Pydantic sub-model with fields:
- `rate_limit_per_observer_per_minute: int = 100`
- `retention_days: int = 90`
- `gc_interval_hours: int = 24`
- `judge_timeout_seconds: int = 30`

Mount as `governance: GovernanceSettings` in `PlatformSettings`.

### Task 3 — governance/models.py
**File**: `apps/control-plane/src/platform/governance/models.py`  
Create `VerdictType(StrEnum)`, `ActionType(StrEnum)`, `TERMINAL_VERDICT_TYPES`, `GovernanceVerdict`, `EnforcementAction` per `data-model.md` Section 2. Follow `fleets/models.py` import style.

### Task 4 — governance/schemas.py
**File**: `apps/control-plane/src/platform/governance/schemas.py`  
Create `VerdictListQuery`, `GovernanceVerdictRead`, `GovernanceVerdictDetail`, `EnforcementActionRead`, `VerdictListResponse`, `EnforcementActionListResponse` per `data-model.md` Section 3 and `contracts/rest-api.md`.

### Task 5 — governance/events.py
**File**: `apps/control-plane/src/platform/governance/events.py`  
Create `GovernanceEventType(StrEnum)` with `verdict_issued = "governance.verdict.issued"` and `enforcement_executed = "governance.enforcement.executed"`. Create `VerdictIssuedPayload`, `EnforcementExecutedPayload`. Add `publish_verdict_issued(producer, payload, correlation_ctx)` and `publish_enforcement_executed(producer, payload, correlation_ctx)`. Add `register_governance_event_types()`. Follow `trust/events.py` pattern.

### Task 6 — governance/exceptions.py
**File**: `apps/control-plane/src/platform/governance/exceptions.py`  
Create `GovernanceError(PlatformError)`, `VerdictNotFoundError`, `ChainConfigError` (used for role mismatch / missing agent / self-referential). Follow `fleets/exceptions.py` style.

### Task 7 — governance/repository.py
**File**: `apps/control-plane/src/platform/governance/repository.py`  
`GovernanceRepository` class with `AsyncSession`:
- `create_verdict(verdict: GovernanceVerdict) → GovernanceVerdict`
- `get_verdict(verdict_id: UUID) → GovernanceVerdict | None`
- `list_verdicts(query: VerdictListQuery) → (list[GovernanceVerdict], next_cursor | None, total)`
- `create_enforcement_action(action: EnforcementAction) → EnforcementAction`
- `list_enforcement_actions(query: EnforcementActionListQuery) → (list[EnforcementAction], next_cursor | None, total)`
- `get_enforcement_action_for_verdict(verdict_id: UUID) → EnforcementAction | None` (idempotency check)
- `delete_expired_verdicts(retention_days: int) → int` (count deleted; cascade handles actions)

### Task 8 — workspaces/models.py — add WorkspaceGovernanceChain
**File**: `apps/control-plane/src/platform/workspaces/models.py`  
Append `WorkspaceGovernanceChain(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin)` per `data-model.md` Section 2. Do NOT modify any existing class.

### Task 9 — workspaces/schemas.py — add workspace chain schemas
**File**: `apps/control-plane/src/platform/workspaces/schemas.py`  
Append `WorkspaceGovernanceChainUpdate` (with FQN list validator), `WorkspaceGovernanceChainResponse`, `WorkspaceGovernanceChainListResponse` per `data-model.md` Section 3.

### Task 10 — workspaces/governance.py — WorkspaceGovernanceChainService
**File**: `apps/control-plane/src/platform/workspaces/governance.py` (new file)  
`WorkspaceGovernanceChainService` mirroring `fleets/governance.py`. Methods: `get_chain(workspace_id)`, `update_chain(workspace_id, request)`, `get_chain_history(workspace_id)`. Publishes `workspace.governance_chain_updated` event (or use existing workspace event type if present). Injects `PipelineConfigService.validate_chain_update()` before persisting.

### Task 11 — workspaces/router.py — add workspace governance chain endpoints
**File**: `apps/control-plane/src/platform/workspaces/router.py`  
Add three endpoints (additive — existing endpoints unchanged):
- `GET /{workspace_id}/governance-chain` → `WorkspaceGovernanceChainResponse`
- `PUT /{workspace_id}/governance-chain` → `WorkspaceGovernanceChainResponse`
- `GET /{workspace_id}/governance-chain/history` → `WorkspaceGovernanceChainListResponse`

### Task 12 — fleets/models.py — add verdict_to_action_mapping field
**File**: `apps/control-plane/src/platform/fleets/models.py`  
Append `verdict_to_action_mapping: Mapped[dict]` field to `FleetGovernanceChain` class (after `is_default`, before the closing of the class body, ~line 222). Follow exact JSONB column pattern used for `observer_fqns`.

### Task 13 — fleets/schemas.py — add verdict_to_action_mapping to schemas
**File**: `apps/control-plane/src/platform/fleets/schemas.py`  
In `FleetGovernanceChainUpdate` (line 166): add `verdict_to_action_mapping: dict[str, str] = Field(default_factory=dict)`.  
In `FleetGovernanceChainResponse` (line 187): add `verdict_to_action_mapping: dict[str, str]`.

### Task 14 — fleets/governance.py — persist mapping + wire oje_service
**File**: `apps/control-plane/src/platform/fleets/governance.py`  
In `update_chain()`: pass `verdict_to_action_mapping=request.verdict_to_action_mapping` to `FleetGovernanceChain(...)` constructor.  
In `trigger_oje_pipeline()`: call `PipelineConfigService.validate_chain_config()` before passing to `oje_service`. No other changes.

### Task 15 — governance/services/pipeline_config.py
**File**: `apps/control-plane/src/platform/governance/services/pipeline_config.py`  
`PipelineConfigService` with:
- `resolve_chain(fleet_id, workspace_id) → ChainConfig | None` — workspace chain wins (FR-013); returns None if neither configured
- `validate_chain_update(observer_fqns, judge_fqns, enforcer_fqns) → None` — FR-011 (role check via registry), FR-012 (existence check), FR-025 (self-referential check)

`ChainConfig` dataclass per `data-model.md` Section 5.

### Task 16 — governance/services/judge_service.py
**File**: `apps/control-plane/src/platform/governance/services/judge_service.py`  
`JudgeService` with:
- `process_signal(signal_envelope, fleet_id, workspace_id) → list[GovernanceVerdict]`
  - Applies per-observer rate limit (FR-024)
  - Calls `pipeline_config.resolve_chain()` — skips if None (FR-003 / no-chain posture)
  - Iterates judge_fqns in order (US5 layered judges)
  - For each judge: builds verdict, persists, publishes `verdict_issued`
  - Stops iteration on terminal verdict (VIOLATION or ESCALATE_TO_HUMAN)
  - Judge unavailable timeout → emit ESCALATE_TO_HUMAN (FR-021)
  - Missing policy → ESCALATE_TO_HUMAN (FR-020)
  - Missing required verdict fields → reject + ESCALATE_TO_HUMAN (FR-023)
- `process_fleet_anomaly_signal(fleet_id, chain, signal) → dict` — oje_service interface for `FleetGovernanceChainService`

### Task 17 — governance/services/enforcer_service.py
**File**: `apps/control-plane/src/platform/governance/services/enforcer_service.py`  
`EnforcerService` with:
- `process_verdict(verdict: GovernanceVerdict) → EnforcementAction`
  - Idempotency check: `repo.get_enforcement_action_for_verdict(verdict.id)` — return existing if found (FR-022)
  - Resolves chain config for the verdict's fleet/workspace
  - Looks up `verdict_to_action_mapping[verdict.verdict_type]`; defaults to `log_and_continue` if missing (FR-010)
  - Dispatches: `_execute_block()`, `_execute_quarantine()`, `_execute_notify()`, `_execute_revoke_cert()`, `_execute_log_and_continue()`
  - `_execute_revoke_cert()` calls `CertificationService.revoke(cert_id, reason, actor_id)` via injected service
  - Target deleted edge case: catch + persist outcome with "target_not_found" (FR-026)
  - Persists enforcement action + publishes `enforcement_executed` event (FR-008, FR-009)

### Task 18 — governance/consumers.py
**File**: `apps/control-plane/src/platform/governance/consumers.py`  
Two consumer classes:

`ObserverSignalConsumer` — consumer group `governance-observer-signals`:
- Subscribes to `monitor.alerts` topic
- Deserializes `EventEnvelope`, extracts `fleet_id` and `workspace_id` from `correlation_context`
- Calls `judge_service.process_signal(envelope, fleet_id, workspace_id)`
- Discards events with no `fleet_id` AND no `workspace_id` (log + skip — no governance target)

`VerdictConsumer` — consumer group `governance-verdict-enforcer`:
- Subscribes to `governance.verdict.issued` topic
- Deserializes `VerdictIssuedPayload`, loads full `GovernanceVerdict` from repo
- Calls `enforcer_service.process_verdict(verdict)` only for terminal verdict types (VIOLATION/ESCALATE_TO_HUMAN) unless a non-terminal type has an explicit mapping
- Handles enforcer unavailable: log + retry via APScheduler pending queue

### Task 19 — governance/router.py
**File**: `apps/control-plane/src/platform/governance/router.py`  
`router = APIRouter(prefix="/governance", tags=["governance"])`.  
Four endpoints per `contracts/rest-api.md`:
- `GET /verdicts` → `VerdictListResponse` (AUDITOR role, FR-017, FR-018)
- `GET /verdicts/{verdict_id}` → `GovernanceVerdictDetail` (AUDITOR role)
- `GET /enforcement-actions` → `EnforcementActionListResponse` (AUDITOR role)

GovernanceService class (thin façade): `list_verdicts(query)`, `get_verdict(verdict_id)`, `list_enforcement_actions(query)`.

### Task 20 — main.py — wire consumers and scheduler
**File**: `apps/control-plane/src/platform/main.py`  
Follow existing connector/notifications consumer patterns:
1. Call `register_governance_event_types()` in lifespan startup.
2. Instantiate `ObserverSignalConsumer` and `VerdictConsumer` in lifespan startup.
3. Start both consumers (`aiokafka start()`).
4. Wire `JudgeService` as `oje_service` in `FleetGovernanceChainService` instantiation.
5. Register APScheduler job: `governance-retention-gc`, interval `settings.governance.gc_interval_hours * 3600`, calls `_run_governance_retention_gc()`.
6. Register `governance.router` in `app.include_router()` with prefix `/api/v1`.

### Task 21 — Tests
**Files**:
- `apps/control-plane/tests/unit/governance/test_pipeline_config.py` — unit tests for `PipelineConfigService.validate_chain_update()`: role mismatch (S12), missing agent (S13), self-referential (S22).
- `apps/control-plane/tests/unit/governance/test_judge_service.py` — unit tests for `JudgeService.process_signal()`: VIOLATION verdict (S1), COMPLIANT (S2), no-chain skip (S4), missing policy → ESCALATE (S5), rate limiting drop (S21), layered chain terminal stop (S20).
- `apps/control-plane/tests/unit/governance/test_enforcer_service.py` — unit tests for `EnforcerService.process_verdict()`: block action (S6), default log_and_continue (S9), idempotency (S10), target deleted (S23).
- `apps/control-plane/tests/integration/governance/test_governance_api.py` — integration tests for all 3 audit endpoints: list verdicts with filters (S15), verdict detail with enforcement action (S16), non-AUDITOR denied (S17).

## Complexity Tracking

No constitution violations. No complexity justification needed.

## Estimated Effort

4 story points (~2 days)

## Artifacts Generated

| Artifact | Path |
|---|---|
| Research | `specs/061-judge-enforcer-governance/research.md` |
| Data Model | `specs/061-judge-enforcer-governance/data-model.md` |
| REST API Contracts | `specs/061-judge-enforcer-governance/contracts/rest-api.md` |
| Quickstart / Scenarios | `specs/061-judge-enforcer-governance/quickstart.md` |
| Plan (this file) | `specs/061-judge-enforcer-governance/plan.md` |
