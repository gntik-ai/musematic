# Feature Specification: Analytics and Cost Intelligence

**Feature Branch**: `020-analytics-cost-intelligence`  
**Created**: 2026-04-11  
**Status**: Draft  
**Input**: User description: "Implement usage event pipeline (Kafka to ClickHouse), materialized views for rollups, cost-per-quality computation, optimization recommendations, budget forecasting, and cost intelligence API."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Usage Data Pipeline and Visibility (Priority: P1)

A platform operator wants to understand how the platform is being used — which agents run, how many tokens they consume, which models are invoked, and how long executions take. As agent executions occur, usage data is automatically captured and aggregated. The operator opens the analytics section of the platform and views usage summaries: total executions, token consumption, cost estimates, and breakdowns by workspace, agent, and model provider. The data updates within minutes of new activity, giving near-real-time visibility into platform utilization.

**Why this priority**: Usage visibility is the foundation of all analytics. Without ingesting and aggregating usage events, no cost intelligence, forecasting, or optimization features can function. This is the data pipeline that feeds everything else.

**Independent Test**: Trigger several agent executions across different workspaces and models. Open the usage analytics view. Verify that execution counts, token totals, and cost estimates appear for the correct workspaces, agents, and models. Verify the data reflects activity from the last few minutes. Query usage data filtered by time range and workspace — verify results match expectations.

**Acceptance Scenarios**:

1. **Given** agent executions producing runtime events, **When** the operator queries usage data, **Then** aggregated usage (executions, tokens, cost) appears within 5 minutes of the events occurring
2. **Given** usage data across multiple workspaces, **When** the operator filters by a specific workspace, **Then** only usage from that workspace is displayed
3. **Given** usage data across multiple agents and models, **When** the operator views breakdowns, **Then** usage is grouped by agent identity and model provider with correct totals
4. **Given** a time range filter, **When** the operator queries usage for "last 24 hours" or a custom date range, **Then** only events within that window are included in the results
5. **Given** an hour with significant activity, **When** the operator views hourly rollups, **Then** the rollup values match the sum of individual events within that hour

---

### User Story 2 — Cost-Per-Quality Analysis (Priority: P1)

A platform operator wants to understand the relationship between cost and quality for each agent and model combination. The system computes a cost-per-quality ratio by correlating usage cost data with quality scores (from the evaluation system). The operator views a cost intelligence report showing which agents are cost-efficient (low cost, high quality) and which are expensive relative to their output quality. This helps identify opportunities to switch to cheaper models without sacrificing quality or to invest more in high-performing but underfunded agents.

**Why this priority**: Cost-per-quality is the core metric of cost intelligence — it transforms raw usage numbers into actionable business insight. Without it, operators see costs but cannot assess value. This is inseparable from the pipeline (US1) in terms of business value.

**Independent Test**: Set up agents with different models (e.g., one using an expensive model, one using a cheaper model). Run executions with known quality scores. Query the cost intelligence endpoint. Verify the cost-per-quality ratio is correctly computed for each agent-model combination. Verify the ranking matches expected efficiency ordering.

**Acceptance Scenarios**:

1. **Given** an agent with recorded usage cost and quality scores, **When** the operator queries cost intelligence, **Then** the cost-per-quality ratio is displayed as cost divided by average quality score
2. **Given** multiple agents with varying cost and quality profiles, **When** the operator views the cost intelligence report, **Then** agents are ranked by cost efficiency (lowest cost-per-quality ratio first)
3. **Given** an agent that switched models mid-period, **When** the operator views the report, **Then** cost-per-quality is reported separately per model used
4. **Given** an agent with no quality scores recorded, **When** the report is generated, **Then** the agent is listed with cost data only and a "quality data unavailable" indicator (not an error)

---

### User Story 3 — Optimization Recommendations (Priority: P2)

