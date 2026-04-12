# API Contracts: Fleet Management and Learning

**Feature**: 033-fleet-management-learning  
**Date**: 2026-04-12  
**Base path**: `/api/v1`

---

## REST Endpoints — `fleets/` context

All endpoints require `Authorization: Bearer <JWT>` and are workspace-scoped via the `workspace_id` claim in the JWT.

---

### Fleet CRUD

#### `POST /fleets`

Create a new fleet in the workspace.

**Request**:
```json
{
  "name": "finance-processing-fleet",
  "topology_type": "hierarchical",
  "quorum_min": 2,
  "topology_config": { "lead_fqn": "finance-ops:orchestrator" },
  "member_fqns": ["finance-ops:kyc-verifier", "finance-ops:risk-assessor"]
}
```

**Response** `201 Created`:
```json
{
  "id": "uuid",
  "workspace_id": "uuid",
  "name": "finance-processing-fleet",
  "status": "active",
  "topology_type": "hierarchical",
  "quorum_min": 2,
  "created_at": "2026-04-12T10:00:00Z",
  "updated_at": "2026-04-12T10:00:00Z"
}
```

**Errors**: `409 Conflict` if name already exists in workspace, `422` validation error.

---

#### `GET /fleets`

List all fleets in the workspace (paginated).

**Query params**: `status`, `page`, `size`

**Response** `200 OK`: `{ "items": [...], "total": int, "page": int, "size": int }`

---

#### `GET /fleets/{fleet_id}`

Get a single fleet.

**Response** `200 OK`: FleetResponse  
**Errors**: `404 Not Found`

---

#### `PUT /fleets/{fleet_id}`

Update fleet settings (quorum_min only; use dedicated endpoints for topology/rules).

**Request**: `{ "quorum_min": 3 }`  
**Response** `200 OK`: FleetResponse

---

#### `POST /fleets/{fleet_id}/archive`

Archive a fleet (irreversible). Deactivates all orchestration rules and governance chains.

**Response** `200 OK`: FleetResponse with `status: "archived"`  
**Errors**: `409 Conflict` if fleet is currently executing tasks

---

#### `GET /fleets/{fleet_id}/health`

Get real-time health projection from Redis.

**Response** `200 OK`:
```json
{
  "fleet_id": "uuid",
  "status": "degraded",
  "health_pct": 0.67,
  "quorum_met": true,
  "available_count": 2,
  "total_count": 3,
  "member_statuses": [
    { "agent_fqn": "finance-ops:kyc-verifier", "availability": "available", "role": "worker" },
    { "agent_fqn": "finance-ops:risk-assessor", "availability": "unavailable", "role": "worker" },
    { "agent_fqn": "finance-ops:orchestrator", "availability": "available", "role": "lead" }
  ],
  "last_updated": "2026-04-12T10:01:30Z"
}
```

---

### Fleet Members

#### `POST /fleets/{fleet_id}/members`

Add an agent as a fleet member.

**Request**: `{ "agent_fqn": "finance-ops:new-agent", "role": "worker" }`  
**Response** `201 Created`: FleetMemberResponse  
**Errors**: `404` if agent FQN not found in registry, `409` if already a member

---

#### `GET /fleets/{fleet_id}/members`

List all fleet members with roles and availability.

**Response** `200 OK`: `{ "items": [FleetMemberResponse, ...] }`

---

#### `DELETE /fleets/{fleet_id}/members/{member_id}`

Remove a member from the fleet.

**Response** `204 No Content`  
**Errors**: `409 Conflict` if removing the member would drop below quorum and no alternative lead exists

---

#### `PUT /fleets/{fleet_id}/members/{member_id}/role`

Change a member's role.

**Request**: `{ "role": "lead" }`  
**Response** `200 OK`: FleetMemberResponse  
**Errors**: `409 Conflict` if promoting to lead but fleet already has a lead (hierarchical topology)

---

### Fleet Topology

#### `PUT /fleets/{fleet_id}/topology`

Update topology type and configuration. Creates a new topology version.

**Request**:
```json
{
  "topology_type": "peer_to_peer",
  "config": {}
}
```

**Response** `200 OK`: FleetTopologyVersionResponse  
**Notes**: Changing from hierarchical removes lead designation from all members.

---

#### `GET /fleets/{fleet_id}/topology/history`

