# Tasks: Fleet Management and Learning

**Input**: Design documents from `specs/033-fleet-management-learning/`  
**Branch**: `033-fleet-management-learning`  
**Prerequisites**: plan.md ✅ spec.md ✅ research.md ✅ data-model.md ✅ contracts/ ✅ quickstart.md ✅

**Tests**: Not requested — no test tasks generated.

**Organization**: Tasks grouped by user story (US1–US8) for independent implementation and delivery.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel with other [P] tasks (different files, no blocking dependency)
- **[Story]**: Maps to user story from spec.md

---

## Phase 1: Setup

**Purpose**: Create bounded context directory structure.

- [x] T001 Create `apps/control-plane/src/platform/fleets/__init__.py` and `apps/control-plane/src/platform/fleet_learning/__init__.py` (empty init files for both bounded contexts)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Migration, models, schemas, repositories, events, exceptions, and DI for both bounded contexts. No user story work begins until this phase is complete.

**⚠️ CRITICAL**: All user stories depend on this phase.

- [x] T002 Write Alembic migration `apps/control-plane/migrations/versions/033_fleet_management.py` — all 12 tables in dependency order: fleets → fleet_members → fleet_topology_versions → fleet_policy_bindings → observer_assignments → fleet_governance_chains → fleet_orchestration_rules → fleet_performance_profiles → fleet_adaptation_rules → fleet_adaptation_log → cross_fleet_transfer_requests → fleet_personality_profiles (see data-model.md for all column definitions, indexes, and partial unique constraints)
- [x] T003 [P] Write `apps/control-plane/src/platform/fleets/models.py` — 7 SQLAlchemy models (Fleet, FleetMember, FleetTopologyVersion, FleetPolicyBinding, ObserverAssignment, FleetGovernanceChain, FleetOrchestrationRules) using `Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, WorkspaceScopedMixin` + 4 enums (FleetStatus, FleetTopologyType, FleetMemberRole, FleetMemberAvailability) per data-model.md
- [x] T004 [P] Write `apps/control-plane/src/platform/fleet_learning/models.py` — 5 SQLAlchemy models (FleetPerformanceProfile, FleetAdaptationRule, FleetAdaptationLog, CrossFleetTransferRequest, FleetPersonalityProfile) + 5 enums (TransferRequestStatus, CommunicationStyle, DecisionSpeed, RiskTolerance, AutonomyLevel) per data-model.md
- [x] T005 [P] Write `apps/control-plane/src/platform/fleets/schemas.py` — all Pydantic v2 request/response schemas: FleetCreate, FleetUpdate, FleetResponse, FleetMemberCreate, FleetMemberRoleUpdate, FleetMemberResponse, FleetTopologyUpdateRequest, FleetTopologyVersionResponse, FleetPolicyBindingResponse, ObserverAssignmentCreate, ObserverAssignmentResponse, FleetGovernanceChainUpdate, FleetGovernanceChainResponse, FleetOrchestrationRulesCreate, FleetOrchestrationRulesResponse, MemberHealthStatus, FleetHealthProjectionResponse, OrchestrationModifier per data-model.md
- [x] T006 [P] Write `apps/control-plane/src/platform/fleet_learning/schemas.py` — all Pydantic v2 schemas: FleetPerformanceProfileQuery, FleetPerformanceProfileResponse, AdaptationCondition, AdaptationAction, FleetAdaptationRuleCreate, FleetAdaptationRuleResponse, FleetAdaptationLogResponse, CrossFleetTransferCreate, TransferApproveRequest, TransferRejectRequest, CrossFleetTransferResponse, FleetPersonalityProfileCreate, FleetPersonalityProfileResponse per data-model.md
- [x] T007 [P] Write `apps/control-plane/src/platform/fleets/exceptions.py` (FleetError, FleetNotFoundError, FleetStateError, QuorumNotMetError, FleetNameConflictError — all inheriting from PlatformError)
- [x] T008 [P] Write `apps/control-plane/src/platform/fleet_learning/exceptions.py` (FleetLearningError, AdaptationError, TransferError, IncompatibleTopologyError — all inheriting from PlatformError)
- [x] T009 [P] Write `apps/control-plane/src/platform/fleets/events.py` — fleet.events and fleet.health event type string constants (fleet.created, fleet.archived, fleet.status.changed, fleet.member.added, fleet.member.removed, fleet.topology.changed, fleet.orchestration_rules.updated, fleet.governance_chain.updated, fleet.adaptation.applied, fleet.transfer.status_changed, fleet.health.updated) + async publish functions wrapping common EventPublisher per data-model.md Kafka events table
- [x] T010 [P] Write `apps/control-plane/src/platform/fleet_learning/events.py` — re-uses fleet.events and fleet.health topics; defines fleet_learning event helpers (fleet.adaptation.applied, fleet.transfer.status_changed)
- [x] T011 Write `apps/control-plane/src/platform/fleets/repository.py` — async SQLAlchemy CRUD: FleetRepository (get_by_id, get_by_workspace, create, update, soft_delete, get_by_name_and_workspace), FleetMemberRepository (get_by_fleet, add, remove, update_role, get_by_agent_fqn_across_fleets), FleetTopologyVersionRepository (get_current, create_version, list_history), FleetPolicyBindingRepository (bind, unbind, list_by_fleet), ObserverAssignmentRepository (assign, deactivate, list_active_by_fleet), FleetGovernanceChainRepository (get_current, create_version, list_history), FleetOrchestrationRulesRepository (get_current, create_version, list_history, get_by_version)
- [x] T012 Write `apps/control-plane/src/platform/fleet_learning/repository.py` — async SQLAlchemy CRUD: FleetPerformanceProfileRepository (insert, get_latest, list_by_range), FleetAdaptationRuleRepository (create, list_active_by_priority, update, deactivate), FleetAdaptationLogRepository (create, list_by_fleet, get_by_id, mark_reverted), CrossFleetTransferRepository (create, get_by_id, update_status, list_for_fleet), FleetPersonalityProfileRepository (get_current, create_version, list_history)
- [x] T013 [P] Write `apps/control-plane/src/platform/fleets/dependencies.py` — FastAPI DI: `get_fleet_service`, `get_health_service`, `get_governance_service` async generator functions
- [x] T014 [P] Write `apps/control-plane/src/platform/fleet_learning/dependencies.py` — FastAPI DI: `get_fleet_learning_service`, `get_performance_service`, `get_adaptation_service`, `get_transfer_service`, `get_personality_service` async generator functions

