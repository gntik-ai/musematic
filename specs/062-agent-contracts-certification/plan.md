# Implementation Plan: Agent Contracts and Certification Enhancements

**Branch**: `062-agent-contracts-certification` | **Date**: 2026-04-19 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/062-agent-contracts-certification/spec.md`

## Summary

Add machine-enforceable agent contracts (task scope, quality thresholds, cost/time limits, enforcement policy) attachable to interactions and executions. Extend the existing `trust/` bounded context with: Alembic migration 049 (5 new tables + 4 table alterations); new flat service files `contract_service.py`, `contract_monitor.py`, `surveillance_service.py`; external certifier registration model; certification status lifecycle extension (`expiring`, `suspended`); and compliance KPI query endpoint. All changes are additive brownfield extensions — no existing files are rewritten.

## Technical Context

**Language/Version**: Python 3.12+ (control plane)  
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, Alembic 1.13+, aiokafka 0.11+, APScheduler 3.x, pytest + pytest-asyncio 8.x  
**Storage**: PostgreSQL 16 (5 new tables + 4 altered tables); Kafka topics: `workflow.runtime`, `runtime.lifecycle`, `policy.events`, `trust.events`  
**Testing**: pytest + pytest-asyncio 8.x  
**Target Platform**: Kubernetes / Linux server (control-plane profile)  
**Performance Goals**: Breach detection ≤1s p95 (SC-001), compliance query ≤3s p95 (SC-009)  
**Constraints**: Brownfield — extend `trust/` only, no subdirectory refactoring; migration 049; backward-compat (SC-013)  
**Scale/Scope**: Low-volume compliance queries (pull-based); contract monitor is event-driven (Kafka consumer)

## Constitution Check

| Rule | Check | Status |
|------|-------|--------|
| Brownfield Rule 1 — Never rewrite | All changes extend existing files or add new flat files | ✅ PASS |
| Brownfield Rule 2 — Alembic migration | All DDL in migration 049 | ✅ PASS |
| Brownfield Rule 3 — Preserve tests | New tests added; existing tests unmodified | ✅ PASS |
| Brownfield Rule 4 — Existing patterns | Flat trust structure preserved; APScheduler, Kafka consumer, event publisher patterns copied | ✅ PASS |
| Brownfield Rule 5 — Reference exact files | All modified files cited below | ✅ PASS |
| Brownfield Rule 6 — Additive enum values | `expiring` and `suspended` added to `CertificationStatus` | ✅ PASS |
| Brownfield Rule 7 — Backward-compatible APIs | `contract_id` nullable on interactions/executions; existing endpoints unchanged | ✅ PASS |
| Brownfield Rule 8 — Feature flags | No default behavior changes; contract attachment is opt-in | ✅ PASS |
| Principle III — Dedicated data stores | Compliance KPI uses PostgreSQL (not ClickHouse) — justified: low-volume compliance query joining existing PG tables; no pipeline into ClickHouse exists | ✅ JUSTIFIED |
| Principle IV — No cross-boundary DB access | Contract monitor reads contracts via `ContractService`; no direct cross-context queries | ✅ PASS |
| Principle VI — Machine-enforced policy | Contracts enforce at runtime via monitor (complements, not replaces, policy engine) | ✅ PASS |

**Post-Phase-1 re-check**: All constitution gates pass. No violations requiring amendment.

## Project Structure

### Documentation (this feature)

```text
specs/062-agent-contracts-certification/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 — 12 decisions
├── data-model.md        # Phase 1 — migration 049, models, schemas, interfaces
├── quickstart.md        # Phase 1 — 23 test scenarios
├── contracts/
│   └── rest-api.md      # Phase 1 — REST endpoints + Kafka event shapes
└── tasks.md             # Phase 2 output (from /speckit.tasks)
```

### Source Code — Files Modified or Created

```text
apps/control-plane/
├── migrations/versions/
│   └── 049_agent_contracts_and_certification.py   [NEW]
└── src/platform/
    ├── trust/
    │   ├── models.py                               [MODIFY] — add Certifier, AgentContract,
    │   │                                             ContractBreachEvent, ReassessmentRecord,
    │   │                                             TrustRecertificationRequest classes;
    │   │                                             extend TrustCertification with
    │   │                                             external_certifier_id, reassessment_schedule;
    │   │                                             extend CertificationStatus enum
    │   ├── contract_schemas.py                     [NEW] — CertifierCreate/Response,
    │   │                                             AgentContractCreate/Response/Update,
    │   │                                             ContractBreachEventResponse,
    │   │                                             ReassessmentCreate/Response,
    │   │                                             ComplianceRateQuery/Response,
    │   │                                             DismissSuspensionRequest
    │   ├── contract_service.py                     [NEW] — ContractService (CRUD + attach + KPI)
    │   ├── contract_monitor.py                     [NEW] — ContractMonitorConsumer
    │   ├── surveillance_service.py                 [NEW] — SurveillanceService (scheduler + consumer)
    │   ├── service.py                              [MODIFY] — extend CertificationService:
    │   │                                             issue_with_certifier(), dismiss_suspension(),
    │   │                                             extend expire_stale() for expiring→expired
    │   ├── router.py                               [MODIFY] — add 15 new endpoints (certifiers,
    │   │                                             contracts, compliance, reassessments,
    │   │                                             recertification-requests, issue-with-certifier,
    │   │                                             dismiss-suspension)
    │   ├── events.py                               [MODIFY] — add TrustEventType values:
    │   │                                             contract.breach, contract.enforcement,
    │   │                                             certification.expiring, certification.suspended
    │   ├── repository.py                           [MODIFY] — add ContractRepository,
    │   │                                             CertifierRepository, BreachEventRepository,
    │   │                                             ReassessmentRepository (query methods)
    │   └── dependencies.py                         [MODIFY] — add get_contract_service(),
    │                                                get_surveillance_service() dependencies
    ├── interactions/
    │   └── models.py                               [MODIFY] — add contract_id, contract_snapshot
    ├── execution/
    │   └── models.py                               [MODIFY] — add contract_id, contract_snapshot
    └── main.py                                     [MODIFY] — register ContractMonitorConsumer
                                                      and SurveillanceConsumer with EventConsumerManager;
                                                      add APScheduler jobs:
                                                        trust-surveillance-cycle (interval, hours=1)
                                                        trust-grace-period-check (interval, hours=1)

