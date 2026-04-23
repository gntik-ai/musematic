# REST API Contracts: Trajectory Evaluation and LLM-as-Judge Formalization

**Feature**: 067-trajectory-judge-evaluation  
**Date**: 2026-04-19  
**Base path**: `/api/v1/evaluation/`  
**Auth**: All endpoints require Bearer JWT. Authorization mirrors existing evaluation endpoints.

---

## New Endpoints

### 1. Rubric CRUD

#### `POST /rubrics`
Create a rubric.

**Request**:
```json
{
  "name": "custom_correctness",
  "description": "Correctness rubric for domain X",
  "criteria": [
    {
      "name": "factual_accuracy",
      "description": "Whether stated facts are correct",
      "scale_min": 1,
      "scale_max": 5,
      "examples": {
        "1": "Contains factual errors",
        "3": "Mostly correct",
        "5": "Fully accurate"
      }
    }
  ]
}
```

**Response** `201 Created`:
```json
{
  "id": "uuid",
  "workspace_id": "uuid",
  "name": "custom_correctness",
  "description": "Correctness rubric for domain X",
  "criteria": [...],
  "version": 1,
  "is_builtin": false,
  "status": "active",
  "created_by": "uuid",
  "created_at": "2026-04-19T12:00:00Z",
  "updated_at": "2026-04-19T12:00:00Z"
}
```

**Errors**:
- `400 Bad Request`: Contradictory examples at same scale point (FR-008)
- `409 Conflict`: Name already exists in workspace

---

#### `GET /rubrics`
List rubrics (workspace-scoped, includes builtins).

**Query params**: `status=active|archived`, `include_builtins=true|false` (default true), `page=1`, `page_size=20`

**Response** `200 OK`:
```json
{
  "items": [{ /* RubricResponse */ }],
  "total": 12,
  "page": 1,
  "page_size": 20
}
```

---

#### `GET /rubrics/{rubric_id}`
Get a single rubric by ID.

**Response** `200 OK`: `RubricResponse`  
**Errors**: `404 Not Found`

---

#### `PATCH /rubrics/{rubric_id}`
Update a rubric. Increments `version`. Blocked on builtin rubrics.

**Request** (partial):
```json
{
  "name": "updated_name",
  "description": "updated desc",
  "criteria": [...]
}
```

**Response** `200 OK`: Updated `RubricResponse` with new `version`  
**Errors**:
- `400 Bad Request`: Contradictory examples
- `403 Forbidden`: Attempt to modify a builtin rubric
- `404 Not Found`
- `409 Conflict`: Rubric has in-flight runs (criteria update blocked; description/name updates allowed)

---

#### `DELETE /rubrics/{rubric_id}`
Archive (soft-delete) a rubric.

**Response** `204 No Content`  
**Errors**:
- `403 Forbidden`: Attempt to delete a builtin rubric
- `404 Not Found`
- `409 Conflict`: Rubric is referenced by at least one in-flight evaluation run (FR-024, SC-015)

---

### 2. Calibration

#### `POST /rubrics/{rubric_id}/calibrate`
Start a calibration run against a reference set.

**Request**:
```json
{
  "judge_model": "gpt-4",
  "reference_set_id": "eval-set-uuid-or-fixture-id"
}
```

**Response** `202 Accepted`:
```json
{
  "id": "uuid",
  "rubric_id": "uuid",
  "rubric_version": 3,
  "judge_model": "gpt-4",
  "reference_set_id": "...",
  "status": "pending",
  "calibrated": null,
  "distribution": null,
  "started_at": "2026-04-19T12:00:00Z",
  "completed_at": null
}
```

Calibration runs asynchronously via `BackgroundTasks`. Poll `GET /calibration-runs/{id}` for results.

**Errors**:
- `404 Not Found`: Rubric not found
- `409 Conflict`: Rubric is archived

---

#### `GET /calibration-runs/{run_id}`
Get calibration run status and report.

**Response** `200 OK`:
```json
{
  "id": "uuid",
  "rubric_id": "uuid",
  "rubric_version": 3,
  "judge_model": "gpt-4",
  "reference_set_id": "...",
  "status": "completed",
  "calibrated": true,
  "error_grade_finding": false,
  "agreement_rate": 0.88,
  "distribution": {
    "overall": {
      "min": 1.5, "max": 4.8, "mean": 3.2, "stddev": 0.9,
      "histogram": {"1": 2, "2": 5, "3": 8, "4": 4, "5": 1}
    },
    "per_criterion": {
      "factual_accuracy": {
        "min": 1.0, "max": 5.0, "mean": 3.1, "stddev": 1.1,
        "histogram": {"1": 3, "2": 4, "3": 7, "4": 5, "5": 1},
        "low_discrimination": false
      }
    },
    "runs": [3.0, 3.5, 2.8],
    "low_confidence": false
  },
  "started_at": "2026-04-19T12:00:00Z",
  "completed_at": "2026-04-19T12:01:30Z"
}
```

**Errors**: `404 Not Found`

---

### 3. Ad-Hoc Judge