List all topology versions for the fleet.

**Response** `200 OK`: `{ "items": [FleetTopologyVersionResponse, ...] }`

---

### Fleet Policy Bindings

#### `POST /fleets/{fleet_id}/policies`

Bind a policy to the fleet.

**Request**: `{ "policy_id": "uuid" }`  
**Response** `201 Created`: FleetPolicyBindingResponse  
**Errors**: `404` if policy not found, `409` if already bound

---

#### `DELETE /fleets/{fleet_id}/policies/{binding_id}`

Unbind a policy from the fleet.

**Response** `204 No Content`

---

### Observer Assignments

#### `POST /fleets/{fleet_id}/observers`

Assign an observer agent to the fleet.

**Request**: `{ "observer_fqn": "monitoring:fleet-watcher" }`  
**Response** `201 Created`: ObserverAssignmentResponse  
**Errors**: `404` if FQN not in registry, `409` if already assigned

---

#### `DELETE /fleets/{fleet_id}/observers/{assignment_id}`

Remove an observer from the fleet.

**Response** `204 No Content`

---

### Orchestration Rules

#### `GET /fleets/{fleet_id}/orchestration-rules`

Get the current versioned orchestration rules.

**Response** `200 OK`: FleetOrchestrationRulesResponse

---

#### `PUT /fleets/{fleet_id}/orchestration-rules`

Replace the current orchestration rules (creates a new immutable version).

**Request**:
```json
{
  "delegation": { "strategy": "capability_match", "config": {} },
  "aggregation": { "strategy": "vote", "config": { "quorum_pct": 0.6 } },
  "escalation": { "timeout_seconds": 120, "failure_count": 2, "escalate_to": "lead" },
  "conflict_resolution": { "strategy": "majority_vote" },
  "retry": { "max_retries": 3, "then": "reassign" },
  "max_parallelism": 2
}
```

**Response** `200 OK`: FleetOrchestrationRulesResponse  
**Notes**: Previous version is marked `is_current = false` but retained for history.

---

#### `GET /fleets/{fleet_id}/orchestration-rules/history`

List all orchestration rule versions.

**Response** `200 OK`: `{ "items": [FleetOrchestrationRulesResponse, ...] }`

---

### Governance Chain

#### `GET /fleets/{fleet_id}/governance-chain`

Get the current governance chain (OJE configuration).

**Response** `200 OK`: FleetGovernanceChainResponse  
**Notes**: Newly created fleets return the default chain (`is_default: true`).

---

#### `PUT /fleets/{fleet_id}/governance-chain`

Replace the governance chain. Creates a new version.

**Request**:
```json
{
  "observer_fqns": ["monitoring:fleet-observer"],
  "judge_fqns": ["trust:fleet-judge"],
  "enforcer_fqns": ["trust:fleet-enforcer"],
  "policy_binding_ids": ["uuid-of-policy"]
}
```

**Response** `200 OK`: FleetGovernanceChainResponse

---

## REST Endpoints — `fleet_learning/` context

---

### Performance Profiles

#### `GET /fleets/{fleet_id}/performance-profile`

Get the latest performance profile for the fleet, optionally filtered by time range.

**Query params**: `start`, `end` (ISO 8601 datetimes, default: last 24h)

**Response** `200 OK`:
```json
{
  "id": "uuid",
  "fleet_id": "uuid",
  "period_start": "2026-04-11T00:00:00Z",
  "period_end": "2026-04-12T00:00:00Z",
  "avg_completion_time_ms": 8500.0,
  "success_rate": 0.94,
  "cost_per_task": 0.023,
  "avg_quality_score": 0.87,
  "throughput_per_hour": 42.0,
  "member_metrics": {
    "finance-ops:kyc-verifier": {
      "avg_completion_time_ms": 7200.0,
      "success_rate": 0.96,
      "cost_per_task": 0.018,
      "quality_score": 0.91
    }
  },
  "flagged_member_fqns": [],
  "created_at": "2026-04-12T01:00:00Z"
}
```

**Errors**: `404 Not Found` if no profile computed yet for fleet

---

#### `POST /fleets/{fleet_id}/performance-profile/compute`

Trigger an on-demand performance profile computation (admin only).

**Response** `202 Accepted`: `{ "message": "computation started" }`  
**Notes**: Computation runs asynchronously. Poll `GET /performance-profile` for result.

