# Data Model: AgentOps Lifecycle Management

**Phase 1 — Design Output**  
**Date**: 2026-04-14  
**Feature**: 037-agentops-lifecycle

---

## PostgreSQL Tables (SQLAlchemy models)

All models follow the project mixin order: `Base` → `UUIDMixin` → `TimestampMixin` → (optional mixins) → concrete columns.

### agentops_health_configs

Workspace-specific weight configuration for health score computation.

```python
class AgentHealthConfig(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "agentops_health_configs"

    # One config row per workspace (upserted on update)
    workspace_id: UUID (FK, unique)

    # Weights: must sum to 100.0
    weight_uptime: Numeric(5, 2)          # default 20.0
    weight_quality: Numeric(5, 2)         # default 35.0
    weight_safety: Numeric(5, 2)          # default 25.0
    weight_cost_efficiency: Numeric(5, 2) # default 10.0
    weight_satisfaction: Numeric(5, 2)    # default 10.0

    # Thresholds
    warning_threshold: Numeric(5, 2)      # default 60.0
    critical_threshold: Numeric(5, 2)     # default 40.0

    # Scoring schedule
    scoring_interval_minutes: Integer     # default 15
    min_sample_size: Integer             # default 50
    rolling_window_days: Integer         # default 30
```

### agentops_health_scores

Latest health score per agent (upserted on each computation run). Historical scores flow to ClickHouse.

```python
class AgentHealthScore(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "agentops_health_scores"

    agent_fqn: String(255)               # indexed
    workspace_id: UUID (FK, indexed)
    revision_id: UUID                    # which revision was active at score time

    # Composite
    composite_score: Numeric(5, 2)       # 0.00–100.00

    # Dimensions
    uptime_score: Numeric(5, 2) | None
    quality_score: Numeric(5, 2) | None
    safety_score: Numeric(5, 2) | None
    cost_efficiency_score: Numeric(5, 2) | None
    satisfaction_score: Numeric(5, 2) | None

    # Weights used (snapshot of config at compute time)
    weights_snapshot: JSONB              # {uptime: 20, quality: 35, ...}

    missing_dimensions: ARRAY(String)    # dimensions excluded due to insufficient data
    sample_counts: JSONB                 # {uptime: 450, quality: 380, ...}

    computed_at: DateTime(tz=True)
    observation_window_start: DateTime(tz=True)
    observation_window_end: DateTime(tz=True)

    # State flags
    below_warning: Boolean               # composite_score < warning_threshold
    below_critical: Boolean              # composite_score < critical_threshold
    insufficient_data: Boolean           # composite_score could not be computed

    # Constraint: unique (agent_fqn, workspace_id) — upsert on conflict
```

### agentops_behavioral_baselines

Materialized baseline metrics per agent revision. Computed once enough executions have accumulated.

```python
class BehavioralBaseline(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "agentops_behavioral_baselines"

    agent_fqn: String(255)
    revision_id: UUID                    # indexed — one baseline per revision
    workspace_id: UUID

    # Aggregated baseline metrics (mean ± stddev over min_sample_size executions)
    quality_mean: Float
    quality_stddev: Float
    latency_p50_ms: Float
    latency_p95_ms: Float
    latency_stddev_ms: Float
    error_rate_mean: Float
    cost_per_execution_mean: Float
    cost_per_execution_stddev: Float
    safety_pass_rate: Float

    sample_size: Integer                 # execution count used to compute baseline
    baseline_window_start: DateTime(tz=True)
    baseline_window_end: DateTime(tz=True)

    status: String                       # 'pending' | 'ready' | 'superseded'
    # 'pending' = not enough samples yet
    # 'ready' = baseline computed and valid
    # 'superseded' = a newer revision's baseline is now in use
```

### agentops_regression_alerts

Detected behavioral regressions. Active alerts block promotion.

```python
class BehavioralRegressionAlert(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "agentops_regression_alerts"

    agent_fqn: String(255)
    new_revision_id: UUID               # revision being tested
    baseline_revision_id: UUID          # revision being compared against
    workspace_id: UUID

    status: String                      # 'active' | 'resolved' | 'dismissed'

    # Statistical results
    regressed_dimensions: ARRAY(String) # ['quality', 'latency', 'cost']
    statistical_test: String            # 'welch_t_test' | 'mann_whitney_u'
    p_value: Float
    effect_size: Float                  # Cohen's d or rank-biserial
    significance_threshold: Float       # threshold used at detection time
    sample_sizes: JSONB                 # {new: 87, baseline: 312}

    detected_at: DateTime(tz=True)
    resolved_at: DateTime(tz=True) | None
    resolved_by: UUID | None            # user who resolved/dismissed
    resolution_reason: String | None

    triggered_rollback: Boolean         # true if canary was rolled back due to this alert
```

