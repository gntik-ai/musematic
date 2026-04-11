# Research: Analytics and Cost Intelligence

**Feature**: 020-analytics-cost-intelligence  
**Date**: 2026-04-11  
**Phase**: Phase 0 — Research & Decisions

## Decision Log

### Decision 1: ClickHouse as Primary Analytics Store (No PostgreSQL for Analytics Data)

- **Decision**: All usage events, rollups, and analytics query results are stored in **ClickHouse**, not PostgreSQL. The only PostgreSQL table in this bounded context is `analytics_cost_models` (pricing configuration — a small, rarely-updated CRUD table that benefits from ACID semantics).
- **Rationale**: Constitution §III is explicit: "ClickHouse: All time-series analytics and aggregations. Never compute rollups in PostgreSQL." Usage events are high-volume, time-series data. ClickHouse's columnar storage, MergeTree engine, and native materialized views make it ideal for this workload. PostgreSQL would be orders of magnitude slower for multi-billion-row scans.
- **Alternatives considered**: PostgreSQL with TimescaleDB (rejected — not in the tech stack; violates §III); ClickHouse for everything including CostModel pricing config (rejected — CostModel is relational config, not OLAP; atomic updates and ACID semantics are valuable for pricing changes).
- **Implication**: The analytics bounded context uses **both** SQLAlchemy 2.x async (for `analytics_cost_models` in PostgreSQL) **and** `clickhouse-connect 0.8+` (for ClickHouse usage data). This is not a violation — each store is used for its correct purpose.

---

### Decision 2: ClickHouse Table Architecture

- **Decision**: Two base tables + three materialized view tables:
  - `analytics_usage_events` — MergeTree, primary key `(toYYYYMM(timestamp), workspace_id, agent_fqn)`, stores raw usage events
  - `analytics_quality_events` — MergeTree, stores quality scores by execution_id
  - `analytics_usage_hourly` — AggregatingMergeTree materialized view from `analytics_usage_events`, `GROUP BY toStartOfHour(timestamp), workspace_id, agent_fqn, model_id`
  - `analytics_usage_daily` — AggregatingMergeTree materialized view, `GROUP BY toStartOfDay(timestamp)`
  - `analytics_usage_monthly` — AggregatingMergeTree materialized view, `GROUP BY toStartOfMonth(timestamp)`
- **Rationale**: Materialized views in ClickHouse are computed incrementally as new rows are inserted — this satisfies FR-004 (rollups within 5 minutes). AggregatingMergeTree with `AggregateFunctionState` for `sum`, `count`, `avg` enables accurate incremental aggregation. MergeTree ordering on `(toYYYYMM(timestamp), workspace_id, ...)` enables efficient time-range + workspace queries.
- **Alternatives considered**: Batch rollup jobs via APScheduler (rejected — higher latency than materialized views; more moving parts); ClickHouse `SummingMergeTree` (rejected — insufficient for avg quality score; AggregatingMergeTree handles sum+count+avg correctly).

---

### Decision 3: Kafka Consumer with Batch Insert Pattern

- **Decision**: The analytics Kafka consumer buffers events in memory and performs batch inserts to ClickHouse. Batch triggers: **100 events accumulated** OR **5 seconds elapsed**, whichever comes first. Failed batches are retried with exponential backoff. Dead-lettered events (after 3 retries) are logged to the DLQ.
- **Rationale**: ClickHouse is optimized for bulk inserts (large batches) — thousands of single-row inserts cause compaction overhead. Batching to 100 events achieves throughput of >10,000 events/min (SC-007) while keeping latency well within 5 minutes (SC-001). The 5-second timeout ensures low-volume periods still see timely updates.
- **Topics consumed**: `workflow.runtime` (primary — execution lifecycle events), `runtime.lifecycle` (agent start/stop, resource usage), `evaluation.events` (quality scores linked to execution IDs).
- **Alternatives considered**: Stream processing via Flink/Spark (rejected — not in tech stack; overkill for this throughput); per-event INSERT (rejected — ClickHouse anti-pattern at high volume); ClickHouse Kafka table engine (rejected — harder to apply transformation logic and workspace authorization filter).