**Checkpoint**: Foundation complete — all models, schemas, repositories, and DI are ready. User story phases can proceed.

---

## Phase 3: User Story 1 — Fleet Domain and Topology (Priority: P1) 🎯 MVP

**Goal**: Fleet CRUD, topology versioning, member management, policy binding, observer assignment, and default governance chain auto-created on fleet creation.

**Independent Test** (quickstart.md T01–T04): Create a hierarchical fleet with 3 members → verify topology version 1 created, default governance chain assigned, all 3 members added. Change topology to peer_to_peer → verify version 2 created and lead role removed. Remove a member → verify fleet continues with 2 members.

- [x] T015 [US1] Implement `FleetService.create_fleet` in `apps/control-plane/src/platform/fleets/service.py` — create Fleet row, insert FleetTopologyVersion (v1, is_current=True), insert FleetGovernanceChain default (platform:default-observer, platform:default-judge, platform:default-enforcer, is_default=True, v1), insert FleetOrchestrationRules defaults (round_robin delegation, first_wins aggregation, 300s escalation, majority_vote conflict, 2 retries reassign, max_parallelism=1, v1), add initial members from request (role=worker), validate name uniqueness → raise FleetNameConflictError on duplicate (workspace_id, name), publish fleet.created event
- [x] T016 [US1] Implement `FleetService` read and archive methods in `apps/control-plane/src/platform/fleets/service.py` — get_fleet (raise FleetNotFoundError if absent or wrong workspace), list_fleets (workspace-scoped cursor pagination, optional status filter), update_fleet (quorum_min only), archive_fleet (state guard: only from active/degraded/paused → archived; deactivate governance chain and orchestration rules; publish fleet.archived)
- [x] T017 [US1] Implement `FleetService` member and topology methods in `apps/control-plane/src/platform/fleets/service.py` — add_member (validate agent FQN not already a member; raise 409 if duplicate), remove_member, update_member_role, list_members, update_topology (create new FleetTopologyVersion with version+1, mark old is_current=False; if changing from hierarchical remove lead designation; update Fleet.topology_type; publish fleet.topology.changed), get_topology_history
- [x] T018 [US1] Implement `FleetService` policy and observer methods in `apps/control-plane/src/platform/fleets/service.py` — bind_policy (create FleetPolicyBinding; 409 on duplicate fleet_id+policy_id), unbind_policy (delete), assign_observer (create ObserverAssignment; 409 on duplicate fleet_id+fqn; validate FQN non-empty), remove_observer (set is_active=False)
- [x] T019 [US1] Implement `FleetGovernanceChainService` in `apps/control-plane/src/platform/fleets/governance.py` — get_chain (return current chain for fleet), update_chain (create new FleetGovernanceChain version with is_default=False, mark old is_current=False; publish fleet.governance_chain.updated), get_chain_history; expose `create_default_chain(fleet_id)` called by FleetService.create_fleet
- [x] T020 [US1] Implement `apps/control-plane/src/platform/fleets/router.py` with 19 endpoints covering US1: POST/GET /fleets, GET/PUT/DELETE(archive) /fleets/{id}, GET /fleets/{id}/health (returns FleetHealthProjectionResponse stub returning active/full health until Phase 6), POST/GET /fleets/{id}/members, DELETE/PUT /fleets/{id}/members/{member_id}/role, PUT/GET(history) /fleets/{id}/topology, POST/DELETE /fleets/{id}/policies/{binding_id}, POST/DELETE /fleets/{id}/observers/{assignment_id}, GET/PUT/GET(history) /fleets/{id}/governance-chain; wire FleetService and FleetGovernanceChainService via dependencies

