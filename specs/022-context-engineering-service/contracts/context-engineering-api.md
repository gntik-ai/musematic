# API Contracts: Context Engineering Service

**Feature**: 022-context-engineering-service  
**Date**: 2026-04-11  
**Base URL**: `/api/v1/context-engineering`  
**Auth**: Bearer JWT (all endpoints require authentication)

---

## Profile Management Endpoints

### POST /api/v1/context-engineering/profiles

Create a context engineering profile.

**Request**
```http
POST /api/v1/context-engineering/profiles
Authorization: Bearer {jwt}
X-Workspace-ID: {workspace_id}
Content-Type: application/json

{
  "name": "default-executor",
  "description": "Default profile for executor-role agents",
  "source_config": [
    {"source_type": "system_instructions", "priority": 100, "enabled": true, "max_elements": 1},
    {"source_type": "conversation_history", "priority": 80, "enabled": true, "max_elements": 20},
    {"source_type": "long_term_memory", "priority": 70, "enabled": true, "max_elements": 5},
    {"source_type": "tool_outputs", "priority": 90, "enabled": true, "max_elements": 10}
  ],
  "budget_config": {
    "max_tokens_step": 4096,
    "max_sources": 4
  },
  "compaction_strategies": ["relevance_truncation", "priority_eviction"],
  "is_default": false
}
```

**Response 201 Created**
```json
{
  "id": "uuid",
  "name": "default-executor",
  "description": "Default profile for executor-role agents",
  "is_default": false,
  "source_config": [...],
  "budget_config": {"max_tokens_step": 4096, "max_sources": 4},
  "compaction_strategies": ["relevance_truncation", "priority_eviction"],
  "workspace_id": "uuid",
  "created_at": "2026-04-11T10:00:00Z"
}
```

**Errors**: `409 Conflict` — profile name already exists in workspace.

---

### GET /api/v1/context-engineering/profiles

List all profiles in a workspace.

**Response 200 OK**
```json
{
  "items": [ { /* ProfileResponse */ } ],
  "total": 3
}
```

---

### GET /api/v1/context-engineering/profiles/{profile_id}

Get a single profile.

**Response 200 OK** — `ProfileResponse`

---

### PUT /api/v1/context-engineering/profiles/{profile_id}

Replace a profile's configuration. Takes effect on the next assembly.

**Request**: Same body as POST  
**Response 200 OK** — updated `ProfileResponse`

---

### DELETE /api/v1/context-engineering/profiles/{profile_id}

Delete a profile. Fails if the profile is currently assigned to agents or in use by an active A/B test.

**Response 204 No Content**  
**Errors**: `409 Conflict` — profile has active assignments.

---

### POST /api/v1/context-engineering/profiles/{profile_id}/assign

Assign a profile to an agent, role type, or workspace.

**Request**
```http
POST /api/v1/context-engineering/profiles/{profile_id}/assign
Content-Type: application/json

{
  "assignment_level": "agent",
  "agent_fqn": "finance-ops:kyc-verifier"
}
```

```json
// Role-type assignment:
{"assignment_level": "role_type", "role_type": "executor"}

// Workspace default:
{"assignment_level": "workspace"}
```

**Response 201 Created**
```json
{
  "id": "uuid",
  "profile_id": "uuid",
  "assignment_level": "agent",
  "agent_fqn": "finance-ops:kyc-verifier",
  "workspace_id": "uuid",
  "created_at": "2026-04-11T10:00:00Z"
}
```

---

## A/B Test Endpoints

### POST /api/v1/context-engineering/ab-tests

Create a new A/B test.

**Request**
```http
POST /api/v1/context-engineering/ab-tests
Authorization: Bearer {jwt}
X-Workspace-ID: {workspace_id}
Content-Type: application/json

{
  "name": "extra-memory-sources-test",
  "control_profile_id": "uuid-control",
  "variant_profile_id": "uuid-variant",
  "target_agent_fqn": "finance-ops:kyc-verifier"
}
```

**Response 201 Created** — `AbTestResponse` with `status: "active"`.

---

### GET /api/v1/context-engineering/ab-tests

