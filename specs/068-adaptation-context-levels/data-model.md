# Data Model: Agent Adaptation Pipeline and Context Engineering Levels

**Feature**: 068-adaptation-context-levels  
**Date**: 2026-04-19  
**Migration**: `055_adaptation_pipeline_and_proficiency.py` (down_revision: `054_trajectory_evaluation_schema`)

## Overview

This feature adds 4 new PostgreSQL tables, extends 1 existing table with 12 columns, adds 6 enum values to an existing enum, and creates 3 new enums. All changes are additive (FR-034, FR-035). Existing agentops adaptation behavior continues to work on historical proposals.

---

## Extended Enum

### `adaptation_proposal_status` — 6 new values added

Existing: `proposed`, `no_opportunities`, `approved`, `rejected`, `testing`, `passed`, `failed`, `promoted`

**Added**: `applied`, `rolled_back`, `expired`, `orphaned`, `stale`, `revoked`

Full state transitions (post-feature):
```
proposed ──approve──▶ approved ──apply──▶ applied ──rollback──▶ rolled_back (terminal)
   │                      │                  │
   │                  revoke approval        └──▶ (auto-outcome) remains "applied" with outcome record
   ├──reject──▶ rejected (terminal)         
   ├──TTL────▶ expired (terminal)
   ├──agent-archived──▶ orphaned (terminal)
   └──target-field-missing──▶ stale (terminal)

Historical compatibility (existing proposals pre-feature-068):
proposed ──▶ testing ──▶ passed ──▶ promoted (treated as "applied")
         └─▶ failed (terminal, treated as "rolled_back")
```

---

## New Enums

### `proficiency_level`
```sql
CREATE TYPE proficiency_level AS ENUM (
    'undetermined', 'novice', 'competent', 'advanced', 'expert'
);
```
Ordered; queries of form "level ≤ competent" use position ordinal.

### `outcome_classification`
```sql
CREATE TYPE outcome_classification AS ENUM (
    'improved', 'no_change', 'regressed', 'inconclusive'
);
```

### `correlation_classification`
```sql
CREATE TYPE correlation_classification AS ENUM (
    'strong_positive', 'moderate_positive', 'weak',
    'moderate_negative', 'strong_negative', 'inconclusive'
);
```

### `snapshot_type`
```sql
CREATE TYPE snapshot_type AS ENUM ('pre_apply', 'post_apply');
```

---

## Existing Table Extensions

### `agentops_adaptation_proposals` — 12 new columns

```sql
ALTER TABLE agentops_adaptation_proposals
  ADD COLUMN expected_improvement JSONB,
  ADD COLUMN pre_apply_snapshot_key TEXT,
  ADD COLUMN applied_at TIMESTAMPTZ,
  ADD COLUMN applied_by UUID REFERENCES users(id) ON DELETE SET NULL,
  ADD COLUMN rolled_back_at TIMESTAMPTZ,
  ADD COLUMN rolled_back_by UUID REFERENCES users(id) ON DELETE SET NULL,
  ADD COLUMN rollback_reason TEXT,
  ADD COLUMN expires_at TIMESTAMPTZ,
  ADD COLUMN revoked_at TIMESTAMPTZ,
  ADD COLUMN revoked_by UUID REFERENCES users(id) ON DELETE SET NULL,
  ADD COLUMN revoke_reason TEXT,
  ADD COLUMN signal_source VARCHAR(32) DEFAULT 'manual';

-- One open proposal per agent constraint (FR-012)
CREATE UNIQUE INDEX ux_agentops_adaptation_one_open_per_agent
  ON agentops_adaptation_proposals (workspace_id, agent_fqn)
  WHERE status IN ('proposed', 'approved', 'applied');

CREATE INDEX ix_agentops_adaptation_expires_at
  ON agentops_adaptation_proposals (expires_at)
  WHERE expires_at IS NOT NULL AND status = 'proposed';

CREATE INDEX ix_agentops_adaptation_applied_at
  ON agentops_adaptation_proposals (applied_at)
  WHERE applied_at IS NOT NULL AND status = 'applied';
```

**`expected_improvement` JSONB schema** (set at propose-time):
```json
{
  "metric": "quality_score",
  "baseline_value": 0.62,
  "target_value": 0.75,
  "target_delta": 0.13,
  "observation_window_hours": 72,
  "measurement_method": "avg_over_window"
}
```

**`signal_source`** values: `manual` (operator-triggered), `automatic` (signal-driven), `scheduled` (periodic analyzer run).