tests/
├── unit/trust/
│   ├── test_contract_service.py                   [NEW]
│   ├── test_contract_monitor.py                   [NEW]
│   └── test_surveillance_service.py               [NEW]
└── integration/trust/
    └── test_contracts_integration.py               [NEW]
```

## Implementation Tasks

### Task 1 — Migration 049: DDL

**File**: `apps/control-plane/migrations/versions/049_agent_contracts_and_certification.py`

Create Alembic migration that:
1. Adds `expiring` (BEFORE expired) and `suspended` to `certification_status` PostgreSQL enum
2. Creates `certifiers` table (UUIDMixin, TimestampMixin, AuditMixin columns + name, organization, credentials JSONB, permitted_scopes JSONB, is_active BOOLEAN DEFAULT true)
3. Creates `agent_contracts` table (UUIDMixin, TimestampMixin, AuditMixin, workspace_id FK, agent_id VARCHAR(512), task_scope TEXT, expected_outputs JSONB, quality_thresholds JSONB, time_constraint_seconds INT, cost_limit_tokens INT, escalation_conditions JSONB, success_criteria JSONB, enforcement_policy VARCHAR(32) DEFAULT 'warn', is_archived BOOLEAN DEFAULT false; indexes on workspace_id, agent_id)
4. Creates `contract_breach_events` table (contract_id FK ON DELETE SET NULL, target_type VARCHAR(32), target_id UUID, breached_term VARCHAR(64), observed_value JSONB, threshold_value JSONB, enforcement_action VARCHAR(32), enforcement_outcome VARCHAR(32), contract_snapshot JSONB; indexes on contract_id, (target_type, target_id), created_at)
5. Creates `reassessment_records` table (certification_id FK ON DELETE CASCADE, verdict VARCHAR(32), reassessor_id VARCHAR(255), notes TEXT; index on certification_id)
6. Creates `trust_recertification_requests` table (certification_id FK ON DELETE CASCADE, trigger_type VARCHAR(32), trigger_reference TEXT, deadline TIMESTAMPTZ, resolution_status VARCHAR(32) DEFAULT 'pending', dismissal_justification TEXT; indexes on certification_id, deadline WHERE resolution_status='pending')
7. ALTERs `trust_certifications`: ADD external_certifier_id UUID FK ON DELETE SET NULL, ADD reassessment_schedule VARCHAR(64)
8. ALTERs `interactions`: ADD contract_id UUID FK ON DELETE SET NULL, ADD contract_snapshot JSONB; partial index WHERE contract_id IS NOT NULL
9. ALTERs `executions`: ADD contract_id UUID FK ON DELETE SET NULL, ADD contract_snapshot JSONB; partial index WHERE contract_id IS NOT NULL

**Downgrade**: DROP all new tables and columns; remove enum values (Alembic note: PostgreSQL does not support removing enum values; downgrade can only DROP columns that reference them).

---

### Task 2 — Extend `CertificationStatus` enum in `trust/models.py`

**File**: `apps/control-plane/src/platform/trust/models.py`

Add `expiring = "expiring"` (between `active` and `expired`) and `suspended = "suspended"` (after `revoked`) to the existing `CertificationStatus(StrEnum)` class.

---

### Task 3 — New SQLAlchemy models in `trust/models.py`

**File**: `apps/control-plane/src/platform/trust/models.py`

Add five new model classes (after `TrustCertification`):
- `Certifier` (UUIDMixin, TimestampMixin, AuditMixin)
- `AgentContract` (UUIDMixin, TimestampMixin, AuditMixin, WorkspaceScopedMixin)
- `ContractBreachEvent` (UUIDMixin, TimestampMixin)
- `ReassessmentRecord` (UUIDMixin, TimestampMixin, AuditMixin)
- `TrustRecertificationRequest` (UUIDMixin, TimestampMixin)

Also add to existing `TrustCertification` class:
- `external_certifier_id: Mapped[UUID | None]` FK to certifiers ON DELETE SET NULL
- `reassessment_schedule: Mapped[str | None]` VARCHAR(64)
- Relationships: `certifier`, `reassessment_records`, `recertification_requests`

---

### Task 4 — Extend `interactions/models.py` and `execution/models.py`

**Files**:
- `apps/control-plane/src/platform/interactions/models.py` (Interaction class)
- `apps/control-plane/src/platform/execution/models.py` (Execution class)

Add to each: `contract_id: Mapped[UUID | None]` FK to agent_contracts ON DELETE SET NULL; `contract_snapshot: Mapped[dict[str, Any] | None]` JSONB.

---

### Task 5 — `trust/contract_schemas.py` (new file)

**File**: `apps/control-plane/src/platform/trust/contract_schemas.py`

Define Pydantic schemas as specified in data-model.md:
- `CertifierCreate`, `CertifierResponse`, `CertifierUpdate`
- `AgentContractCreate`, `AgentContractResponse`, `AgentContractUpdate`
- `ContractBreachEventResponse`
- `ReassessmentCreate`, `ReassessmentResponse`
- `TrustRecertificationRequestResponse`
- `ComplianceRateQuery`, `ComplianceRateResponse`
- `DismissSuspensionRequest`

---

### Task 6 — Extend `trust/repository.py`

**File**: `apps/control-plane/src/platform/trust/repository.py`

Add repository methods (following the existing pattern in the file):

```python
# CertifierRepository methods
async def create_certifier(self, data: dict) -> Certifier: ...
async def get_certifier(self, certifier_id: UUID) -> Certifier | None: ...
async def list_certifiers(self, include_inactive: bool = False) -> list[Certifier]: ...
async def deactivate_certifier(self, certifier_id: UUID) -> Certifier: ...

