# REST API Contracts: Agent Adaptation Pipeline and Context Engineering Levels

**Feature**: 068-adaptation-context-levels  
**Date**: 2026-04-19  
**Base path**: `/api/v1/agentops/` and `/api/v1/context-engineering/`  
**Auth**: All endpoints require Bearer JWT. Authorization reuses existing agentops and context_engineering RBAC.

---

## Existing Endpoints (Reference — No Changes to Behavior)

The following endpoints already exist and keep working:

```
POST /api/v1/agentops/{agent_fqn}/adapt
     Previous behavior: propose + auto-run ATE on approval (legacy auto-apply flow)
     New behavior: propose only; approval + apply are now separate steps
     Backward compat: existing historical proposals in `testing/passed/promoted` states continue to load
POST /api/v1/agentops/adaptations/{proposal_id}/review
     Existing: approve/reject; approval used to auto-trigger ATE + promote
     New: approval sets status=approved only; no auto-apply (D-011)
GET  /api/v1/agentops/{agent_fqn}/adaptation-history
     Additive response: new fields (expected_improvement, applied_at, rolled_back_at, etc.) appear as optional
```

---

## New Endpoints — Adaptation Pipeline

### `POST /api/v1/agentops/adaptations/{proposal_id}/apply`

Apply an approved proposal. Creates pre-apply snapshot, mutates agent configuration, enqueues outcome measurement.

**Request**:
```json
{
  "reason": "Applying approved quality-regression fix"
}
```

**Response** `200 OK`:
```json
{
  "proposal_id": "uuid",
  "status": "applied",
  "applied_at": "2026-04-19T12:00:00Z",
  "applied_by": "uuid",
  "pre_apply_snapshot_id": "uuid",
  "pre_apply_configuration_hash": "sha256:...",
  "post_apply_configuration_hash": "sha256:...",
  "outcome_measurement_scheduled_at": "2026-04-22T12:00:00Z"
}
```

**Errors**:
- `404 Not Found` — proposal not found
- `409 Conflict` — proposal not in `approved` state
- `409 Conflict` — status=`stale` because target configuration field no longer exists (FR-014)
- `422 Unprocessable Entity` — validation error

---

### `POST /api/v1/agentops/adaptations/{proposal_id}/rollback`

Roll back an applied adaptation to the pre-apply snapshot. Fails if snapshot is outside retention window.

**Request**:
```json
{
  "reason": "Post-apply outcome classified as regressed; reverting"
}
```

**Response** `200 OK`:
```json
{
  "proposal_id": "uuid",
  "status": "rolled_back",
  "rolled_back_at": "2026-04-22T14:30:00Z",
  "rolled_back_by": "uuid",
  "rollback_reason": "...",
  "restored_snapshot_id": "uuid",
  "restored_configuration_hash": "sha256:...",
  "byte_identical_to_pre_apply": true
}
```

**Errors**:
- `404 Not Found`
- `409 Conflict` — proposal not in `applied` state
- `410 Gone` — rollback window expired (pre-apply snapshot beyond retention)

---

### `POST /api/v1/agentops/adaptations/{proposal_id}/revoke-approval`

Revoke approval prior to apply. Returns proposal to `proposed` state.

**Request**:
```json
{
  "reason": "Signal appears to have self-resolved; re-analysis needed"
}
```

**Response** `200 OK`: Updated `AdaptationProposalResponse` with `status=proposed`.

**Errors**:
- `404 Not Found`
- `409 Conflict` — proposal not in `approved` state (cannot revoke after apply)

---

### `GET /api/v1/agentops/adaptations/{proposal_id}/outcome`

Retrieve the outcome record for an applied proposal.

