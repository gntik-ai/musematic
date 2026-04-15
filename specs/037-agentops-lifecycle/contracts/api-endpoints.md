# API Contracts: AgentOps Lifecycle Management

All endpoints require `Authorization: Bearer <access_token>` and are workspace-scoped.  
Base path: `/api/v1/agentops`  
Responses use JSON. Timestamps are ISO 8601 strings. IDs are UUIDs.

---

## Health Score Endpoints

### Get Agent Health Score
```
GET /api/v1/agentops/{agent_fqn}/health
  ?workspace_id={id}
→ AgentHealthScoreResponse
```

### Get Health Score History
```
GET /api/v1/agentops/{agent_fqn}/health/history
  ?workspace_id={id}&start_time={ISO8601}&end_time={ISO8601}&limit={n}
→ { items: AgentHealthScoreResponse[], next_cursor: string | null }
```

### Get Health Config
```
GET /api/v1/agentops/health-config
  ?workspace_id={id}
→ AgentHealthConfigResponse
```

### Update Health Config
```
PUT /api/v1/agentops/health-config
  ?workspace_id={id}
body: AgentHealthConfigUpdateRequest  (weights must sum to 100.0)
→ AgentHealthConfigResponse
```

---

## Regression Detection Endpoints

### List Regression Alerts
```
GET /api/v1/agentops/{agent_fqn}/regression-alerts
  ?workspace_id={id}&status=active|resolved|dismissed
→ { items: RegressionAlertResponse[], next_cursor: string | null }
```

### Get Regression Alert
```
GET /api/v1/agentops/regression-alerts/{alert_id}
→ RegressionAlertResponse
```

### Resolve/Dismiss Regression Alert
```
POST /api/v1/agentops/regression-alerts/{alert_id}/resolve
body: { resolution: "resolved" | "dismissed", reason: string }
→ RegressionAlertResponse
```

---

## CI/CD Gate Endpoints

### Run Gate Check
```
POST /api/v1/agentops/{agent_fqn}/gate-check
body: { revision_id: string, workspace_id: string }
→ CiCdGateResultResponse  (completes synchronously, all 5 gates run in parallel)
```

### Get Gate Check History
```
GET /api/v1/agentops/{agent_fqn}/gate-checks
  ?workspace_id={id}&revision_id={id}&limit={n}
→ { items: CiCdGateResultResponse[], next_cursor: string | null }
```

---

## Canary Deployment Endpoints

### Start Canary Deployment
```
POST /api/v1/agentops/{agent_fqn}/canary
body: CanaryDeploymentCreateRequest
→ CanaryDeploymentResponse  (201 Created)
Errors: 409 Conflict if a canary is already active for this agent
```

### Get Active Canary
```
GET /api/v1/agentops/{agent_fqn}/canary/active
  ?workspace_id={id}
→ CanaryDeploymentResponse | null
```

### Get Canary by ID
```
GET /api/v1/agentops/canaries/{canary_id}
→ CanaryDeploymentResponse
```

### Manually Promote Canary
```
POST /api/v1/agentops/canaries/{canary_id}/promote
body: { reason: string }
→ CanaryDeploymentResponse
Errors: 409 if not in 'active' status
```

### Manually Roll Back Canary
```
POST /api/v1/agentops/canaries/{canary_id}/rollback
body: { reason: string }
→ CanaryDeploymentResponse
Errors: 409 if not in 'active' status
```

### List Canary History
```
GET /api/v1/agentops/{agent_fqn}/canaries
  ?workspace_id={id}&limit={n}
→ { items: CanaryDeploymentResponse[], next_cursor: string | null }
```

---

## Retirement Workflow Endpoints

### Initiate Retirement (operator-triggered)
```
POST /api/v1/agentops/{agent_fqn}/retire
body: { workspace_id, reason: string }
→ RetirementWorkflowResponse  (201 Created)
```

### Get Retirement Workflow
```
GET /api/v1/agentops/retirements/{workflow_id}
→ RetirementWorkflowResponse
```

### Halt Retirement
```
POST /api/v1/agentops/retirements/{workflow_id}/halt
body: { reason: string }
→ RetirementWorkflowResponse
```

### Confirm High-Impact Retirement
```
POST /api/v1/agentops/retirements/{workflow_id}/confirm
body: { confirmed: true, reason: string }
→ RetirementWorkflowResponse
```

---

## Governance Endpoints

### List Governance Events (audit trail)
```
GET /api/v1/agentops/{agent_fqn}/governance-events
  ?workspace_id={id}&event_type={type}&since={ISO8601}&limit={n}
→ { items: GovernanceEventResponse[], next_cursor: string | null }
```

### Get Governance Summary
```
GET /api/v1/agentops/{agent_fqn}/governance
  ?workspace_id={id}
→ GovernanceSummaryResponse  (current cert status, pending triggers, upcoming expirations)
```

---

## Adaptation Pipeline Endpoints

### Trigger Adaptation Analysis
```
POST /api/v1/agentops/{agent_fqn}/adapt
body: { workspace_id }
→ AdaptationProposalResponse  (201 Created; status: 'proposed' or 'no_opportunities')
```

### Review Adaptation Proposal
```
POST /api/v1/agentops/adaptations/{proposal_id}/review
body: { decision: "approved" | "rejected", reason: string }
→ AdaptationProposalResponse
```

### Get Adaptation History
```
GET /api/v1/agentops/{agent_fqn}/adaptation-history
  ?workspace_id={id}&limit={n}
→ { items: AdaptationProposalResponse[], next_cursor: string | null }
```

---

## Internal Service Interface

Consumed by: workflow execution engine, runtime controller (gate check before deploy).

```python
class AgentOpsServiceInterface(Protocol):
    async def get_active_regression_alerts(
        self, agent_fqn: str, revision_id: UUID
    ) -> list[RegressionAlertSummary]: ...

    async def get_current_health_score(
        self, agent_fqn: str, workspace_id: UUID
    ) -> AgentHealthScoreSummary | None: ...

    async def run_gate_check(
        self, agent_fqn: str, revision_id: UUID, workspace_id: UUID
    ) -> CiCdGateSummary: ...

    async def is_agent_retiring(
        self, agent_fqn: str, workspace_id: UUID
    ) -> bool: ...
```

---

## Error Responses

```json
{ "code": "...", "message": "...", "details": {} }
```

| HTTP | Code | When |
|------|------|------|
| 400 | `VALIDATION_ERROR` | Invalid request body or weight sum ≠ 100 |
| 403 | `AUTHORIZATION_ERROR` | Insufficient workspace role |
| 404 | `NOT_FOUND` | Agent, alert, canary, or retirement not found |
| 409 | `CONFLICT` | Canary already active; retirement already in progress |
| 412 | `PRECONDITION_FAILED` | Gate check cannot run (e.g., baseline not ready) |
