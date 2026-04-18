# API Contracts: FQN Namespace System and Agent Identity

**Feature**: 051-fqn-namespace-agent-identity
**Phase**: 1 — Design
**Date**: 2026-04-18
**Status**: Mostly existing (021); this document records the full contract including changes

---

## Base Path: `/api/v1`

All endpoints require `X-Workspace-ID` header (workspace UUID) and a valid JWT bearer token.

---

## Namespace Endpoints (EXISTING — no changes)

### POST /namespaces

Create a namespace within the authenticated workspace.

**Request**:
```json
{
  "name": "finance-ops",
  "description": "Financial operations agents"
}
```

**Validation**:
- `name`: slug pattern `[a-z][a-z0-9-]{0,62}`, unique within workspace
- `description`: optional, max 500 chars

**Response 201**:
```json
{
  "id": "uuid",
  "name": "finance-ops",
  "description": "Financial operations agents",
  "workspace_id": "uuid",
  "created_at": "ISO8601",
  "created_by": "uuid"
}
```

**Errors**: 409 if name already exists in workspace, 422 on validation failure

---

### GET /namespaces

List all namespaces in the authenticated workspace.

**Query params**: `limit` (default 50, max 200), `offset` (default 0)

**Response 200**:
```json
{
  "items": [/* NamespaceResponse[] */],
  "total": 3
}
```

---

### DELETE /namespaces/{namespace_id}

Delete a namespace. Blocked if any agent profiles exist in the namespace.

**Response 204**: Success

**Errors**: 404 if not found, 409 if namespace has active agents (response includes agent count)

---

## Agent Endpoints (EXISTING — validation change only)

### POST /agents/upload

Upload an agent package (multipart/form-data). Parses manifest from package.

**Manifest fields (changed in this feature)**:
```yaml
namespace: finance-ops              # must exist in workspace
local_name: kyc-verifier            # slug, unique in namespace
purpose: >                          # CHANGED: now min_length=50
  Verifies KYC compliance for new account applications by checking
  submitted documents against regulatory requirements.
approach: >                         # optional
  Uses a document verification pipeline with confidence scoring.
role_types: [executor]              # at least one required
version: "1.0.0"                    # semver
```

**Response 201**: `AgentProfileResponse` (see GET /agents/{id})

**Errors**: 422 on validation failure (including purpose < 50 chars), 409 if FQN already taken

---

### GET /agents/resolve/{fqn}

Resolve an agent by exact FQN. FQN format: `namespace:local_name`.

**Path param**: `fqn` — e.g., `finance-ops:kyc-verifier`

**Response 200**:
```json
{
  "id": "uuid",
  "fqn": "finance-ops:kyc-verifier",
  "namespace_id": "uuid",
  "display_name": "KYC Verifier",
  "purpose": "Verifies KYC compliance...",
  "approach": null,
  "role_types": ["executor"],
  "visibility_agents": ["finance-ops:aml-checker"],
  "visibility_tools": ["tools:document-verify:*"],
  "tags": [],
  "status": "published",
  "maturity_level": 2,
  "workspace_id": "uuid",
  "created_at": "ISO8601",
  "current_revision": {
    "id": "uuid",
    "version": "1.0.0",
    "sha256_digest": "abc123...",
    "uploaded_by": "uuid",
    "created_at": "ISO8601"
  }
}
```

**Errors**: 404 if FQN does not exist in the workspace

---

### GET /agents

List agents with optional filtering including FQN pattern discovery.

**Query params**:
- `fqn_pattern`: glob pattern e.g., `finance-ops:*`, `*:kyc-*`
- `keyword`: full-text search in purpose/display_name
- `status`: one of `draft|validated|published|disabled|deprecated|archived`
- `maturity_min`: integer 0–3
- `limit`: default 50, max 200
- `offset`: default 0

**Pattern syntax**:
- `finance-ops:*` — all agents in namespace "finance-ops"
- `*:kyc-*` — agents whose local name starts with "kyc-" in any namespace
- `finance-ops:kyc-verifier` — exact match (same as resolve endpoint)
- `*` — all agents visible to caller (subject to visibility enforcement)

**Response 200**:
```json
{
  "items": [/* AgentProfileResponse[] */],
  "total": 42,
  "limit": 50,
  "offset": 0
}
```

---

### GET /agents/{agent_id}

Get agent by UUID.

**Response 200**: `AgentProfileResponse` (same as resolve)

**Errors**: 404 if not found in workspace

---

### PATCH /agents/{agent_id}

Update agent metadata. Partial update — only provided fields are changed.

**Request**:
```json
{
  "display_name": "Updated Name",
  "approach": "New approach text",
  "visibility_agents": ["finance-ops:*"],
  "visibility_tools": ["tools:doccheck:*"],
  "role_types": ["executor", "observer"],
  "tags": ["finance", "kyc"]
}
```

**Note**: `purpose` is NOT patchable via PATCH (requires re-upload with new package version). This preserves the audit trail linking purpose to a specific agent revision.

**Response 200**: Updated `AgentProfileResponse`

---

### POST /agents/{agent_id}/transition

Lifecycle state transition.

**Request**: `{"target_status": "published", "reason": "Passed all eval checks"}`

**Response 200**: Updated `AgentProfileResponse`

---

## Event Context Contract (CHANGED)

### CorrelationContext (Kafka event payload field)

Used in every `EventEnvelope.correlation_context`.

```json
{
  "workspace_id": "uuid | null",
  "conversation_id": "uuid | null",
  "interaction_id": "uuid | null",
  "execution_id": "uuid | null",
  "fleet_id": "uuid | null",
  "goal_id": "uuid | null",
  "correlation_id": "uuid",
  "agent_fqn": "string | null"
}
```

**Changed field**: `agent_fqn` — NEW optional string field. Format: `"namespace:local_name"` (e.g., `"finance-ops:kyc-verifier"`). Set by event producers that have access to the originating agent's FQN. `null` for events not originating from an identified agent (e.g., system events, human actions).

**Backward compatibility**: All existing consumers that deserialize `CorrelationContext` continue to work. JSON deserialization ignores unknown fields by default in Pydantic v2.

---

## Internal Service Interface (EXISTING — no changes)

### RegistryService.resolve_effective_visibility(agent_id, workspace_id)

Returns the union of per-agent and workspace-level visibility patterns. Called by:
- Policy engine (tool gateway)
- Agent discovery service (filtering query results)

No changes to this interface. The FQN patterns in `visibility_agents` and `visibility_tools` are already the correct format.