**Checkpoint**: Fleet CRUD, topology versioning, member management, policy binding, observer assignment, and default governance chain all functional. Can be tested independently via quickstart.md T01–T04.

---

## Phase 4: User Story 2 — Orchestration Rules (Priority: P1)

**Goal**: Versioned orchestration rules CRUD with delegation/aggregation/escalation/conflict/retry strategies; immutable versioning on change.

**Independent Test** (quickstart.md T05): Update orchestration rules from defaults → verify version 2 created with is_current=True, old version retained with is_current=False; verify GET /orchestration-rules/history returns both versions.

- [x] T021 [US2] Implement `FleetService` orchestration rule methods in `apps/control-plane/src/platform/fleets/service.py` — get_orchestration_rules (return current version for fleet), update_orchestration_rules (validate FleetOrchestrationRulesCreate schema; create new FleetOrchestrationRules row with version+1, is_current=True; mark old row is_current=False; update Fleet.topology_type if delegation strategy implies structural change; publish fleet.orchestration_rules.updated), get_rules_history (list all versions ordered by version desc)
- [x] T022 [US2] Implement `FleetOrchestrationModifierService` stub in `apps/control-plane/src/platform/fleets/service.py` — get_modifier(fleet_id) returns OrchestrationModifier with all defaults (max_wait_ms=None, require_quorum_for_decision=False, auto_approve=False, escalate_unverified=False); will be replaced in Phase 10 (US8) with personality-driven logic
- [x] T023 [US2] Add orchestration rules endpoints to `apps/control-plane/src/platform/fleets/router.py` — GET /fleets/{id}/orchestration-rules, PUT /fleets/{id}/orchestration-rules, GET /fleets/{id}/orchestration-rules/history; complete FleetServiceInterface stub (get_fleet_members, get_orchestration_rules, get_governance_chain, get_orchestration_modifier, record_member_failure) as internal service interface in fleets/service.py

**Checkpoint**: Orchestration rules CRUD with versioning complete. Quickstart T05 passes.

---

## Phase 5: User Story 3 — Observer Agents and Governance Chain (Priority: P2)

**Goal**: Observer agents receive execution stream events for fleet member tasks without owning tasks; governance chain OJE pipeline delegation to trust/ service; full governance chain customization.

**Independent Test** (quickstart.md T06, T07 partial): Assign observer to fleet → simulate workflow.runtime execution event for a fleet member → verify fleet.events receives re-published event tagged with fleet_id. Customize governance chain → verify new version created with is_default=False.

