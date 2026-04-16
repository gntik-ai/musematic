# Research: Simulation and Digital Twins

**Feature**: 040-simulation-digital-twins  
**Phase**: 0 (Research)  
**Date**: 2026-04-15

---

## Decision 1: SimulationControlService Client Pattern

**Decision**: Use the existing `SimulationControllerClient` in `apps/control-plane/src/platform/common/clients/simulation_controller.py` (already created by feature 012) for all gRPC calls to the Simulation Controller satellite service (port 50055).

**Rationale**: The SimulationControllerClient already wraps the 6 gRPC RPCs (`CreateSimulation`, `GetSimulation`, `ListSimulations`, `CancelSimulation`, `GetSimulationArtifacts`, `StreamSimulationEvents`). The `simulation/` bounded context is the designated consumer/coordinator for this service — it delegates pod-level execution to the Go satellite and handles control-plane state (twins, predictions, comparison, isolation policy) in Python.

**Alternatives considered**:
- Direct gRPC stub calls without a client wrapper — rejected; the client wrapper provides retry, timeout, error mapping, and connection pooling already configured in feature 012.
- Implementing simulation execution in Python — rejected; Go satellite handles Kubernetes pod lifecycle, namespace isolation, remotecommand, and NetworkPolicy. Duplicating this in Python would violate the modular architecture.

---

## Decision 2: Digital Twin Config Snapshot Source

**Decision**: Snapshot agent configuration from `RegistryServiceInterface` (feature 021) for model/tools/policies/context profile and connector wiring. Behavioral history summary fetched directly from ClickHouse `execution_metrics` aggregated views (feature 020 analytics pipeline).

**Rationale**: The registry owns agent profile + revision state. RegistryServiceInterface provides `get_agent_profile` and `get_agent_revision` as the sanctioned cross-boundary interface. ClickHouse is the OLAP analytics store used across contexts for time-series reads — reading execution_metrics directly is consistent with the fleet management (feature 033) and evaluation (feature 034) pattern.

**Alternatives considered**:
- Snapshotting directly from PostgreSQL registry tables — rejected; Constitution IV prohibits cross-boundary DB access. The service interface is the correct path.
- Fetching behavioral history via an AnalyticsServiceInterface — rejected; analytics doesn't expose a time-series query interface. Direct ClickHouse reads for aggregated metrics are the established pattern (features 033, 034 both read directly from ClickHouse analytics tables).

---

## Decision 3: Behavioral Prediction Algorithm

**Decision**: Use `scipy.stats.linregress` for linear trend fitting over 30-day metric history from ClickHouse; compute confidence intervals from regression residuals; apply load scaling via linear extrapolation (quality degrades proportionally to load based on historical scaling observations). No machine learning models in v1.

**Rationale**: The spec assumption explicitly states "statistical methods, not machine learning models (v1 scope)." scipy is already in the stack (features 037, 039). Linear regression provides interpretable trend indicators (improving/degrading/volatile) and confidence intervals. For condition modifiers (load scaling), historical patterns from ClickHouse provide the scaling coefficients.

**Alternatives considered**:
- ARIMA time-series forecasting — rejected; overcomplicated for v1, adds statsmodels dependency.
- Fixed rule-based prediction — rejected; doesn't capture trends and provides no confidence intervals.
- Machine learning models (Prophet, LSTM) — explicitly out of scope per spec.

**Insufficient data threshold**: < 7 days of execution history → return `insufficient_data` status (per spec FR-016).

---

## Decision 4: Simulation Isolation Enforcement Approach

**Decision**: Translate `SimulationIsolationPolicy` rules into a temporary enforcement bundle and pass them through the existing `PolicyServiceInterface` (feature 028) `ToolGatewayService` by injecting the isolation rules as a simulation-scoped policy. The `IsolationEnforcer` in the `simulation/isolation/` sub-module translates isolation policy declarations into policy enforcement rules and registers them for the duration of the simulation run. Connector stubbing responses are stored in policy enforcement context. Isolation events are published on `simulation.events`.

**Rationale**: The ToolGatewayService (feature 028) already performs 4-check enforcement (permission → purpose → budget → safety). Extending it with simulation isolation avoids building a parallel enforcement path. The simulation-scoped policy has workspace_id isolation and auto-expires when the simulation completes.

**Alternatives considered**:
- Building a standalone simulation-specific tool interceptor — rejected; duplicates the existing policy enforcement infrastructure.
- K8s-level only isolation (relying on SimulationController NetworkPolicy) — insufficient; spec requires action-level interception with stub responses and per-action logging.

---

## Decision 5: Comparison Statistical Significance Method

**Decision**: Use `scipy.stats.ttest_ind` (Welch's two-sample t-test, equal_var=False) to compute p-values for metric differences between two simulation runs. Significance classification: p < 0.01 → "high", p < 0.05 → "medium", p >= 0.05 → "low". Sample sizes derived from step-level metric records in simulation results.

**Rationale**: Welch's t-test is robust to unequal sample sizes and variances — appropriate when two simulations may have different run durations or step counts. scipy is already in the stack. The α = 0.05 threshold is configurable via `SIMULATION_COMPARISON_SIGNIFICANCE_ALPHA`.

**Alternatives considered**:
- Mann-Whitney U test (non-parametric) — viable but Welch's is more interpretable for normally-distributed execution metrics.
- Fixed-threshold significance (% difference only) — rejected; doesn't account for variance and produces misleading significance claims on small samples.

---

## Decision 6: Kafka Integration

**Decision**: Consume `simulation.events` topic (key: `simulation_id`) to receive status updates from the SimulationControlService Go satellite. Publish additional control-plane events to the same `simulation.events` topic for: `twin_created`, `twin_modified`, `prediction_completed`, `comparison_completed`, `isolation_breach_detected`. Topic already registered in the platform Kafka topics registry.

**Rationale**: The topic already exists and is consumed by `simulation coord` per the Kafka topics registry. Co-producing to the same topic (typed by `event_type`) keeps the event space coherent and avoids needing a new topic registration. Control-plane consumers (ws_hub, analytics) can subscribe once and receive all simulation-related events.

**Alternatives considered**:
- Separate `simulation.control-plane.events` topic — rejected; unnecessary topic proliferation; the existing topic with event_type filtering is sufficient.

---

## Decision 7: No New Python Packages Required

**Decision**: No new Python packages needed. All dependencies already in the established stack:
- `grpcio 1.65+` — SimulationControllerClient gRPC calls (already in stack)
- `clickhouse-connect 0.8+` — ClickHouse behavioral history queries (already in stack)
- `scipy >= 1.13` — trend regression + Welch's t-test (added in feature 037, confirmed in 039)
- `numpy >= 1.26` — metric arrays (added in feature 037)
- `redis-py 5.x` async — simulation status caching (already in stack)

**New configuration additions** to `PlatformSettings`:
```python
SIMULATION_MAX_DURATION_SECONDS: int = 1800
SIMULATION_BEHAVIORAL_HISTORY_DAYS: int = 30
SIMULATION_MIN_PREDICTION_HISTORY_DAYS: int = 7
SIMULATION_COMPARISON_SIGNIFICANCE_ALPHA: float = 0.05
SIMULATION_DEFAULT_STRICT_ISOLATION: bool = True
```
