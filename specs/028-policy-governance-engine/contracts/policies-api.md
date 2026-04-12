# API Contracts: Policy and Governance Engine

**Branch**: `028-policy-governance-engine` | **Date**: 2026-04-12 | **Phase**: 1

All endpoints prefixed `/api/v1`. Requires `Authorization: Bearer <access_token>` (platform_admin or workspace_admin role for write operations; any authenticated user for read).

---

## Policy CRUD Endpoints

### `POST /policies`

Create a new policy with version 1.

**Request Body**: `PolicyCreate`
```json
{
  "name": "Finance Workspace Policy",
  "description": "Restricts finance agents to approved tools",
  "scope_type": "workspace",
  "workspace_id": "uuid",
  "rules": {
    "enforcement_rules": [
      {
        "id": "rule-001",
        "action": "allow",
        "tool_patterns": ["calculator", "spreadsheet"],
        "applicable_step_types": ["tool_invocation"]
      },
      {
        "id": "rule-002",
        "action": "deny",
        "tool_patterns": ["*"],
        "applicable_step_types": ["tool_invocation"]
      }
    ],
    "budget_limits": { "max_tool_invocations_per_execution": 50 }
  },
  "change_summary": "Initial finance workspace policy"
}
```

**Response**: `201 Created` — `PolicyWithVersionResponse`

**Error Codes**:
- `403` — Insufficient permissions
- `422` — Validation error (e.g., negative budget, invalid scope_type)

---

### `GET /policies`

List policies with optional filters.

**Query Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `scope_type` | `string?` | Filter by scope (global/deployment/workspace/agent) |
| `status` | `string?` | Filter by status (active/archived, default: active) |
| `workspace_id` | `uuid?` | Filter by workspace |
| `page` | `int?` | Page number (default: 1) |
| `page_size` | `int?` | Items per page (default: 20, max: 100) |

**Response**: `200 OK` — `PolicyListResponse`

---

### `GET /policies/{policy_id}`

Retrieve a specific policy with its current version.

**Response**: `200 OK` — `PolicyWithVersionResponse`

**Error Codes**: `404` — Policy not found

---

### `PATCH /policies/{policy_id}`

Update policy name/description/rules — creates a new immutable version.

**Request Body**: `PolicyUpdate`
```json
{
  "rules": { "enforcement_rules": [...] },
  "change_summary": "Added external API denial rule"
}
```

**Response**: `200 OK` — `PolicyWithVersionResponse` (current_version reflects new version)

**Error Codes**: `403`, `404`, `422`

---

### `POST /policies/{policy_id}/archive`

Archive a policy (soft-delete). Existing attachments are flagged as inactive.

**Request Body**: _(empty)_

**Response**: `200 OK` — `PolicyResponse`

**Error Codes**: `403`, `404`, `409` — Policy already archived

---

### `GET /policies/{policy_id}/versions`

Retrieve the full version history of a policy.

**Response**: `200 OK`
```json
{
  "items": [PolicyVersionResponse, ...],
  "total": 5
}
```

---

### `GET /policies/{policy_id}/versions/{version_number}`

Retrieve a specific historical version.

**Response**: `200 OK` — `PolicyVersionResponse`

**Error Codes**: `404`

---

## Policy Attachment Endpoints

### `POST /policies/{policy_id}/attach`

Attach a policy version to a target entity.

**Request Body**: `PolicyAttachRequest`
```json
{
  "policy_version_id": null,
  "target_type": "workspace",
  "target_id": "workspace-uuid"
}
```
`policy_version_id: null` — attaches current version.

**Response**: `201 Created` — `PolicyAttachResponse`

**Error Codes**: `403`, `404` (policy or target not found), `409` (already attached)

---

### `DELETE /policies/{policy_id}/attach/{attachment_id}`

Deactivate a policy attachment.

**Response**: `204 No Content`

**Error Codes**: `403`, `404`

---

### `GET /policies/{policy_id}/attachments`

List all active attachments for a policy.

**Response**: `200 OK`
```json
{ "items": [PolicyAttachResponse, ...] }
```

---

## Effective Policy and Compilation Endpoints

### `GET /policies/effective/{agent_id}`

Resolve and return the effective policy for an agent (composition across all scopes).

**Query Parameters**: `workspace_id` (required)