- [x] T024 [US3] Implement `FleetGovernanceChainService.trigger_oje_pipeline` in `apps/control-plane/src/platform/fleets/governance.py` — accept (fleet_id, signal: dict); load current governance chain; call `OJEPipelineServiceInterface.process_fleet_anomaly_signal(fleet_id, chain_config, signal)` via internal service interface (from trust/ bounded context); return OJEVerdictResponse; log signal + verdict
- [x] T025 [US3] Implement `workflow.runtime` observer routing Kafka consumer handler in `apps/control-plane/src/platform/fleets/` — function `route_execution_event_to_observers(event: EventEnvelope)`: extract `agent_fqn` from event payload; query FleetMemberRepository for all active fleets containing that agent_fqn; for each matching fleet, re-publish event to `fleet.events` topic with fleet_id added to correlation_context (so WS gateway delivers it to agents subscribed to the fleet channel); add this consumer handler to worker_main.py consumer registration (separate from runtime.lifecycle consumer in Phase 6)
- [x] T026 [US3] Ensure `apps/control-plane/src/platform/fleets/router.py` observer assignment and governance chain endpoints are fully wired end-to-end (POST /fleets/{id}/observers, DELETE /fleets/{id}/observers/{assignment_id} calling FleetService; GET /fleets/{id}/governance-chain and PUT /fleets/{id}/governance-chain calling FleetGovernanceChainService; verify route handlers return correct response schemas)

**Checkpoint**: Observer event routing active; governance chain customization functional; OJE pipeline delegation wired.

---

## Phase 6: User Story 4 — Degraded Operation (Priority: P2)

**Goal**: Redis-backed fleet health projection; quorum tracking with automatic fleet status transitions (active/degraded/paused); attention notifications on quorum breach; auto-resume when quorum recovers.

**Independent Test** (quickstart.md T07–T10): Create fleet (quorum_min=2, 3 members) → simulate heartbeat_missed for 1 member → verify fleet:health:{id} Redis updated, fleet.status.changed event published, fleet status=degraded. Simulate second heartbeat_missed → verify status=paused, interaction.attention event published. Simulate runtime.started for one member → verify auto-resume to degraded.

- [x] T027 [US4] Implement `FleetHealthProjectionService.get_health` in `apps/control-plane/src/platform/fleets/health.py` — read `fleet:health:{fleet_id}` JSON blob from Redis (deserialize to FleetHealthProjectionResponse); if key missing fall back to computing from PostgreSQL fleet_members availability; return response; Redis TTL = 90s
- [x] T028 [US4] Implement `FleetHealthProjectionService.refresh_health` in `apps/control-plane/src/platform/fleets/health.py` — SCAN `fleet:member:avail:{fleet_id}:*` keys to count available members; compute health_pct = available/total; determine new FleetStatus (all_available → ACTIVE; some_unavailable + quorum_met → DEGRADED; quorum_not_met → PAUSED); if status changed from current: update Fleet.status in PostgreSQL; publish fleet.status.changed on fleet.events; publish fleet.health.updated on fleet.health (with full member_statuses array); SET `fleet:health:{fleet_id}` JSON blob (TTL 90s)
- [x] T029 [US4] Implement `FleetHealthProjectionService.handle_member_availability_change` in `apps/control-plane/src/platform/fleets/health.py` — accept (agent_fqn: str, is_available: bool); look up all fleets containing agent_fqn via FleetMemberRepository.get_by_agent_fqn_across_fleets; for each fleet: if is_available → SET `fleet:member:avail:{fleet_id}:{agent_fqn}` = "1" with TTL 120s; else → DEL `fleet:member:avail:{fleet_id}:{agent_fqn}`; call refresh_health(fleet_id); on PAUSED transition: publish to interaction.attention Kafka topic with urgency="high", fleet_id, workspace_id, message "Fleet {name} quorum breached"
- [x] T030 [US4] Register `runtime.lifecycle` Kafka consumer in `apps/control-plane/entrypoints/worker_main.py` — consume events with event_type IN ["runtime.heartbeat_missed", "runtime.started"]; map to FleetHealthProjectionService.handle_member_availability_change(agent_fqn=event.agent_fqn, is_available=(event_type=="runtime.started")); update GET /fleets/{id}/health endpoint in fleets/router.py to call FleetHealthProjectionService.get_health (replace stub from Phase 3)

**Checkpoint**: Health projection fully functional. Fleet auto-pauses on quorum breach and auto-resumes. Quickstart T07–T10 all pass.

---

## Phase 7: User Story 5 — Fleet Performance Profiles (Priority: P2)

**Goal**: Fleet-wide performance metrics aggregated from ClickHouse execution data; daily APScheduler job; queryable profiles with per-member breakdown and outlier flagging.

**Independent Test** (quickstart.md T11–T12): Verify ClickHouse query runs for a fleet's member FQNs; check FleetPerformanceProfile row inserted with correct aggregated metrics; verify flagged_member_fqns contains members with >2σ deviation.