# ContractRepository methods
async def create_contract(self, data: dict, workspace_id: UUID) -> AgentContract: ...
async def get_contract(self, contract_id: UUID) -> AgentContract | None: ...
async def list_contracts(self, workspace_id: UUID, agent_id: str | None, include_archived: bool) -> list[AgentContract]: ...
async def update_contract(self, contract_id: UUID, data: dict) -> AgentContract: ...

# Contract attachment methods
async def get_interaction_contract(self, interaction_id: UUID) -> AgentContract | None: ...
async def attach_contract_to_interaction(self, interaction_id: UUID, contract_id: UUID, snapshot: dict) -> None: ...
async def attach_contract_to_execution(self, execution_id: UUID, contract_id: UUID, snapshot: dict) -> None: ...

# BreachEvent methods
async def create_breach_event(self, data: dict) -> ContractBreachEvent: ...
async def list_breach_events(self, contract_id: UUID, **filters) -> list[ContractBreachEvent]: ...

# ReassessmentRecord methods
async def create_reassessment(self, certification_id: UUID, data: dict) -> ReassessmentRecord: ...
async def list_reassessments(self, certification_id: UUID) -> list[ReassessmentRecord]: ...

# RecertificationRequest methods
async def create_recertification_request(self, data: dict) -> TrustRecertificationRequest: ...
async def list_recertification_requests(self, **filters) -> list[TrustRecertificationRequest]: ...
async def get_pending_requests_past_deadline(self, now: datetime) -> list[TrustRecertificationRequest]: ...