The platform analyzes historical cost and quality data to generate actionable optimization recommendations. Recommendations include: suggesting cheaper models for agents whose quality scores remain high regardless of model used, identifying agents with excessive self-correction loops (high cost from retries without quality improvement), flagging agents with oversized context windows (high token cost relative to output), and highlighting underutilized agents (cost of provisioning with minimal actual use). Each recommendation includes the estimated cost savings and the confidence level based on the amount of historical data available.

**Why this priority**: Recommendations turn data into action. However, they require sufficient historical data (from US1) and cost-quality analysis (from US2) to be meaningful. They are valuable but not blocking for initial platform observability.

**Independent Test**: Seed the system with historical data where one agent consistently uses a premium model but achieves similar quality scores as runs on a cheaper model. Query recommendations. Verify a "model switch" recommendation appears for that agent with estimated savings. Seed data with an agent that has high self-correction loop counts — verify a "self-correction tuning" recommendation appears.

**Acceptance Scenarios**:

1. **Given** an agent achieving similar quality scores across a cheaper and more expensive model, **When** recommendations are generated, **Then** a "model switch" recommendation appears with estimated cost savings
2. **Given** an agent with self-correction loop counts significantly above the fleet average, **When** recommendations are generated, **Then** a "self-correction tuning" recommendation appears identifying the agent and the excess retry cost
3. **Given** an agent with context window token usage in the top 10% but output quality below the fleet median, **When** recommendations are generated, **Then** a "context optimization" recommendation appears
4. **Given** fewer than 100 data points for an agent, **When** a recommendation is generated for that agent, **Then** the confidence level is marked as "low" and the recommendation is flagged as preliminary

---

### User Story 4 — Budget Forecasting (Priority: P2)

A platform operator wants to project future costs based on historical trends. The system analyzes past usage patterns (token consumption, execution volume, model mix) and extrapolates to forecast costs for the next 7, 30, and 90 days. The forecast accounts for trend direction (increasing/decreasing usage) and seasonal patterns if sufficient data exists. The operator can view the forecast alongside actual spend to calibrate expectations and plan budgets.

**Why this priority**: Forecasting requires a stable pipeline and sufficient historical data. It provides planning value but is not needed for day-to-day operations. It builds on the same data foundation as US1–US3.

**Independent Test**: Seed the system with 30 days of historical usage data with a clear upward trend. Query the forecast endpoint for 30-day projection. Verify the forecast projects a continuation of the trend. Verify the forecast total is higher than the last 30 days' actual spend (reflecting the upward trend). Query with stable (flat) historical data — verify the forecast approximates recent actuals.

**Acceptance Scenarios**:

1. **Given** 30+ days of historical usage data, **When** the operator requests a 30-day cost forecast, **Then** a projected cost range (low/expected/high) is returned based on trend analysis
2. **Given** usage with a clear upward trend, **When** the forecast is generated, **Then** the projected cost is higher than the trailing 30-day actual
3. **Given** fewer than 7 days of historical data, **When** the operator requests a forecast, **Then** the system returns a warning that insufficient data exists and provides a rough estimate based on available data
4. **Given** a forecast alongside actual spending, **When** both are displayed, **Then** the operator can visually compare forecast vs. actual over the selected time range

---

### User Story 5 — KPI Dashboarding (Priority: P3)

A platform operator wants a high-level dashboard showing key performance indicators (KPIs) over time: total cost, average cost per execution, average quality score, cost-per-quality trend, execution volume trend, and model mix distribution. The dashboard supports different time granularities (hourly, daily, monthly) and workspace-level filtering. KPIs update as new data arrives without requiring manual refresh beyond page load.

**Why this priority**: The KPI dashboard is a presentation layer over data already computed by US1 and US2. It provides convenient visualization but does not introduce new data processing — it queries existing rollups and aggregates.

**Independent Test**: Seed the system with data across multiple days and workspaces. Open the KPI dashboard. Verify total cost, execution count, and quality trend line appear. Switch to a different workspace — verify the KPIs update to reflect that workspace only. Switch time granularity from daily to hourly — verify the chart resolution changes.

