# REST API Contracts: Judge/Enforcer Governance Pipeline

**Feature**: 061-judge-enforcer-governance  
**Base Path**: `/api/v1`  
**Date**: 2026-04-18

---

## Fleet Governance Chain (already exists — additive changes only)

The following endpoints already exist in `fleets/router.py`. They are updated only in their request/response shape to include the new `verdict_to_action_mapping` field.

### GET /fleets/{fleet_id}/governance-chain

**Description**: Retrieve the current governance chain configuration for a fleet.  
**Auth**: Workspace-scoped; any workspace member can read.  
**Change**: Response now includes `verdict_to_action_mapping`.

**Response 200**:
```json
{
  "id": "uuid",
  "fleet_id": "uuid",
  "version": 3,
  "observer_fqns": ["platform:anomaly-detector"],
  "judge_fqns": ["platform:policy-judge"],
  "enforcer_fqns": ["platform:enforcer-1"],
  "policy_binding_ids": ["uuid"],
  "verdict_to_action_mapping": {
    "VIOLATION": "block",
    "WARNING": "notify",
    "ESCALATE_TO_HUMAN": "quarantine"
  },
  "is_current": true,
  "is_default": false,
  "created_at": "2026-04-18T10:00:00Z"
}
```

### PUT /fleets/{fleet_id}/governance-chain

**Description**: Replace the current governance chain configuration for a fleet.  
**Auth**: Workspace admin or owner.  
**Change**: Request body now includes optional `verdict_to_action_mapping`.

**Request body**:
```json
{
  "observer_fqns": ["platform:anomaly-detector"],
  "judge_fqns": ["platform:policy-judge"],
  "enforcer_fqns": ["platform:enforcer-1"],
  "policy_binding_ids": ["uuid"],
  "verdict_to_action_mapping": {
    "VIOLATION": "block",
    "WARNING": "notify"
  }
}
```

**Response 200**: Same shape as GET.

**Response 422** (validation error — FR-011, FR-012, FR-025):
```json
{
  "detail": "Agent platform:policy-judge does not have the judge role",
  "code": "CHAIN_VALIDATION_ERROR"
}
```

---

## Workspace Governance Chain (new endpoints)

These endpoints mirror the fleet governance chain pattern.

### GET /workspaces/{workspace_id}/governance-chain

**Description**: Retrieve the current workspace-level governance chain.  
**Auth**: Workspace-scoped member.

**Response 200**:
```json
{
  "id": "uuid",
  "workspace_id": "uuid",
  "version": 1,
  "observer_fqns": ["platform:anomaly-detector"],
  "judge_fqns": ["platform:policy-judge"],
  "enforcer_fqns": ["platform:enforcer-1"],
  "policy_binding_ids": ["uuid"],
  "verdict_to_action_mapping": {
    "VIOLATION": "block",
    "WARNING": "notify",
    "ESCALATE_TO_HUMAN": "quarantine"
  },
  "is_current": true,
  "is_default": false,
  "created_at": "2026-04-18T10:00:00Z"
}
```

**Response 404** — workspace has no configured chain:
```json
{
  "detail": "Workspace governance chain not configured",
  "code": "WORKSPACE_GOVERNANCE_NOT_FOUND"
}
```

### PUT /workspaces/{workspace_id}/governance-chain

**Description**: Configure or replace the workspace-level governance chain. Takes precedence over the fleet-level chain (FR-013).  
**Auth**: Workspace admin or owner.

**Request body**:
```json
{
  "observer_fqns": ["platform:anomaly-detector"],
  "judge_fqns": ["platform:policy-judge"],
  "enforcer_fqns": ["platform:enforcer-1"],
  "policy_binding_ids": ["uuid"],
  "verdict_to_action_mapping": {
    "VIOLATION": "block"
  }
}
```

**Response 200**: Same shape as GET /governance-chain.  
**Response 422**: Same validation errors as fleet endpoint.

### GET /workspaces/{workspace_id}/governance-chain/history

**Description**: List all historical versions of the workspace governance chain.  
**Auth**: Workspace admin or owner (audit trail).

**Response 200**:
```json
{
  "items": [...],
  "total": 3
}
```

---

## Governance Audit Queries (new endpoints)

All audit endpoints require `RoleType.AUDITOR`.

### GET /governance/verdicts

**Description**: List governance verdicts with filtering. FR-017, FR-018.  
**Auth**: AUDITOR role.

**Query parameters**:
| Parameter | Type | Description |
|---|---|---|
| `target_agent_fqn` | string | Filter by target agent FQN (matched via source_event_id resolution) |
| `judge_agent_fqn` | string | Filter by judge agent FQN |
| `policy_id` | UUID | Filter by policy reference |
| `verdict_type` | string | COMPLIANT / WARNING / VIOLATION / ESCALATE_TO_HUMAN |
| `fleet_id` | UUID | Filter by fleet |
| `workspace_id` | UUID | Filter by workspace |
| `from_time` | ISO8601 | Start of time range (inclusive) |
| `to_time` | ISO8601 | End of time range (inclusive) |
| `limit` | int | Page size (default 50, max 200) |
| `cursor` | string | Opaque pagination cursor |

