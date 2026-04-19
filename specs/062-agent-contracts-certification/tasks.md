# Tasks: Agent Contracts and Certification Enhancements

**Input**: Design documents from `specs/062-agent-contracts-certification/`  
**Prerequisites**: plan.md ✅ | spec.md ✅ | research.md ✅ | data-model.md ✅ | contracts/rest-api.md ✅ | quickstart.md ✅

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no incomplete dependencies)
- **[US#]**: User story this task belongs to (from spec.md)

---

## Phase 1: Setup

**Purpose**: Create the Alembic migration that enables all subsequent model work.

- [X] T001 Create Alembic migration 049 at `apps/control-plane/migrations/versions/049_agent_contracts_and_certification.py`: (1) ALTER TYPE certification_status ADD VALUE 'expiring' BEFORE 'expired'; ADD VALUE 'suspended'; (2) CREATE TABLE certifiers (UUIDMixin cols + name VARCHAR(256), organization VARCHAR(256), credentials JSONB, permitted_scopes JSONB, is_active BOOLEAN DEFAULT true); (3) CREATE TABLE agent_contracts (UUIDMixin + AuditMixin + workspace_id FK + agent_id VARCHAR(512) + task_scope TEXT + expected_outputs/quality_thresholds/escalation_conditions/success_criteria JSONB + time_constraint_seconds INT + cost_limit_tokens INT + enforcement_policy VARCHAR(32) DEFAULT 'warn' + is_archived BOOLEAN DEFAULT false; indexes on workspace_id, agent_id); (4) CREATE TABLE contract_breach_events (contract_id FK ON DELETE SET NULL, target_type VARCHAR(32), target_id UUID, breached_term VARCHAR(64), observed_value JSONB, threshold_value JSONB, enforcement_action VARCHAR(32), enforcement_outcome VARCHAR(32), contract_snapshot JSONB; indexes on contract_id, (target_type,target_id), created_at); (5) CREATE TABLE reassessment_records (certification_id FK ON DELETE CASCADE, verdict VARCHAR(32), reassessor_id VARCHAR(255), notes TEXT; index on certification_id); (6) CREATE TABLE trust_recertification_requests (certification_id FK ON DELETE CASCADE, trigger_type VARCHAR(32), trigger_reference TEXT, deadline TIMESTAMPTZ, resolution_status VARCHAR(32) DEFAULT 'pending', dismissal_justification TEXT; indexes on certification_id, deadline WHERE resolution_status='pending'); (7) ALTER TABLE trust_certifications ADD external_certifier_id UUID FK ON DELETE SET NULL, ADD reassessment_schedule VARCHAR(64); (8) ALTER TABLE interactions ADD contract_id UUID FK ON DELETE SET NULL, ADD contract_snapshot JSONB; partial index WHERE contract_id IS NOT NULL; (9) ALTER TABLE executions ADD contract_id UUID FK ON DELETE SET NULL, ADD contract_snapshot JSONB; partial index WHERE contract_id IS NOT NULL; downgrade reverses all.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Models, schemas, events, and repository methods that ALL user stories depend on.

**⚠️ CRITICAL**: No user story work can begin until T002 and T007 are complete. T003–T006 can run in parallel after T002.

- [X] T002 Extend `apps/control-plane/src/platform/trust/models.py`: (a) add `expiring = "expiring"` (between active and expired) and `suspended = "suspended"` to existing `CertificationStatus(StrEnum)`; (b) add 5 new SQLAlchemy model classes after TrustCertification: `Certifier` (UUIDMixin+TimestampMixin+AuditMixin), `AgentContract` (UUIDMixin+TimestampMixin+AuditMixin+WorkspaceScopedMixin), `ContractBreachEvent` (UUIDMixin+TimestampMixin), `ReassessmentRecord` (UUIDMixin+TimestampMixin+AuditMixin), `TrustRecertificationRequest` (UUIDMixin+TimestampMixin) — use field definitions from data-model.md; (c) add to existing `TrustCertification` class: `external_certifier_id: Mapped[UUID | None]` FK to certifiers ON DELETE SET NULL, `reassessment_schedule: Mapped[str | None]` VARCHAR(64), and relationships `certifier`, `reassessment_records`, `recertification_requests`

- [X] T003 [P] Add to `Interaction` class in `apps/control-plane/src/platform/interactions/models.py`: `contract_id: Mapped[UUID | None]` FK to agent_contracts ON DELETE SET NULL, and `contract_snapshot: Mapped[dict[str, Any] | None]` JSONB column

- [X] T004 [P] Add to `Execution` class in `apps/control-plane/src/platform/execution/models.py`: `contract_id: Mapped[UUID | None]` FK to agent_contracts ON DELETE SET NULL, and `contract_snapshot: Mapped[dict[str, Any] | None]` JSONB column

- [X] T005 [P] Create `apps/control-plane/src/platform/trust/contract_schemas.py` with all Pydantic v2 schemas: `CertifierCreate` (name, organization, credentials, permitted_scopes), `CertifierResponse` (id + all fields + is_active, from_attributes=True), `AgentContractCreate` (agent_id FQN, task_scope, optional fields, enforcement_policy Literal with default "warn"), `AgentContractResponse` (all fields, from_attributes=True), `AgentContractUpdate` (all fields optional), `ContractBreachEventResponse`, `ReassessmentCreate` (verdict Literal["pass","fail","action_required"], notes), `ReassessmentResponse`, `TrustRecertificationRequestResponse`, `ComplianceRateQuery` (scope Literal["agent","fleet","workspace"], scope_id, start, end, bucket Literal["hourly","daily"]="daily"), `ComplianceRateResponse` (totals, compliance_rate float|None, breach_by_term dict, trend list), `DismissSuspensionRequest` (justification Field min_length=10)

- [X] T006 [P] Extend `apps/control-plane/src/platform/trust/events.py`: (a) add to existing `TrustEventType(StrEnum)`: `contract_breach = "trust.contract.breach"`, `contract_enforcement = "trust.contract.enforcement"`, `certification_expiring = "trust.certification.expiring"`, `certification_suspended = "trust.certification.suspended"`; (b) register each with `event_registry.register(event_type, schema)` following the existing pattern; (c) add publisher methods to `TrustEventPublisher`: `publish_contract_breach()`, `publish_contract_enforcement()`, `publish_certification_expiring()`, `publish_certification_suspended()` — follow the existing `_publish()` delegation pattern with correct topic (`trust.events`) and source (`platform.trust`)

- [X] T007 Extend `apps/control-plane/src/platform/trust/repository.py` with new query methods following the existing repository pattern: CertifierRepository — `create_certifier`, `get_certifier`, `list_certifiers(include_inactive)`, `deactivate_certifier`; ContractRepository — `create_contract`, `get_contract`, `list_contracts(workspace_id, agent_id, include_archived)`, `update_contract`, `archive_contract`; Attachment methods — `get_interaction_contract_snapshot(interaction_id)`, `attach_contract_to_interaction(interaction_id, contract_id, snapshot)` (raises ConflictError if already attached to different contract; no-op if same contract), `attach_contract_to_execution(execution_id, contract_id, snapshot)` (same idempotency); BreachEvent — `create_breach_event`, `list_breach_events(contract_id, **filters)`; Reassessment — `create_reassessment(certification_id, data)`, `list_reassessments(certification_id)`; RecertificationRequest — `create_recertification_request`, `list_recertification_requests(**filters)`, `get_pending_requests_past_deadline(now)`, `resolve_recertification_request(request_id, status, justification)`; Compliance stats — `get_compliance_stats(scope, scope_id, start, end, bucket)` using PostgreSQL aggregation over contract_breach_events + executions/interactions (returns dict with total_contract_attached, compliant, warned, throttled, escalated, terminated, breach_by_term counts, and trend time-series)

**Checkpoint**: Foundation complete — all 4 user stories can now be implemented.

---

## Phase 3: User Story 1 — Author Defines Contract and Attaches at Runtime (Priority: P1) 🎯 MVP

**Goal**: Create and manage contracts, attach them to interactions/executions with snapshot capture, and detect + enforce contract term breaches at runtime.

**Independent Test** (from quickstart.md S1–S6): Create a contract with `time_constraint_seconds=10, enforcement_policy=terminate`. Attach to an execution. Simulate runtime.lifecycle event with elapsed=15s. Verify ContractBreachEvent created with `breached_term=time_constraint`, `enforcement_action=terminate`. Verify second attachment of same contract is idempotent (204, no duplicate). Verify attachment of different contract raises 409.

- [X] T008 [US1] Implement `ContractService` class in `apps/control-plane/src/platform/trust/contract_service.py` with constructor `(repository: TrustRepository, publisher: TrustEventPublisher)` and methods: `create_contract(data, workspace_id, actor_id)` — validates FR-002 (enforcement_policy in allowed set; numeric limits ≥ 1) and FR-025 (cost_limit_tokens=0 with non-empty expected_outputs → raise ValidationError); `get_contract(contract_id)`; `list_contracts(workspace_id, agent_id, include_archived)`; `update_contract(contract_id, data, actor_id)` — validates same rules; `archive_contract(contract_id, actor_id)` — raises ConflictError if any in-flight executions have non-null contract_id pointing to this contract; `attach_to_interaction(interaction_id, contract_id)` — fetches contract snapshot, calls repository.attach_contract_to_interaction (idempotent FR-026, one-contract FR-003, snapshot FR-004); `attach_to_execution(execution_id, contract_id)` — same pattern; `get_attached_execution_snapshot(execution_id)` and `get_attached_interaction_snapshot(interaction_id)` — helpers for monitor use

- [X] T009 [P] [US1] Extend `apps/control-plane/src/platform/trust/dependencies.py` with FastAPI dependency `get_contract_service(db: AsyncSession = Depends(get_db), producer = Depends(get_event_producer)) -> ContractService` following the existing dependency pattern in the file

- [X] T010 [US1] Implement `ContractMonitorConsumer` class in `apps/control-plane/src/platform/trust/contract_monitor.py`: `register(manager)` subscribes to `workflow.runtime` (group `{settings.kafka.consumer_group}.trust-contract-monitor`) and `runtime.lifecycle` (group `{settings.kafka.consumer_group}.trust-contract-monitor-lifecycle`); `handle_event(envelope)` — (1) extract execution_id/interaction_id from envelope payload, (2) fetch attached contract snapshot via ContractService, (3) if no contract → return immediately (FR-027 backward compat), (4) evaluate applicable terms: for `workflow.runtime` events check token_count vs cost_limit_tokens, for `runtime.lifecycle` completed events check elapsed_seconds vs time_constraint_seconds, (5) on breach call `_evaluate_and_breach()`, (6) for each breach create ContractBreachEvent via repository, publish `trust.contract.breach` event; `_enforce(breach, snapshot)` — warn: log; throttle/escalate/terminate: publish to `monitor.alerts` topic with appropriate action type; returns outcome `"success"|"failed"` (terminate failure → quarantine note in enforcement_outcome)

- [X] T011 [US1] Add contract CRUD and breach query endpoints to `apps/control-plane/src/platform/trust/router.py`: `POST /contracts` (201, AGENT_OWNER or PLATFORM_ADMIN), `GET /contracts` (200, any workspace member, query params: agent_id, include_archived), `GET /contracts/{contract_id}` (200), `PUT /contracts/{contract_id}` (200, AGENT_OWNER or PLATFORM_ADMIN), `DELETE /contracts/{contract_id}` (204), `POST /contracts/{contract_id}/attach-interaction` (204, body: {interaction_id}), `POST /contracts/{contract_id}/attach-execution` (204, body: {execution_id}), `GET /contracts/{contract_id}/breaches` (200, cursor-paginated, query params: target_type, start, end) — all delegate to ContractService; use `_require_roles()` pattern from existing router

- [X] T012 [US1] Wire `ContractMonitorConsumer` in `apps/control-plane/src/platform/main.py`: in the lifespan startup block, instantiate `ContractMonitorConsumer(contract_service)` and call `contract_monitor.register(consumer_manager)` following the pattern used for other consumers (see governance consumers wiring)

---

## Phase 4: User Story 2 — Third-Party Certifier Issues Certification (Priority: P1)

**Goal**: Register external certifiers with scoped permissions; link them to certifications; validate scope at issuance time; certifier de-listing leaves existing certs valid.

**Independent Test** (from quickstart.md S7–S10): Register "ACME Labs" with permitted_scopes=["financial_calculations"]. Issue a certification with certifier_id=ACME, scope="financial_calculations" → succeeds. Attempt scope="medical_diagnosis" → 422. De-list ACME → existing cert stays active, new issuance from ACME → 409.

- [X] T013 [P] [US2] Add certifier management methods to existing `CertificationService` in `apps/control-plane/src/platform/trust/service.py`: `issue_with_certifier(cert_id, certifier_id, scope, actor_id)` — fetches certifier (raises NotFoundError if missing), checks `certifier.is_active` (raises ConflictError if inactive), validates `scope in certifier.permitted_scopes` (raises ValidationError if not, FR-010), sets `certification.external_certifier_id = certifier_id`, publishes `trust.certification.updated` event; also add certifier CRUD delegates: `create_certifier(data, actor_id)`, `get_certifier(certifier_id)`, `list_certifiers(include_inactive)`, `deactivate_certifier(certifier_id, actor_id)` — all delegating to the repository

- [X] T014 [US2] Add certifier endpoints and issue-with-certifier endpoint to `apps/control-plane/src/platform/trust/router.py`: `POST /certifiers` (201, PLATFORM_ADMIN or COMPLIANCE_OFFICER), `GET /certifiers` (200, any authenticated, query param: include_inactive=false), `GET /certifiers/{certifier_id}` (200), `DELETE /certifiers/{certifier_id}` (204, PLATFORM_ADMIN — soft delete via deactivate_certifier), `POST /certifications/{certification_id}/issue-with-certifier` (200, COMPLIANCE_OFFICER or PLATFORM_ADMIN, body: {certifier_id, scope}) — all delegate to updated CertificationService

---

## Phase 5: User Story 3 — Certification Expiry and Ongoing Surveillance (Priority: P2)

**Goal**: Surveillance cycle transitions active→expiring (approaching window), expiring→expired (past expiry), triggers scheduled reassessments, and emits operator alerts.

**Independent Test** (from quickstart.md S11–S14): Create cert with expires_at=now+2d, status=active. Trigger `SurveillanceService.run_surveillance_cycle()`. Verify status→"expiring", trust.certification.expiring event emitted. Create cert with expires_at=now-1d, status=expiring. Trigger cycle. Verify status→"expired". Record `verdict=fail` reassessment → cert→"suspended". Record `verdict=pass` → cert→"active".

- [X] T015 [US3] Implement `SurveillanceService` class in `apps/control-plane/src/platform/trust/surveillance_service.py` with `run_surveillance_cycle(self) -> None`: (1) query all certifications with status in [active, expiring] and expires_at IS NOT NULL; (2) for each: if expires_at ≤ now() → transition expiring/active → expired (call expire_stale flow), if expires_at ≤ now()+warning_window_days (default 7, configurable from TrustSettings) and status=active → transition to expiring, persist status change, publish `trust.certification.expiring` event, fire alert via `monitor.alerts`; (3) check cron-scheduled certifications (reassessment_schedule IS NOT NULL): use croniter or APScheduler's CronTrigger to determine if a reassessment is due since last `reassessment_records.created_at`; if due: create `ReassessmentRecord(verdict="action_required", reassessor_id="automated")`, publish alert to `monitor.alerts` indicating reassessment is required; constructor: `(repository: TrustRepository, publisher: TrustEventPublisher, settings: TrustSettings)`

- [X] T016 [P] [US3] Extend `expire_stale()` in `apps/control-plane/src/platform/trust/service.py`: current implementation transitions `active → expired` for past-expiry certs; extend to also handle `expiring → expired` (certs in `expiring` status with expires_at < now() must also be caught and transitioned); ensure `expiring`-status certs are NOT skipped by the existing active-only filter

- [X] T017 [P] [US3] Add reassessment endpoints to `apps/control-plane/src/platform/trust/router.py`: `GET /certifications/{certification_id}/reassessments` (200, any workspace member), `POST /certifications/{certification_id}/reassessments` (201, COMPLIANCE_OFFICER or PLATFORM_ADMIN, body: ReassessmentCreate) — handler calls new `CertificationService.record_reassessment(cert_id, data, actor_id)` which: creates ReassessmentRecord, transitions cert status (pass → active if suspended; fail → suspended if active/expiring; action_required → no status change), publishes event

- [X] T018 [US3] Wire surveillance into `apps/control-plane/src/platform/main.py` and `apps/control-plane/src/platform/trust/dependencies.py`: (a) add `get_surveillance_service(db, producer) -> SurveillanceService` to dependencies.py; (b) in main.py lifespan startup: instantiate SurveillanceService, add APScheduler job `trust-surveillance-cycle` with `"interval", hours=1` (following existing `trust-expire-stale` pattern in main.py); also add `record_reassessment()` method to `CertificationService` (trust/service.py) that creates ReassessmentRecord, applies status transitions per verdict, publishes trust event

---

## Phase 6: User Story 4 — Material Change Triggers Recertification (Priority: P2)

**Goal**: Kafka consumer suspends active certifications on material-change signals; grace period scanner revokes uncertified suspended certs; operators can dismiss suspensions.

**Independent Test** (from quickstart.md S15–S18): Emit mock `policy.events` payload with agent_id matching an active cert. Verify SurveillanceService.handle_material_change() suspends cert, creates TrustRecertificationRequest with deadline=now+14d. Advance past deadline. Trigger check_grace_period_expiry(). Verify cert→"revoked". Separately: dismiss-suspension endpoint with justification → cert→"active".

- [X] T019 [US4] Implement `handle_material_change(envelope)` and `check_grace_period_expiry()` in `apps/control-plane/src/platform/trust/surveillance_service.py`: `handle_material_change` — (1) extract agent_id from envelope (check payload fields: agent_id or agent_fqn); (2) query all active/expiring certifications for this agent_id; (3) for each: transition to `suspended`, create `TrustRecertificationRequest(trigger_type=derived_from_event_type, trigger_reference=event source id, deadline=now+grace_period_days, resolution_status="pending")`; (4) publish `trust.certification.suspended` event + `monitor.alerts` entry; derive trigger_type: `policy.*` events → "policy", others → "signal"; `check_grace_period_expiry` — query pending `TrustRecertificationRequests` with deadline < now(); for each: transition cert to `revoked` (reason: "recertification timeout"), resolve request with `resolution_status="revoked"`, publish trust event

- [X] T020 [P] [US4] Add `dismiss_suspension(cert_id, justification, actor_id)` to `CertificationService` in `apps/control-plane/src/platform/trust/service.py`: validate cert is in `suspended` status (raise ConflictError if not), transition to `active`, find the active (pending) `TrustRecertificationRequest` for this cert and set `resolution_status="dismissed"` + `dismissal_justification=justification`, persist an audit record (create `TrustSignal` or append to audit trail per existing service pattern), publish `trust.certification.updated` event

- [X] T021 [US4] Add recertification-request and dismiss-suspension endpoints to `apps/control-plane/src/platform/trust/router.py`: `POST /certifications/{certification_id}/dismiss-suspension` (200, PLATFORM_ADMIN, body: DismissSuspensionRequest), `GET /recertification-requests` (200, COMPLIANCE_OFFICER or PLATFORM_ADMIN, query params: certification_id, status), `GET /recertification-requests/{request_id}` (200) — all delegate to CertificationService / repository

- [X] T022 [US4] Register `SurveillanceConsumer` Kafka subscriptions and grace-period APScheduler job in `apps/control-plane/src/platform/main.py`: call `surveillance_svc.register(consumer_manager)` to subscribe to `policy.events` (group `{group}.trust-surveillance-material-change`) and `trust.events` (group `{group}.trust-surveillance-revision-signals`); add APScheduler job `trust-grace-period-check` with `"interval", hours=1`; also add `register(manager: EventConsumerManager)` method to `SurveillanceService` in `trust/surveillance_service.py`

---

## Phase 7: User Story 5 — Contract Compliance Rate as KPI (Priority: P3)

**Goal**: Compliance officers can query aggregate and per-term compliance rates for an agent, fleet, or workspace over a time window; unauthorized users are denied.

**Independent Test** (from quickstart.md S19–S21): Pre-seed 100 breach events (85 compliant, 10 warned, 3 throttled, 2 terminated). Query GET /compliance/rates?scope=agent&scope_id=fqn&start=...&end=.... Verify compliance_rate=0.85, breach_by_term populated, trend non-empty, response < 3s. Query with viewer token → 403. Query for agent with no contract-attached executions → compliance_rate=null, trend=[].

- [X] T023 [US5] Implement `get_compliance_rates(query: ComplianceRateQuery, workspace_id: UUID) -> ComplianceRateResponse` in `apps/control-plane/src/platform/trust/contract_service.py`: delegates to `repository.get_compliance_stats(scope, scope_id, start, end, bucket)`; handles zero-total edge case: if `total_contract_attached == 0` return `compliance_rate=None` and `trend=[]`; builds `ComplianceRateResponse` from repository result; validates date range (end > start)

- [X] T024 [US5] Add `GET /compliance/rates` endpoint to `apps/control-plane/src/platform/trust/router.py`: requires COMPLIANCE_OFFICER or PLATFORM_ADMIN role (FR-021, SC-010); accepts query params `scope`, `scope_id`, `start`, `end`, `bucket`; validates with `ComplianceRateQuery`; delegates to `ContractService.get_compliance_rates()`; returns `ComplianceRateResponse`

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T025 [P] Write unit tests in `apps/control-plane/tests/unit/trust/test_contract_service.py`: test create_contract (valid, invalid enforcement_policy, conflicting terms FR-025); attach_to_interaction (success + snapshot capture, idempotent same-contract FR-026, conflict different contract FR-003); attach_to_execution (same); archive_contract (success, conflict when in-flight attachments); get_compliance_rates (zero-total → compliance_rate=None, non-zero → correct rate, unauthorized → 403)

- [X] T026 [P] Write unit tests in `apps/control-plane/tests/unit/trust/test_contract_monitor.py`: handle_event — no contract on execution → skip (FR-027); cost breach → ContractBreachEvent created with enforcement_action=warn; time breach → terminate triggered; quality metric unavailable → breach marked "not_evaluated"; termination failure → enforcement_outcome="failed" with quarantine note; verify SC-011 (idempotent enforcement: same breach + action produces no additional side effects)

- [X] T027 [P] Write unit tests in `apps/control-plane/tests/unit/trust/test_surveillance_service.py`: run_surveillance_cycle — active cert 30d out → no change; active cert 2d out → status=expiring + event emitted; expiring cert past expiry → status=expired; reassessment due per cron → ReassessmentRecord(action_required) created; check_grace_period_expiry — pending request past deadline → cert=revoked; handle_material_change — active cert → suspended + TrustRecertificationRequest created with correct deadline

- [X] T028 Write integration tests in `apps/control-plane/tests/integration/trust/test_contracts_integration.py`: full contract lifecycle against real DB — create, attach to execution, simulate breach event, verify ContractBreachEvent; certification lifecycle transitions (pending→active→expiring→expired via expire_stale); compliance rate aggregation with seeded breach events; certifier registration + scope validation; dismiss-suspension flow

---

## Dependencies Between User Stories

```
US1 (P1) ─────────────────────────────────┐
                                           ↓
Foundation (T001–T007) ────────────────────→ US2 (P1) ─────────────────────────┐
                                           ↓                                    ↓
                                         US3 (P2) ── depends on US2 certs ──→ US4 (P2)
                                           ↓
                                         US5 (P3) ── depends on US1 breach data
```

- **US1 and US2** can be implemented in parallel after foundation
- **US3** should follow US2 (certifications need certifier FK data for complete lifecycle)
- **US4** depends on US3 infrastructure (SurveillanceService class)
- **US5** depends on US1 (breach events must exist to aggregate)

---

## Parallel Execution by Story

### US1 — T008, T009, T010 can run in parallel (different new files)
```
T007 (repository) ──→ T008 (contract_service.py) ──→ T011 (router.py endpoints)
                  └──→ T009 (dependencies.py)    ──↗
                  └──→ T010 (contract_monitor.py) ──→ T012 (main.py wiring)
```

### US2 — T013 parallel with US1 work
```
T007 (repository) ──→ T013 (service.py certifier methods) ──→ T014 (router.py certifiers)
```

### US3 — T015, T016, T017 can run in parallel
```
T007 (repository) ──→ T015 (surveillance_service.py cycle) ──→ T018 (main.py + dependencies.py)
                  └──→ T016 (service.py expire_stale ext)
                  └──→ T017 (router.py reassessment endpoints)
```

### US4 — T019 extends US3's surveillance_service.py
```
T015 (surveillance_service.py) ──→ T019 (handle_material_change + check_grace_period_expiry)
T016 (service.py)               ──→ T020 [P] (service.py dismiss_suspension)
                                 └──→ T021 [P] (router.py recertification endpoints)
T019 + T020                     ──→ T022 (main.py wiring + register method)
```

### US5 — T023 and T024
```
T008 (contract_service.py) ──→ T023 (get_compliance_rates method) ──→ T024 (router.py /compliance/rates)
```

---

## Implementation Strategy

**MVP scope** (US1 only — T001–T012): Delivers contract definition, attachment, runtime enforcement, and breach audit trail. Everything else builds on top.

**Incremental delivery**:
1. **Sprint 1 (Day 1 AM)**: T001–T007 (foundation) + T008–T012 (US1 complete)
2. **Sprint 2 (Day 1 PM)**: T013–T014 (US2 certifiers) + T015–T018 (US3 surveillance)
3. **Sprint 3 (Day 2 AM)**: T019–T022 (US4 material change)
4. **Sprint 4 (Day 2 PM)**: T023–T024 (US5 KPI) + T025–T028 (tests)

**Total tasks**: 28  
**Estimated effort**: 4 story points (~2 days)
