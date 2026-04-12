# Quickstart: Fleet Management and Learning

**Feature**: 033-fleet-management-learning  
**Date**: 2026-04-12  
**Phase**: 1 — Test scenario catalog

---

## Setup Notes

All scenarios assume:
- A workspace with ID `ws-001` exists
- The current user has `admin` role in `ws-001`
- Agent FQNs `finance-ops:orchestrator`, `finance-ops:kyc-verifier`, `finance-ops:risk-assessor` are pre-registered in the agent registry
- Platform agents `platform:default-observer`, `platform:default-judge`, `platform:default-enforcer` are pre-registered
- PostgreSQL, Redis, ClickHouse, Kafka are running
- Migration 033 applied (`alembic upgrade head`)

---

## Test Scenarios

### T01 — Create a hierarchical fleet

**Given**: No fleet exists in workspace `ws-001`  
**When**: `POST /api/v1/fleets` with name `"finance-fleet"`, topology `hierarchical`, `quorum_min=2`, lead `finance-ops:orchestrator`, members `[finance-ops:kyc-verifier, finance-ops:risk-assessor]`  
**Then**:
- Response `201` with `status: "active"`, `topology_type: "hierarchical"`
- 3 `fleet_members` rows created (roles: lead, worker, worker)
- `fleet_topology_versions` row with `version=1, is_current=true`
- `fleet_governance_chains` row with `is_default=true` using platform FQNs
- `fleet_orchestration_rules` default row created with `version=1`
- `fleet.created` event published on `fleet.events`

---

### T02 — Fleet name uniqueness within workspace

**Given**: Fleet `"finance-fleet"` already exists in `ws-001`  
**When**: `POST /api/v1/fleets` with name `"finance-fleet"` in `ws-001`  
**Then**: `409 Conflict` response; no new fleet created

---

### T03 — Add and remove fleet members

**Given**: Fleet `"finance-fleet"` with 3 members  
**When**: `DELETE /api/v1/fleets/{fleet_id}/members/{member_id}` for `finance-ops:risk-assessor`  
**Then**:
- `fleet_members` row soft-deleted (or removed)
- `fleet.member.removed` event published
- Fleet continues with 2 members
- Health projection (`fleet:health:{fleet_id}`) shows `available_count=2`, `total_count=2`

---

### T04 — Change fleet topology from hierarchical to peer-to-peer

**Given**: Fleet in `hierarchical` topology  
**When**: `PUT /api/v1/fleets/{fleet_id}/topology` with `topology_type: "peer_to_peer"`  
**Then**:
- New `fleet_topology_versions` row with `version=2, is_current=true`
- Previous version has `is_current=false`
- `finance-ops:orchestrator` role changes from `lead` to `worker`
- `fleet.topology.changed` event published
- `Fleet.topology_type` column updated to `peer_to_peer`

---

### T05 — Update orchestration rules and verify versioning

**Given**: Fleet with default orchestration rules (`version=1`)  
**When**: `PUT /api/v1/fleets/{fleet_id}/orchestration-rules` with `delegation.strategy="round_robin"`, `max_parallelism=3`  
**Then**:
- New `fleet_orchestration_rules` row with `version=2, is_current=true`
- Old row has `is_current=false`
- `GET /orchestration-rules/history` returns both versions
- `fleet.orchestration_rules.updated` event published

---

### T06 — Customize governance chain

**Given**: Fleet with default governance chain  
**When**: `PUT /api/v1/fleets/{fleet_id}/governance-chain` with custom `observer_fqns`, `judge_fqns`, `enforcer_fqns`  
**Then**:
- New `fleet_governance_chains` row with `version=2, is_default=false, is_current=true`
- Old default chain has `is_current=false`
- `fleet.governance_chain.updated` event published with `is_default: false`

---

### T07 — Member availability change triggers health projection update

**Given**: Fleet with 3 available members, `quorum_min=2`  
**When**: `runtime.lifecycle` event arrives with `event_type: "runtime.heartbeat_missed"`, `agent_fqn: "finance-ops:risk-assessor"`  
**Then**:
- `fleet:member:avail:{fleet_id}:finance-ops:risk-assessor` key deleted (or set to `"0"`)
- `fleet:health:{fleet_id}` Redis blob updated: `available_count=2`, `health_pct=0.67`, `status="degraded"`, `quorum_met=true`
- `fleet.health.updated` event published on `fleet.health`
- Fleet status in PostgreSQL updated to `"degraded"`
- `fleet.status.changed` event published on `fleet.events`

---

### T08 — Quorum violation triggers fleet pause and notification

**Given**: Fleet with `quorum_min=2`, 2 members available (1 already unavailable)  
**When**: Second member's `runtime.heartbeat_missed` event arrives  
**Then**:
- `fleet:health:{fleet_id}` updated: `available_count=1`, `quorum_met=false`, `status="paused"`
- Fleet PostgreSQL status updated to `"paused"`
- `fleet.status.changed` event with `status="paused"` published
- Attention notification published to `interaction.attention` Kafka topic with urgency `high`
- `GET /fleets/{fleet_id}/health` returns `status: "paused"`, `quorum_met: false`

---

### T09 — Fleet auto-resumes when quorum recovers

**Given**: Fleet in `"paused"` state (2 members unavailable), `quorum_min=2`  
**When**: `runtime.lifecycle` event arrives with `event_type: "runtime.started"` for one previously unavailable member  
**Then**:
- `fleet:member:avail:{fleet_id}:{agent_fqn}` key set to `"1"` with TTL 120s
- `fleet:health:{fleet_id}` updated: `available_count=2`, `quorum_met=true`, `status="degraded"`
- Fleet status updated to `"degraded"` (not back to `"active"` — one member still unavailable)
- `fleet.status.changed` event with `status="degraded"` published

