# API Contracts: AI-Assisted Agent Composition

All endpoints require `Authorization: Bearer <access_token>` and are workspace-scoped.  
Base path: `/api/v1/compositions`  
Responses use JSON. Timestamps are ISO 8601. IDs are UUIDs.

---

## Agent Blueprint Endpoints

### Generate Agent Blueprint
```
POST /api/v1/compositions/agent-blueprint
body: AgentBlueprintGenerateRequest
→ AgentBlueprintResponse  (201 Created)
Errors: 400 empty description, 503 LLM service unavailable
```

**AgentBlueprintGenerateRequest**:
```json
{
  "workspace_id": "uuid",
  "description": "string (required, 1–10000 chars)"
}
```

**AgentBlueprintResponse**:
```json
{
  "request_id": "uuid",
  "blueprint_id": "uuid",
  "version": 1,
  "workspace_id": "uuid",
  "description": "...",
  "model_config": {
    "model_id": "string",
    "temperature": 0.7,
    "max_tokens": 4096,
    "reasoning_mode": "standard | extended | budget"
  },
  "tool_selections": [
    {"tool_name": "string", "tool_id": "uuid", "relevance_justification": "string", "status": "available | not_available | alternative_suggested"}
  ],
  "connector_suggestions": [
    {"connector_type": "string", "connector_name": "string", "purpose": "string", "status": "configured | not_configured | suggested"}
  ],
  "policy_recommendations": [
    {"policy_id": "uuid", "policy_name": "string", "attachment_reason": "string"}
  ],
  "context_profile": {
    "assembly_strategy": "standard | compressed | hierarchical",
    "memory_scope": "session | workspace | long_term",
    "knowledge_sources": ["string"]
  },
  "maturity_estimate": "experimental | developing | production_ready",
  "maturity_reasoning": "string",
  "confidence_score": 0.85,
  "low_confidence": false,
  "follow_up_questions": [],
  "llm_reasoning_summary": "string",
  "alternatives_considered": [
    {"field": "model_config.model_id", "alternatives": ["..."], "reason_rejected": "string"}
  ],
  "generation_time_ms": 8200,
  "created_at": "ISO8601"
}
```

---

### Get Agent Blueprint
```
GET /api/v1/compositions/agent-blueprints/{blueprint_id}
→ AgentBlueprintResponse
Errors: 404 not found
```

---

### Override Agent Blueprint
```
PATCH /api/v1/compositions/agent-blueprints/{blueprint_id}
body: AgentBlueprintOverrideRequest
→ AgentBlueprintResponse  (new version number)
```

**AgentBlueprintOverrideRequest**:
```json
{
  "overrides": [
    {
      "field_path": "model_config.model_id",
      "new_value": "claude-3.5-sonnet",
      "reason": "string (optional)"
    }
  ]
}
```

Override creates a new version (old version preserved for audit). Response contains updated blueprint at `version: N+1`.

---

### Validate Agent Blueprint
```
POST /api/v1/compositions/agent-blueprints/{blueprint_id}/validate
→ CompositionValidationResponse
```

**CompositionValidationResponse**:
```json
{
  "validation_id": "uuid",
  "blueprint_id": "uuid",
  "overall_valid": true,
  "tools_check": {
    "passed": true,
    "details": [{"tool_name": "string", "status": "available | not_available", "remediation": "string | null"}]
  },
  "model_check": {
    "passed": true,
    "details": {"model_id": "string", "status": "available | not_available | permission_denied", "remediation": null}
  },
  "connectors_check": {
    "passed": true,
    "details": [{"connector_name": "string", "status": "configured | not_configured | error", "remediation": "string | null"}]
  },
  "policy_check": {
    "passed": true,
    "details": [{"policy_id": "uuid", "status": "compatible | conflict", "conflict_description": null}]
  },
  "cycle_check": null,
  "validated_at": "ISO8601"
}
```

---

## Fleet Blueprint Endpoints

