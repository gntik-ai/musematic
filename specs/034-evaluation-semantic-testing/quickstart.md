# Quickstart / Test Scenarios: Evaluation Framework and Semantic Testing

**Branch**: `034-evaluation-semantic-testing`

These scenarios cover end-to-end flows for all 8 user stories. Each can be executed independently after the `agentops-testing` runtime profile is running.

---

## T01 — Create eval set and run it (US1 core flow)

```python
# 1. Create an eval set with 5 benchmark cases
POST /api/v1/evaluations/eval-sets
{
  "name": "Finance Agent Smoke Test",
  "scorer_config": {
    "exact_match": {"enabled": true, "threshold": 1.0},
    "regex": {"enabled": true},
    "semantic": {"enabled": true, "threshold": 0.8}
  },
  "pass_threshold": 0.7
}
# → 201 {id: "eval-set-uuid", ...}

POST /api/v1/evaluations/eval-sets/{id}/cases (×5)
# → 201 BenchmarkCaseResponse for each

# 2. Run eval set against agent
POST /api/v1/evaluations/eval-sets/{id}/run
{"agent_fqn": "finance-ops:balance-checker"}
# → 202 {id: "run-uuid", status: "pending"}

# 3. Poll until completed
GET /api/v1/evaluations/runs/{run-uuid}
# → 200 {status: "completed", aggregate_score: 0.84, passed_cases: 4, total_cases: 5}

# 4. Inspect verdicts
GET /api/v1/evaluations/runs/{run-uuid}/verdicts
# → 200 [{id, benchmark_case_id, overall_score, passed, scorer_results: {exact_match: {...}, regex: {...}, semantic: {...}}}]
```

**Expected**: 5 verdicts with scores from all 3 configured scorers. 4/5 cases pass with aggregate = 0.84.

---

## T02 — Semantic similarity scorer with threshold (US1 scorer)

```python
# Create eval set with semantic scorer only, threshold=0.75
POST /api/v1/evaluations/eval-sets
{"scorer_config": {"semantic": {"enabled": true, "threshold": 0.75}}, ...}

# Add benchmark case with paraphrased expected output
POST .../cases
{"input_data": {"query": "What is the balance?"}, "expected_output": "Your current account balance is $1,234.56"}

# Run eval — agent returns "The balance on your account is $1234.56"
POST .../run {"agent_fqn": "finance-ops:balance-checker"}

# Check verdict
GET .../verdicts/{id}
# scorer_results.semantic: {score: 0.94, passed: true, threshold: 0.75}
```

**Expected**: Semantic score ~0.94 (high similarity, different wording), verdict passed=true.

---

## T03 — A/B experiment comparing two agents (US1 A/B)

```python
# Run same eval set against agent-A and agent-B
POST .../eval-sets/{id}/run {"agent_fqn": "finance-ops:agent-a"}  # → run_a_id
POST .../eval-sets/{id}/run {"agent_fqn": "finance-ops:agent-b"}  # → run_b_id

# Wait for both to complete, then create experiment
POST /api/v1/evaluations/experiments
{"name": "A vs B comparison", "run_a_id": "...", "run_b_id": "..."}
# → 202 {id: "experiment-uuid", status: "pending"}

GET /api/v1/evaluations/experiments/{id}
# → {status: "completed", p_value: 0.03, effect_size: 0.41, winner: "a",
#    analysis_summary: "Agent A significantly outperforms Agent B (p=0.03, medium effect)"}
```

**Expected**: p_value < 0.05, winner identified, confidence interval does not include 0.

---

## T04 — LLM-as-Judge with calibration (US2)

```python
# Create eval set with llm_judge scorer, calibration_runs=5
POST /api/v1/evaluations/eval-sets
{
  "scorer_config": {
    "llm_judge": {
      "enabled": true,
      "judge_model": "claude-opus-4-6",
      "rubric": {"template": "helpfulness"},
      "calibration_runs": 5
    }
  }
}

# Add case + run
POST .../run {"agent_fqn": "support:ticket-resolver"}

# Check verdict scorer_results
GET .../verdicts/{id}
# scorer_results.llm_judge:
#   {
#     "score": 4.2,
#     "rationale": "...",
#     "calibration_distribution": {
#       "mean": 4.2, "stddev": 0.4,
#       "confidence_interval": {"lower": 3.85, "upper": 4.55},
#       "runs": [4, 4, 5, 4, 4]
#     }
#   }
```