### agentops_cicd_gate_results

Record of each deployment gate check.

```python
class CiCdGateResult(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "agentops_cicd_gate_results"

    agent_fqn: String(255)
    revision_id: UUID
    workspace_id: UUID
    requested_by: UUID                  # user triggering deployment

    overall_passed: Boolean

    # Per-gate results
    policy_gate_passed: Boolean
    policy_gate_detail: JSONB          # {violations: [...]} or {}
    policy_gate_remediation: String | None

    evaluation_gate_passed: Boolean
    evaluation_gate_detail: JSONB      # {score: 0.78, threshold: 0.80, failed_cases: [...]}
    evaluation_gate_remediation: String | None

    certification_gate_passed: Boolean
    certification_gate_detail: JSONB   # {status: 'expired', expires_at: ...}
    certification_gate_remediation: String | None

    regression_gate_passed: Boolean
    regression_gate_detail: JSONB      # {alert_id: ...} or {}
    regression_gate_remediation: String | None

    trust_tier_gate_passed: Boolean
    trust_tier_gate_detail: JSONB      # {tier: 1, required: 2}
    trust_tier_gate_remediation: String | None

    evaluated_at: DateTime(tz=True)
    evaluation_duration_ms: Integer
```

### agentops_canary_deployments

Canary deployment configuration and lifecycle tracking.

```python
class CanaryDeployment(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "agentops_canary_deployments"

    agent_fqn: String(255)
    production_revision_id: UUID
    canary_revision_id: UUID
    workspace_id: UUID
    initiated_by: UUID

    # Configuration
    traffic_percentage: Integer         # 1–50
    observation_window_hours: Float     # minimum 1.0
    quality_tolerance_pct: Float        # e.g., 5.0 = allow up to 5% worse
    latency_tolerance_pct: Float
    error_rate_tolerance_pct: Float
    cost_tolerance_pct: Float

    # State machine
    status: String
    # 'active' | 'auto_promoted' | 'auto_rolled_back' | 'manually_promoted'
    # | 'manually_rolled_back' | 'completed'

    started_at: DateTime(tz=True)
    observation_ends_at: DateTime(tz=True)
    completed_at: DateTime(tz=True) | None

    # Outcome
    promoted_at: DateTime(tz=True) | None
    rolled_back_at: DateTime(tz=True) | None
    rollback_reason: String | None      # metric that triggered rollback
    manual_override_by: UUID | None
    manual_override_reason: String | None

    # Latest metric snapshot (updated by monitoring task)
    latest_metrics_snapshot: JSONB | None
```

### agentops_retirement_workflows

Lifecycle process for retiring a degraded or non-compliant agent.

```python
class RetirementWorkflow(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "agentops_retirement_workflows"

    agent_fqn: String(255)
    revision_id: UUID                   # revision being retired
    workspace_id: UUID

    trigger_reason: String              # 'sustained_degradation' | 'certification_expiry'
                                        # | 'policy_non_compliance' | 'operator_initiated'
    trigger_detail: JSONB               # e.g., {consecutive_intervals: 6, threshold: 40.0}

    # State machine
    status: String
    # 'initiated' | 'grace_period' | 'retired' | 'halted'

    # Dependency impact
    dependent_workflows: JSONB          # [{workflow_id, workflow_name, owner_user_id}, ...]
    notifications_sent_at: DateTime(tz=True) | None

    # Grace period
    grace_period_days: Integer          # default 14
    grace_period_starts_at: DateTime(tz=True)
    grace_period_ends_at: DateTime(tz=True)

    # Completion
    retired_at: DateTime(tz=True) | None
    halted_at: DateTime(tz=True) | None
    halted_by: UUID | None
    halt_reason: String | None
    high_impact_flag: Boolean           # true if agent is sole provider of any workflow
    operator_confirmed: Boolean         # required true for high_impact_flag=true
```

### agentops_governance_events

Append-only audit trail. Never updated or deleted.

