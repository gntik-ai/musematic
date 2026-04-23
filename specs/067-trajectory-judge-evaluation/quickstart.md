# Quickstart & Acceptance Scenarios: Trajectory Evaluation and LLM-as-Judge Formalization

**Feature**: 067-trajectory-judge-evaluation  
**Date**: 2026-04-19

## Setup Prerequisites

1. Create a workspace and an evaluation set with at least one benchmark case
2. Have at least one agent execution recorded (produces trajectory data)
3. Judge model configured via `EVALUATION_LLM_JUDGE_MODEL` + `EVALUATION_LLM_JUDGE_API_URL`

---

## Scenario S1 — Trajectory exact-match comparison

```python
# BenchmarkCase scoring_criteria includes expected trajectory
case_payload = {
    "input_data": {"execution_id": "exec-uuid-001"},
    "expected_output": "Agent completed task",
    "scoring_criteria": {
        "trajectory": {
            "comparison_method": "exact",
            "expected_steps": [
                {"tool": "search_web", "order": 1},
                {"tool": "summarize", "order": 2}
            ]
        }
    }
}
# Expected: trajectory scorer returns comparison_score=1.0 when actual steps match exactly
# Expected: four dimension scores returned (path_efficiency, tool_appropriateness, reasoning_coherence, cost_effectiveness)
```

---

## Scenario S2 — Trajectory any-order comparison: same tools, different order

```python
# Agent produced steps: [summarize, search_web] — reversed from expected
scoring_criteria = {
    "trajectory": {
        "comparison_method": "any_order",
        "expected_steps": [
            {"tool": "search_web"},
            {"tool": "summarize"}
        ]
    }
}
# Expected: comparison_score=1.0 (both expected tools appeared, order irrelevant)
```

---

## Scenario S3 — Trajectory precision: extra unrequested tool steps

```python
# Agent took 3 steps: [search_web, summarize, translate] — last step not in expected
scoring_criteria = {
    "trajectory": {
        "comparison_method": "precision",
        "expected_steps": [{"tool": "search_web"}, {"tool": "summarize"}]
    }
}
# Expected: comparison_score = 2/3 ≈ 0.667 (2 of 3 taken steps were expected)
```

---

## Scenario S4 — Trajectory recall: missing expected step

```python
# Agent took 1 step: [search_web] — missed "summarize"
scoring_criteria = {
    "trajectory": {
        "comparison_method": "recall",
        "expected_steps": [{"tool": "search_web"}, {"tool": "summarize"}]
    }
}
# Expected: comparison_score=0.5 (1 of 2 expected steps appeared)
```

---

## Scenario S5 — Create and use a rubric for LLM judge scoring

```python
# 1. Create a rubric
POST /api/v1/evaluation/rubrics
{
    "name": "output_correctness",
    "description": "Checks factual accuracy and completeness",
    "criteria": [
        {
            "name": "factual_accuracy",
            "scale_min": 1, "scale_max": 5,
            "examples": {
                "1": "Contains factual errors",
                "3": "Mostly correct",
                "5": "Fully accurate"
            }
        }
    ]
}
# Expected: 201, rubric_id returned, version=1

# 2. Reference rubric in eval set scorer_config
eval_set_scorer_config = {
    "llm_judge": {
        "rubric_id": "<rubric_id>",
        "judge_model": "gpt-4",
        "calibration_runs": 3
    }
}
# Expected: run completes with per-criterion scores, overall_score, rationale per verdict
```

---

## Scenario S6 — Verdict immutability and audit trail

```python
# After a run, inspect a verdict
GET /api/v1/evaluation/verdicts/{verdict_id}
# Expected response includes scorer_results with:
# { "llm_judge": { "rubric_id": "uuid", "rubric_version": 1, "judge_model": "gpt-4",
#   "per_criterion_scores": {...}, "principal_id": "uuid", "timestamp": "..." } }
# Expected: NO endpoint exists to PATCH or DELETE a verdict (immutability — FR-010)
```

---

## Scenario S7 — Rubric validation rejects contradictory examples

