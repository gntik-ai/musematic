# Research: AgentOps Lifecycle Management

**Phase 0 — Research Output**  
**Date**: 2026-04-14  
**Feature**: 037-agentops-lifecycle

---

## Bounded Context Placement

**Decision**: New `agentops/` bounded context under `apps/control-plane/src/platform/`, following identical structure to all other 25 bounded contexts.

**Rationale**: No `agentops/` context exists yet — this is fully greenfield. The existing contexts provide all the foundational data this feature orchestrates (trust, evaluation, fleet, analytics). The `agentops/` context is a pure orchestration layer that reads from these contexts via their internal service interfaces and never touches their tables directly.

**Alternatives considered**: Extending existing `trust/` or `evaluation/` contexts — rejected because agentops lifecycle spans multiple bounded contexts and has its own entities (health scores, canary deployments, governance events, retirement workflows).

---

## Statistical Testing — Library Choice

**Decision**: Add `numpy>=1.26` and `scipy>=1.13` to `apps/control-plane/pyproject.toml`.

**Rationale**: Neither package is currently in the dependency manifest. `scipy.stats.ttest_ind` and `scipy.stats.mannwhitneyu` are the standard, well-tested implementations for parametric and non-parametric comparison. `numpy` is required as `scipy`'s array foundation. Both are lightweight, production-stable, and strictly typed (py.typed markers available for mypy).

**Statistical test selection logic** (rule-based, deterministic):
- When both samples have ≥30 observations and pass a normality screen (Shapiro-Wilk, p > 0.05): use Welch's t-test (unequal variance assumed)
- Otherwise: use Mann-Whitney U (non-parametric, no normality assumption)
- Report: test type, statistic, p-value, Cohen's d (t-test) or rank-biserial correlation (Mann-Whitney)
- Significance threshold: configurable, default p < 0.05

**Alternatives considered**:
- `pingouin` — more ergonomic but heavier; rejected to minimize dependency surface.
- `statsmodels` — more comprehensive but overkill for two-sample comparison. Rejected.
- Custom implementation — brittle for edge cases (ties, unequal sizes). Rejected.

---

## Behavioral Versioning Storage

**Decision**: New ClickHouse table `agentops_behavioral_versions` for per-revision time-series behavioral metrics.

**Rationale**: Behavioral data is a time-series with high write volume (one row per execution per revision). ClickHouse's `MergeTree` engine with partition by `toYYYYMM(measured_at)` and order by `(agent_fqn, revision_id, measured_at)` provides fast aggregation queries needed for baseline computation and trend analysis. PostgreSQL would be wrong for this workload per constitution Principle III.

**Source data**: `analytics_quality_events` and `analytics_usage_events` tables (feature 020) are the source of quality + cost data. `testing_drift_metrics` (feature 034) provides evaluation-run-level scores. The agentops context consumes these tables in ClickHouse and writes derived behavioral snapshots to the new `agentops_behavioral_versions` table.

**Baseline computation**: A revision's baseline is computed as mean + stddev per dimension over a minimum of 50 executions (configurable). Baselines are materialized into PostgreSQL (`agentops_behavioral_baselines`) for fast retrieval during regression checks.

---

## Health Score Computation — Scheduler

**Decision**: APScheduler 3.x background task running the health score computation loop, consistent with `context_engineering/` and `fleet_learning/` patterns.

**Rationale**: APScheduler is already in the project dependencies (features 022, 023, 025, 033 use it). Health score updates at configurable intervals (default 15 minutes) do not require a separate process — they run in the `agentops` runtime profile.

**Data sources per health dimension**:
- **Uptime**: heartbeat data from runtime controller Redis keys (`fleet:member:avail:{fleet_id}:{fqn}`)
- **Quality**: 30-day rolling average of `agentops_behavioral_versions.quality_score`
- **Safety**: 30-day guardrail pass rate from `trust_tier_scores` or circuit breaker event log
- **Cost efficiency**: cost-per-quality ratio from `analytics_cost_models` (feature 020)
- **Satisfaction**: human grading signals from `evaluation_human_grades` (feature 034), when available

**Missing dimension handling**: If a dimension has fewer executions than the minimum sample size, compute score from available dimensions with redistributed weights; flag the missing dimension in `agentops_health_scores.missing_dimensions`.

---

## CI/CD Gate Integration

**Decision**: Gate checks call internal service interfaces in-process (not REST calls).