**Response** `200 OK`:
```json
{
  "id": "uuid",
  "proposal_id": "uuid",
  "observation_window_start": "2026-04-19T12:00:00Z",
  "observation_window_end": "2026-04-22T12:00:00Z",
  "expected_delta": {
    "metric": "quality_score",
    "baseline_value": 0.62,
    "target_value": 0.75,
    "target_delta": 0.13
  },
  "observed_delta": {
    "metric": "quality_score",
    "pre_apply_value": 0.62,
    "observation_period_value": 0.71,
    "observed_delta": 0.09,
    "observed_stddev": 0.04,
    "sample_count": 127
  },
  "classification": "improved",
  "variance_annotation": null,
  "measured_at": "2026-04-22T12:15:00Z"
}
```

**Errors**:
- `404 Not Found` — proposal not found
- `425 Too Early` — outcome not yet measured (observation window not elapsed)

---

### `GET /api/v1/agentops/adaptations/{proposal_id}/lineage`

End-to-end traceability: signal → proposal → approval → apply → outcome → rollback (if any). Supports FR-033 + SC-015.

**Response** `200 OK`:
```json
{
  "proposal_id": "uuid",
  "signals": [{"rule_type": "quality_trend", "captured_at": "...", "metrics": {...}}],
  "proposal_created_at": "2026-04-19T10:00:00Z",
  "proposal_created_by": "uuid",
  "review": {
    "decision": "approved",
    "reviewer_id": "uuid",
    "reviewed_at": "...",
    "reason": "..."
  },
  "application": {
    "applied_at": "...",
    "applied_by": "uuid",
    "pre_apply_snapshot_id": "uuid",
    "post_apply_snapshot_id": "uuid"
  },
  "outcome": { /* OutcomeResponse */ },
  "rollback": null,
  "current_status": "applied"
}
```

**Errors**: `404 Not Found`

---

## New Endpoints — Proficiency Levels

### `GET /api/v1/agentops/{agent_fqn}/proficiency`

Get the current proficiency assessment for an agent.

**Response** `200 OK`:
```json
{
  "agent_fqn": "...",
  "workspace_id": "uuid",
  "level": "competent",
  "dimension_values": {
    "retrieval_accuracy": 0.82,
    "instruction_adherence": 0.78,
    "context_coherence": 0.71,
    "aggregate_score": 0.77
  },
  "observation_count": 105,
  "missing_dimensions": [],
  "trigger": "scheduled",
  "assessed_at": "2026-04-19T06:00:00Z"
}
```

**Response for insufficient data**:
```json
{
  "agent_fqn": "...",
  "level": "undetermined",
  "missing_dimensions": ["context_coherence"],
  "observation_count": 8,
  "min_observations_required": 10
}
```

**Errors**: `404 Not Found` — agent does not exist in workspace.

---

### `GET /api/v1/agentops/{agent_fqn}/proficiency/history`

Get the proficiency trajectory for an agent over time.

**Query params**: `since?`, `until?`, `cursor?`, `limit=[1,100]`

**Response** `200 OK`:
```json
{
  "items": [
    { /* ProficiencyAssessmentResponse */ }
  ],
  "next_cursor": null,
  "total": 42
}
```

---

### `GET /api/v1/agentops/proficiency`

Fleet-wide query: list agents at a proficiency level or below.

**Query params**: `level_at_or_below=advanced`, `level=competent`, `workspace_id` (required), `cursor?`, `limit=[1,100]`

**Response** `200 OK`:
```json
{
  "items": [
    {
      "agent_fqn": "...",
      "current_level": "competent",
      "assessed_at": "..."
    }
  ],
  "next_cursor": null
}
```

---

## New Endpoints — Context-Performance Correlation

### `GET /api/v1/context-engineering/correlations/{agent_fqn}`

Get the latest correlation coefficients for an agent across all (dimension, performance_metric) pairs.

**Query params**: `window_days=30`, `performance_metric?`, `dimension?`

