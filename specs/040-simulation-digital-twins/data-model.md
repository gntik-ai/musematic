# Data Model: Simulation and Digital Twins

**Feature**: 040-simulation-digital-twins  
**Storage**: PostgreSQL 16 (5 tables) + Redis (simulation status cache) + ClickHouse (behavioral history reads — existing tables)

---

## PostgreSQL Tables

### 1. `simulation_runs`

Top-level simulation execution record.

```python
class SimulationRun(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "simulation_runs"

    name: Mapped[str]
    description: Mapped[str | None]
    scenario_config: Mapped[dict]     # JSONB: {inputs, duration_seconds, success_criteria, agent_fqns}
    digital_twin_ids: Mapped[list]    # JSONB: [uuid, ...] — twins used in this simulation
    status: Mapped[str]               # "provisioning" | "running" | "completed" | "cancelled" | "failed" | "timeout"
    isolation_policy_id: Mapped[UUID | None]   # FK → simulation_isolation_policies.id
    controller_run_id: Mapped[str | None]      # Run ID from SimulationControlService
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    results: Mapped[dict | None]      # JSONB: {execution_metrics, agent_outputs, errors, isolation_events_count}
    initiated_by: Mapped[UUID]        # FK → auth.users.id

    __table_args__ = (
        Index("ix_simulation_runs_workspace_status", "workspace_id", "status"),
        CheckConstraint(
            "status IN ('provisioning', 'running', 'completed', 'cancelled', 'failed', 'timeout')",
            name="ck_run_status"
        ),
    )
```

---

### 2. `simulation_digital_twins`

Versioned point-in-time snapshot of a production agent's configuration and behavioral summary.

```python
class DigitalTwin(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "simulation_digital_twins"

    source_agent_fqn: Mapped[str]           # FQN of the snapshotted production agent
    source_revision_id: Mapped[UUID | None] # Registry revision that was snapshotted
    version: Mapped[int]                    # 1-based; incremented on each modification
    parent_twin_id: Mapped[UUID | None]     # FK → simulation_digital_twins.id (previous version)
    config_snapshot: Mapped[dict]           # JSONB: {model, tools, policies, context_profile, connectors}
    behavioral_history_summary: Mapped[dict] # JSONB: {period_days, avg_quality_score, avg_response_time_ms,
                                            #          avg_error_rate, quality_trend, response_trend}
    modifications: Mapped[list]             # JSONB: [{field, old_value, new_value, description}]
    is_active: Mapped[bool]                 # Default True; set False when superseded by new version

    __table_args__ = (
        Index("ix_digital_twins_agent_fqn", "source_agent_fqn"),
        Index("ix_digital_twins_workspace_active", "workspace_id", "is_active"),
        CheckConstraint("version >= 1", name="ck_twin_version_positive"),
    )
```

---

### 3. `simulation_behavioral_predictions`

Forecasted performance metrics for a digital twin under specified conditions.

```python
class BehavioralPrediction(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "simulation_behavioral_predictions"

    digital_twin_id: Mapped[UUID]     # FK → simulation_digital_twins.id
    condition_modifiers: Mapped[dict] # JSONB: {load_factor: float, config_changes: {}}
    predicted_metrics: Mapped[dict]   # JSONB: {
                                      #   quality_score: {value, lower_ci, upper_ci, trend},
                                      #   response_time_ms: {value, lower_ci, upper_ci, trend},
                                      #   error_rate: {value, lower_ci, upper_ci, trend}
                                      # }
    confidence_level: Mapped[str]     # "high" | "medium" | "low" | "insufficient_data"
    history_days_used: Mapped[int]    # Actual days of history available when prediction ran
    accuracy_report: Mapped[dict | None]  # JSONB: filled after comparison — {metric, predicted, actual, accuracy_pct}
    status: Mapped[str]               # "pending" | "completed" | "insufficient_data" | "failed"

    __table_args__ = (
        Index("ix_behavioral_predictions_twin_id", "digital_twin_id"),
        CheckConstraint(
            "confidence_level IN ('high', 'medium', 'low', 'insufficient_data')",
            name="ck_confidence_level"
        ),
        CheckConstraint(
            "status IN ('pending', 'completed', 'insufficient_data', 'failed')",
            name="ck_prediction_status"
        ),
    )
```

---

### 4. `simulation_isolation_policies`

Declares which actions are blocked, stubbed, or permitted within a simulation.