**Acceptance Scenarios**:

1. **Given** aggregated usage data exists, **When** the operator opens the KPI dashboard, **Then** key metrics (total cost, avg cost/execution, avg quality, execution volume) are displayed within 3 seconds
2. **Given** daily granularity selected, **When** the operator switches to hourly, **Then** the time-series charts update to show hourly data points
3. **Given** a workspace filter applied, **When** the operator views KPIs, **Then** only data from the selected workspace is included in the metrics
4. **Given** new usage events arriving, **When** the operator refreshes the dashboard, **Then** KPIs reflect the latest available data

---

### Edge Cases

- What happens when the event pipeline receives malformed or incomplete usage events? The system logs the malformed event for diagnostics and skips it without stopping the pipeline. A count of skipped events is tracked and visible in operational metrics.
- What happens when quality scores are not available for an agent? Cost data is still displayed. The cost-per-quality ratio shows "N/A" and the agent is excluded from cost-efficiency rankings. Recommendations requiring quality data are not generated for that agent.
- What happens when there is zero usage data for a workspace? The analytics view shows an empty state with a message indicating no activity has been recorded yet. All endpoints return valid but empty responses (not errors).
- What happens when the analytics data store is temporarily unreachable? The pipeline buffers events (leveraging the event backbone's durability). API queries for analytics data return a service-unavailable response. The system resumes normal operation when connectivity is restored without data loss.
- What happens when cost model pricing changes? The system uses cost model data that can be updated. Historical cost calculations are not retroactively recalculated — they reflect the pricing at the time of computation. Future calculations use updated pricing.
- What happens when the forecast algorithm has very volatile input data? The confidence interval widens. The forecast response includes a "high volatility" flag, and the projected range (low/expected/high) reflects the uncertainty.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST consume runtime execution events from the event backbone and extract usage data (tokens consumed, model used, execution duration, agent identity, workspace)
- **FR-002**: The system MUST store usage event data in an analytics-optimized data store suitable for time-series aggregation
- **FR-003**: The system MUST compute aggregated rollups at hourly, daily, and monthly granularities by workspace, agent, and model
- **FR-004**: Rollup computations MUST complete within 5 minutes of the underlying events being produced
- **FR-005**: The system MUST provide a usage query endpoint that supports filtering by workspace, agent, model, and time range
- **FR-006**: The system MUST compute a cost estimate for each usage event based on token counts, model pricing, and execution duration
- **FR-007**: The system MUST compute a cost-per-quality ratio by correlating usage cost with quality scores from the evaluation system
- **FR-008**: The system MUST provide a cost intelligence endpoint that returns cost-per-quality ratios ranked by cost efficiency
- **FR-009**: The system MUST generate optimization recommendations based on historical cost and quality data: model switch suggestions, self-correction tuning, context optimization, and underutilization alerts
- **FR-010**: Each recommendation MUST include estimated cost savings and a confidence level (high/medium/low) based on available data volume
- **FR-011**: The system MUST provide a recommendations endpoint that returns actionable suggestions for a given workspace
- **FR-012**: The system MUST generate cost forecasts for 7, 30, and 90-day horizons based on historical trend analysis
- **FR-013**: Cost forecasts MUST include a projected range (low/expected/high) reflecting uncertainty
- **FR-014**: The system MUST provide a forecast endpoint that returns projected costs for a given workspace
- **FR-015**: The system MUST provide a KPI time-series endpoint returning key metrics (total cost, average cost per execution, average quality, execution volume) at configurable time granularity
- **FR-016**: All analytics endpoints MUST enforce workspace-scoped access — users only see data for workspaces they belong to
- **FR-017**: The system MUST handle malformed usage events gracefully by logging and skipping them without interrupting the pipeline
- **FR-018**: The system MUST support cost model configuration that can be updated without code changes (pricing per token per model)
- **FR-019**: The system MUST emit events on the event backbone when significant analytics are computed (new recommendation generated, forecast updated, budget threshold crossed)
- **FR-020**: The system MUST track and expose pipeline health metrics (events processed, events skipped, processing lag)

### Key Entities

- **UsageEvent**: A single usage data point extracted from a runtime execution event — captures tokens consumed (input/output), model identifier, execution duration, agent FQN, workspace, timestamp, and estimated cost.
- **UsageRollup**: A pre-aggregated summary of usage over a fixed time window (hour/day/month) for a specific grouping dimension (workspace, agent, model). Contains totals for executions, tokens, cost, and average quality score.
- **CostEstimate**: The calculated cost for a single usage event or rollup period, derived from token counts and model pricing configuration.
- **CostIntelligenceReport**: An analysis result showing cost-per-quality ratios for agents and models within a workspace, with efficiency ranking.
- **OptimizationRecommendation**: An actionable suggestion (model switch, context optimization, self-correction tuning, underutilization alert) with estimated savings, confidence level, and supporting data summary.
- **ResourcePrediction**: A cost forecast for a future period (7/30/90 days) including low, expected, and high projections with trend direction and volatility flag.
- **KpiSeries**: A time-series of KPI data points at a given granularity, used for dashboard visualization.
- **CostModel**: Configuration defining per-token pricing for each model provider, used to compute cost estimates.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Usage data from runtime events is available for querying within 5 minutes of the events occurring
- **SC-002**: Hourly, daily, and monthly rollups are computed automatically and available without manual intervention
- **SC-003**: Cost-per-quality ratios are computed for all agents with both usage data and quality scores, with 100% accuracy against the underlying data
- **SC-004**: The system generates at least one relevant optimization recommendation for workspaces with 30+ days of usage history and identifiable inefficiencies
- **SC-005**: Cost forecasts for 30-day horizons are within 25% of actual costs (measured retroactively after 30 days of operation)
- **SC-006**: All analytics queries for a single workspace return results within 3 seconds
- **SC-007**: The pipeline processes at least 10,000 usage events per minute without falling behind
- **SC-008**: Users can only access analytics data for workspaces they are members of — zero cross-workspace data leakage
- **SC-009**: The system gracefully handles pipeline interruptions (event backbone outages) and resumes without data loss
- **SC-010**: Test coverage of the analytics and cost intelligence system is at least 95%

## Assumptions

- The runtime execution system (features 009, 011) produces events on the event backbone that contain sufficient data to extract usage metrics: tokens consumed (input and output), model identifier, execution duration, agent FQN, workspace ID, and timestamp.
- Quality scores are available from the evaluation system (a separate bounded context) via either an in-process service interface or by consuming evaluation events from the event backbone. Quality scores are linked to executions by execution ID.
- Cost model pricing data (per-token cost per model provider) is maintained as configuration. Initial values are seeded during deployment. Updates to pricing configuration take effect for future cost calculations only — historical cost data is not retroactively recalculated.
- The analytics data store (ClickHouse per constitution §III) is operational and accessible. Rollup computations are performed by the data store's native aggregation capabilities (materialized views or equivalent), not by application-level batch processing.
- The recommendation engine uses rule-based heuristics (not machine learning) for the initial implementation. Rules are based on statistical comparisons of agent metrics against fleet-wide baselines (e.g., "self-correction loop count > 2x fleet average" triggers a recommendation).
- Forecasting uses linear trend extrapolation with confidence intervals for the initial implementation. Advanced time-series forecasting (ARIMA, Prophet) is out of scope for the first version.
- The analytics bounded context does not write to or read from PostgreSQL. All analytics data is stored in the OLAP-optimized data store per constitution §III ("Never compute rollups in PostgreSQL").
- Workspace authorization for analytics queries is resolved using the same workspace membership mechanism as other bounded contexts (via workspaces service interface from feature 018).