---

#### `GET /fleets/{fleet_id}/performance-profile/history`

List all historical performance profiles.

**Query params**: `page`, `size`  
**Response** `200 OK`: `{ "items": [FleetPerformanceProfileResponse, ...] }`

---

### Adaptation Rules

#### `GET /fleets/{fleet_id}/adaptation-rules`

List all adaptation rules for a fleet.

**Response** `200 OK`: `{ "items": [FleetAdaptationRuleResponse, ...] }`

---

#### `POST /fleets/{fleet_id}/adaptation-rules`

Create an adaptation rule.

**Request**:
```json
{
  "name": "slow-fleet-parallelism-boost",
  "condition": {
    "metric": "avg_completion_time_ms",
    "operator": "gt",
    "threshold": 30000
  },
  "action": {
    "type": "set_max_parallelism",
    "value": 3
  },
  "priority": 10
}
```

**Response** `201 Created`: FleetAdaptationRuleResponse

---

#### `PUT /fleets/{fleet_id}/adaptation-rules/{rule_id}`

Update an adaptation rule.

**Response** `200 OK`: FleetAdaptationRuleResponse

---

#### `DELETE /fleets/{fleet_id}/adaptation-rules/{rule_id}`

Deactivate an adaptation rule (`is_active = false`).

**Response** `204 No Content`

---

#### `GET /fleets/{fleet_id}/adaptation-log`

List adaptation log entries (applied adaptations).

**Query params**: `is_reverted` (bool filter), `page`, `size`  
**Response** `200 OK`: `{ "items": [FleetAdaptationLogResponse, ...] }`

---

#### `POST /fleets/{fleet_id}/adaptation-log/{log_id}/revert`

Revert an applied adaptation (restores pre-adaptation orchestration rules version).

**Response** `200 OK`: FleetAdaptationLogResponse with `is_reverted: true`  
**Errors**: `409 Conflict` if already reverted, `404` if log entry not found

---

### Cross-Fleet Transfer

#### `POST /fleets/{fleet_id}/transfers`

Propose a knowledge transfer request from this fleet (source) to another.

**Request**:
```json
{
  "target_fleet_id": "uuid",
  "pattern_definition": {
    "orchestration_rules_version": 5,
    "description": "Optimized delegation pattern for high-volume processing",
    "rules_snapshot": { "delegation": {...}, "aggregation": {...} }
  }
}
```

**Response** `201 Created`: CrossFleetTransferResponse  
**Errors**: `404` if target fleet not found, `422` if source and target are the same fleet

---

#### `GET /fleets/{fleet_id}/transfers`

List transfer requests where this fleet is either source or target.

**Query params**: `role` (`source|target`), `status`, `page`, `size`  
**Response** `200 OK`: `{ "items": [CrossFleetTransferResponse, ...] }`

---

#### `GET /fleets/transfers/{transfer_id}`

Get a specific transfer request.

**Response** `200 OK`: CrossFleetTransferResponse

---

#### `POST /fleets/transfers/{transfer_id}/approve`

Approve a transfer request (target fleet admin only).

**Response** `200 OK`: CrossFleetTransferResponse with `status: "approved"`  
**Errors**: `403 Forbidden` if not target fleet admin, `409 Conflict` if not in `proposed` status

---

#### `POST /fleets/transfers/{transfer_id}/reject`

Reject a transfer request (target fleet admin).

**Request**: `{ "reason": "Pattern incompatible with current topology" }`  
**Response** `200 OK**: CrossFleetTransferResponse with `status: "rejected"`  
**Errors**: `409 Conflict` if not in `proposed` status

---

#### `POST /fleets/transfers/{transfer_id}/apply`

Apply an approved transfer (system or admin action). Adapts pattern to target fleet topology.

**Response** `200 OK`: CrossFleetTransferResponse with `status: "applied"`  
**Errors**: `409 Conflict` if not in `approved` status, `422` if pattern is incompatible with target topology (returns reason `incompatible_topology`)

---

#### `POST /fleets/transfers/{transfer_id}/revert`

Revert an applied transfer.

**Response** `200 OK**: CrossFleetTransferResponse with `reverted_at` set  
**Errors**: `409 Conflict` if not in `applied` status

---

### Personality Profiles

#### `GET /fleets/{fleet_id}/personality-profile`

