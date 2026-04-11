# API Contracts: Agent Registry and Ingest

**Feature**: 021-agent-registry-ingest  
**Date**: 2026-04-11  
**Base URL**: `/api/v1`  
**Auth**: Bearer JWT (all endpoints require authentication)

---

## Namespace Endpoints

### POST /api/v1/namespaces

Create a new namespace within a workspace.

**Request**
```http
POST /api/v1/namespaces
Authorization: Bearer {jwt}
Content-Type: application/json
X-Workspace-ID: {workspace_id}

{
  "name": "finance-ops",
  "description": "Financial operations agents"
}
```

**Response 201 Created**
```json
{
  "id": "uuid",
  "name": "finance-ops",
  "description": "Financial operations agents",
  "workspace_id": "uuid",
  "created_at": "2026-04-11T10:00:00Z",
  "created_by": "uuid"
}
```

**Errors**:
- `409 Conflict` — namespace name already exists in this workspace
- `422 Unprocessable Entity` — invalid name format (not slug)
- `403 Forbidden` — user not a member of the workspace

---

### GET /api/v1/namespaces

List all namespaces in a workspace.

**Request**
```http
GET /api/v1/namespaces
Authorization: Bearer {jwt}
X-Workspace-ID: {workspace_id}
```

**Response 200 OK**
```json
{
  "items": [
    {
      "id": "uuid",
      "name": "finance-ops",
      "description": "Financial operations agents",
      "workspace_id": "uuid",
      "created_at": "2026-04-11T10:00:00Z",
      "created_by": "uuid"
    }
  ],
  "total": 1
}
```

---

### DELETE /api/v1/namespaces/{namespace_id}

Delete an empty namespace (no registered agents).

**Request**
```http
DELETE /api/v1/namespaces/{namespace_id}
Authorization: Bearer {jwt}
X-Workspace-ID: {workspace_id}
```

**Response 204 No Content**

**Errors**:
- `409 Conflict` — namespace still has registered agents
- `404 Not Found` — namespace does not exist in this workspace

---

## Agent Endpoints

### POST /api/v1/agents/upload

Upload an agent package. Accepts `.tar.gz` or `.zip` archives via multipart form.

**Request**
```http
POST /api/v1/agents/upload
Authorization: Bearer {jwt}
X-Workspace-ID: {workspace_id}
Content-Type: multipart/form-data

namespace_name=finance-ops
package=@kyc-verifier-1.0.0.tar.gz
```

**Response 201 Created** (new agent)
```json
{
  "agent_profile": {
    "id": "uuid",
    "namespace_id": "uuid",
    "fqn": "finance-ops:kyc-verifier",
    "display_name": "KYC Verifier",
    "purpose": "Verifies Know Your Customer documents for regulatory compliance.",
    "approach": "Extracts document data, cross-references against compliance rules, emits verdict.",
    "role_types": ["executor"],
    "custom_role_description": null,
    "visibility_agents": [],
    "visibility_tools": [],
    "tags": ["kyc", "compliance", "finance"],
    "status": "draft",
    "maturity_level": 0,
    "embedding_status": "pending",
    "workspace_id": "uuid",
    "created_at": "2026-04-11T10:00:00Z",
    "current_revision": {
      "id": "uuid",
      "agent_profile_id": "uuid",
      "version": "1.0.0",
      "sha256_digest": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "storage_key": "ws-abc/finance-ops/kyc-verifier/rev-def/package.tar.gz",
      "manifest_snapshot": { "local_name": "kyc-verifier", "version": "1.0.0", "purpose": "..." },
      "uploaded_by": "uuid",
      "created_at": "2026-04-11T10:00:00Z"
    }
  },
  "revision": { /* same as current_revision above */ },
  "created": true
}
```

**Response 200 OK** (new revision of existing agent — `"created": false`)

**Errors**:
- `422 Unprocessable Entity` — package validation failed
  ```json
  {
    "error_type": "path_traversal",
    "detail": "Package contains path traversal: ../../etc/passwd",
    "field": null
  }
  ```
  ```json
  {
    "error_type": "manifest_invalid",
    "detail": "Field 'purpose' is required",
    "field": "purpose"
  }
  ```
  ```json
  {
    "error_type": "size_limit",
    "detail": "Package size 55.2 MB exceeds maximum of 50 MB",
    "field": null
  }
  ```
- `404 Not Found` — namespace does not exist in this workspace
- `503 Service Unavailable` — object storage unavailable

---

### GET /api/v1/agents

List agents with filtering. Results filtered by requesting principal's visibility.

**Request**
```http
GET /api/v1/agents?status=published&maturity_min=1&fqn_pattern=finance-ops:*&limit=20&offset=0
Authorization: Bearer {jwt}
X-Workspace-ID: {workspace_id}
```

**Query Parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `status` | string | `published` | Lifecycle status filter |
| `maturity_min` | integer | `0` | Minimum maturity level (0-3) |
| `fqn_pattern` | string | — | Wildcard/regex FQN pattern (e.g., `finance-ops:*`) |
| `keyword` | string | — | Full-text search against name, purpose, tags |
| `limit` | integer | `20` | Max results (≤ 100) |
| `offset` | integer | `0` | Pagination offset |