# Compliance KPI
async def get_compliance_stats(self, scope: str, scope_id: str, start: datetime, end: datetime, bucket: str) -> dict: ...
```

---

### Task 7 — `trust/contract_service.py` (new file)

**File**: `apps/control-plane/src/platform/trust/contract_service.py`

Implement `ContractService` class with constructor `(repository: TrustRepository, publisher: TrustEventPublisher)` and all methods from data-model.md:
- `create_contract()` — validates FR-002 (allowed policy values, non-negative limits) and FR-025 (conflicting terms)
- `attach_to_interaction()` — idempotent (FR-026); rejects second different contract (FR-003); captures snapshot (FR-004)
- `attach_to_execution()` — same as above
- `get_compliance_rates()` — delegates to repository, computes rate, handles zero-attachment edge case

---

### Task 8 — Extend `trust/service.py` (CertificationService)

**File**: `apps/control-plane/src/platform/trust/service.py`

Add three methods to existing `CertificationService`:

1. `issue_with_certifier(cert_id, certifier_id, scope, actor_id)` — fetches certifier, validates scope in `permitted_scopes` (FR-010), sets `external_certifier_id`, publishes event
2. `dismiss_suspension(cert_id, justification, actor_id)` — validates cert is `suspended`, transitions to `active`, updates active recertification request with `dismissed` status and justification, appends audit record (FR-024)
3. Extend `expire_stale()` — add case: `CertificationStatus.expiring → expired` when `expires_at < now()` (current implementation only handles `active → expired`; also update to NOT skip certs in `expiring` status)

---

### Task 9 — `trust/contract_monitor.py` (new file)

**File**: `apps/control-plane/src/platform/trust/contract_monitor.py`

Implement `ContractMonitorConsumer`:

```python
class ContractMonitorConsumer:
    def register(self, manager: EventConsumerManager) -> None: ...

    async def handle_event(self, envelope: EventEnvelope) -> None:
        # 1. Extract execution_id / interaction_id from envelope
        # 2. Look up attached contract snapshot (contract_service.get_attached_snapshot())
        # 3. If no contract: return (backward compat, FR-027)
        # 4. Evaluate terms based on event payload:
        #    - workflow.runtime: check token count vs cost_limit_tokens
        #    - runtime.lifecycle (completed): check elapsed time vs time_constraint_seconds
        # 5. On breach: create ContractBreachEvent, call _enforce()
        # 6. Publish trust.contract.breach event

    async def _enforce(self, breach, snapshot, target_type, target_id) -> str:
        # warn → log only
        # throttle → publish throttle signal to monitor.alerts
        # escalate → publish to monitor.alerts (escalation)
        # terminate → publish terminate request; record failure if termination API call fails
        # Returns enforcement_outcome: "success" | "failed"
```

---

### Task 10 — `trust/surveillance_service.py` (new file)

**File**: `apps/control-plane/src/platform/trust/surveillance_service.py`

Implement `SurveillanceService`:

```python
class SurveillanceService:
    async def run_surveillance_cycle(self) -> None:
        # 1. Get all active/expiring certifications with expires_at set
        # 2. For each: if expires_at within warning_window (default 7d) → transition to "expiring", publish event, fire alert
        # 3. For cron-scheduled certifications: evaluate reassessment_schedule vs last reassessment date
        #    if due: trigger reassessment (create ReassessmentRecord with verdict=action_required, notify)

    async def check_grace_period_expiry(self) -> None:
        # Get suspended TrustRecertificationRequests where deadline < now()
        # For each: transition certification to "revoked" (reason: recertification timeout)
        # Resolve the request with status=revoked

    async def handle_material_change(self, envelope: EventEnvelope) -> None:
        # Extract agent_id from event
        # Find active/expiring certifications for agent_id
        # For each: transition to "suspended", create TrustRecertificationRequest
        # (trigger_type derived from event_type: policy.* → "policy", registry/agent.* → "revision")
        # Set deadline = now() + grace_period_days (default 14)
        # Publish trust.certification.suspended event + monitor.alerts

    def register(self, manager: EventConsumerManager) -> None:
        manager.subscribe("policy.events", f"...trust-surveillance-material-change", self.handle_material_change)
        manager.subscribe("trust.events", f"...trust-surveillance-revision-signals", self.handle_material_change)
