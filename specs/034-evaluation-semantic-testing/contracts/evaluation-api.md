# API Contracts: Evaluation Framework and Semantic Testing

**Branch**: `034-evaluation-semantic-testing`  
**Base path**: `/api/v1`

---

## evaluation/ Endpoints — `/api/v1/evaluations`

### Eval Sets

```
POST   /eval-sets
       Body: EvalSetCreate
       Returns: 201 EvalSetResponse
       Auth: workspace member

GET    /eval-sets
       Query: ?status=active|archived&page=0&page_size=20
       Returns: 200 PaginatedResponse[EvalSetResponse]
       Auth: workspace member

GET    /eval-sets/{eval_set_id}
       Returns: 200 EvalSetResponse
       404 if not found

PATCH  /eval-sets/{eval_set_id}
       Body: EvalSetUpdate (name, description, scorer_config, pass_threshold)
       Returns: 200 EvalSetResponse
       Auth: workspace admin or creator

DELETE /eval-sets/{eval_set_id}
       Returns: 204 (soft delete — sets status=archived)
       Auth: workspace admin
```

### Benchmark Cases

```
POST   /eval-sets/{eval_set_id}/cases
       Body: BenchmarkCaseCreate
       Returns: 201 BenchmarkCaseResponse
       Auth: workspace member

GET    /eval-sets/{eval_set_id}/cases
       Query: ?category=adversarial|positive&page=0&page_size=50
       Returns: 200 PaginatedResponse[BenchmarkCaseResponse]

GET    /eval-sets/{eval_set_id}/cases/{case_id}
       Returns: 200 BenchmarkCaseResponse

DELETE /eval-sets/{eval_set_id}/cases/{case_id}
       Returns: 204
       Auth: workspace admin or creator
```

### Evaluation Runs

```
POST   /eval-sets/{eval_set_id}/run
       Body: EvaluationRunCreate (agent_fqn, agent_id?)
       Returns: 202 EvaluationRunResponse (status=pending)
       Note: run is started asynchronously via BackgroundTask

GET    /runs
       Query: ?eval_set_id=&agent_fqn=&status=&page=0&page_size=20
       Returns: 200 PaginatedResponse[EvaluationRunResponse]
       Auth: workspace member

GET    /runs/{run_id}
       Returns: 200 EvaluationRunResponse

GET    /runs/{run_id}/verdicts
       Query: ?passed=true|false&status=scored|error&page=0&page_size=50
       Returns: 200 PaginatedResponse[JudgeVerdictResponse]

GET    /verdicts/{verdict_id}
       Returns: 200 JudgeVerdictResponse (includes human_grade if present)
```

### A/B Experiments

```
POST   /experiments
       Body: AbExperimentCreate (name, run_a_id, run_b_id)
       Returns: 202 AbExperimentResponse (status=pending)
       Constraint: run_a_id and run_b_id must both be status=completed
       Constraint: both runs must use the same eval_set_id

GET    /experiments/{experiment_id}
       Returns: 200 AbExperimentResponse
```

### Accredited Testing Environments

```
POST   /ate
       Body: ATEConfigCreate
       Returns: 201 ATEConfigResponse
       Auth: workspace admin

GET    /ate
       Query: ?page=0&page_size=20
       Returns: 200 PaginatedResponse[ATEConfigResponse]

GET    /ate/{ate_config_id}
       Returns: 200 ATEConfigResponse

PATCH  /ate/{ate_config_id}
       Body: ATEConfigUpdate
       Returns: 200 ATEConfigResponse
       Auth: workspace admin

POST   /ate/{ate_config_id}/run/{agent_fqn}
       Body: ATERunRequest (agent_id?: UUID)
       Returns: 202 ATERunResponse (status=pending)
       Note: pre-check runs synchronously; simulation starts async

GET    /ate/{ate_config_id}/results
       Query: ?page=0&page_size=20
       Returns: 200 PaginatedResponse[ATERunResponse]
       Note: all ATERun rows for this config, across all agents — enables cross-agent comparison

GET    /ate/runs/{ate_run_id}
       Returns: 200 ATERunResponse (includes full report if completed)
```

### Robustness Testing

```
POST   /robustness-runs
       Body: RobustnessRunCreate (eval_set_id, agent_fqn, trial_count, variance_threshold?,
                                  benchmark_case_id?)
       Returns: 202 RobustnessTestRunResponse

GET    /robustness-runs/{robustness_run_id}
       Returns: 200 RobustnessTestRunResponse (includes distribution when completed)
```

### Human-AI Grading