---

## New Tables

### `agentops_adaptation_snapshots`

Stores pre-apply and post-apply configuration snapshots for byte-identical rollback.

```sql
CREATE TABLE agentops_adaptation_snapshots (
    id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    proposal_id           UUID        NOT NULL REFERENCES agentops_adaptation_proposals(id) ON DELETE CASCADE,
    snapshot_type         snapshot_type NOT NULL,
    configuration_hash    VARCHAR(64) NOT NULL,
    configuration         JSONB       NOT NULL,
    revision_id           UUID,
    retention_expires_at  TIMESTAMPTZ NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_agentops_adaptation_snapshots_proposal ON agentops_adaptation_snapshots (proposal_id);
CREATE INDEX ix_agentops_adaptation_snapshots_retention ON agentops_adaptation_snapshots (retention_expires_at);
```

**`configuration` JSONB schema** (for pre-apply snapshot):
```json
{
  "profile_fields": {
    "display_name": "...",
    "purpose": "...",
    "approach": "...",
    "role_types": ["..."],
    "tags": ["..."],
    "visibility_agents": [],
    "visibility_tools": [],
    "mcp_server_refs": []
  },
  "active_revision_id": "uuid"
}
```

**`configuration_hash`**: SHA-256 of canonical JSON of `configuration`. Byte-identity verified by hash match on rollback.

**Retention**: rows with `retention_expires_at < now()` are deleted by a scanner (default 30-day retention per `AgentOpsSettings.adaptation_rollback_retention_days`).

---

### `agentops_adaptation_outcomes`

Immutable post-apply outcome measurement.

```sql
CREATE TABLE agentops_adaptation_outcomes (
    id                        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    proposal_id               UUID        NOT NULL REFERENCES agentops_adaptation_proposals(id) ON DELETE CASCADE,
    observation_window_start  TIMESTAMPTZ NOT NULL,
    observation_window_end    TIMESTAMPTZ NOT NULL,
    expected_delta            JSONB       NOT NULL,
    observed_delta            JSONB       NOT NULL,
    classification            outcome_classification NOT NULL,
    variance_annotation       JSONB,
    measured_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX ux_agentops_adaptation_outcomes_proposal ON agentops_adaptation_outcomes (proposal_id);
CREATE INDEX ix_agentops_adaptation_outcomes_classification ON agentops_adaptation_outcomes (classification);
```

**Immutability**: enforced at service layer — `outcome_service.persist_outcome()` raises `OutcomeImmutableError` if a record already exists for the proposal.

**`observed_delta` JSONB schema**:
```json
{
  "metric": "quality_score",
  "pre_apply_value": 0.62,
  "observation_period_value": 0.71,
  "observed_delta": 0.09,
  "observed_stddev": 0.04,
  "sample_count": 127
}
```

**`variance_annotation`** (when classification = inconclusive):
```json
{
  "observed_stddev": 0.15,
  "expected_delta_magnitude": 0.13,
  "reason": "variance exceeds expected-improvement magnitude"
}
```

---

### `agentops_proficiency_assessments`

Per-agent proficiency level at a point in time. Append-only for full historical trajectory.

```sql
CREATE TABLE agentops_proficiency_assessments (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_fqn         VARCHAR(512) NOT NULL,
    workspace_id      UUID        NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    level             proficiency_level NOT NULL,
    dimension_values  JSONB       NOT NULL,
    observation_count INTEGER     NOT NULL,
    trigger           VARCHAR(32) NOT NULL,
    assessed_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_proficiency_assessments_agent_workspace ON agentops_proficiency_assessments (workspace_id, agent_fqn, assessed_at DESC);
CREATE INDEX ix_proficiency_assessments_level ON agentops_proficiency_assessments (workspace_id, level);
```

**`dimension_values` JSONB schema**:
```json
{
  "retrieval_accuracy": 0.82,
  "instruction_adherence": 0.78,
  "context_coherence": 0.71,
  "aggregate_score": 0.77,
  "per_dimension_observation_counts": {
    "retrieval_accuracy": 42,
    "instruction_adherence": 35,
    "context_coherence": 28
  }
}
```

**`trigger`** values: `scheduled` (periodic recompute), `manual` (on-demand API call), `signal_event` (context-quality regression detected), `initial` (first assessment).

**"Undetermined" handling**: when `observation_count < min_observations_per_dimension` for any dimension, `level = 'undetermined'` and `dimension_values` records which dimensions were missing.