```python
class SimulationIsolationPolicy(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "simulation_isolation_policies"

    name: Mapped[str]
    description: Mapped[str | None]
    blocked_actions: Mapped[list]    # JSONB: [{action_type, severity: "critical|warning"}]
    stubbed_actions: Mapped[list]    # JSONB: [{action_type, stub_response_template: {}}]
    permitted_read_sources: Mapped[list]  # JSONB: [{source_type, source_id}]
    is_default: Mapped[bool]         # Default False; workspace-level default policy
    halt_on_critical_breach: Mapped[bool]  # Default True

    __table_args__ = (
        Index("ix_isolation_policies_workspace_default", "workspace_id", "is_default"),
    )
```

---

### 5. `simulation_comparison_reports`

Structured comparison of two simulation runs, or a simulation vs. production baseline.

```python
class SimulationComparisonReport(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "simulation_comparison_reports"

    comparison_type: Mapped[str]             # "simulation_vs_simulation" | "simulation_vs_production" | "prediction_vs_actual"
    primary_run_id: Mapped[UUID]             # FK → simulation_runs.id
    secondary_run_id: Mapped[UUID | None]    # FK → simulation_runs.id (if sim-vs-sim)
    production_baseline_period: Mapped[dict | None]  # JSONB: {start_date, end_date} (if sim-vs-production)
    prediction_id: Mapped[UUID | None]       # FK → simulation_behavioral_predictions.id (if prediction-vs-actual)
    metric_differences: Mapped[list]         # JSONB: [{metric, primary_value, secondary_value, delta,
                                             #           direction: "better|worse|unchanged",
                                             #           significance: "high|medium|low"}]
    overall_verdict: Mapped[str]             # "primary_better" | "secondary_better" | "equivalent" | "inconclusive"
    status: Mapped[str]                      # "pending" | "completed" | "failed"
    compatible: Mapped[bool]                 # True if comparison is valid; False if incompatible
    incompatibility_reasons: Mapped[list]    # JSONB: [reason_string] (empty if compatible)

    __table_args__ = (
        Index("ix_comparison_reports_primary_run_id", "primary_run_id"),
        CheckConstraint(
            "comparison_type IN ('simulation_vs_simulation', 'simulation_vs_production', 'prediction_vs_actual')",
            name="ck_comparison_type"
        ),
        CheckConstraint(
            "overall_verdict IN ('primary_better', 'secondary_better', 'equivalent', 'inconclusive')",
            name="ck_overall_verdict"
        ),
        CheckConstraint(
            "status IN ('pending', 'completed', 'failed')",
            name="ck_comparison_status"
        ),
    )
```

---

## Redis Hot State

```
sim:status:{run_id}
  Type: String (JSON)
  Value: {status, progress_pct, current_step, last_updated}
  TTL: 24h after simulation completion
  Used: Real-time status polling fallback (primary status via WebSocket)
```

---

## ClickHouse (Read-Only Access)

The simulation bounded context reads from existing ClickHouse tables written by the analytics pipeline (feature 020):

```sql
-- Behavioral history for prediction (reads from analytics materialized views)
-- Table: execution_metrics_daily (written by analytics pipeline)
-- Columns used: agent_fqn, workspace_id, date, avg_quality_score,
--               avg_response_time_ms, avg_error_rate, execution_count

-- Query pattern for behavioral history:
SELECT date, avg_quality_score, avg_response_time_ms, avg_error_rate, execution_count
FROM execution_metrics_daily
WHERE agent_fqn = {fqn} AND workspace_id = {workspace_id}
  AND date >= today() - {SIMULATION_BEHAVIORAL_HISTORY_DAYS}
ORDER BY date ASC
```

---

## Kafka Event Schema

**Topic**: `simulation.events`
**Key**: `simulation_id` (string UUID)

Control-plane event types added by this feature:
```json
{
  "event_id": "uuid",
  "event_type": "twin_created|twin_modified|prediction_completed|comparison_completed|isolation_breach_detected|simulation_run_created|simulation_run_cancelled",
  "simulation_id": "uuid | null",
  "workspace_id": "uuid",
  "actor_id": "uuid | null",
  "timestamp": "ISO8601",
  "payload": {}
}
```

---

## State Transitions

### SimulationRun.status
```
provisioning → running       (SimulationControlService confirms execution started)
running → completed          (all agents complete successfully)
running → failed             (execution error)
running → timeout            (exceeds SIMULATION_MAX_DURATION_SECONDS)
running → cancelled          (operator requests cancellation)
```

### BehavioralPrediction.status
```
pending → completed          (ClickHouse query + regression complete)
pending → insufficient_data  (< SIMULATION_MIN_PREDICTION_HISTORY_DAYS)
pending → failed             (ClickHouse unavailable or computation error)
```

### SimulationComparisonReport.status
```
pending → completed          (Welch's t-test complete, metrics compared)
pending → failed             (one or both simulation runs not in 'completed' status)
```