List A/B tests in a workspace.

**Query Parameters**: `status` (active/paused/completed), `limit`, `offset`  
**Response 200 OK** — `{items: [AbTestResponse], total: N}`

---

### GET /api/v1/context-engineering/ab-tests/{test_id}

Get a single A/B test with current metrics.

**Response 200 OK** — `AbTestResponse` with current aggregated metrics.

---

### POST /api/v1/context-engineering/ab-tests/{test_id}/end

End an active A/B test.

**Response 200 OK** — `AbTestResponse` with `status: "completed"` and final metrics.

---

## Assembly Records Endpoints

### GET /api/v1/context-engineering/assembly-records

List assembly records for debugging and audit.

**Request**
```http
GET /api/v1/context-engineering/assembly-records?agent_fqn=finance-ops:kyc-verifier&limit=20&offset=0
Authorization: Bearer {jwt}
X-Workspace-ID: {workspace_id}
```

**Response 200 OK**
```json
{
  "items": [
    {
      "id": "uuid",
      "execution_id": "uuid",
      "step_id": "uuid",
      "agent_fqn": "finance-ops:kyc-verifier",
      "quality_score_pre": 0.82,
      "quality_score_post": 0.79,
      "token_count_pre": 6200,
      "token_count_post": 4050,
      "compaction_applied": true,
      "sources_queried": ["system_instructions", "conversation_history", "long_term_memory"],
      "sources_available": ["system_instructions", "conversation_history"],
      "privacy_exclusions": [],
      "flags": ["partial_sources"],
      "ab_test_group": null,
      "created_at": "2026-04-11T10:00:00Z"
    }
  ],
  "total": 47,
  "limit": 20,
  "offset": 0
}
```

---

### GET /api/v1/context-engineering/assembly-records/{record_id}

Get a single assembly record with full provenance chain.

**Response 200 OK** — full `AssemblyRecordResponse` including `provenance_chain` and `compaction_actions`.

---

## Drift Alert Endpoints

### GET /api/v1/context-engineering/drift-alerts

List drift alerts for a workspace.

**Request**
```http
GET /api/v1/context-engineering/drift-alerts?resolved=false&limit=20
Authorization: Bearer {jwt}
X-Workspace-ID: {workspace_id}
```

**Response 200 OK**
```json
{
  "items": [
    {
      "id": "uuid",
      "agent_fqn": "finance-ops:kyc-verifier",
      "workspace_id": "uuid",
      "historical_mean": 0.81,
      "historical_stddev": 0.04,
      "recent_mean": 0.62,
      "degradation_delta": 0.19,
      "suggested_actions": [
        "Check if long-term memory source has fresh embeddings",
        "Review recent changes to agent's context engineering profile",
        "Inspect assembly records for partial_sources flags"
      ],
      "resolved_at": null,
      "created_at": "2026-04-11T08:00:00Z"
    }
  ],
  "total": 1
}
```

---

### POST /api/v1/context-engineering/drift-alerts/{alert_id}/resolve

Mark a drift alert as resolved.

**Response 200 OK** — updated `DriftAlertResponse` with `resolved_at` set.

---

## Internal Service Interface

### assemble_context(execution_id, step_id, agent_fqn, workspace_id, goal_id, profile, budget) → ContextBundle

The primary internal interface. Called in-process by the execution bounded context.

```python
# In-process call via service interface injection
bundle = await context_engineering_service.assemble_context(
    execution_id=execution_id,
    step_id=step_id,
    agent_fqn="finance-ops:kyc-verifier",
    workspace_id=workspace_id,
    goal_id=goal_id,               # None if not goal-oriented
    profile=None,                   # None = auto-resolve from assignments
    budget=BudgetEnvelope(max_tokens_step=4096),
)
# bundle.elements: ordered, filtered, compacted context elements
# bundle.quality_score: 0.0-1.0 aggregate
# bundle.token_count: total tokens after compaction
# bundle.flags: ["partial_sources", ...] if applicable
```

**Latency target**: ≤ 500ms for bundles with up to 5 sources; ≤ 2s for all 8+ sources (SC-001).