**Expected**: 5 calibration runs, distribution computed, confidence interval present.

---

## T05 — Custom rubric for LLM-as-Judge (US2)

```python
# Eval set with custom rubric
POST /api/v1/evaluations/eval-sets
{
  "scorer_config": {
    "llm_judge": {
      "enabled": true,
      "judge_model": "claude-sonnet-4-6",
      "rubric": {
        "custom_criteria": [
          {"name": "domain_accuracy", "description": "Is the financial data accurate?", "scale": 5},
          {"name": "regulatory_compliance", "description": "Does the response comply with financial regulations?", "scale": 3}
        ]
      }
    }
  }
}
# → scorer_results.llm_judge.criteria_scores: {domain_accuracy: 4, regulatory_compliance: 3}
```

**Expected**: Per-criterion scores in verdict, rubric stored in eval set config.

---

## T06 — Trajectory scorer on a completed execution (US3)

```python
# Evaluate trajectory of a completed agent execution
POST /api/v1/evaluations/eval-sets
{
  "scorer_config": {
    "trajectory": {
      "enabled": true,
      "include_llm_holistic": true,
      "judge_model": "claude-sonnet-4-6"
    }
  }
}

# BenchmarkCase references an execution_id via input_data
POST .../cases
{"input_data": {"execution_id": "exec-uuid"}, "expected_output": "task_completed"}

POST .../run {"agent_fqn": "ops:document-processor"}

GET .../verdicts/{id}
# scorer_results.trajectory:
#   {
#     "efficiency_score": 0.7,        # took 14 steps, optimal was 10
#     "tool_appropriateness_score": 0.9,
#     "reasoning_coherence_score": 0.85,
#     "cost_effectiveness_score": 0.75,
#     "overall_trajectory_score": 0.8,
#     "llm_judge_holistic": {"score": 4.0, "rationale": "..."}
#   }
```

**Expected**: 5-dimensional trajectory score, holistic LLM assessment present.

---

## T07 — Adversarial test suite generation (US4)

```python
# Generate adversarial suite for a finance agent
POST /api/v1/testing/suites/generate
{
  "agent_fqn": "finance-ops:payment-processor",
  "suite_type": "adversarial",
  "cases_per_category": 10
}
# → 202 {id: "suite-uuid", status: "generating", ...}

# Poll until generated
GET /api/v1/testing/suites/{id}
# → {case_count: 60, category_counts: {prompt_injection: 10, jailbreak: 10,
#    contradictory: 10, malformed_data: 10, ambiguous: 10, resource_exhaustion: 10}}

# Get cases for a specific category
GET /api/v1/testing/suites/{id}/cases?category=prompt_injection
# → 10 AdversarialCaseResponse rows

# Import into eval set
POST /api/v1/testing/suites/{id}/import
{"eval_set_id": "existing-eval-set-uuid"}
# → {imported_case_count: 60, eval_set_id: "..."}
```

**Expected**: 60 cases (10 per category), domain-specific (finance-themed injections), importable.

---

## T08 — ATE create and run against two agents (US5)

