# Data Model: Trajectory Evaluation and LLM-as-Judge Formalization

**Feature**: 067-trajectory-judge-evaluation  
**Date**: 2026-04-19  
**Migration**: `054_trajectory_evaluation_schema.py` (down_revision: `053_mcp_integration`)

## Overview

This feature adds 2 new PostgreSQL tables and 2 new enum types. All existing tables are untouched (FR-021 backward-compatibility). Expected trajectory data leverages the existing `BenchmarkCase.scoring_criteria JSONB` column.

---

## New Enums

### `rubric_status`
```sql
CREATE TYPE rubric_status AS ENUM ('active', 'archived');
```
- `active`: Rubric is usable for new evaluations
- `archived`: Rubric is soft-deleted; new evaluations cannot reference it; in-flight runs proceed on archived version

### `calibration_run_status`
```sql
CREATE TYPE calibration_run_status AS ENUM ('pending', 'running', 'completed', 'failed');
```

---

## New Tables

### `evaluation_rubrics`

Stores formal rubric definitions used by the LLM-as-Judge scorer. Built-in templates are loaded as `is_builtin=true` records at startup from YAML files.

```sql
CREATE TABLE evaluation_rubrics (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID        REFERENCES workspaces(id) ON DELETE CASCADE,
    name            TEXT        NOT NULL,
    description     TEXT        NOT NULL DEFAULT '',
    criteria        JSONB       NOT NULL,  -- list[CriterionDefinition]
    version         INTEGER     NOT NULL DEFAULT 1,
    is_builtin      BOOLEAN     NOT NULL DEFAULT false,
    status          rubric_status NOT NULL DEFAULT 'active',
    created_by      UUID        REFERENCES users(id) ON DELETE SET NULL,
    deleted_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_evaluation_rubrics_workspace_id ON evaluation_rubrics (workspace_id);
CREATE INDEX ix_evaluation_rubrics_status ON evaluation_rubrics (status);
CREATE INDEX ix_evaluation_rubrics_is_builtin ON evaluation_rubrics (is_builtin);
CREATE UNIQUE INDEX uq_evaluation_rubrics_builtin_name
    ON evaluation_rubrics (name) WHERE is_builtin = true;
```

**`criteria` JSONB schema** (`list[CriterionDefinition]`):
```json
[
  {
    "name": "factual_accuracy",
    "description": "Whether the output contains factually correct statements",
    "scale_min": 1,
    "scale_max": 5,
    "examples": {
      "1": "Contains factual errors that mislead the reader",
      "3": "Mostly correct with minor inaccuracies",
      "5": "Fully accurate and verifiable against sources"
    }
  }
]
```

Constraints enforced at application layer (FR-008):
- `name` must be unique within a workspace (excluding builtins)
- Each criterion `examples` must not contain contradictory examples at the same scale point
- `scale_min < scale_max`

**Rubric versioning**: `version` is incremented by `RubricService.update_rubric()` on any change to `criteria`, `name`, or `description`. Verdicts reference the `version` value at time of scoring.

---

### `evaluation_calibration_runs`

Stores immutable calibration reports. A run assesses how well a rubric + judge combination performs against a labelled reference set.

```sql
CREATE TABLE evaluation_calibration_runs (
    id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    rubric_id             UUID        NOT NULL REFERENCES evaluation_rubrics(id) ON DELETE RESTRICT,
    rubric_version        INTEGER     NOT NULL,
    judge_model           TEXT        NOT NULL,
    reference_set_id      TEXT        NOT NULL,  -- Opaque identifier for the reference set (eval_set_id or fixture id)
    status                calibration_run_status NOT NULL DEFAULT 'pending',
    distribution          JSONB,      -- CalibrationReport, set on completion
    agreement_rate        FLOAT,      -- Fraction of verdicts within expected range
    calibrated            BOOLEAN,    -- true only when status=completed and no error-grade finding
    error_grade_finding   BOOLEAN     NOT NULL DEFAULT false,
    started_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at          TIMESTAMPTZ,
    created_by            UUID        REFERENCES users(id) ON DELETE SET NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_evaluation_calibration_runs_rubric_id ON evaluation_calibration_runs (rubric_id);
CREATE INDEX ix_evaluation_calibration_runs_status ON evaluation_calibration_runs (status);
```