Get the current personality profile.

**Response** `200 OK`:
```json
{
  "id": "uuid",
  "fleet_id": "uuid",
  "communication_style": "concise",
  "decision_speed": "fast",
  "risk_tolerance": "moderate",
  "autonomy_level": "semi_autonomous",
  "version": 2,
  "is_current": true,
  "created_at": "2026-04-10T09:00:00Z"
}
```

---

#### `PUT /fleets/{fleet_id}/personality-profile`

Update personality profile (creates a new version).

**Request**:
```json
{
  "communication_style": "structured",
  "decision_speed": "deliberate",
  "risk_tolerance": "conservative",
  "autonomy_level": "supervised"
}
```

**Response** `200 OK`: FleetPersonalityProfileResponse  
**Notes**: Takes effect on the next task dispatch. Previous version retained for history.

---

## Internal Service Interfaces

### `FleetServiceInterface` (used by execution engine, trust service)

```python
class FleetServiceInterface:
    """Internal interface for other bounded contexts to query fleet state."""

    async def get_fleet_members(fleet_id: UUID) -> list[FleetMemberResponse]
    """Returns current active member list with roles and availability."""

    async def get_orchestration_rules(fleet_id: UUID) -> FleetOrchestrationRulesResponse
    """Returns current orchestration rules for dispatch decisions."""

    async def get_governance_chain(fleet_id: UUID) -> FleetGovernanceChainResponse
    """Returns OJE chain config for trust service to execute."""

    async def get_orchestration_modifier(fleet_id: UUID) -> OrchestrationModifier
    """Returns personality-derived modifier for dispatch defaults."""

    async def record_member_failure(fleet_id: UUID, agent_fqn: str) -> None
    """Called by execution engine when a member fails; triggers health refresh."""
```

### `OJEPipelineServiceInterface` (called by governance.py, defined in trust/)

```python
class OJEPipelineServiceInterface:
    """trust/ bounded context interface — fleet governance delegates OJE execution here."""

    async def process_fleet_anomaly_signal(
        fleet_id: UUID,
        chain_config: FleetGovernanceChainResponse,
        signal: dict,
    ) -> OJEVerdictResponse
    """Executes the OJE pipeline for a fleet anomaly signal.
    Observer already ran (is the signal source). Invokes judge agents by FQN
    against bound policies; routes enforcer action based on verdict."""
```

### `AnalyticsClickHouseQueryInterface` (used by performance.py, defined in common/clients)

```python
# FleetPerformanceProfileService uses ClickHouseClient directly:
# Query execution_metrics table for fleet member FQNs over period
# SELECT agent_fqn, avg(completion_time_ms), count(*), sum(cost), avg(quality_score)
# FROM execution_metrics
# WHERE agent_fqn IN (:member_fqns) AND completed_at BETWEEN :start AND :end
# GROUP BY agent_fqn
```

---

## Kafka Events Reference

### Topic: `fleet.events`

| Event type | Key | Schema |
|---|---|---|
| `fleet.created` | fleet_id | `{fleet_id, workspace_id, name, topology_type}` |
| `fleet.archived` | fleet_id | `{fleet_id, workspace_id}` |
| `fleet.status.changed` | fleet_id | `{fleet_id, status, previous_status, reason}` |
| `fleet.member.added` | fleet_id | `{fleet_id, agent_fqn, role}` |
| `fleet.member.removed` | fleet_id | `{fleet_id, agent_fqn}` |
| `fleet.topology.changed` | fleet_id | `{fleet_id, version, topology_type}` |
| `fleet.orchestration_rules.updated` | fleet_id | `{fleet_id, version}` |
| `fleet.governance_chain.updated` | fleet_id | `{fleet_id, version, is_default}` |
| `fleet.adaptation.applied` | fleet_id | `{fleet_id, rule_id, before_version, after_version}` |
| `fleet.transfer.status_changed` | transfer_id | `{transfer_id, source_fleet_id, target_fleet_id, status}` |

### Topic: `fleet.health`

| Event type | Key | Schema |
|---|---|---|
| `fleet.health.updated` | fleet_id | `{fleet_id, workspace_id, health_pct, quorum_met, status, available_count, total_count, member_statuses: [...]}` |

All events use the canonical `EventEnvelope` with `correlation_context` (workspace_id, fleet_id) and `trace_context`.
