# REST API Contracts: Workspace Goal Management and Agent Response Decision

**Phase 1 output for**: [plan.md](plan.md)
**Date**: 2026-04-18

All endpoints are under `/api/v1`. Authentication: Bearer JWT (existing middleware).
Workspace-scoped RBAC: member (read), admin (write lifecycle + configs).

---

## New Endpoints

### 1. Transition Goal State

```
POST /workspaces/{workspace_id}/goals/{goal_id}/transition
```

**Authorization**: workspace admin or owner  
**Body**:
```json
{
  "target_state": "complete",
  "reason": "Objective achieved — deploying v2.3"
}
```

**Responses**:

| Status | Meaning |
|--------|---------|
| 200 OK | Transition succeeded |
| 400 Bad Request | `target_state` not recognized |
| 404 Not Found | Goal not found in this workspace |
| 409 Conflict | Goal already in COMPLETE state (terminal — no re-transition) |
| 409 Conflict | Target state is READY or WORKING (only COMPLETE allowed via this endpoint) |
| 403 Forbidden | Caller is not workspace admin/owner |

**200 Response body**:
```json
{
  "goal_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "previous_state": "working",
  "new_state": "complete",
  "automatic": false,
  "transitioned_at": "2026-04-18T14:30:00Z"
}
```

---

### 2. Upsert Agent Decision Config

```
PUT /workspaces/{workspace_id}/agent-decision-configs/{agent_fqn}
```

**Authorization**: workspace admin  
**Note**: `agent_fqn` is URL-encoded. Example: `finance-ops%3Akyc-verifier` for `finance-ops:kyc-verifier`  
**Body**:
```json
{
  "response_decision_strategy": "keyword",
  "response_decision_config": {
    "keywords": ["deploy", "release", "rollback"],
    "mode": "any_of"
  }
}
```

**Responses**:

| Status | Meaning |
|--------|---------|
| 200 OK | Config updated |
| 201 Created | Config created for first time |
| 422 Unprocessable Entity | Unknown strategy name or malformed config schema |
| 404 Not Found | Agent FQN not subscribed to this workspace |
| 403 Forbidden | Caller is not workspace admin |

**200/201 Response body**:
```json
{
  "id": "...",
  "workspace_id": "...",
  "agent_fqn": "finance-ops:kyc-verifier",
  "response_decision_strategy": "keyword",
  "response_decision_config": {
    "keywords": ["deploy", "release", "rollback"],
    "mode": "any_of"
  },
  "subscribed_at": "2026-04-10T09:00:00Z",
  "created_at": "2026-04-18T14:00:00Z",
  "updated_at": "2026-04-18T14:30:00Z"
}
```

---

### 3. List Agent Decision Configs

```
GET /workspaces/{workspace_id}/agent-decision-configs
```

**Authorization**: workspace admin  
**Query params**: none (workspace-scoped, small cardinality — no pagination needed)

**200 Response body**:
```json
{
  "items": [
    {
      "id": "...",
      "agent_fqn": "finance-ops:kyc-verifier",
      "response_decision_strategy": "keyword",
      "response_decision_config": { "keywords": ["deploy"] },
      "subscribed_at": "2026-04-10T09:00:00Z",
      "created_at": "...",
      "updated_at": "..."
    }
  ],
  "total": 1
}
```

---

### 4. Get Decision Rationale for a Message

```
GET /workspaces/{workspace_id}/goals/{goal_id}/messages/{message_id}/rationale
```

**Authorization**: workspace admin or owner  
**Query params**: none  

**200 Response body**:
```json
{
  "items": [
    {
      "id": "...",
      "goal_id": "...",
      "message_id": "...",
      "agent_fqn": "finance-ops:kyc-verifier",
      "strategy_name": "keyword",
      "decision": "respond",
      "score": null,
      "matched_terms": ["deploy"],
      "rationale": "Keyword 'deploy' matched in mode any_of",
      "error": null,
      "created_at": "2026-04-18T14:30:01Z"
    },
    {
      "id": "...",
      "agent_fqn": "hr-ops:onboarding-bot",
      "strategy_name": "llm_relevance",
      "decision": "skip",
      "score": 0.34,
      "matched_terms": [],
      "rationale": "Relevance score 0.34 below threshold 0.70",
      "error": null,
      "created_at": "2026-04-18T14:30:02Z"
    }
  ],
  "total": 2
}
```

**404**: Message not found or not in the given goal.

---

### 5. List Decision Rationale for a Goal

```
GET /workspaces/{workspace_id}/goals/{goal_id}/rationale
```

**Authorization**: workspace admin  
**Query params**: `page` (int, default 1), `page_size` (int, default 50, max 200), `agent_fqn` (str, optional filter), `decision` (respond|skip, optional filter)

**200 Response body**:
```json
{
  "items": [ ... ],
  "total": 120,
  "page": 1,
  "page_size": 50,
  "has_next": true,
  "has_prev": false
}
```

---

## Modified Existing Endpoints

### `POST /workspaces/{workspace_id}/goals/{goal_id}/messages`

**No change to request/response shape.** New behavior:
- Returns 409 Conflict (instead of prior 422) when `goal.state == COMPLETE` with body `{"detail": "Goal is complete and cannot accept new messages"}`.
- The existing 422 check for `goal.status in (completed, cancelled)` is preserved alongside the new 409 check.

---

## Unchanged Existing Endpoints

All other `GET /workspaces/{workspace_id}/goals/...` and `GET /workspaces/{workspace_id}/goals/{goal_id}` endpoints are unchanged in shape. The `state` field is additively returned in `WorkspaceGoal` response schemas.

---

## Error Envelope

All errors follow the existing `PlatformError` shape:

```json
{
  "code": "goal_state_conflict",
  "message": "Goal is in terminal state COMPLETE and cannot be transitioned",
  "details": {
    "goal_id": "...",
    "current_state": "complete"
  }
}
```