**`distribution` JSONB schema** (`CalibrationReport`):
```json
{
  "overall": {
    "min": 1.5,
    "max": 4.8,
    "mean": 3.2,
    "stddev": 0.9,
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
}
```

**Immutability**: `completed_at` is set once. After that, `CalibrationService.update_calibration_run()` raises `CalibrationRunImmutableError` if any field change is attempted.

---

## No Changes to Existing Tables

| Table | Change | Rationale |
|---|---|---|
| `evaluation_judge_verdicts` | None | `scorer_results JSONB` already stores rubric_version + judge_model via `extra` field in ScoreResult |
| `evaluation_benchmark_cases` | None | Expected trajectory stored as `scoring_criteria["trajectory"]["expected_steps"]` JSONB |
| `evaluation_eval_sets` | None | Rubric referenced by `scorer_config["llm_judge"]["rubric_id"]` JSONB |
| All other tables | None | FR-021: additive only |

---

## Existing Tables (Reference)

These tables are already implemented and are consumed by this feature without modification:

| Table | Used By |
|---|---|
| `evaluation_eval_sets` | Rubric in-flight guard: query `scorer_config` for `rubric_id` references |
| `evaluation_runs` | In-flight guard: `status = 'running'` check before rubric deletion |
| `evaluation_judge_verdicts` | Verdict audit: existing structure holds `scorer_results JSONB` which includes rubric_version |
| `execution_events` | TrajectoryScorer: reads action sequence |
| `execution_task_plan_records` | TrajectoryScorer: reads tool choices |
| `execution_reasoning_trace_records` | TrajectoryScorer: reads reasoning coherence |

---

## YAML Rubric Template Files

Not DB tables — version-controlled files loaded at startup:

```
apps/control-plane/src/platform/evaluation/rubrics/
├── correctness.yaml
├── helpfulness.yaml
├── safety.yaml
├── style.yaml
├── faithfulness.yaml
└── instruction_following.yaml
```

**YAML format** (example — `correctness.yaml`):
```yaml
name: correctness
description: Evaluates factual accuracy and completeness of agent outputs
criteria:
  - name: factual_accuracy
    description: Whether stated facts are correct and verifiable
    scale_min: 1
    scale_max: 5
    examples:
      1: "Contains factual errors that could mislead the reader"
      3: "Mostly correct with minor inaccuracies that do not affect main conclusions"
      5: "Fully accurate; every claim is verifiable against authoritative sources"
  - name: completeness
    description: Whether the output covers all relevant aspects of the question
    scale_min: 1
    scale_max: 5
    examples:
      1: "Missing critical information required to answer the question"
      3: "Covers the main points but omits some supporting details"
      5: "Comprehensive; all relevant aspects addressed with appropriate depth"
```

---

## Redis Keys (None New)

No new Redis keys introduced by this feature.

---

## Kafka Events (Additive)

New event types on existing `evaluation.events` topic:

| Event Type | Payload | When |
|---|---|---|
| `evaluation.rubric.created` | `RubricCreatedPayload(rubric_id, workspace_id, name, version)` | Rubric saved |
| `evaluation.rubric.updated` | `RubricUpdatedPayload(rubric_id, old_version, new_version)` | Rubric criteria changed |
| `evaluation.rubric.archived` | `RubricArchivedPayload(rubric_id, workspace_id)` | Rubric soft-deleted |
| `evaluation.calibration.started` | `CalibrationStartedPayload(run_id, rubric_id, rubric_version)` | Calibration triggered |
| `evaluation.calibration.completed` | `CalibrationCompletedPayload(run_id, rubric_id, calibrated, error_grade_finding)` | Calibration finished |
| `evaluation.judge.adhoc` | `AdHocJudgePayload(rubric_id, judge_model, principal_id, duration_ms)` | Ad-hoc judge endpoint called |