**Response** `200 OK`:
```json
{
  "agent_fqn": "...",
  "window_start": "2026-03-20T00:00:00Z",
  "window_end": "2026-04-19T00:00:00Z",
  "results": [
    {
      "dimension": "retrieval_accuracy",
      "performance_metric": "quality_score",
      "coefficient": 0.72,
      "classification": "strong_positive",
      "data_point_count": 45
    },
    {
      "dimension": "context_coherence",
      "performance_metric": "quality_score",
      "coefficient": null,
      "classification": "inconclusive",
      "data_point_count": 12
    }
  ]
}
```

**Errors**: `404 Not Found`

---

### `GET /api/v1/context-engineering/correlations`

Fleet-wide correlation query, supports triage of strong-negative cases.

**Query params**: `workspace_id` (required), `classification?` (e.g., `strong_negative`), `dimension?`, `performance_metric?`, `cursor?`, `limit=[1,100]`

**Response** `200 OK`:
```json
{
  "items": [
    {
      "agent_fqn": "...",
      "dimension": "context_coherence",
      "performance_metric": "quality_score",
      "coefficient": -0.81,
      "classification": "strong_negative",
      "data_point_count": 38,
      "window_end": "2026-04-19T00:00:00Z"
    }
  ],
  "next_cursor": null
}
```

---

### `POST /api/v1/context-engineering/correlations/recompute`

Manually trigger correlation recomputation (normally scheduled). Enqueues background work.

**Request**:
```json
{
  "workspace_id": "uuid",
  "agent_fqn": "..."
}
```

**Response** `202 Accepted`: `{"enqueued": true, "estimated_completion_seconds": 30}`

---

## Modified Endpoint Shapes

### `AdaptationProposalResponse` (additive fields)

Existing fields preserved; new fields appear as optional:
```json
{
  "id": "uuid",
  "agent_fqn": "...",
  "workspace_id": "uuid",
  "revision_id": "uuid",
  "status": "applied",
  "proposal_details": { /* existing */ },
  "signals": [ /* existing */ ],
  "review_reason": "...",
  "reviewed_by": "uuid",
  "reviewed_at": "...",
  "candidate_revision_id": "uuid",
  "evaluation_run_id": "uuid",
  "completed_at": "...",
  "completion_note": "...",

  "expected_improvement": { /* NEW, optional */ },
  "expires_at": "2026-04-26T10:00:00Z",
  "pre_apply_snapshot_id": "uuid",
  "applied_at": "...",
  "applied_by": "uuid",
  "rolled_back_at": null,
  "rolled_back_by": null,
  "rollback_reason": null,
  "revoked_at": null,
  "revoked_by": null,
  "revoke_reason": null,
  "signal_source": "automatic"
}
```

---

## Internal Service Interfaces

### Extended `AgentOpsService`

```python
# New methods:
async def apply_adaptation(self, proposal_id: UUID, payload: AdaptationApplyRequest, actor: UUID) -> AdaptationProposalResponse
async def rollback_adaptation(self, proposal_id: UUID, payload: AdaptationRollbackRequest, actor: UUID) -> AdaptationProposalResponse
async def revoke_adaptation_approval(self, proposal_id: UUID, payload: AdaptationRevokeRequest, actor: UUID) -> AdaptationProposalResponse
async def get_adaptation_outcome(self, proposal_id: UUID) -> AdaptationOutcomeResponse
async def get_adaptation_lineage(self, proposal_id: UUID) -> AdaptationLineageResponse
async def get_proficiency(self, agent_fqn: str, workspace_id: UUID) -> ProficiencyResponse
async def list_proficiency_history(self, agent_fqn: str, workspace_id: UUID, **kwargs) -> ProficiencyHistoryResponse
async def query_proficiency_fleet(self, workspace_id: UUID, level_filter: ProficiencyLevel, **kwargs) -> ProficiencyFleetResponse

# Scheduler entry points:
async def ttl_scanner_task(self) -> None           # scans proposed proposals for expiration
async def orphan_scanner_task(self) -> None         # scans for archived agents
async def outcome_measurer_task(self) -> None       # scans applied proposals for outcome observation
async def proficiency_recomputer_task(self) -> None # daily recompute
async def snapshot_retention_gc_task(self) -> None  # drop expired snapshots
```