- [x] T031 [P] [US5] Implement `FleetPerformanceProfileService.compute_profile` in `apps/control-plane/src/platform/fleet_learning/performance.py` — accept (fleet_id, workspace_id, period_start, period_end); get member FQNs via FleetServiceInterface.get_fleet_members; execute ClickHouse query via ClickHouseClient: `SELECT agent_fqn, avg(completion_time_ms) as avg_ms, countIf(status='success')/count() as success_rate, sum(cost_usd)/count() as cost_per_task, avg(quality_score) as quality FROM execution_metrics WHERE agent_fqn IN (:fqns) AND completed_at BETWEEN :start AND :end GROUP BY agent_fqn`; aggregate fleet-wide averages; flag members with |member_metric - fleet_avg| > 2 * stddev; insert FleetPerformanceProfile; return response
- [x] T032 [US5] Implement `FleetPerformanceProfileService.compute_all_profiles`, `get_profile`, and `get_profile_history` in `apps/control-plane/src/platform/fleet_learning/performance.py` — compute_all_profiles: query all active fleets (status IN [active, degraded]) across all workspaces, call compute_profile(fleet_id, ws_id, yesterday_start, yesterday_end) for each; get_profile: query fleet_performance_profiles by fleet_id with period overlap for the requested time range; get_profile_history: list all profiles for fleet ordered by period_end desc
- [x] T033 [US5] Implement `apps/control-plane/src/platform/fleet_learning/router.py` with performance profile endpoints — GET /fleets/{id}/performance-profile (with query params start/end), POST /fleets/{id}/performance-profile/compute (trigger on-demand, 202 Accepted), GET /fleets/{id}/performance-profile/history; wire FleetPerformanceProfileService via dependencies
- [x] T034 [US5] Register `FleetPerformanceProfileService.compute_all_profiles` as APScheduler cron job in `apps/control-plane/entrypoints/scheduler_main.py` — schedule: daily at 01:00 UTC; pass period_start=yesterday 00:00 UTC, period_end=yesterday 23:59:59 UTC

**Checkpoint**: Performance profiles computed daily. Quickstart T11–T12 pass.

---

## Phase 8: User Story 6 — Adaptation Engine (Priority: P3)

**Goal**: Condition-action adaptation rules evaluated against fleet performance profiles; automatic orchestration rule updates logged with before/after state; revert capability.

**Independent Test** (quickstart.md T13–T15): Create adaptation rule (avg_completion_time_ms > 30000 → set_max_parallelism=3); create performance profile with avg=35000ms; run evaluate_rules_for_fleet → verify new orchestration rules version created, adaptation log entry inserted; call revert_adaptation → verify previous version restored.

- [x] T035 [P] [US6] Implement `FleetAdaptationEngineService` rule CRUD in `apps/control-plane/src/platform/fleet_learning/adaptation.py` — create_rule (validate condition.metric is a valid FleetPerformanceProfile field, action.type is a valid orchestration modifier type; insert FleetAdaptationRule), list_rules (by fleet_id, filter is_active), update_rule (update condition/action/priority/is_active), deactivate_rule (set is_active=False)
- [x] T036 [US6] Implement `FleetAdaptationEngineService.evaluate_rules_for_fleet` in `apps/control-plane/src/platform/fleet_learning/adaptation.py` — load latest FleetPerformanceProfile for fleet (FleetPerformanceProfileRepository.get_latest); load active adaptation rules ordered by priority DESC; for first rule where condition evaluates true (compare profile metric to threshold using operator): apply action to current orchestration rules copy (e.g., set max_parallelism=action.value); call FleetServiceInterface.update_orchestration_rules(fleet_id, updated_rules) → returns new version; insert FleetAdaptationLog (before_rules_version, after_rules_version, performance_snapshot=relevant metrics, adaptation_rule_id); publish fleet.adaptation.applied event; return log entry or empty list if no rule matched
- [x] T037 [US6] Implement `FleetAdaptationEngineService.evaluate_all_fleets` and `revert_adaptation` in `apps/control-plane/src/platform/fleet_learning/adaptation.py` — evaluate_all_fleets: list all active fleets with at least one active adaptation rule; call evaluate_rules_for_fleet for each; revert_adaptation: load FleetAdaptationLog by log_id; raise AdaptationError if is_reverted=True; get before_rules_version; call FleetOrchestrationRulesRepository to mark before_version as is_current=True and after_version as is_current=False; set FleetAdaptationLog.is_reverted=True, reverted_at=now; publish fleet.orchestration_rules.updated with before_version number
- [x] T038 [US6] Add adaptation endpoints to `apps/control-plane/src/platform/fleet_learning/router.py` — GET /fleets/{id}/adaptation-rules, POST /fleets/{id}/adaptation-rules, PUT /fleets/{id}/adaptation-rules/{rule_id}, DELETE /fleets/{id}/adaptation-rules/{rule_id}, GET /fleets/{id}/adaptation-log (with is_reverted query param), POST /fleets/{id}/adaptation-log/{log_id}/revert
- [x] T039 [US6] Register `FleetAdaptationEngineService.evaluate_all_fleets` as APScheduler cron job in `apps/control-plane/entrypoints/scheduler_main.py` — schedule: daily at 01:05 UTC (5 minutes after performance profile job completes)