```

---

### Task 11 — Extend `trust/events.py`

**File**: `apps/control-plane/src/platform/trust/events.py`

Add to existing `TrustEventType(StrEnum)`:
- `contract_breach = "trust.contract.breach"`
- `contract_enforcement = "trust.contract.enforcement"`
- `certification_expiring = "trust.certification.expiring"`
- `certification_suspended = "trust.certification.suspended"`

Register new event types with `event_registry` (following existing `event_registry.register(...)` pattern in the file).

Add publisher methods to `TrustEventPublisher`:
- `publish_contract_breach(payload, correlation_ctx)`
- `publish_contract_enforcement(payload, correlation_ctx)`
- `publish_certification_expiring(payload, correlation_ctx)`
- `publish_certification_suspended(payload, correlation_ctx)`

---

### Task 12 — Extend `trust/router.py`

**File**: `apps/control-plane/src/platform/trust/router.py`

Add 15 new route handlers (all additive, no existing routes modified):

**Certifier endpoints** (4):
- `POST /certifiers` (201)
- `GET /certifiers` (200)
- `GET /certifiers/{certifier_id}` (200)
- `DELETE /certifiers/{certifier_id}` (204)

**Contract endpoints** (7):
- `POST /contracts` (201)
- `GET /contracts` (200)
- `GET /contracts/{contract_id}` (200)
- `PUT /contracts/{contract_id}` (200)
- `DELETE /contracts/{contract_id}` (204)
- `POST /contracts/{contract_id}/attach-interaction` (204)
- `POST /contracts/{contract_id}/attach-execution` (204)

**Contract breach query** (1):
- `GET /contracts/{contract_id}/breaches` (200)

**Compliance KPI** (1):
- `GET /compliance/rates` (200)

**Certification extensions** (3):
- `POST /certifications/{certification_id}/issue-with-certifier` (200)
- `POST /certifications/{certification_id}/dismiss-suspension` (200)
- `GET /certifications/{certification_id}/reassessments` (200)
- `POST /certifications/{certification_id}/reassessments` (201)

**Recertification requests** (2):
- `GET /recertification-requests` (200)
- `GET /recertification-requests/{request_id}` (200)

---

### Task 13 — Extend `trust/dependencies.py`

**File**: `apps/control-plane/src/platform/trust/dependencies.py`

Add FastAPI dependency functions:
- `get_contract_service(db: AsyncSession = Depends(get_db), producer = Depends(get_event_producer)) -> ContractService`
- `get_surveillance_service(db: AsyncSession = Depends(get_db), producer = Depends(get_event_producer)) -> SurveillanceService`

---

### Task 14 — Wire in `main.py`

**File**: `apps/control-plane/src/platform/main.py`

In the lifespan/startup section:

1. Register `ContractMonitorConsumer` with the `EventConsumerManager`:
   ```python
   contract_monitor = ContractMonitorConsumer(contract_service)
   contract_monitor.register(consumer_manager)
   ```

2. Register `SurveillanceService` consumer subscriptions:
   ```python
   surveillance_svc = SurveillanceService(...)
   surveillance_svc.register(consumer_manager)
   ```

3. Add APScheduler jobs to the trust scheduler:
   ```python
   scheduler.add_job(
       surveillance_svc.run_surveillance_cycle,
       "interval", hours=1, id="trust-surveillance-cycle"
   )
   scheduler.add_job(
       surveillance_svc.check_grace_period_expiry,
       "interval", hours=1, id="trust-grace-period-check"
   )
   ```

---

### Task 15 — Unit tests

**Files**:
- `tests/unit/trust/test_contract_service.py` — ContractService: create/update/archive contract, attach interaction/execution (idempotent, conflict, snapshot capture), compliance rate with zero/non-zero attachments
- `tests/unit/trust/test_contract_monitor.py` — handle_event: no contract → skip; cost breach → warn; time breach → terminate; quality breach → warn; enforcement failure handling
- `tests/unit/trust/test_surveillance_service.py` — run_surveillance_cycle: active within window → no change; active approaching expiry → expiring; expiring past expiry → expired; reassessment schedule due → verdict created; check_grace_period_expiry: past deadline → revoked; handle_material_change: active cert → suspended, recertification request created

**Integration test**:
- `tests/integration/trust/test_contracts_integration.py` — end-to-end contract attach + monitor breach flow against real DB; certification lifecycle transitions; compliance rate aggregation query with known dataset

## Estimated Effort

4 story points (~2 days)

## Dependencies

- **Existing**: `trust/` bounded context (BE-012 / feature 012 Trust & Certification)
- **Existing**: `interactions/` bounded context (interaction.py model)
- **Existing**: `execution/` bounded context (execution.py model)
- **Existing**: APScheduler already wired in `main.py` for trust scheduler
- **Existing**: `EventConsumerManager` in `common/events/consumer.py`
- **Existing**: `TrustEventPublisher` in `trust/events.py`
- **Existing**: `trust/repository.py` patterns for query methods