```python
POST /api/v1/evaluation/rubrics
{
    "name": "bad_rubric",
    "criteria": [{
        "name": "quality",
        "scale_min": 1, "scale_max": 5,
        "examples": {
            "3": "This is excellent output",
            "3": "This is terrible output"  # same score, contradictory examples
        }
    }]
}
# Expected: 400 Bad Request with message identifying the contradictory criterion
```

---

## Scenario S8 — Trigger and retrieve a calibration run

```python
# 1. Start calibration
POST /api/v1/evaluation/rubrics/{rubric_id}/calibrate
{
    "judge_model": "gpt-4",
    "reference_set_id": "eval-set-uuid"
}
# Expected: 202, run_id returned, status=pending

# 2. Poll until complete
GET /api/v1/evaluation/calibration-runs/{run_id}
# Expected (completed): status=completed, calibrated=true,
#   distribution.overall.stddev < 0.2 (within variance envelope)
#   distribution.per_criterion.*.low_discrimination = false
```

---

## Scenario S9 — Calibration flags low-discrimination rubric

```python
# Reference set: 20 examples, all scored at 3 by the judge regardless of quality
# Expected calibration report: error_grade_finding=true, calibrated=false
# Expected: per_criterion.quality.low_discrimination=true
# Expected: agreement_rate near 0.0 (judge disagrees with all reference labels)
```

---

## Scenario S10 — Use a built-in rubric template

```python
# 1. List built-in templates
GET /api/v1/evaluation/rubric-templates
# Expected: exactly 6 templates listed with names:
# [correctness, helpfulness, safety, style, faithfulness, instruction_following]

# 2. Use template directly in scorer config
eval_set_scorer_config = {
    "llm_judge": {
        "rubric_id": "<correctness_template_rubric_id>",
        "judge_model": "gpt-4"
    }
}
# Expected: evaluation runs and returns verdicts using the correctness criteria
```

---

## Scenario S11 — Copy built-in template as custom rubric

```python
# 1. Get template details
GET /api/v1/evaluation/rubric-templates/helpfulness
# Expected: full rubric criteria returned

# 2. Create custom copy (POST to /rubrics with modified criteria)
POST /api/v1/evaluation/rubrics
{
    "name": "custom_helpfulness_v1",
    "criteria": [ /* modified copy of helpfulness criteria */ ]
}
# Expected: 201, new rubric with is_builtin=false, version=1
# Expected: GET /rubric-templates/helpfulness still returns original unchanged criteria
```

---

## Scenario S12 — Rubric deletion blocked when in-flight

```python
# Evaluation run in status="running" references rubric_id
DELETE /api/v1/evaluation/rubrics/{rubric_id}
# Expected: 409 Conflict with message: "Rubric is referenced by 1 in-flight evaluation run(s)"

# Archive is allowed instead:
PATCH /api/v1/evaluation/rubrics/{rubric_id}
# (via status field or via the archive semantics in DELETE becoming archive?)
# Actually: deletion of archived rubrics with no in-flight runs = 204
# Archiving while in-flight: allowed (status=archived, new runs blocked, in-flight proceed)
```

---

## Scenario S13 — Ad-hoc judge endpoint

```python
POST /api/v1/evaluation/judge
{
    "rubric_id": "<correctness_rubric_id>",
    "output": "The capital of France is Paris, a major European city.",
    "judge_model": "gpt-4"
}
# Expected: 200 within 30s p95 (SC-013)
# Expected: per_criterion_scores, overall_score, rationale, rubric_version, principal_id, timestamp
# Expected: same auth enforcement as POST /eval-sets/{id}/run
```

---

## Scenario S14 — Ad-hoc judge with judge model unavailable

```python
POST /api/v1/evaluation/judge
# Judge model service is down
# Expected: 503 Service Unavailable, clear "judge_unavailable" classification
# Expected: NO partial verdict recorded
```

---

## Scenario S15 — Pre-existing scorers produce byte-identical results (no regression)

```python
# Snapshot scores from exact_match, regex, json_schema, semantic scorers on 100-case corpus
# Deploy feature 067
# Re-run same 100-case corpus with same scorer configurations
# Expected: 100% of scores are byte-identical (FR-020, SC-010)
# Expected: no extra latency on cases that use only pre-existing scorers
```