**Checkpoint**: Adaptation engine fires and logs correctly. Quickstart T13–T15 pass.

---

## Phase 9: User Story 7 — Cross-Fleet Knowledge Transfer (Priority: P3)

**Goal**: Transfer request state machine (proposed → approved/rejected; approved → applied; applied → reverted); pattern adapted to target fleet topology; MinIO for large payloads.

**Independent Test** (quickstart.md T16–T18): Propose transfer from Fleet A to Fleet B → verify PROPOSED status; approve → verify APPROVED; apply → verify APPLIED with target fleet getting new orchestration rules version; reject alternative path → verify REJECTED.

- [x] T040 [P] [US7] Implement `CrossFleetTransferService.propose` in `apps/control-plane/src/platform/fleet_learning/transfer.py` — validate source_fleet_id != target_fleet_id; validate target_fleet_id exists in same workspace via FleetServiceInterface.get_fleet (raise FleetNotFoundError if absent); if pattern_definition JSON size > 50KB: write to MinIO `fleet-patterns/{transfer_id}/pattern.json` via S3Client, set pattern_minio_key, clear pattern_definition; else: store inline; insert CrossFleetTransferRequest (status=PROPOSED, proposed_by=current_user_id); publish fleet.transfer.status_changed event
- [x] T041 [US7] Implement `CrossFleetTransferService.approve` and `reject` in `apps/control-plane/src/platform/fleet_learning/transfer.py` — approve: guard status==PROPOSED (raise TransferError on wrong status); update status=APPROVED, approved_by; publish event; reject: guard status==PROPOSED; update status=REJECTED, rejected_reason; publish event
- [x] T042 [US7] Implement `CrossFleetTransferService.apply` and `revert` in `apps/control-plane/src/platform/fleet_learning/transfer.py` — apply: guard status==APPROVED; load pattern (from pattern_definition or fetch from MinIO if pattern_minio_key set); load target fleet topology (FleetServiceInterface); adapt pattern: for hierarchical target re-map lead FQN to target's lead; for peer_to_peer target strip leader-specific config; if no compatible mapping raise IncompatibleTopologyError (422); call FleetServiceInterface.update_orchestration_rules(target_fleet_id, adapted_rules); update status=APPLIED, applied_at; publish event; revert: guard status==APPLIED; determine pre-transfer orchestration rules version (store original target version before apply; if not tracked use version before applied_at); call FleetOrchestrationRulesRepository to restore; update reverted_at; publish event
- [x] T043 [US7] Implement `CrossFleetTransferService.list_for_fleet` and `get` + add transfer endpoints to `apps/control-plane/src/platform/fleet_learning/router.py` — POST /fleets/{id}/transfers, GET /fleets/{id}/transfers (with role=source|target filter), GET /fleets/transfers/{transfer_id}, POST /fleets/transfers/{transfer_id}/approve, POST /fleets/transfers/{transfer_id}/reject, POST /fleets/transfers/{transfer_id}/apply, POST /fleets/transfers/{transfer_id}/revert

**Checkpoint**: Cross-fleet transfer lifecycle complete. Quickstart T16–T18 pass.

---

## Phase 10: User Story 8 — Fleet Personality Profiles (Priority: P3)

**Goal**: Personality profile CRUD with immutable versioning; advisory OrchestrationModifier computation replacing the stub from Phase 4; takes effect on next task dispatch without restart.

**Independent Test** (quickstart.md T19–T20): Set personality to `decision_speed=fast` → verify FleetOrchestrationModifierService.get_modifier returns max_wait_ms=0. Set to `consensus_seeking` + explicit round_robin orchestration rule → verify orchestration rule takes precedence.