#### `POST /judge`
Score a single output against a rubric without an eval run. Rate-limited identically to eval run starts.

**Request**:
```json
{
  "rubric_id": "uuid",
  "output": "The capital of France is Paris, established as capital in 987 AD.",
  "judge_model": "gpt-4"
}
```

OR with inline rubric (no DB required):
```json
{
  "rubric": {
    "name": "quick_check",
    "criteria": [{
      "name": "accuracy",
      "scale_min": 1, "scale_max": 5,
      "examples": {"1": "Wrong", "5": "Correct"}
    }]
  },
  "output": "The answer is 42.",
  "judge_model": "gpt-4"
}
```

**Response** `200 OK` (within 30s p95 — SC-013):
```json
{
  "rubric_id": "uuid",
  "rubric_version": 3,
  "judge_model": "gpt-4",
  "per_criterion_scores": {
    "factual_accuracy": {
      "score": 4.0,
      "rationale": "Claim is accurate; Paris has been capital since 987 CE.",
      "out_of_range": false
    }
  },
  "overall_score": 4.0,
  "aggregation_method": "arithmetic_mean",
  "rationale": "Output is factually accurate with minor historical imprecision.",
  "principal_id": "uuid",
  "timestamp": "2026-04-19T12:00:00Z",
  "duration_ms": 1240
}
```

**Errors**:
- `400 Bad Request`: Neither `rubric_id` nor `rubric` provided
- `404 Not Found`: `rubric_id` not found
- `409 Conflict`: Rubric is archived
- `503 Service Unavailable`: Judge model unreachable (FR-027)
- `429 Too Many Requests`: Rate limit exceeded

---

### 4. Discovery Endpoints

#### `GET /scorers`
Enumerate all registered scorer types.

**Response** `200 OK`:
```json
{
  "scorer_types": [
    {
      "type": "exact_match",
      "category": "deterministic",
      "description": "Byte-identical string comparison"
    },
    {
      "type": "regex",
      "category": "deterministic",
      "description": "Regular expression match"
    },
    {
      "type": "json_schema",
      "category": "deterministic",
      "description": "JSON Schema validation"
    },
    {
      "type": "semantic",
      "category": "semantic",
      "description": "Cosine similarity of embeddings"
    },
    {
      "type": "trajectory",
      "category": "trajectory",
      "description": "Full action path evaluation"
    },
    {
      "type": "llm_judge",
      "category": "judge",
      "description": "LLM-as-Judge rubric scoring"
    }
  ]
}
```

No auth required (public discovery endpoint). No DB read — served from in-memory `ScorerRegistry`.

---

#### `GET /rubric-templates`
List all built-in rubric templates.

**Response** `200 OK`:
```json
{
  "templates": [
    {
      "name": "correctness",
      "description": "Factual accuracy and completeness",
      "criteria_count": 2,
      "rubric_id": "uuid"
    },
    { "name": "helpfulness", ... },
    { "name": "safety", ... },
    { "name": "style", ... },
    { "name": "faithfulness", ... },
    { "name": "instruction_following", ... }
  ]
}
```

Returns exactly 6 items (SC-008).

---

#### `GET /rubric-templates/{template_name}`
Get full template details (same as `GET /rubrics/{id}` but by name).

**Response** `200 OK`: `RubricResponse`  
**Errors**: `404 Not Found`

---

## Internal Service Interfaces

### `RubricService` (new class in `service.py`)

```python
class RubricService:
    async def create_rubric(self, payload: RubricCreate, workspace_id: UUID, actor_id: UUID) -> RubricResponse
    async def get_rubric(self, rubric_id: UUID, workspace_id: UUID | None = None) -> RubricResponse
    async def list_rubrics(self, *, workspace_id: UUID, status: RubricStatus | None, include_builtins: bool, page: int, page_size: int) -> RubricListResponse
    async def update_rubric(self, rubric_id: UUID, payload: RubricUpdate, actor_id: UUID) -> RubricResponse
    async def archive_rubric(self, rubric_id: UUID, actor_id: UUID) -> None  # 409 if in-flight
    async def get_by_name_builtin(self, name: str) -> RubricResponse
```

### `CalibrationService` (new class in `service.py`)

```python
class CalibrationService:
    async def start_calibration(self, rubric_id: UUID, payload: CalibrationRunCreate, actor_id: UUID) -> CalibrationRunResponse
    async def get_calibration_run(self, run_id: UUID) -> CalibrationRunResponse
    async def run_calibration_background(self, run_id: UUID) -> None  # called by BackgroundTasks
```

### Extended `EvalRunnerService`

```python
# New method added to existing EvalRunnerService:
async def judge_adhoc(self, payload: AdHocJudgeRequest, actor_id: UUID) -> AdHocJudgeResponse
```

### Extended `TrajectoryScorer`

```python
# New method on existing TrajectoryScorer:
async def score_cooperation(
    self,
    agent_execution_ids: list[UUID],
    config: dict[str, Any]
) -> CooperationScoreResult
```

---

## Modified Existing Endpoints (None)

No existing endpoints are modified. All changes are additive (FR-019–FR-021, Brownfield Rule 7).