**Response 200 OK**
```json
{
  "items": [
    {
      "id": "uuid",
      "fqn": "finance-ops:kyc-verifier",
      "display_name": "KYC Verifier",
      "purpose": "Verifies Know Your Customer documents for regulatory compliance.",
      "role_types": ["executor"],
      "maturity_level": 1,
      "status": "published",
      "tags": ["kyc", "compliance"],
      "workspace_id": "uuid",
      "created_at": "2026-04-11T10:00:00Z"
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

---

### GET /api/v1/agents/resolve/{fqn}

Resolve an exact FQN to an agent profile. Requires visibility authorization.

**Request**
```http
GET /api/v1/agents/resolve/finance-ops:kyc-verifier
Authorization: Bearer {jwt}
X-Workspace-ID: {workspace_id}
```

**Response 200 OK** — full `AgentProfileResponse` with `current_revision`

**Errors**:
- `404 Not Found` — no agent with this FQN in the workspace, or not visible to requester

**Performance**: ≤ 200ms (SC-003) — index lookup on `fqn` column.

---

### GET /api/v1/agents/{agent_id}

Retrieve a single agent profile by UUID.

**Request**
```http
GET /api/v1/agents/{agent_id}
Authorization: Bearer {jwt}
X-Workspace-ID: {workspace_id}
```

**Response 200 OK** — full `AgentProfileResponse` with `current_revision`

---

### PATCH /api/v1/agents/{agent_id}

Update mutable agent metadata. Does NOT create a new revision.

**Request**
```http
PATCH /api/v1/agents/{agent_id}
Authorization: Bearer {jwt}
X-Workspace-ID: {workspace_id}
Content-Type: application/json

{
  "display_name": "KYC Document Verifier",
  "tags": ["kyc", "compliance", "finance", "pep-screening"],
  "visibility_agents": ["finance-ops:*"],
  "visibility_tools": ["tools:document-extractor"],
  "approach": "1. Extract fields from uploaded document. 2. Query compliance rules. 3. Emit pass/fail verdict with evidence."
}
```

**Response 200 OK** — updated `AgentProfileResponse`

**Errors**:
- `422 Unprocessable Entity` — invalid visibility pattern (malformed regex)

---

### POST /api/v1/agents/{agent_id}/transition

Trigger a lifecycle state transition.

**Request**
```http
POST /api/v1/agents/{agent_id}/transition
Authorization: Bearer {jwt}
X-Workspace-ID: {workspace_id}
Content-Type: application/json

{
  "target_status": "published",
  "reason": "All integration tests pass, QA sign-off received"
}
```

**Response 200 OK** — updated `AgentProfileResponse`

**Errors**:
- `409 Conflict` — invalid transition from current status
  ```json
  {
    "detail": "Invalid transition: draft → deprecated. Valid transitions from draft: [validated]"
  }
  ```

---

### POST /api/v1/agents/{agent_id}/maturity

Update an agent's maturity classification.

**Request**
```http
POST /api/v1/agents/{agent_id}/maturity
Authorization: Bearer {jwt}
X-Workspace-ID: {workspace_id}
Content-Type: application/json

{
  "maturity_level": 2,
  "reason": "Evaluation suite results demonstrate ≥90% accuracy on benchmark dataset"
}
```

**Response 200 OK** — updated `AgentProfileResponse`

---

### GET /api/v1/agents/{agent_id}/revisions

List all revisions for an agent, in chronological order.

**Request**
```http
GET /api/v1/agents/{agent_id}/revisions
Authorization: Bearer {jwt}
X-Workspace-ID: {workspace_id}
```

**Response 200 OK**
```json
{
  "items": [
    {
      "id": "uuid",
      "agent_profile_id": "uuid",
      "version": "1.0.0",
      "sha256_digest": "e3b0c44...",
      "storage_key": "ws-abc/finance-ops/kyc-verifier/rev-def/package.tar.gz",
      "manifest_snapshot": {},
      "uploaded_by": "uuid",
      "created_at": "2026-04-11T10:00:00Z"
    },
    {
      "id": "uuid",
      "version": "1.1.0",
      "sha256_digest": "a1b2c3...",
      "created_at": "2026-04-12T09:00:00Z"
    }
  ],
  "total": 2
}
```

---

### GET /api/v1/agents/{agent_id}/lifecycle-audit

Retrieve full lifecycle audit trail for an agent.

**Request**
```http
GET /api/v1/agents/{agent_id}/lifecycle-audit
Authorization: Bearer {jwt}
X-Workspace-ID: {workspace_id}
```

**Response 200 OK**
```json
{
  "items": [
    {
      "id": "uuid",
      "agent_profile_id": "uuid",
      "previous_status": "draft",
      "new_status": "validated",
      "actor_id": "uuid",
      "reason": "Automated structure check passed",
      "created_at": "2026-04-11T10:05:00Z"
    }
  ],
  "total": 1
}
```

---

## Internal Service Interface

### get_agent_profile(fqn: str) → AgentProfileResponse | None

Used by execution context, context engineering, and policy bounded contexts.

```python
# In-process call via service interface (not HTTP)
# Returns None if agent not found or archived
agent = await registry_service.get_agent_by_fqn(fqn=fqn)
if agent is None or agent.status == LifecycleStatus.ARCHIVED:
    raise AgentNotFoundError(fqn)
```

### resolve_effective_visibility(agent_id: UUID, workspace_id: UUID) → EffectiveVisibility

Used by discovery endpoints to apply visibility filtering.

```python
@dataclass
class EffectiveVisibility:
    agent_patterns: list[str]   # union of per-agent + workspace grants
    tool_patterns: list[str]
```