```
GET    /runs/{run_id}/review-progress
       Returns: 200 ReviewProgressResponse
       (total_verdicts, pending_review, reviewed, overridden)

GET    /verdicts/{verdict_id}/grade
       Returns: 200 HumanAiGradeResponse | 404 if not yet graded

POST   /verdicts/{verdict_id}/grade
       Body: HumanGradeSubmit (decision, override_score?, feedback?)
       Returns: 201 HumanAiGradeResponse
       Constraint: only one grade per verdict; use PATCH to update
       Auth: evaluator role or workspace admin

PATCH  /grades/{grade_id}
       Body: HumanGradeUpdate (override_score?, feedback?)
       Returns: 200 HumanAiGradeResponse
       Auth: grade.reviewer_id == current_user OR workspace admin
```

---

## testing/ Endpoints — `/api/v1/testing`

### Test Suite Generation

```
POST   /suites/generate
       Body: GenerateSuiteRequest (agent_fqn, agent_id?, suite_type, cases_per_category?)
       Returns: 202 GeneratedTestSuiteResponse (generation starts async)
       Note: returns immediately with suite record; cases populated as generation completes

GET    /suites
       Query: ?agent_fqn=&suite_type=adversarial|positive|mixed&page=0&page_size=20
       Returns: 200 PaginatedResponse[GeneratedTestSuiteResponse]
       Auth: workspace member

GET    /suites/{suite_id}
       Returns: 200 GeneratedTestSuiteResponse (includes category_counts)

GET    /suites/{suite_id}/cases
       Query: ?category=prompt_injection|jailbreak|...&page=0&page_size=50
       Returns: 200 PaginatedResponse[AdversarialCaseResponse]

POST   /suites/{suite_id}/import
       Body: ImportSuiteRequest (eval_set_id: UUID)
       Returns: 200 {imported_case_count: int, eval_set_id: UUID}
       Note: creates BenchmarkCase rows in the target eval set for each case in the suite
       Constraint: eval_set must be active and in same workspace
```

### Coordination Testing

```
POST   /coordination-tests
       Body: CoordinationTestRequest (fleet_id, execution_id?)
       Returns: 202 CoordinationTestResultResponse

GET    /coordination-tests/{result_id}
       Returns: 200 CoordinationTestResultResponse
       Auth: workspace member
```

### Behavioral Drift

```
GET    /drift-alerts
       Query: ?agent_fqn=&eval_set_id=&acknowledged=false&page=0&page_size=20
       Returns: 200 PaginatedResponse[DriftAlertResponse]
       Auth: workspace admin

PATCH  /drift-alerts/{alert_id}/acknowledge
       Returns: 200 DriftAlertResponse (acknowledged=true)
       Auth: workspace admin
```

---

## Internal Service Interfaces

### EvalSuiteServiceInterface (exported from evaluation/)

```python
class EvalSuiteServiceInterface(Protocol):
    """Read-only interface consumed by analytics/ and notifications/."""

    async def get_run_summary(self, run_id: UUID) -> EvalRunSummaryDTO:
        """Returns aggregate stats for a completed run."""

    async def get_latest_agent_score(
        self, agent_fqn: str, eval_set_id: UUID, workspace_id: UUID
    ) -> float | None:
        """Returns the aggregate_score of the most recent completed run for this agent+eval_set."""
```

### CoordinationTestServiceInterface (exported from testing/)

```python
class CoordinationTestServiceInterface(Protocol):
    """Called by fleets/ FleetService when a fleet execution completes."""

    async def run_coordination_test(
        self,
        fleet_id: UUID,
        execution_id: UUID,
        workspace_id: UUID,
    ) -> CoordinationTestResult:
        """
        Evaluates coordination quality from a completed fleet execution.
        Reads per-agent execution journals via ExecutionQueryInterface.
        """
```

---

## Kafka Event Schemas

**Topic**: `evaluation.events`

```json
{
  "event_type": "evaluation.run.completed",
  "event_id": "uuid",
  "timestamp": "ISO-8601",
  "workspace_id": "uuid",
  "payload": {
    "run_id": "uuid",
    "eval_set_id": "uuid",
    "agent_fqn": "string",
    "aggregate_score": 0.87,
    "passed_cases": 9,
    "failed_cases": 1,
    "total_cases": 10
  }
}

{
  "event_type": "evaluation.drift.detected",
  "event_id": "uuid",
  "timestamp": "ISO-8601",
  "workspace_id": "uuid",
  "payload": {
    "alert_id": "uuid",
    "agent_fqn": "string",
    "eval_set_id": "uuid",
    "metric_name": "overall_score",
    "baseline_value": 0.92,
    "current_value": 0.71,
    "stddevs_from_baseline": 2.4
  }
}

{
  "event_type": "evaluation.ate.run.completed",
  "event_id": "uuid",
  "timestamp": "ISO-8601",
  "workspace_id": "uuid",
  "payload": {
    "ate_run_id": "uuid",
    "ate_config_id": "uuid",
    "agent_fqn": "string",
    "scenarios_passed": 4,
    "scenarios_failed": 1,
    "total_scenarios": 5,
    "overall_passed": false,
    "evidence_artifact_key": "evaluation-ate-evidence/{run_id}/evidence.json"
  }
}
```