**Rationale**: The constitution requires inter-context communication within the Python monolith to use in-process service interfaces, not HTTP. Gate checks call:
- **Policy conformance**: `PolicyService.evaluate_conformance(agent_fqn)`
- **Evaluation pass**: `EvalSuiteService.get_latest_agent_score(agent_fqn)`
- **Active certification**: `TrustService.is_agent_certified(agent_fqn, revision_id)`
- **No regression**: `AgentOpsService.get_active_regression_alerts(agent_fqn, revision_id)`
- **Trust tier**: `TrustService.get_agent_trust_tier(agent_fqn)`

All 5 gates run concurrently via `asyncio.gather` (no short-circuit) to produce the full gate report in a single request.

---

## Canary Traffic Routing

**Decision**: Redis key `canary:{workspace_id}:{agent_fqn}` stores canary routing configuration; the runtime controller reads this key at dispatch time.

**Rationale**: The agentops context writes canary routing config to Redis when a canary deployment starts. The runtime controller (feature 009) reads `canary:{workspace_id}:{agent_fqn}` at dispatch time to route a percentage of executions to the canary revision using a deterministic hash of the execution ID (consistent routing — same execution always goes to same revision). This approach requires no code changes to the dispatch path beyond one Redis lookup.

**Key schema**: `canary:{workspace_id}:{agent_fqn}` → JSON:
```json
{
  "canary_revision_id": "...",
  "production_revision_id": "...",
  "traffic_percentage": 10,
  "observation_window_end": "ISO8601",
  "deployment_id": "..."
}
```

**TTL**: Set to `observation_window_end + 1 hour` for automatic cleanup.

**Rollback**: Clear the Redis key to restore 100% production traffic instantly.

---

## Retirement Workflow — Dependency Detection

**Decision**: Detect dependent workflows by querying `workflow_definitions.compiled_ir` for step `agent_fqn` references in PostgreSQL.

**Rationale**: The workflow execution engine (feature 029) stores the compiled IR as JSONB in PostgreSQL. A JSONB `@>` containment query on `agent_fqn` can find all workflow definitions that reference the retiring agent. This is an infrequent, low-volume query (only runs at retirement initiation) — acceptable to run against the workflow tables directly since retirement is an operator action.

**Cross-boundary rule**: This constitutes reading from the `workflows/` bounded context tables, which violates Principle IV. **Mitigation**: Expose `WorkflowService.find_workflows_using_agent(agent_fqn)` as an internal service interface. The agentops context calls this interface, not the tables directly.

---

## Governance Events — Append-Only Audit Trail

**Decision**: `agentops_governance_events` PostgreSQL table is append-only; no UPDATE or DELETE operations ever run against it.

**Rationale**: Aligns with constitution Principle V (append-only execution journal) and the trust certification evidence immutability principle. Governance events are created once and never mutated. Querying uses `created_at` ordering with cursor pagination.

---

## Adaptation Proposal Generation — Rule-Based

**Decision**: Proposals are generated by a deterministic, rule-based analyzer from operational data patterns — not an LLM.

**Rationale**: The spec assumption explicitly states rule-based analysis. LLM-generated proposals would be non-deterministic, hard to audit, and require LLM budget. Rule-based analysis is fully auditable, which is required for human-in-the-loop approval (the reviewer must understand why a change is proposed).

**Adaptation signal rules**:
1. **Quality degradation trend**: 14-day linear regression slope < -0.005/day → propose evaluation profile adjustment
2. **Cost-quality imbalance**: cost-per-quality ratio > 2× workspace average → propose model parameter or context budget optimization
3. **Consistent failure patterns**: >20% of failures share the same error category over 7 days → propose approach text or tool selection adjustment
4. **Underutilized capabilities**: tool invocation rate < 10% of available tools over 30 days → propose tool selection refinement

---

## Kafka Topic

**Decision**: New `agentops.events` topic for all AgentOps lifecycle events.

**Rationale**: The existing `agentops.behavioral` topic (feature 033) covers fleet-level behavioral signals. A dedicated `agentops.events` topic covers lifecycle events: health score threshold crossing, regression detected, gate result, canary started/promoted/rolled-back, retirement initiated/completed, recertification triggered, adaptation proposed/approved/completed.

**Consumers**: Notification service (for alerts), trust module (for certification triggers), marketplace search (for retirement/expiry → hide from discovery), analytics (for lifecycle KPIs).
