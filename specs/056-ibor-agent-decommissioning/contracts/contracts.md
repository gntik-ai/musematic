# Interface Contracts: IBOR Integration and Agent Decommissioning

**Feature**: `specs/056-ibor-agent-decommissioning/spec.md`
**Date**: 2026-04-18

---

## Contract 1: POST /api/v1/registry/{workspace_id}/agents/{agent_id}/decommission

**Auth**: Bearer JWT; requires `workspace_owner` on the agent's workspace OR `platform_admin` (403 otherwise per FR-009)

**Request body**:
```json
{
  "reason": "Regulatory retirement — Q2 2026 compliance audit"
}
```
`reason` MUST be between 10 and 2000 characters (422 otherwise per FR-008).

**Response 200**:
```json
{
  "agent_id": "550e8400-e29b-41d4-a716-446655440000",
  "agent_fqn": "acme/finance/tax-reconciler",
  "decommissioned_at": "2026-04-18T12:34:56Z",
  "decommission_reason": "Regulatory retirement — Q2 2026 compliance audit",
  "decommissioned_by": "7c9b2a1d-...",
  "active_instances_stopped": 2
}
```

**Response 200 (idempotent)**: Identical response when called on an already-decommissioned agent; `decommissioned_at` and `decommission_reason` are the ORIGINAL values, not updated.

**Response 403**: Caller lacks required role.
**Response 404**: Agent not found in the specified workspace.
**Response 409**: Invalid state transition (should not occur — all non-terminal states permit decommission per state machine).
**Response 422**: `reason` shorter than 10 chars or longer than 2000 chars.

---

## Contract 2: POST /api/v1/auth/ibor/connectors

**Auth**: Bearer JWT; requires `platform_admin`.

**Request body**:
```json
{
  "name": "corp-ldap-primary",
  "source_type": "ldap",
  "sync_mode": "pull",
  "cadence_seconds": 3600,
  "credential_ref": "ibor-ldap-creds-primary",
  "role_mapping_policy": [
    { "directory_group": "CN=PlatformAdmins,OU=Groups,DC=corp,DC=com",
      "platform_role": "platform_admin", "workspace_scope": null },
    { "directory_group": "CN=MLEngineers,OU=Groups,DC=corp,DC=com",
      "platform_role": "workspace_member", "workspace_scope": "550e8400-..." }
  ],
  "enabled": true
}
```

**Response 201**: `IBORConnectorResponse` (credential_ref returned as name only, value never exposed).

**Response 409**: Connector `name` already exists.
**Response 422**: Validation error (invalid `source_type`, `cadence_seconds` out of [60, 86400], etc.).

---

## Contract 3: GET /api/v1/auth/ibor/connectors

**Auth**: `platform_admin`.
**Response 200**: `{"items": [IBORConnectorResponse, ...]}` — all connectors, sorted by `name`. `credential_ref` values redacted.

---

## Contract 4: GET /api/v1/auth/ibor/connectors/{id}

**Auth**: `platform_admin`.
**Response 200**: `IBORConnectorResponse`.
**Response 404**: Not found.

---

## Contract 5: PUT /api/v1/auth/ibor/connectors/{id}

**Auth**: `platform_admin`.
**Request body**: Same schema as POST (full replacement).
**Response 200**: Updated `IBORConnectorResponse`.

---

## Contract 6: DELETE /api/v1/auth/ibor/connectors/{id}

**Auth**: `platform_admin`.
**Behavior**: Soft-disable — sets `enabled=false`. Existing `ibor_sync_runs` history retained (FR-006). Existing IBOR-sourced `user_roles` rows are NOT auto-revoked; operator must do so explicitly via a separate admin action if desired.
**Response 204**: No content.

---

## Contract 7: POST /api/v1/auth/ibor/connectors/{id}/sync

**Auth**: `platform_admin`.
**Request body**: Empty.
**Response 202**:
```json
{
  "run_id": "f3a8b1c2-...",
  "connector_id": "7c9b2a1d-...",
  "status": "running",
  "started_at": "2026-04-18T12:34:56Z"
}
```