---

### Decision 4: Quality Score Integration via Kafka Consumer

- **Decision**: Quality scores are ingested by consuming the `evaluation.events` Kafka topic. Each quality event carries `execution_id` and `quality_score`. The analytics consumer inserts these into `analytics_quality_events`. Cost-per-quality JOIN is computed in ClickHouse at query time: `SELECT ... FROM analytics_usage_events u LEFT JOIN analytics_quality_events q ON u.execution_id = q.execution_id`.
- **Rationale**: Consuming quality events from Kafka is the correct decoupled pattern (§I — bounded contexts communicate via Kafka). A JOIN at query time against pre-ingested quality data is cheaper than calling the evaluation service on every analytics query. The LEFT JOIN ensures agents without quality data still appear in the report (FR-007 assumption: "N/A" for agents without quality scores).
- **Alternatives considered**: In-process call to evaluation service per analytics query (rejected — high latency at scale; tight coupling); periodic batch pull from evaluation service (rejected — not event-driven; polling violates §III principle).

---

### Decision 5: Cost Model Pricing in PostgreSQL

- **Decision**: A single `analytics_cost_models` table in PostgreSQL stores pricing configuration: `model_id` (str), `provider` (str), `input_token_cost_usd` (Decimal), `output_token_cost_usd` (Decimal), `per_second_cost_usd` (Decimal, nullable), `valid_from` (datetime), `valid_until` (datetime, nullable). The Kafka consumer reads pricing at startup (cached in memory, refreshed every 5 minutes) to compute `CostEstimate` during event ingestion.
- **Rationale**: Pricing changes are rare, transactional, and need audit history. PostgreSQL with a `valid_from`/`valid_until` range approach allows historical pricing accuracy without retroactive recalculation. The memory cache avoids a DB lookup on every event.
- **Alternatives considered**: Environment variable configuration (rejected — cannot be updated without redeploy; no audit trail); ClickHouse storage (rejected — not suited for small, mutable config tables).

---

### Decision 6: Recommendation Engine as Rule-Based Heuristics (Service Layer)

- **Decision**: OptimizationRecommendations are generated **on-demand** in the Python service layer by applying rule-based heuristics against aggregated ClickHouse data. Rules are evaluated per workspace:
  1. **Model switch**: `agent_fqn` has runs on model A (costly) with avg quality ≥ 0.8 AND runs on model B (cheaper) with avg quality ≥ 0.75 → recommend switching to model B. Required: ≥ 30 data points per model.
  2. **Self-correction tuning**: `avg_self_correction_loops > fleet_avg_self_correction_loops * 2.0`. Required: ≥ 10 executions.
  3. **Context optimization**: `avg_input_tokens / avg_output_tokens > 95th percentile` AND `avg_quality_score < fleet_median_quality`. Required: ≥ 20 executions.
  4. **Underutilization**: `execution_count_last_30d < 5` for an agent provisioned > 7 days ago.
  5. Confidence: High ≥ 100 data points, Medium ≥ 30, Low < 30.
- **Alternatives considered**: ML-based recommendations (rejected — premature; requires sufficient training data; rule-based heuristics are explainable); pre-computed recommendations stored in DB (rejected — rules can change; on-demand is simpler and always current).

---

### Decision 7: Budget Forecasting via Linear Trend Extrapolation

- **Decision**: Forecasting uses linear regression (`scipy.stats.linregress` or a simple manual implementation to avoid the scipy dependency) on daily cost aggregates for the past 30 days. Produces a trend line (slope + intercept). Forecast for day N = `intercept + slope * N`. Confidence intervals use residual standard deviation × t-factor. Output: `{low, expected, high}` for 7/30/90-day horizons. Volatility flag: `std(residuals) / mean(daily_costs) > 0.3`.
- **Rationale**: Linear regression is simple, explainable, and requires no external ML library. It satisfies SC-005 (within 25% accuracy for stable trends). The t-factor confidence interval is standard statistical practice.
- **Alternatives considered**: scipy dependency (rejected — adds large dependency for one function; `statistics` stdlib sufficient for linear regression); ARIMA / Prophet (deferred per spec assumption — out of scope for v1); flat average projection (rejected — ignores trend direction, less accurate).
- **Implementation detail**: Pure Python implementation using `statistics.mean()`, `statistics.stdev()`, and basic linear algebra to avoid scipy dependency.