- [x] T044 [P] [US8] Implement `FleetPersonalityProfileService.get` and `update` in `apps/control-plane/src/platform/fleet_learning/personality.py` — get: query FleetPersonalityProfileRepository.get_current(fleet_id); if no profile exists return defaults (CONCISE, DELIBERATE, MODERATE, SEMI_AUTONOMOUS); update: mark old profile is_current=False; insert new with version+1, is_current=True
- [x] T045 [US8] Implement `FleetPersonalityProfileService.get_modifier` in `apps/control-plane/src/platform/fleet_learning/personality.py` — compute OrchestrationModifier from personality: FAST → max_wait_ms=0; DELIBERATE → max_wait_ms=5000; CONSENSUS_SEEKING → require_quorum_for_decision=True; CONSERVATIVE risk → escalate_unverified=True; FULLY_AUTONOMOUS → auto_approve=True; return OrchestrationModifier; update `FleetOrchestrationModifierService.get_modifier` in `apps/control-plane/src/platform/fleets/service.py` to call FleetPersonalityProfileService.get_modifier via in-process call (replacing the stub from T022)
- [x] T046 [US8] Add personality profile endpoints to `apps/control-plane/src/platform/fleet_learning/router.py` — GET /fleets/{id}/personality-profile, PUT /fleets/{id}/personality-profile; include FleetPersonalityProfileService via dependencies; add fleet_learning_router import to fleet_learning/__init__.py for router export

**Checkpoint**: Personality profiles functional and influencing dispatch modifiers. Quickstart T19–T20 pass.

---

## Phase 11: Polish and Cross-Cutting Concerns

**Purpose**: Router registration, Kafka consumer registration, APScheduler job wiring, coverage gate, linting.

- [x] T047 [P] Register `fleets_router` in `apps/control-plane/src/platform/main.py` — `app.include_router(fleets_router, prefix="/api/v1", tags=["fleets"])`
- [x] T048 [P] Register `fleet_learning_router` in `apps/control-plane/src/platform/main.py` — `app.include_router(fleet_learning_router, prefix="/api/v1", tags=["fleet-learning"])`
- [x] T049 Register all fleet Kafka consumer handlers in `apps/control-plane/entrypoints/worker_main.py` — (1) `runtime.lifecycle` consumer → FleetHealthProjectionService.handle_member_availability_change (event_types: runtime.heartbeat_missed, runtime.started); (2) `workflow.runtime` consumer → observer routing handler; both in separate consumer group registrations per topic
- [x] T050 [P] Run `ruff check apps/control-plane/src/platform/fleets/ apps/control-plane/src/platform/fleet_learning/` and `mypy apps/control-plane/src/platform/fleets/ apps/control-plane/src/platform/fleet_learning/ --strict` — fix all lint errors and type annotation gaps
- [x] T051 Validate ≥95% test coverage with `pytest --cov=platform.fleets --cov=platform.fleet_learning apps/control-plane/tests/` — add any missing unit tests for uncovered branches in service, health, governance, performance, adaptation, transfer, personality modules

---

## Dependencies and Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — **BLOCKS all user story phases**
- **Phase 3 (US1)**: Depends on Phase 2 — foundation of all fleet features
- **Phase 4 (US2)**: Depends on Phase 3 — orchestration rules methods build on FleetService
- **Phase 5 (US3)**: Depends on Phase 3 (observer assignments in FleetService), Phase 4 (governance chain fully wired)
- **Phase 6 (US4)**: Depends on Phase 3 (fleet members, fleet status), can run parallel with Phase 5
- **Phase 7 (US5)**: Depends on Phase 3 (get_fleet_members via FleetServiceInterface), independent of Phase 5/6
- **Phase 8 (US6)**: Depends on Phase 7 (performance profiles as input), Phase 4 (orchestration rules update)
- **Phase 9 (US7)**: Depends on Phase 4 (update_orchestration_rules via FleetServiceInterface), Phase 3 (get_fleet)
- **Phase 10 (US8)**: Depends on Phase 4 (FleetOrchestrationModifierService stub to replace), Phase 3 (fleet exists)
- **Phase 11 (Polish)**: Depends on all user story phases complete

### User Story Dependencies

| Story | Priority | Depends On | Parallel With |
|---|---|---|---|
| US1 Fleet Domain | P1 | Phase 2 | — |
| US2 Orchestration | P1 | US1 | — |
| US3 Observer/OJE | P2 | US1, US2 | US4 |
| US4 Degraded Ops | P2 | US1 | US3 |
| US5 Performance | P2 | US1 | US3, US4 |
| US6 Adaptation | P3 | US2, US5 | US7, US8 |
| US7 Transfer | P3 | US2 | US6, US8 |
| US8 Personality | P3 | US2 | US6, US7 |