```python
# Create ATE
POST /api/v1/evaluations/ate
{
  "name": "Payment Processor Certification v1",
  "scenarios": [
    {"id": "s1", "name": "Valid payment", "input_data": {...}, "expected_output": "...", "timeout_seconds": 30},
    {"id": "s2", "name": "Duplicate payment rejection", ...},
    {"id": "s3", "name": "Insufficient funds handling", ...}
  ],
  "scorer_config": {"semantic": {"enabled": true, "threshold": 0.85}},
  "performance_thresholds": {"latency_p95_ms": 3000},
  "safety_checks": [{"check_type": "no_pii_leak", "expected_outcome": "pass"}]
}
# → 201 {id: "ate-uuid"}

# Run against agent-A
POST /api/v1/evaluations/ate/{ate-uuid}/run/finance-ops:payment-a
# → 202 {id: "run-a-uuid", status: "pending"}

# Run against agent-B (same ATE — enables comparison)
POST /api/v1/evaluations/ate/{ate-uuid}/run/finance-ops:payment-b
# → 202 {id: "run-b-uuid", status: "pending"}

# Compare results
GET /api/v1/evaluations/ate/{ate-uuid}/results
# → [{run-a: passed=true, score=0.91}, {run-b: passed=false, score=0.63}]
```

**Expected**: Two ATERuns with identical scoring criteria, directly comparable, evidence stored in MinIO.

---

## T09 — ATE pre-check failure (US5 edge case)

```python
# Create ATE with non-existent scenario reference
POST /api/v1/evaluations/ate/{ate-uuid}/run/finance-ops:test-agent

# Simulate: scenario "s-missing" referenced but not in config
GET /api/v1/evaluations/ate/runs/{run-uuid}
# → {status: "pre_check_failed",
#    pre_check_errors: ["Scenario s-missing not found in ATE config"]}
```

**Expected**: ATERun created with pre_check_failed status, no simulation started, errors documented.

---

## T10 — Robustness test: statistical distribution (US6)

```python
POST /api/v1/evaluations/robustness-runs
{
  "eval_set_id": "eval-set-uuid",
  "agent_fqn": "finance-ops:balance-checker",
  "trial_count": 20,
  "variance_threshold": 0.15
}
# → 202 {id: "robustness-uuid", status: "pending", trial_count: 20}

# After all 20 trials complete:
GET /api/v1/evaluations/robustness-runs/{id}
# → {
#   status: "completed",
#   completed_trials: 20,
#   distribution: {mean: 0.87, stddev: 0.04, p5: 0.8, p25: 0.84, p50: 0.88, p75: 0.9, p95: 0.93},
#   is_unreliable: false   # stddev 0.04 < threshold 0.15
# }
```

**Expected**: 20 trials, distribution computed, is_unreliable=false for low-variance agent.

---

## T11 — Robustness test: unreliable agent flagged (US6)

```python
# Same as T10 but against an inconsistent agent
# After 20 trials with high variance (stddev=0.22 > threshold=0.15):
GET .../robustness-runs/{id}
# → {is_unreliable: true, distribution: {mean: 0.75, stddev: 0.22, ...}}
```

**Expected**: is_unreliable=true when stddev exceeds threshold.

---

## T12 — Behavioral drift detection (US6)

```python
# APScheduler runs drift scanner daily
# Scenario: agent had 30 days of 0.9 average score, today scores 0.65

# After drift scanner fires:
GET /api/v1/testing/drift-alerts?agent_fqn=finance-ops:balance-checker&acknowledged=false
# → [{
#   id: "alert-uuid",
#   metric_name: "overall_score",
#   baseline_value: 0.90,
#   current_value: 0.65,
#   stddevs_from_baseline: 2.6,
#   acknowledged: false
# }]

# Acknowledge
PATCH /api/v1/testing/drift-alerts/{id}/acknowledge
# → {acknowledged: true}
```

**Expected**: Alert fired at >2 stddev deviation, acknowledged by admin.

---

## T13 — Drift suppression during robustness test (US6 edge case)

```python
# Robustness test is running for agent X (introduces intentional variance)
# Drift scanner fires for same agent during this window
# → drift alert suppressed (not created)
# After robustness test completes → drift scanner resumes normal evaluation
```

**Expected**: No drift alert created during active robustness test window.

---

## T14 — Coordination test on 3-agent fleet (US7)