---

## Scenario S16 — Scorer registry enumeration

```python
GET /api/v1/evaluation/scorers
# Expected: 6 scorer types listed:
# exact_match (deterministic), regex (deterministic), json_schema (deterministic),
# semantic (semantic), trajectory (trajectory), llm_judge (judge)
# Expected: no name collisions, pre-existing types still present
```

---

## Scenario S17 — Multi-agent cooperation scoring

```python
# Two-agent workflow execution: agent A (exec-uuid-001), agent B (exec-uuid-002)
# Agent A produces draft, hands off to agent B for review
eval_set_scorer_config = {
    "trajectory": {
        "cooperation_mode": true,
        "agent_execution_ids": ["exec-uuid-001", "exec-uuid-002"],
        "comparison_method": "any_order"
    }
}
# Expected: per_agent_scores[exec-uuid-001] and per_agent_scores[exec-uuid-002]
# Expected: cooperation_scores: { coordination_overhead, handoff_timeliness, redundancy, joint_path_efficiency }
```

---

## Scenario S18 — Cooperation cycle detection

```python
# Agent A → agent B → agent A → agent B without progress (cycle)
# Expected: cooperation_scores.cycle_flags = ["exec-001 → exec-002 → exec-001"]
# Expected: coordination_overhead score significantly lower due to cycle penalty
```

---

## Scenario S19 — Trajectory truncation

```python
# Execution with 15000 steps; EVALUATION_TRAJECTORY_MAX_STEPS=10000
# Expected: trajectory scored on first 10000 steps
# Expected: ScoreResult.extra["truncated"] = true, extra["original_step_count"] = 15000
# Expected: original trajectory data in execution tables untouched
```

---

## Scenario S20 — Empty trajectory scores without error

```python
# Agent execution produced zero actions
scoring_criteria = {"trajectory": {"comparison_method": "exact", "expected_steps": [...]}}
# Expected: comparison_score=0.0, no exception raised
# Expected: dimension scores = null/unscored, explicitly annotated
```

---

## Scenario S21 — Missing cost data in trajectory

```python
# Execution has no cost_data in ExecutionCheckpoint.accumulated_costs
# Expected: cost_effectiveness dimension = null (not 0.0)
# Expected: ScoreResult.extra["cost_effectiveness_unscored"] = true
# Expected: overall_score excludes cost_effectiveness from aggregation (not zero-substituted)
```

---

## Scenario S22 — Out-of-scale judge score is clamped

```python
# Judge returns factual_accuracy=7 on a 1-5 scale
# Expected: score clamped to 5.0
# Expected: ScoreResult.extra["out_of_range_clamped"] = { "factual_accuracy": {"original": 7, "clamped": 5} }
# Expected: original judge output retained in extra["raw_judge_output"]
```

---

## Scenario S23 — Malformed judge output triggers classified failure

```python
# Judge returns non-JSON or JSON missing required fields
# For transient failure (first call): retry up to EVALUATION_LLM_JUDGE_MAX_RETRIES=2 times
# After retries exhausted → permanent failure
# Expected: ScoreResult.error = "judge_failure_permanent"
# Expected: verdict recorded with status=error, failure_classification present
# Expected: NO synthetic score recorded
```

---

## Scenario S24 — Rubric archival blocks new runs but not in-flight

```python
# 1. Archive rubric while no runs are in-flight
PATCH /api/v1/evaluation/rubrics/{rubric_id}
# → 200, status=archived (or via DELETE semantics if treating archive as soft-delete)

# 2. Attempt to start a new run referencing archived rubric
POST /api/v1/evaluation/eval-sets/{id}/run
# → 409 Conflict: rubric is archived

# 3. In-flight run (started before archive) continues to completion
# → run completes normally; verdicts record rubric_version from time of run start
```

---

## Scenario S25 — Calibration report is immutable after completion

```python
# Calibration run completed_at is set
# Attempt to update fields on completed run from service layer
# Expected: CalibrationRunImmutableError raised; no DB update applied
# Expected: GET returns original completed report unchanged
```