---

### T10 — Health projection read from Redis

**Given**: Fleet with 3 members (1 unavailable)  
**When**: `GET /api/v1/fleets/{fleet_id}/health`  
**Then**:
- Response served from `fleet:health:{fleet_id}` Redis key (not PostgreSQL)
- Response time < 50ms
- Correct member statuses returned

---

### T11 — Compute performance profile

**Given**: Fleet with 3 members who have execution history in ClickHouse for the last 24h  
**When**: APScheduler daily job runs `FleetPerformanceProfileService.compute_all_profiles()`  
**Then**:
- ClickHouse query executed with `agent_fqn IN (member FQNs)` filter
- `fleet_performance_profiles` row inserted with `avg_completion_time_ms`, `success_rate`, `cost_per_task`, `avg_quality_score`, `throughput_per_hour` computed correctly
- `member_metrics` JSON contains per-member breakdown
- `GET /fleets/{fleet_id}/performance-profile` returns the new profile

---

### T12 — Performance profile flags underperforming members

**Given**: Fleet with 3 members; `finance-ops:risk-assessor` has success_rate 0.4 vs fleet average 0.9  
**When**: Performance profile is computed  
**Then**:
- `flagged_member_fqns` contains `["finance-ops:risk-assessor"]`
- Member deviation threshold is > 2 standard deviations from mean (or configurable threshold)

---

### T13 — Adaptation rule fires on threshold breach

**Given**: Fleet with adaptation rule `{condition: {metric: "avg_completion_time_ms", operator: "gt", threshold: 30000}, action: {type: "set_max_parallelism", value: 3}}`  
**When**: Performance profile is computed with `avg_completion_time_ms=35000.0`  
**Then**:
- `FleetAdaptationEngineService.evaluate_rules_for_fleet()` matches rule
- New `fleet_orchestration_rules` version created with `max_parallelism=3`
- `fleet_adaptation_log` row inserted with `before_rules_version=N, after_rules_version=N+1`
- `fleet.adaptation.applied` event published

---

### T14 — Adaptation rule priority resolves conflicts

**Given**: Fleet has two active adaptation rules:
  - Rule A (priority=10): `avg_completion_time > 30s → set max_parallelism=3`
  - Rule B (priority=5): `avg_completion_time > 20s → set delegation_strategy=round_robin`
- Current performance: `avg_completion_time=35000ms`  
**When**: `evaluate_rules_for_fleet` runs  
**Then**: Only Rule A fires (higher priority, first match wins in single-rule-per-interval policy)

---

### T15 — Revert adaptation

**Given**: Adaptation log entry with `before_rules_version=5, after_rules_version=6, is_reverted=false`  
**When**: `POST /api/v1/fleets/{fleet_id}/adaptation-log/{log_id}/revert`  
**Then**:
- `fleet_orchestration_rules` version 5 marked `is_current=true`; version 6 marked `is_current=false`
- `fleet_adaptation_log.is_reverted=true`, `reverted_at` set
- `fleet.orchestration_rules.updated` event published with previous version number

---

### T16 — Propose cross-fleet transfer

**Given**: Fleets `"fleet-A"` and `"fleet-B"` in workspace `ws-001`  
**When**: Fleet A admin calls `POST /fleets/{fleet_a_id}/transfers` with `target_fleet_id=fleet_b_id` and pattern definition  
**Then**:
- `cross_fleet_transfer_requests` row created with `status="proposed"`
- `fleet.transfer.status_changed` event published
- `GET /fleets/{fleet_b_id}/transfers?role=target` shows the request

---

### T17 — Transfer approval and application

**Given**: Transfer request in `"proposed"` status  
**When**: Fleet B admin calls `POST /fleets/transfers/{transfer_id}/approve`, then `POST /fleets/transfers/{transfer_id}/apply`  
**Then**:
- Status transitions: `proposed → approved → applied`
- Pattern adapted to Fleet B's topology (e.g., hierarchical-specific lead FQNs mapped to Fleet B's lead)
- Fleet B gets a new orchestration rules version incorporating the transferred pattern
- `applied_at` timestamp set
- `fleet.transfer.status_changed` events for both transitions

---

### T18 — Transfer rejected with reason

**Given**: Transfer request in `"proposed"` status  
**When**: Fleet B admin calls `POST /fleets/transfers/{transfer_id}/reject` with reason `"Incompatible with peer-to-peer topology"`  
**Then**:
- `status="rejected"`, `rejected_reason` stored
- No orchestration rules changes applied to Fleet B

---

### T19 — Personality profile update affects dispatch modifier

**Given**: Fleet with default personality profile  
**When**: `PUT /api/v1/fleets/{fleet_id}/personality-profile` with `decision_speed="fast"`  
**Then**:
- New `fleet_personality_profiles` version created with `is_current=true`
- `FleetOrchestrationModifierService.get_modifier(fleet_id)` returns `max_wait_ms=0`
- Previous personality version retained for history with `is_current=false`

---

### T20 — Orchestration rules override personality profile

**Given**: Fleet with `decision_speed="consensus_seeking"` personality (requires quorum polling)  
**When**: Orchestration rules explicitly set `delegation.strategy="round_robin"` (no quorum requirement)  
**Then**:
- `get_modifier()` returns `require_quorum_for_decision=true` from personality
- But explicit `delegation.strategy="round_robin"` in orchestration rules takes precedence
- Dispatch uses round_robin without quorum wait
- `FleetOrchestrationService` applies explicit rules after personality modifier defaults