### Generate Fleet Blueprint
```
POST /api/v1/compositions/fleet-blueprint
body: FleetBlueprintGenerateRequest
→ FleetBlueprintResponse  (201 Created)
Errors: 400 empty description, 503 LLM service unavailable
```

**FleetBlueprintGenerateRequest**:
```json
{
  "workspace_id": "uuid",
  "description": "string (required, 1–10000 chars)"
}
```

**FleetBlueprintResponse**:
```json
{
  "request_id": "uuid",
  "blueprint_id": "uuid",
  "version": 1,
  "workspace_id": "uuid",
  "description": "...",
  "topology_type": "sequential | hierarchical | peer | hybrid",
  "member_count": 3,
  "member_roles": [
    {
      "role_name": "string",
      "purpose": "string",
      "agent_blueprint_inline": { /* AgentBlueprintResponse fields */ }
    }
  ],
  "orchestration_rules": [
    {"rule_type": "routing | splitting | aggregating", "trigger": "string", "action": "string", "target_role": "string"}
  ],
  "delegation_rules": [
    {"from_role": "string", "to_role": "string", "trigger_condition": "string"}
  ],
  "escalation_rules": [
    {"from_role": "string", "to_role": "string", "trigger_condition": "string", "urgency": "low | medium | high"}
  ],
  "single_agent_suggestion": false,
  "confidence_score": 0.82,
  "low_confidence": false,
  "follow_up_questions": [],
  "llm_reasoning_summary": "string",
  "alternatives_considered": [],
  "generation_time_ms": 12400,
  "created_at": "ISO8601"
}
```

---

### Get Fleet Blueprint
```
GET /api/v1/compositions/fleet-blueprints/{blueprint_id}
→ FleetBlueprintResponse
```

---

### Override Fleet Blueprint
```
PATCH /api/v1/compositions/fleet-blueprints/{blueprint_id}
body: FleetBlueprintOverrideRequest
→ FleetBlueprintResponse
```

---

### Validate Fleet Blueprint
```
POST /api/v1/compositions/fleet-blueprints/{blueprint_id}/validate
→ CompositionValidationResponse  (includes cycle_check field)
```

---

## Audit Trail Endpoints

### List Audit Entries for a Request
```
GET /api/v1/compositions/requests/{request_id}/audit
  ?workspace_id={id}&event_type={type}&limit={n}&cursor={cursor}
→ { items: CompositionAuditEntryResponse[], next_cursor: string | null }
```

**CompositionAuditEntryResponse**:
```json
{
  "entry_id": "uuid",
  "request_id": "uuid",
  "event_type": "blueprint_generated | blueprint_validated | blueprint_overridden | blueprint_finalized | generation_failed",
  "actor_id": "uuid | null",
  "payload": {},
  "created_at": "ISO8601"
}
```

---

### Get Composition Request
```
GET /api/v1/compositions/requests/{request_id}
  ?workspace_id={id}
→ CompositionRequestResponse
```

### List Composition Requests
```
GET /api/v1/compositions/requests
  ?workspace_id={id}&request_type=agent|fleet&status=pending|completed|failed&limit={n}&cursor={cursor}
→ { items: CompositionRequestResponse[], next_cursor: string | null }
```

---

## Error Responses

```json
{ "code": "...", "message": "...", "details": {} }
```

| HTTP | Code | When |
|------|------|------|
| 400 | `VALIDATION_ERROR` | Empty description, field validation failure |
| 400 | `DESCRIPTION_TOO_LONG` | Description > 10000 characters |
| 403 | `AUTHORIZATION_ERROR` | Insufficient workspace role |
| 404 | `NOT_FOUND` | Blueprint or request not found |
| 409 | `BLUEPRINT_VERSION_CONFLICT` | Override conflicts with concurrent modification |
| 503 | `LLM_SERVICE_UNAVAILABLE` | LLM API unreachable or timed out |
| 503 | `PARTIAL_VALIDATION` | Validation service interface unreachable (returns partial results) |