### Within Each Phase (task ordering)

**Phase 2**: T002 first (migration); T003–T010 and T013–T014 in parallel (all different files); T011–T012 after models+schemas complete  
**Phase 3**: T015 → T016 → T017 → T018 (sequential, same service.py); T019 parallel (different file); T020 after T015–T019  
**Phase 4**: T021 → T022 (service then router); T022 parallel with T021 once methods exist  
**Phase 8**: T035 → T036 → T037 (sequential, same adaptation.py); T035 [P] can start from foundation; T039 after T036+T037

---

## Parallel Execution Examples

### Phase 2 Foundational (all in parallel after T002):

```
[parallel group after T002]
Task A: T003 fleets/models.py
Task B: T004 fleet_learning/models.py
Task C: T005 fleets/schemas.py
Task D: T006 fleet_learning/schemas.py
Task E: T007 fleets/exceptions.py
Task F: T008 fleet_learning/exceptions.py
Task G: T009 fleets/events.py
Task H: T010 fleet_learning/events.py
Task I: T013 fleets/dependencies.py
Task J: T014 fleet_learning/dependencies.py

[after T003+T005 complete]
Task K: T011 fleets/repository.py

[after T004+T006 complete]
Task L: T012 fleet_learning/repository.py
```

### Phase 7 US5 + Phase 6 US4 (parallel P2 stories):

```
Developer A (US4):
  T027 health.get_health → T028 refresh_health → T029 handle_member_availability_change → T030 Kafka consumer

Developer B (US5):
  T031 compute_profile → T032 compute_all/get/history → T033 router → T034 APScheduler
```

### Phase 8–10 (parallel P3 stories after US5+US2 complete):

```
Developer A (US6 Adaptation):
  T035 rule CRUD → T036 evaluate_rules → T037 evaluate_all + revert → T038 router → T039 APScheduler

Developer B (US7 Transfer):
  T040 propose → T041 approve/reject → T042 apply/revert → T043 router

Developer C (US8 Personality):
  T044 get/update → T045 get_modifier → T046 router + stub replacement
```

---

## Implementation Strategy

### MVP (US1 + US2 only — P1 stories)

1. Complete Phase 1 (Setup) + Phase 2 (Foundational)
2. Complete Phase 3 (US1: Fleet Domain) — T015–T020
3. Complete Phase 4 (US2: Orchestration Rules) — T021–T023
4. **VALIDATE**: Fleet CRUD, topology versioning, member management, and orchestration rules all functional
5. Register router + run ruff/mypy for P1 scope

**MVP delivers**: Full fleet lifecycle (create/archive), versioned topology, member management, policy/observer binding, governance chain, and versioned orchestration rules.

### Incremental Delivery

- **Drop 1 (P1)**: MVP — fleet domain + orchestration rules
- **Drop 2 (P2)**: Observer routing + governance chain OJE + degraded operation + performance profiles  
- **Drop 3 (P3)**: Adaptation engine + cross-fleet transfer + personality profiles
- **Drop 4**: Polish — full coverage + linting

### Single Developer Strategy (sequential priority order)

Phase 1 → Phase 2 → Phase 3 (US1) → Phase 4 (US2) → Phase 6 (US4) → Phase 5 (US3) → Phase 7 (US5) → Phase 8 (US6) → Phase 9 (US7) → Phase 10 (US8) → Phase 11 (Polish)

---

## Notes

- [P] = different files or no blocking dependency within the same phase
- All service methods are async (`async def`) per constitution §III (coding conventions)
- Repository calls use `AsyncSession` exclusively — no sync SQLAlchemy
- Redis keys: `fleet:health:{fleet_id}` (JSON blob TTL 90s), `fleet:member:avail:{fleet_id}:{fqn}` (string TTL 120s)
- FleetServiceInterface methods in fleets/service.py serve as the cross-context internal interface (called by fleet_learning services in-process)
- ClickHouse queries in performance.py use common ClickHouseClient wrapper; no cross-boundary PostgreSQL access
- Pattern adaptation in transfer.py must handle 3 topology cases: hierarchical↔peer_to_peer↔hybrid
- Stop at each checkpoint to validate the story independently before proceeding