**Response 409**: A sync run is already in progress for this connector (Redis lock `ibor:sync:{connector_id}` held).

The run completes asynchronously; poll `GET /runs` for status.

---

## Contract 8: GET /api/v1/auth/ibor/connectors/{id}/runs

**Auth**: `platform_admin`.
**Query params**: `limit` (default 90, max 500), `cursor` (opaque pagination cursor).
**Response 200**:
```json
{
  "items": [
    {
      "id": "f3a8b1c2-...",
      "connector_id": "7c9b2a1d-...",
      "mode": "pull",
      "started_at": "2026-04-18T12:34:56Z",
      "finished_at": "2026-04-18T12:35:42Z",
      "status": "succeeded",
      "counts": {
        "users_created": 0,
        "users_updated": 3,
        "roles_added": 5,
        "roles_revoked": 1,
        "errors": 0
      },
      "error_details": [],
      "triggered_by": null
    }
  ],
  "next_cursor": null
}
```

---

## Contract 9: Kafka event `agent_decommissioned`

**Topic**: `registry.events` (existing)
**Event type**: `"agent_decommissioned"`
**Schema**:
```json
{
  "event_id": "<uuid>",
  "event_type": "agent_decommissioned",
  "correlation_id": "<correlation_id>",
  "workspace_id": "<uuid>",
  "created_at": "<iso8601>",
  "data": {
    "agent_profile_id": "<uuid>",
    "fqn": "acme/finance/tax-reconciler",
    "decommissioned_by": "<uuid>",
    "decommissioned_at": "<iso8601>",
    "reason": "<text>",
    "active_instance_count_at_decommission": 2
  }
}
```

**Consumers**: Analytics (feature 020) for cost attribution; Trust (feature 012) for certification state update; Operator dashboard (feature 044) for alerts.

---

## Contract 10: Kafka event `ibor_sync_completed`

**Topic**: `auth.events` (existing)
**Event type**: `"ibor_sync_completed"`
**Schema**:
```json
{
  "event_id": "<uuid>",
  "event_type": "ibor_sync_completed",
  "correlation_id": "<correlation_id>",
  "created_at": "<iso8601>",
  "data": {
    "run_id": "<uuid>",
    "connector_id": "<uuid>",
    "connector_name": "corp-ldap-primary",
    "mode": "pull",
    "status": "succeeded",
    "duration_ms": 46000,
    "counts": { "users_created": 0, "users_updated": 3, "roles_added": 5, "roles_revoked": 1, "errors": 0 }
  }
}
```

---

## Contract 11: Registry list/search contract (invisibility extension)

**Existing endpoints** (behavior change — decommissioned agents now excluded where `archived` was):

- `GET /api/v1/registry/{workspace_id}/agents` — excludes `decommissioned` from default listing; `include_decommissioned=true` query param allowed for admin/audit views only.
- `GET /api/v1/marketplace/search` — excludes `decommissioned` unconditionally (no override).
- `GET /api/v1/marketplace/agents/{namespace}/{name}` — returns 200 with `status="decommissioned"` and an `invocable=false` flag; does NOT 404 so historical deep-links resolve for audit/context.
- Workflow-builder agent picker and fleet-composition picker (backend endpoints consumed by UI): exclude `decommissioned` unconditionally.

Audit APIs (`/api/v1/policies/blocked-actions`, `/api/v1/analytics/agents/*`, `/api/v1/evaluation/agents/*`, lifecycle audit queries): include `decommissioned` agents in results so prior executions, blocks, metrics, and certifications remain queryable (FR-012).

---

## Contract 12: State transition contract — decommissioned is terminal

**Existing endpoint**: `POST /api/v1/registry/{workspace_id}/agents/{agent_id}/transition`

**New behavior**: Any request where `current_status == decommissioned` returns 409 with `{"code": "INVALID_TRANSITION", "message": "decommissioned is a terminal state; re-register the agent to restore functionality"}`.

**No change to existing valid transitions**; `decommissioned` is purely additive as a target state from every non-terminal status.