---

### Decision 8: REST API — Read-Only Endpoints (No SQLAlchemy Repository for Analytics Queries)

- **Decision**: The analytics bounded context exposes 4 GET endpoints. Analytics queries (`GET /analytics/usage`, `/cost-intelligence`, `/cost-forecast`, `/recommendations`) execute directly against ClickHouse via `clickhouse-connect`. Only the `CostModel` config CRUD uses the SQLAlchemy repository pattern.
- **Rationale**: ClickHouse queries cannot go through SQLAlchemy (no SQLAlchemy dialect for ClickHouse in the tech stack). A dedicated `AnalyticsRepository` wraps `clickhouse-connect` for all OLAP queries. The `CostModelRepository` wraps SQLAlchemy for pricing config.
- **API endpoint summary**:
  - `GET /api/v1/analytics/usage` — paginated usage rollups
  - `GET /api/v1/analytics/cost-intelligence` — cost-per-quality report
  - `GET /api/v1/analytics/cost-forecast` — budget forecast
  - `GET /api/v1/analytics/recommendations` — optimization recommendations

---

### Decision 9: Workspace Authorization via Workspaces Service

- **Decision**: All analytics endpoints validate workspace membership via `workspaces_service.get_user_workspace_ids(user_id)` (in-process, from feature 018). The `workspace_id` query parameter is required on all endpoints. If the requesting user is not a member of the requested workspace, the endpoint returns 403 Forbidden.
- **Rationale**: §IV — no cross-boundary DB access. The workspaces service interface provides workspace membership without querying the `workspaces_memberships` table directly. This ensures SC-008 (zero cross-workspace data leakage).

---

### Decision 10: No Alembic for ClickHouse Schema

- **Decision**: ClickHouse tables and materialized views are created by a **dedicated setup script** (`analytics/clickhouse_setup.py`) that is idempotent (`CREATE TABLE IF NOT EXISTS` / `CREATE MATERIALIZED VIEW IF NOT EXISTS`). This script runs at application startup if ClickHouse tables don't exist. No Alembic migration for ClickHouse.
- **Rationale**: Alembic is a PostgreSQL migration tool (SQLAlchemy-based). ClickHouse DDL is managed separately — it's standard practice in ClickHouse deployments. The setup script is idempotent and safe to run on every startup.
- **PostgreSQL migration**: One Alembic migration (`005_analytics_cost_models.py`) for the `analytics_cost_models` table only.

---

### Decision 11: Kafka Events Emitted by Analytics

- **Decision**: The analytics bounded context emits on `analytics.events` topic:
  - `analytics.recommendation.generated` — when new recommendations are computed for a workspace
  - `analytics.forecast.updated` — when a forecast is recomputed
  - `analytics.budget.threshold_crossed` — when cumulative spend crosses a configured threshold
- **Topic registry**: `analytics.events` is a new topic needing constitution registry update (same situation as `workspaces.events` in feature 018).
- **Rationale**: FR-019 requires event emission. These events enable downstream features (notification system in feature 016, dashboard auto-refresh).

---

### Decision 12: ClickHouse Self-Correction and Reasoning Fields

- **Decision**: The `analytics_usage_events` table includes fields for `self_correction_loops: UInt32` and `reasoning_tokens: UInt64` extracted from the runtime event payload. These fields are used by the self-correction tuning recommendation rule (Decision 6) and are nullable (default 0 for non-reasoning executions).
- **Rationale**: These fields are present in the constitution (§XI — reasoning engine tracks these metrics) and are essential for the self-correction tuning recommendation rule. Capturing them at ingestion time avoids a JOIN with reasoning data later.