```python
class GovernanceEvent(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "agentops_governance_events"

    agent_fqn: String(255)              # indexed
    workspace_id: UUID                   # indexed
    actor: String(255)                   # user_id or 'system'

    event_type: String
    # 'recertification_triggered' | 'certifier_notified' | 'grace_period_started'
    # | 'recertification_completed' | 'certification_expired'
    # | 'retirement_initiated' | 'retirement_completed' | 'retirement_halted'
    # | 'canary_started' | 'canary_promoted' | 'canary_rolled_back'
    # | 'gate_check_passed' | 'gate_check_failed'
    # | 'regression_detected' | 'regression_resolved'
    # | 'adaptation_proposed' | 'adaptation_approved' | 'adaptation_rejected'
    # | 'adaptation_promoted' | 'adaptation_failed'
    # | 'health_score_warning' | 'health_score_critical'

    trigger_reason: String | None       # why this event occurred
    related_entity_type: String | None  # 'canary_deployment' | 'retirement_workflow' | ...
    related_entity_id: UUID | None      # FK to the related entity

    payload: JSONB                       # event-specific detail

    # Immutable timestamp
    created_at: DateTime(tz=True)       # set at insert; no updated_at
```

### agentops_adaptation_proposals

Self-improvement pipeline proposals and their lifecycle.

```python
class AdaptationProposal(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "agentops_adaptation_proposals"

    agent_fqn: String(255)
    current_revision_id: UUID
    workspace_id: UUID
    triggered_by: UUID                  # operator who initiated adaptation

    # Analysis signals that led to this proposal
    analysis_signals: JSONB
    # {quality_trend_slope: -0.012, cost_quality_ratio: 3.2, failure_patterns: [...]}

    # Proposed adjustments
    adjustments: JSONB
    # [{type: 'context_profile', field: 'max_tokens', from: 8192, to: 4096, rationale: '...'},
    #  {type: 'approach_text', from: '...', to: '...', rationale: '...'}]

    # Decision workflow
    status: String
    # 'proposed' | 'approved' | 'rejected' | 'candidate_created' | 'testing' | 'promoted' | 'failed'

    reviewed_by: UUID | None
    review_decision: String | None      # 'approved' | 'rejected'
    review_reason: String | None
    reviewed_at: DateTime(tz=True) | None

    # Revision candidate (if approved)
    candidate_revision_id: UUID | None
    ate_run_id: UUID | None             # ATE run that tested the candidate
    ate_result: String | None           # 'passed' | 'failed'

    proposed_at: DateTime(tz=True)
    completed_at: DateTime(tz=True) | None
```

---

## ClickHouse Table

### agentops_behavioral_versions

Time-series of per-execution behavioral metrics keyed by agent revision. Used for baseline computation and regression analysis.

```sql
CREATE TABLE agentops_behavioral_versions (
    workspace_id       UUID,
    agent_fqn          String,
    revision_id        UUID,
    execution_id       UUID,
    measured_at        DateTime64(3, 'UTC'),

    -- Quality
    quality_score      Float32,         -- eval aggregate score, null if no eval

    -- Latency
    execution_duration_ms Float32,

    -- Cost
    cost_usd           Float32,
    input_tokens       UInt32,
    output_tokens      UInt32,

    -- Safety
    safety_passed      UInt8,           -- 1 = all guardrails passed, 0 = any failed

    -- Self-correction
    correction_iterations UInt8,        -- 0 if no self-correction
    converged          UInt8            -- 1 = converged, 0 = budget_exceeded
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(measured_at)
ORDER BY (workspace_id, agent_fqn, revision_id, measured_at)
SETTINGS index_granularity = 8192;
```

---

## State Transitions

### CanaryDeployment.status

```
active
  ├─ observation_window_ends + metrics OK → auto_promoted
  ├─ metric threshold breach → auto_rolled_back
  └─ manual action:
       ├─ operator promote → manually_promoted
       └─ operator rollback → manually_rolled_back
auto_promoted / auto_rolled_back / manually_promoted / manually_rolled_back → completed
```

### RetirementWorkflow.status

```
initiated → grace_period → retired
                        └─ operator halt → halted
```

### BehavioralBaseline.status

```
pending (insufficient samples)
  └─ sample_size >= min_sample_size → ready
ready
  └─ new revision baseline computed → superseded
```

### AdaptationProposal.status

```
proposed
  ├─ human approved → approved → candidate_created → testing
  │                                                    ├─ ATE passes → promoted
  │                                                    └─ ATE fails → failed
  └─ human rejected → rejected
```

---

## Kafka Event Schema

All events published to `agentops.events` topic use the existing `EventEnvelope` with `event_type` from the `GovernanceEvent.event_type` enum. Key: `agent_fqn`.

Example payload for `regression_detected`:
```json
{
  "agent_fqn": "finance-ops:kyc-verifier",
  "revision_id": "...",
  "workspace_id": "...",
  "regressed_dimensions": ["quality", "latency"],
  "p_value": 0.0031,
  "effect_size": 0.42,
  "statistical_test": "welch_t_test"
}
```
