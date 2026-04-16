# API Contracts: Simulation and Digital Twins

All endpoints require `Authorization: Bearer <access_token>` and are workspace-scoped.  
Base path: `/api/v1/simulations`  
Responses use JSON. Timestamps are ISO 8601. IDs are UUIDs.

---

## Simulation Run Endpoints

### Create Simulation Run
```
POST /api/v1/simulations
body: SimulationRunCreateRequest
→ SimulationRunResponse  (201 Created)
```

**SimulationRunCreateRequest**:
```json
{
  "workspace_id": "uuid",
  "name": "string (required)",
  "description": "string | null",
  "digital_twin_ids": ["uuid", "..."],
  "scenario_config": {
    "inputs": {},
    "duration_seconds": 300,
    "success_criteria": {}
  },
  "isolation_policy_id": "uuid | null"
}
```

**SimulationRunResponse**:
```json
{
  "run_id": "uuid",
  "workspace_id": "uuid",
  "name": "string",
  "status": "provisioning",
  "digital_twin_ids": ["uuid"],
  "scenario_config": {},
  "isolation_policy_id": "uuid | null",
  "controller_run_id": "string | null",
  "started_at": "ISO8601 | null",
  "completed_at": "ISO8601 | null",
  "results": null,
  "initiated_by": "uuid",
  "created_at": "ISO8601"
}
```

### Get Simulation Run
```
GET /api/v1/simulations/{run_id}
→ SimulationRunResponse
```

### List Simulation Runs
```
GET /api/v1/simulations
  ?workspace_id={id}&status=provisioning|running|completed|cancelled|failed|timeout&limit={n}&cursor={cursor}
→ { items: SimulationRunResponse[], next_cursor: string | null }
```

### Cancel Simulation Run
```
POST /api/v1/simulations/{run_id}/cancel
→ SimulationRunResponse  (200)
Errors: 409 if status is not 'provisioning' or 'running'
```

---

## Digital Twin Endpoints

### Create Digital Twin (Snapshot from Agent)
```
POST /api/v1/simulations/twins
body: { workspace_id: string, agent_fqn: string, revision_id: string | null, description: string | null }
→ DigitalTwinResponse  (201 Created)
Errors: 404 if agent_fqn not found in registry
```

**DigitalTwinResponse**:
```json
{
  "twin_id": "uuid",
  "workspace_id": "uuid",
  "source_agent_fqn": "string",
  "source_revision_id": "uuid | null",
  "version": 1,
  "parent_twin_id": "uuid | null",
  "config_snapshot": {
    "model": {},
    "tools": [],
    "policies": [],
    "context_profile": {},
    "connectors": []
  },
  "behavioral_history_summary": {
    "period_days": 30,
    "avg_quality_score": 0.87,
    "avg_response_time_ms": 1250,
    "avg_error_rate": 0.02,
    "quality_trend": "improving",
    "response_trend": "stable"
  },
  "modifications": [],
  "is_active": true,
  "created_at": "ISO8601"
}
```

### Get Digital Twin
```
GET /api/v1/simulations/twins/{twin_id}
→ DigitalTwinResponse
```

### List Digital Twins
```
GET /api/v1/simulations/twins
  ?workspace_id={id}&agent_fqn={fqn}&is_active=true|false&limit={n}&cursor={cursor}
→ { items: DigitalTwinResponse[], next_cursor: string | null }
```

### Modify Digital Twin (Creates New Version)
```
PATCH /api/v1/simulations/twins/{twin_id}
body: { modifications: [{field: string, value: any, description: string}] }
→ DigitalTwinResponse  (201 Created — new version)
```

### List Twin Version History
```
GET /api/v1/simulations/twins/{twin_id}/versions
→ { items: DigitalTwinResponse[], total_versions: int }
```

---

## Isolation Policy Endpoints

### Create Isolation Policy
```
POST /api/v1/simulations/isolation-policies
body: SimulationIsolationPolicyCreateRequest
→ SimulationIsolationPolicyResponse  (201 Created)
```

**SimulationIsolationPolicyCreateRequest**:
```json
{
  "workspace_id": "uuid",
  "name": "string",
  "description": "string | null",
  "blocked_actions": [{"action_type": "connector.send_message", "severity": "critical"}],
  "stubbed_actions": [{"action_type": "connector.read_data", "stub_response_template": {}}],
  "permitted_read_sources": [{"source_type": "dataset", "source_id": "uuid"}],
  "is_default": false,
  "halt_on_critical_breach": true
}
```

### Get Isolation Policy
```
GET /api/v1/simulations/isolation-policies/{policy_id}
→ SimulationIsolationPolicyResponse
```

### List Isolation Policies
```
GET /api/v1/simulations/isolation-policies
  ?workspace_id={id}
→ { items: SimulationIsolationPolicyResponse[] }
```

---

## Behavioral Prediction Endpoints

### Create Behavioral Prediction
```
POST /api/v1/simulations/twins/{twin_id}/predict
body: { workspace_id: string, condition_modifiers: {load_factor: float, config_changes: {}} }
→ BehavioralPredictionResponse  (202 Accepted — runs asynchronously)
```

**BehavioralPredictionResponse**:
```json
{
  "prediction_id": "uuid",
  "digital_twin_id": "uuid",
  "status": "pending",
  "condition_modifiers": {},
  "predicted_metrics": null,
  "confidence_level": null,
  "history_days_used": 0,
  "accuracy_report": null,
  "created_at": "ISO8601"
}
```

### Get Behavioral Prediction
```
GET /api/v1/simulations/predictions/{prediction_id}
→ BehavioralPredictionResponse
```

---

## Comparison Endpoints

### Create Comparison Report
```
POST /api/v1/simulations/{run_id}/compare
body: {
  "workspace_id": "string",
  "comparison_type": "simulation_vs_simulation | simulation_vs_production | prediction_vs_actual",
  "secondary_run_id": "uuid | null",
  "production_baseline_period": {"start_date": "ISO8601", "end_date": "ISO8601"} | null,
  "prediction_id": "uuid | null"
}
→ SimulationComparisonReportResponse  (202 Accepted)
Errors: 422 if incompatible comparison configuration
```

**SimulationComparisonReportResponse**:
```json
{
  "report_id": "uuid",
  "comparison_type": "simulation_vs_simulation",
  "primary_run_id": "uuid",
  "secondary_run_id": "uuid | null",
  "status": "pending",
  "compatible": true,
  "incompatibility_reasons": [],
  "metric_differences": [],
  "overall_verdict": null,
  "created_at": "ISO8601"
}
```

### Get Comparison Report
```
GET /api/v1/simulations/comparisons/{report_id}
→ SimulationComparisonReportResponse
```

---

## Error Responses

```json
{ "code": "...", "message": "...", "details": {} }
```

| HTTP | Code | When |
|------|------|------|
| 400 | `VALIDATION_ERROR` | Invalid request body |
| 403 | `AUTHORIZATION_ERROR` | Insufficient workspace role |
| 404 | `NOT_FOUND` | Run, twin, prediction, or report not found |
| 409 | `SIMULATION_NOT_CANCELLABLE` | Cancel requested on a terminal-state simulation |
| 409 | `SIMULATION_INFRASTRUCTURE_UNAVAILABLE` | SimulationControlService unreachable |
| 422 | `INCOMPATIBLE_COMPARISON` | Comparison between incompatible simulation configurations |