**Response 200**:
```json
{
  "items": [
    {
      "id": "uuid",
      "judge_agent_fqn": "platform:policy-judge",
      "verdict_type": "VIOLATION",
      "policy_id": "uuid",
      "rationale": "Signal exceeded threshold for policy X",
      "recommended_action": "block",
      "source_event_id": "uuid",
      "fleet_id": "uuid",
      "workspace_id": "uuid",
      "created_at": "2026-04-18T10:00:00Z"
    }
  ],
  "total": 42,
  "next_cursor": "opaque-cursor-string"
}
```

**Response 403** — not AUDITOR:
```json
{"detail": "Insufficient role: auditor required", "code": "AUTHORIZATION_ERROR"}
```

### GET /governance/verdicts/{verdict_id}

**Description**: Full detail for a single verdict, including evidence payload and linked enforcement action.  
**Auth**: AUDITOR role.

**Response 200**:
```json
{
  "id": "uuid",
  "judge_agent_fqn": "platform:policy-judge",
  "verdict_type": "VIOLATION",
  "policy_id": "uuid",
  "evidence": {"signal_value": 0.97, "threshold": 0.8, "metric": "error_rate"},
  "rationale": "Error rate 0.97 exceeds policy threshold 0.8",
  "recommended_action": "block",
  "source_event_id": "uuid",
  "fleet_id": "uuid",
  "workspace_id": "uuid",
  "created_at": "2026-04-18T10:00:00Z",
  "enforcement_action": {
    "id": "uuid",
    "enforcer_agent_fqn": "platform:enforcer-1",
    "verdict_id": "uuid",
    "action_type": "block",
    "target_agent_fqn": "acme:my-agent",
    "outcome": {"blocked": true, "previous_state": "active"},
    "workspace_id": "uuid",
    "created_at": "2026-04-18T10:00:03Z"
  }
}
```

**Response 404** — verdict not found:
```json
{"detail": "Governance verdict not found", "code": "VERDICT_NOT_FOUND"}
```

### GET /governance/enforcement-actions

**Description**: List enforcement actions with filtering.  
**Auth**: AUDITOR role.

**Query parameters**:
| Parameter | Type | Description |
|---|---|---|
| `action_type` | string | block / quarantine / notify / revoke_cert / log_and_continue |
| `verdict_id` | UUID | Filter by triggering verdict |
| `target_agent_fqn` | string | Filter by target agent |
| `workspace_id` | UUID | Filter by workspace |
| `from_time` | ISO8601 | Start of time range |
| `to_time` | ISO8601 | End of time range |
| `limit` | int | Page size (default 50, max 200) |
| `cursor` | string | Opaque pagination cursor |

**Response 200**:
```json
{
  "items": [
    {
      "id": "uuid",
      "enforcer_agent_fqn": "platform:enforcer-1",
      "verdict_id": "uuid",
      "action_type": "revoke_cert",
      "target_agent_fqn": "acme:my-agent",
      "outcome": {"revoked_cert_id": "uuid", "revocation_reason": "VIOLATION verdict"},
      "workspace_id": "uuid",
      "created_at": "2026-04-18T10:00:03Z"
    }
  ],
  "total": 17,
  "next_cursor": null
}
```

---

## Kafka Event Shapes

### governance.verdict.issued

**Topic**: `governance.verdict.issued`  
**Producer**: `JudgeService`  
**Consumers**: `EnforcerService (VerdictConsumer)`, audit log, operator dashboard  
**Key**: `str(fleet_id or workspace_id)`

**Payload** (`VerdictIssuedPayload`):
```json
{
  "verdict_id": "uuid",
  "judge_agent_fqn": "platform:policy-judge",
  "verdict_type": "VIOLATION",
  "policy_id": "uuid",
  "fleet_id": "uuid",
  "workspace_id": "uuid",
  "source_event_id": "uuid",
  "recommended_action": "block"
}
```

### governance.enforcement.executed

**Topic**: `governance.enforcement.executed`  
**Producer**: `EnforcerService`  
**Consumers**: Audit log, operator dashboard  
**Key**: `str(verdict_id)`

**Payload** (`EnforcementExecutedPayload`):
```json
{
  "action_id": "uuid",
  "verdict_id": "uuid",
  "enforcer_agent_fqn": "platform:enforcer-1",
  "action_type": "block",
  "target_agent_fqn": "acme:my-agent",
  "workspace_id": "uuid",
  "outcome": {"blocked": true}
}
```