**Response**: `200 OK` — `EffectivePolicyResponse`
```json
{
  "agent_id": "uuid",
  "resolved_rules": [
    {
      "rule": { "action": "allow", "tool_patterns": ["calculator"] },
      "provenance": {
        "policy_id": "uuid",
        "version_id": "uuid",
        "scope_level": 2,
        "scope_type": "workspace",
        "scope_target_id": "workspace-uuid"
      }
    }
  ],
  "conflicts": [],
  "source_policies": ["uuid1", "uuid2"]
}
```

**Error Codes**: `400` (workspace_id missing), `404` (agent not found)

---

### `GET /policies/bundle/{agent_id}`

Return the compiled enforcement bundle for an agent (from cache or freshly compiled).

**Query Parameters**: `workspace_id` (required), `step_type?` (optional — returns task-scoped shard)

**Response**: `200 OK` — `EnforcementBundle`

Includes `manifest.fingerprint` for cache verification.

---

### `POST /policies/bundle/{agent_id}/invalidate`

Explicitly invalidate the cached bundle for an agent (admin use, e.g., after emergency policy change).

**Response**: `204 No Content`

---

## Blocked Action Records Endpoints

### `GET /policies/blocked-actions`

List blocked action records with filtering.

**Query Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `agent_id` | `uuid?` | Filter by agent |
| `enforcement_component` | `string?` | tool_gateway / memory_write_gate / sanitizer |
| `workspace_id` | `uuid?` | Filter by workspace |
| `execution_id` | `uuid?` | Filter by execution |
| `since` | `datetime?` | ISO 8601 start time |
| `page` | `int?` | Default: 1 |
| `page_size` | `int?` | Default: 20 |

**Response**: `200 OK`
```json
{
  "items": [{
    "id": "uuid",
    "agent_id": "uuid",
    "agent_fqn": "finance-ops:kyc-verifier",
    "enforcement_component": "tool_gateway",
    "action_type": "tool_invocation",
    "target": "external-api:payment-gateway",
    "block_reason": "permission_denied",
    "policy_rule_ref": { "policy_id": "uuid", "version_id": "uuid", "rule_id": "rule-002" },
    "execution_id": "uuid",
    "workspace_id": "uuid",
    "created_at": "2026-04-12T10:00:00Z"
  }],
  "total": 42
}
```

---

### `GET /policies/blocked-actions/{record_id}`

Retrieve a specific blocked action record.

**Response**: `200 OK` — full `PolicyBlockedActionRecord`

---

## Maturity Gate Endpoints

### `GET /policies/maturity-gates`

List maturity gate rules (what capabilities each level unlocks).

**Response**: `200 OK`
```json
{
  "levels": [
    { "level": 0, "capabilities": ["basic_tools", "own_namespace_memory"] },
    { "level": 1, "capabilities": ["external_api_calls"] },
    { "level": 2, "capabilities": ["cross_namespace_memory"] },
    { "level": 3, "capabilities": ["fleet_coordination"] }
  ]
}
```

---

## Internal Service Interfaces

### `PolicyService.get_enforcement_bundle(agent_id, workspace_id)` — called by:
- `execution/` bounded context tool dispatcher (before every native tool invocation)
- `a2a_gateway/` (before every A2A tool invocation)
- `connectors/` MCP proxy (before every MCP tool invocation)

### `ToolGatewayService.validate_tool_invocation(...)` — called by:
- Execution engine tool dispatcher
- A2A gateway task handler
- MCP proxy handler

### `ToolGatewayService.sanitize_tool_output(...)` — called by:
- Same callers, after tool execution completes

### `MemoryWriteGateService.validate_memory_write(...)` — called by:
- `memory/` bounded context `MemoryService.write_entry()` before every write

### `PolicyService.get_visibility_filter(agent_id)` — called by:
- `registry/` bounded context repository for agent/tool discovery queries

---

## Kafka Events Produced

| Topic | Event Type | Key | Description |
|-------|-----------|-----|-------------|
| `policy.events` | `policy.created` | `policy_id` | New policy created |
| `policy.events` | `policy.updated` | `policy_id` | Policy version incremented |
| `policy.events` | `policy.archived` | `policy_id` | Policy archived |
| `policy.events` | `policy.attached` | `policy_id` | Policy version attached to target |
| `policy.events` | `policy.detached` | `policy_id` | Attachment deactivated |
| `policy.gate.blocked` | `policy.gate.blocked` | `agent_id` | Tool or memory write blocked |
| `policy.gate.allowed` | `policy.gate.allowed` | `agent_id` | Tool allowed (opt-in per rule) |