```python
POST /api/v1/testing/coordination-tests
{"fleet_id": "fleet-uuid", "execution_id": "exec-uuid"}
# → 202 {id: "coord-result-uuid"}

GET /api/v1/testing/coordination-tests/{id}
# → {
#   fleet_id: "fleet-uuid",
#   completion_score: 0.93,
#   coherence_score: 0.81,
#   goal_achievement_score: 0.88,
#   overall_score: 0.87,
#   per_agent_scores: {
#     "fleet:agent-1": {completion_score: 0.95, coherence_score: 0.85, contribution_score: 0.9},
#     "fleet:agent-2": {completion_score: 0.92, coherence_score: 0.80, contribution_score: 0.85},
#     "fleet:agent-3": {completion_score: 0.92, coherence_score: 0.78, contribution_score: 0.85}
#   },
#   insufficient_members: false
# }
```

**Expected**: Fleet-level and per-agent scores, insufficient_members=false for 3-agent fleet.

---

## T15 — Coordination test on single-agent fleet (US7 edge case)

```python
POST /api/v1/testing/coordination-tests
{"fleet_id": "single-agent-fleet-uuid"}

GET .../coordination-tests/{id}
# → {insufficient_members: true, overall_score: 0.9, per_agent_scores: {agent-1: {...}},
#    coherence_score: null, goal_achievement_score: null}
```

**Expected**: insufficient_members=true, fleet-level coordination metrics marked N/A.

---

## T16 — Human grading: confirm automated score (US8)

```python
# Eval run already completed with verdicts
GET /api/v1/evaluations/runs/{run-id}/review-progress
# → {total_verdicts: 10, pending_review: 10, reviewed: 0, overridden: 0}

POST /api/v1/evaluations/verdicts/{verdict-id}/grade
{"decision": "confirmed"}
# → 201 {id: "grade-uuid", decision: "confirmed", original_score: 0.85, override_score: null}

GET /api/v1/evaluations/runs/{run-id}/review-progress
# → {total_verdicts: 10, pending_review: 9, reviewed: 1, overridden: 0}
```

---

## T17 — Human grading: override automated score (US8)

```python
POST /api/v1/evaluations/verdicts/{verdict-id}/grade
{"decision": "overridden", "override_score": 0.3, "feedback": "Agent provided wrong currency conversion"}
# → 201 {id: "grade-uuid", decision: "overridden", original_score: 0.85, override_score: 0.3,
#         feedback: "Agent provided wrong currency conversion"}
```

**Expected**: Override recorded, original score snapshotted, feedback stored, review status=overridden.

---

## T18 — Human grading audit trail (US8)

```python
GET /api/v1/evaluations/verdicts/{verdict-id}
# → JudgeVerdictResponse with human_grade:
#   {
#     decision: "overridden",
#     original_score: 0.85,
#     override_score: 0.3,
#     feedback: "...",
#     reviewer_id: "user-uuid",
#     reviewed_at: "2026-04-12T14:30:00Z"
#   }
```

**Expected**: Full audit trail visible on verdict response.

---

## T19 — Scorer error handling: one scorer fails (US1 edge case)

```python
# Eval set with semantic + exact_match scorers
# Simulate: Qdrant unavailable during a run

GET .../verdicts/{id}
# → {
#   status: "scored",
#   scorer_results: {
#     "exact_match": {score: 1.0, passed: true},
#     "semantic": {score: null, error: "Qdrant unavailable: connection refused", passed: null}
#   },
#   overall_score: 1.0  # computed only from successful scorers
# }
```

**Expected**: Partial results preserved, other scorers continue, overall score computed from successful scorers only.

---

## T20 — Test suite import and run (US4 + US1 integration)

```python
# Generate mixed suite (adversarial + positive)
POST /api/v1/testing/suites/generate
{"agent_fqn": "finance-ops:payment-processor", "suite_type": "mixed"}

# Import into eval set
POST /api/v1/testing/suites/{suite-id}/import
{"eval_set_id": "eval-set-uuid"}
# → {imported_case_count: 80}

# Run the eval set (now contains generated cases)
POST /api/v1/evaluations/eval-sets/{eval-set-uuid}/run
{"agent_fqn": "finance-ops:payment-processor"}
# → full EvaluationRun with verdicts for all 80 cases including adversarial categories
```

**Expected**: Generated cases importable into eval sets and fully runnable through the evaluation pipeline.