### New `AdaptationApplyService` (in `agentops/adaptation/apply_service.py`)

```python
class AdaptationApplyService:
    async def apply(proposal, actor) -> ApplyResult
        # 1. Validate proposal in `approved` status
        # 2. Load current agent config
        # 3. Validate targeted fields still exist → raise StaleProposalError → status=stale
        # 4. Create pre-apply snapshot (JSONB + hash)
        # 5. Call registry_service.update_agent_profile() / activate_revision()
        # 6. Capture post-apply snapshot hash
        # 7. Update proposal: status=applied, applied_at, applied_by
        # 8. Publish `agentops.adaptation.applied` event
    async def rollback(proposal, actor, reason) -> RollbackResult
        # 1. Validate proposal in `applied` status
        # 2. Load pre-apply snapshot → validate retention not expired
        # 3. Restore profile fields via registry_service
        # 4. Restore active revision via registry_service.activate_revision()
        # 5. Verify post-rollback hash matches pre-apply hash byte-identically
        # 6. Update proposal: status=rolled_back
        # 7. Publish `agentops.adaptation.rolled_back` event
```

### New `AdaptationOutcomeService` (in `agentops/adaptation/outcome_service.py`)

```python
class AdaptationOutcomeService:
    async def measure_outcome(proposal) -> AdaptationOutcome
        # 1. Query ClickHouse for performance metric over observation window
        # 2. Compare against expected_delta
        # 3. Classify: improved | no_change | regressed | inconclusive
        # 4. Persist AdaptationOutcome (immutable)
        # 5. Publish `agentops.adaptation.outcome_recorded` event
```

### New `ProficiencyService` (in `agentops/proficiency.py`)

```python
class ProficiencyService:
    async def compute_for_agent(agent_fqn, workspace_id, trigger) -> ProficiencyAssessment
        # 1. Query context_assembly_records for dimension values over window
        # 2. Apply aggregation function (see D-015)
        # 3. Apply dwell-time gate
        # 4. Append row to agentops_proficiency_assessments
    async def get_current(agent_fqn, workspace_id) -> ProficiencyResponse
    async def list_history(agent_fqn, workspace_id, **kwargs) -> ProficiencyHistoryResponse
    async def query_fleet(workspace_id, level_at_or_below, **kwargs) -> ProficiencyFleetResponse
```

### New `CorrelationService` (in `context_engineering/correlation_service.py`)

```python
class CorrelationService:
    async def compute_for_agent(agent_fqn, workspace_id, window_days) -> list[CorrelationResult]
        # For each (dimension, performance_metric) pair:
        #   - Fetch paired observations (context_assembly_records × ClickHouse usage_events by execution_id)
        #   - Compute Pearson coefficient via scipy.stats.pearsonr
        #   - Classify + persist
        #   - Publish `context_engineering.correlation.computed` event
        #   - If strong_negative, publish `context_engineering.correlation.strong_negative`
    async def get_latest(agent_fqn, workspace_id, **kwargs) -> list[CorrelationResult]
    async def query_fleet(workspace_id, classification_filter, **kwargs) -> CorrelationFleetResponse
    async def enqueue_recompute(workspace_id, agent_fqn) -> None
```

### Extended `BehavioralAnalyzer` (in `agentops/adaptation/analyzer.py`)

```python
# New 5th signal rule:
async def _analyze_convergence_regression(agent_fqn, workspace_id) -> AdaptationSignal | None
    # Read self_correction_loops from ClickHouse over configured window
    # Compare against baseline (first half of window or stored baseline)
    # Return signal with rule_type="convergence_regression" if loops-per-execution exceeds baseline by threshold
```