**Dwell-time enforcement**: the scheduler appends a new row only when (a) computed level differs from latest row's level AND (b) latest row's `assessed_at < now() - dwell_time_hours`, OR when the computed level matches the latest row's level (routine refresh).

---

### `context_engineering_correlation_results`

Cached per-agent correlation coefficients.

```sql
CREATE TABLE context_engineering_correlation_results (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id        UUID        NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    agent_fqn           VARCHAR(512) NOT NULL,
    dimension           VARCHAR(64) NOT NULL,
    performance_metric  VARCHAR(64) NOT NULL,
    window_start        TIMESTAMPTZ NOT NULL,
    window_end          TIMESTAMPTZ NOT NULL,
    coefficient         FLOAT,
    classification      correlation_classification NOT NULL,
    data_point_count    INTEGER     NOT NULL,
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_correlation_results_agent_workspace
    ON context_engineering_correlation_results (workspace_id, agent_fqn, computed_at DESC);
CREATE INDEX ix_correlation_results_classification
    ON context_engineering_correlation_results (workspace_id, classification);
CREATE UNIQUE INDEX ux_correlation_results_latest
    ON context_engineering_correlation_results
    (workspace_id, agent_fqn, dimension, performance_metric, window_end);
```

**`dimension`** values: one of the 6 context-quality dimensions (`retrieval_accuracy`, `instruction_adherence`, `context_coherence`, etc.) or `aggregate`.

**`performance_metric`** values: `quality_score`, `task_success_rate`, `execution_duration_ms`, `cost_per_execution`, `self_correction_loops`.

**`coefficient`**: NULL when `classification = 'inconclusive'` (insufficient data).

**Recomputation**: daily scheduler; unique index on `(workspace_id, agent_fqn, dimension, performance_metric, window_end)` enforces one row per window.

---

## No Changes to These Tables

| Table | Used By |
|---|---|
| `registry_agent_profiles` | Read for current config; mutated by `registry_service.update_agent_profile()` during apply — no schema change |
| `registry_agent_revisions` | Read for revision activation during apply/rollback — no schema change |
| `analytics_usage_events` (ClickHouse) | Read for performance metrics in correlation and convergence signal — no schema change |
| `context_assembly_records` | Read for context-quality dimensions in correlation — no schema change |
| `context_drift_alerts` | Read for signal ingestion — no schema change |
| `evaluation_judge_verdicts` | Read for convergence signal (self-correction loops via JudgeVerdict.scorer_results) — no schema change |

---

## Redis Keys (None New)

No new Redis keys. Existing `cache:*` patterns unchanged.

---

## Kafka Events (Additive on `agentops.events` topic)

Existing events preserved: `agentops.adaptation.proposed`, `agentops.adaptation.reviewed`, `agentops.adaptation.completed`.

**New events added:**

| Event Type | Payload (extends `AgentOpsLifecyclePayload`) | When |
|---|---|---|
| `agentops.adaptation.applied` | `proposal_id, applied_by, pre_apply_snapshot_id, post_apply_snapshot_id` | Proposal applied to live agent |
| `agentops.adaptation.rolled_back` | `proposal_id, rolled_back_by, reason, restored_snapshot_id` | Applied proposal rolled back |
| `agentops.adaptation.outcome_recorded` | `proposal_id, classification, observed_delta, expected_delta` | Post-apply outcome measured |
| `agentops.adaptation.approval_revoked` | `proposal_id, revoked_by, reason` | Reviewer revoked prior approval |
| `agentops.adaptation.expired` | `proposal_id, created_at, ttl_hours` | TTL scanner expired a proposal |
| `agentops.adaptation.orphaned` | `proposal_id, agent_fqn, reason` | Orphan scanner detected agent archive/delete |
| `agentops.adaptation.stale` | `proposal_id, target_field_missing` | Apply-time validation found removed field |
| `agentops.adaptation.ingestion_degraded` | `source, consecutive_failure_count, recovery_attempts_remaining` | Signal source unreachable |
| `agentops.proficiency.assessed` | `agent_fqn, level, previous_level, trigger` | Proficiency row appended |
| `context_engineering.correlation.computed` (on `context_engineering.events` topic) | `agent_fqn, dimension, performance_metric, coefficient, classification` | Correlation recomputed |
| `context_engineering.correlation.strong_negative` | `agent_fqn, dimension, coefficient, data_point_count` | Strong-negative flagged for triage |
