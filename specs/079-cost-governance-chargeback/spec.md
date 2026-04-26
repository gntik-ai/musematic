# Feature Specification: Cost Governance and Chargeback

**Feature Branch**: `079-cost-governance-chargeback`
**Created**: 2026-04-26
**Status**: Draft
**Input**: User description: "Per-execution cost attribution, workspace chargeback/showback reports, budget alerts with hard caps, cost intelligence dashboard with anomaly detection."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Per-Execution Cost Attribution (Priority: P1)

Every workflow execution that consumes platform resources (model tokens, compute time, storage, platform overhead) MUST produce a durable, queryable cost record attributed to the workspace, agent, and (when available) initiating user that caused it. This is the foundation of every other capability in this feature: without trustworthy attribution there is no chargeback, no budget enforcement, no forecasting, and no anomaly detection.

**Why this priority**: All other user stories depend on a complete, accurate, per-execution cost record. Until attribution is proven correct end-to-end, any downstream report or alert is unsafe to act on.

**Independent Test**: Trigger a sample of workflow executions across multiple workspaces with mixed model use, compute consumption, and storage writes. Verify each completed execution has exactly one attribution record, the per-category cents sum to the recorded total, and the record is reachable from both the execution detail view and a workspace-scoped cost query.

**Acceptance Scenarios**:

1. **Given** a workflow that calls a model and writes an artifact, **When** the execution finishes, **Then** an attribution record exists for that execution with non-zero model and storage cost, the workspace and agent are correctly identified, and the user who triggered the execution is recorded.
2. **Given** an execution that fails partway through after consuming model tokens, **When** the execution terminates, **Then** an attribution record is still produced reflecting the costs actually incurred up to the failure.
3. **Given** an execution that runs for several minutes, **When** the operator queries cost during the execution, **Then** the in-progress cost is visible (not only the final post-completion total).
4. **Given** a system-initiated execution with no human originator (e.g., scheduled trigger), **When** attribution is recorded, **Then** the record is still complete and the absence of a user is represented unambiguously rather than misattributed.

---

### User Story 2 - Budget Enforcement with Soft Alerts and Hard Caps (Priority: P2)

Workspace administrators MUST be able to set per-workspace spending budgets at daily, weekly, or monthly periods, receive proactive alerts as spending approaches the budget, and optionally configure a hard cap that blocks new execution starts once the budget is exhausted — with a documented admin override path so legitimate critical work is never silently stalled.

**Why this priority**: Cost visibility without enforcement is the most common complaint from finance and platform owners. Soft alerts plus a hard-cap toggle are the smallest wedge that gives operators real control.

**Independent Test**: Configure a daily budget on a test workspace with thresholds at 50%, 80%, 100% and the hard cap enabled. Drive synthetic load until each threshold is crossed; verify alerts fire exactly once per threshold per period, the hard cap blocks new execution starts at 100%, and an authorized admin override allows a single critical execution to proceed (with the override recorded for audit).

**Acceptance Scenarios**:

1. **Given** a workspace with a monthly budget and default thresholds (50, 80, 100), **When** cumulative spend in the period crosses 50%, **Then** a 50% threshold alert is delivered to the workspace administrators exactly once for that period.
2. **Given** a workspace with hard cap disabled, **When** spend crosses 100%, **Then** the 100% alert fires but new executions continue to start.
3. **Given** a workspace with hard cap enabled, **When** spend reaches the budget, **Then** new execution starts are refused with a clear, actionable error referencing the budget and the override path.
4. **Given** a hard-capped workspace, **When** a workspace administrator with override authority requests an exception, **Then** the override succeeds, the next execution proceeds, and an audit record captures who overrode, when, and why.
5. **Given** an execution already running when the hard cap is hit, **When** the threshold crosses 100%, **Then** the in-flight execution is allowed to complete (the cap only blocks new starts) and a clear warning is recorded.
6. **Given** the budget period rolls over (e.g., new month), **When** the new period begins, **Then** alert state resets and previously fired thresholds can fire again as spending in the new period accumulates.

---

### User Story 3 - Chargeback and Showback Reports (Priority: P3)

Finance, platform owners, and workspace administrators MUST be able to produce reports that aggregate cost across configurable dimensions — workspace, agent, user, cost type, time range — and export them in a format suitable for downstream finance systems or internal showback emails.

**Why this priority**: Reports turn raw attribution into a usable artifact for cross-team conversations and internal billing. Lower priority than enforcement because read-only consumers can wait briefly behind correctness and control.

**Independent Test**: With a populated attribution dataset, generate a chargeback report grouped by workspace and cost type for the prior month, verify the totals reconcile to the sum of underlying attribution records, and export the report in a structured format that an external system can ingest.

**Acceptance Scenarios**:

1. **Given** at least one full month of attribution data, **When** an administrator requests a chargeback report grouped by workspace and cost type for that month, **Then** the report renders within an acceptable time, totals reconcile to the underlying records, and the report is exportable.
2. **Given** a report request, **When** the requester applies a workspace filter they are not authorized to view, **Then** the unauthorized workspaces are excluded with no leakage of their existence in the response.
3. **Given** a generated report, **When** it is exported, **Then** the export includes the dimensions, the time range, the per-category breakdown, and the totals, in a format that downstream systems can parse.

---

### User Story 4 - Cost Forecasts and Anomaly Detection (Priority: P4)

Workspace administrators and platform operators MUST be able to see a forward-looking forecast of end-of-period spend (with a confidence range) and be alerted when actual spend departs significantly from the established baseline so they can investigate before a small spike becomes a budget breach.

**Why this priority**: Predictive intelligence is a clear value-add but only meaningful once attribution, enforcement, and reporting are trustworthy. Anomaly detection without solid attribution generates noise; forecasting without history is inaccurate.

**Independent Test**: Seed a workspace with a steady cost trend over multiple periods, then inject a controlled spike. Verify that (a) the forecast for the current period reflects the historical trend before the spike, (b) the spike triggers an anomaly notification with a baseline-vs-observed comparison, and (c) the forecast updates after the spike is incorporated into history.

**Acceptance Scenarios**:

1. **Given** a workspace with at least the minimum required history, **When** the dashboard is viewed, **Then** an end-of-period forecast is shown with a confidence range and the forecast's freshness is visible to the user.
2. **Given** a sudden, sustained spike in spend that exceeds the configured deviation from baseline, **When** the anomaly evaluator next runs, **Then** an anomaly record is created with type, severity, baseline, observed value, and a human-readable summary, and the responsible parties are notified.
3. **Given** insufficient history to forecast confidently, **When** the dashboard is rendered, **Then** the forecast section communicates the limitation rather than displaying a misleading number.
4. **Given** an anomaly that has already been raised, **When** the same condition persists into the next evaluation window, **Then** the system does not re-alert on the same anomaly (no alert storms) but the anomaly remains visible until acknowledged or resolved.

---

### Edge Cases

- **Mid-execution failures and crashes**: Attribution must capture costs already incurred even if the execution crashes, is killed by the hard cap of an unrelated period rollover, or is preempted; orphan executions must not silently leave costs unattributed.
- **Pricing changes**: When the underlying pricing model for a category (e.g., model token rates) changes, historical attribution records must remain immutable; only future executions reflect the new pricing. Reports clearly indicate the pricing-effective date when relevant.
- **Currency**: All monetary values are stored and displayed in a single canonical unit (cents) with the currency policy stated explicitly; multi-currency is out of scope for v1.
- **Late-arriving cost data**: When a cost component (e.g., a delayed compute invoice signal) arrives after the initial attribution write, the original record is updated additively and downstream rollups reconcile without double-counting.
- **Budget changed mid-period**: When an admin raises or lowers a budget mid-period, alert thresholds are re-evaluated against the new budget and previously-fired thresholds for the same period are not re-fired unless the new budget makes a previously-uncrossed threshold cross.
- **Concurrent executions racing the hard cap**: When multiple new executions are requested simultaneously near the cap, the enforcement decision is consistent — either all that fit are admitted and the rest are refused, or all are refused; no partial-state leakage.
- **Admin override scope**: An override permits the next start (or a bounded number/window of starts) — never a permanent cap removal; the override does not silently disable enforcement.
- **Workspace deletion / archival**: Cost attribution and historical reports survive workspace archival; deleting a workspace does not destroy the audit-relevant cost record.
- **Cross-workspace executions / shared resources**: Costs incurred by shared infrastructure (e.g., warm-pool warmups, platform overhead) are attributed using a clearly documented allocation rule rather than silently dropped.
- **Anomaly during onboarding**: A brand-new workspace with no history must not be flagged as anomalous on its first real execution.
- **Forecast with extreme outliers**: A single extreme execution should not poison the forecast — the forecast methodology must be resilient to outliers or clearly mark low-confidence forecasts.
- **Reporting on a workspace the requester only partially can see**: RBAC must filter at the data layer, not the rendering layer; unauthorized rows must never reach the requester even as totals.

## Requirements *(mandatory)*

### Functional Requirements

**Attribution (FR-501)**

- **FR-501.1**: System MUST record exactly one cost attribution record per completed execution, capturing workspace, agent (when applicable), initiating user (when applicable), and per-category costs (model, compute, storage, overhead).
- **FR-501.2**: System MUST attribute partial costs for executions that fail, are cancelled, or are pre-empted, reflecting only the work actually performed.
- **FR-501.3**: System MUST make per-execution cost visible from the execution detail view and queryable by workspace within a bounded time of execution completion.
- **FR-501.4**: Attribution records MUST be immutable to historical pricing changes; pricing-rate updates affect only executions that occur after the change.
- **FR-501.5**: System MUST support late-arriving cost components by updating the attribution record additively without producing duplicate downstream rollup entries.
- **FR-501.6**: System MUST allocate costs from shared infrastructure (e.g., warm pools, platform overhead) using a documented rule and attribute them to the workspaces that benefited.

**Chargeback / Showback (FR-502)**

- **FR-502.1**: Authorized users MUST be able to generate cost reports aggregated by configurable dimensions (workspace, agent, user, cost type) over a configurable time range.
- **FR-502.2**: Report totals MUST reconcile exactly to the sum of the underlying attribution records that were in the requester's authorization scope.
- **FR-502.3**: Reports MUST be exportable in a structured format consumable by downstream finance/billing systems.
- **FR-502.4**: Reports MUST enforce visibility rules at the data layer — rows the requester cannot view are excluded entirely (not aggregated into a total they should not see).

**Budgets and Enforcement (FR-503)**

- **FR-503.1**: Workspace administrators MUST be able to configure a budget per workspace per period type (daily, weekly, monthly) with configurable soft-alert thresholds and an optional hard-cap toggle.
- **FR-503.2**: Soft-alert thresholds MUST fire at most once per threshold per period and MUST be delivered through the platform's notification channels to the workspace administrators.
- **FR-503.3**: When a workspace's hard cap is enabled and reached, new execution starts MUST be refused with a clear error message that names the budget and the override mechanism.
- **FR-503.4**: In-flight executions MUST be allowed to complete when the hard cap is reached; only new starts are blocked.
- **FR-503.5**: Authorized administrators MUST be able to issue a bounded override (single execution or short, time-limited window) that is fully audited (who, when, why, scope).
- **FR-503.6**: Budget evaluation MUST be safe under concurrent execution starts so that the cap is not silently exceeded by a race.
- **FR-503.7**: Period rollover MUST reset alert state cleanly; budgets, thresholds, and hard-cap configuration persist across rollovers.

**Cost Intelligence: Forecasting and Anomaly Detection (FR-504)**

- **FR-504.1**: System MUST produce an end-of-period spend forecast per workspace with an associated confidence range when sufficient history exists.
- **FR-504.2**: When history is insufficient for a confident forecast, the system MUST communicate that limitation rather than display a low-confidence number as if it were reliable.
- **FR-504.3**: System MUST detect anomalies (sudden spikes, sustained deviations) by comparing observed spend against an established baseline and MUST record anomaly type, severity, baseline value, observed value, and a human-readable summary.
- **FR-504.4**: Anomaly detection MUST suppress duplicate alerts for an anomaly that is already open; a single condition must not generate alert storms across consecutive evaluation windows.
- **FR-504.5**: Anomalies MUST be acknowledgable / resolvable so that the operator's investigation state is captured.
- **FR-504.6**: A new workspace with no operating history MUST NOT be flagged as anomalous on first use.

**Cross-Cutting**

- **FR-CC-1**: All cost values MUST be stored and exposed in a single canonical monetary unit with the currency policy declared explicitly.
- **FR-CC-2**: All cost-affecting administrative actions (budget create/update, hard-cap toggle, override) MUST be auditable.
- **FR-CC-3**: Cost attribution and historical reports MUST survive workspace archival.
- **FR-CC-4**: Visibility and enforcement actions MUST integrate with the platform's existing RBAC and policy/governance layer rather than introducing a parallel authorization path.

### Key Entities

- **Cost Attribution**: The per-execution cost record. Identifies the execution, its workspace and agent, the initiating user (when applicable), and the per-category breakdown that sums to a total. Immutable to retroactive pricing changes; updatable for late-arriving components.
- **Workspace Budget**: A spending ceiling for a workspace over a recurring period (daily/weekly/monthly), with configurable alert thresholds, an optional hard cap, and an admin-override policy.
- **Budget Alert**: A record that a specific threshold of a specific budget was crossed in a specific period — used to drive notifications and to prevent duplicate alerting.
- **Cost Forecast**: A predicted end-of-period spend value for a workspace, with a confidence range and a freshness timestamp.
- **Cost Anomaly**: A detected deviation from an expected baseline, with type, severity, baseline-vs-observed values, summary, and acknowledgement state.
- **Override Record**: An auditable authorization that permits a bounded amount of execution past a hard cap, capturing actor, reason, scope, and time.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of completed executions in a representative production-like sample have a corresponding cost attribution record whose per-category sum equals the recorded total.
- **SC-002**: Cost attribution for a completed execution is queryable within a defined post-completion latency budget that an operator can rely on for real-time cost dashboards.
- **SC-003**: Soft-alert thresholds fire exactly once per threshold per period — no missed alerts, no duplicates — verified across at least one full daily, weekly, and monthly cycle.
- **SC-004**: With the hard cap enabled, no workspace exceeds its configured budget by more than a small, bounded race tolerance defined by the platform's concurrency guarantees, and zero unauthorized overrides occur in audit review.
- **SC-005**: Chargeback reports for any supported dimension combination reconcile exactly to the underlying attribution records in the requester's authorization scope.
- **SC-006**: Forecast accuracy meets a stated mean error target for workspaces with steady usage, and forecasts are explicitly flagged as low-confidence (rather than silently inaccurate) when history is insufficient.
- **SC-007**: A controlled spike in synthetic load produces an anomaly notification within one evaluation window, and a sustained anomaly does not produce duplicate alerts in subsequent windows.
- **SC-008**: Operators can complete the end-to-end "investigate a spike → identify owning workspace and agent → confirm or override budget action" workflow without leaving the cost dashboard.
- **SC-009**: No workspace's cost data leaks across the visibility boundary in any report, drill-down, or export, verified by automated authorization tests across all read paths.

## Assumptions

- Pricing inputs (model rates, compute rates, storage rates, overhead allocation rules) are sourced from a configuration owned by the platform operator and are versioned over time.
- The platform's existing notification, audit, and RBAC subsystems are reused; this feature does not introduce a parallel notification or authorization path.
- Multi-currency is out of scope for v1; all values use a single canonical currency declared at deployment.
- The platform's existing workspace, execution, and agent identifiers are stable and suitable as attribution dimensions.
- Cost attribution is computed from observable execution telemetry (token counts, runtime duration, storage I/O) plus the operator-managed pricing configuration; reconciliation against external provider invoices is out of scope for v1 but the design must not preclude it.
- "Period" boundaries (daily/weekly/monthly) are evaluated in a single platform-default time zone declared at deployment; per-workspace time zones are out of scope for v1.
- The set of cost categories (model, compute, storage, overhead) is fixed for v1; adding new categories is a future change.
- Historical cost data must be retained long enough to support the forecasting window and at least one full annual finance cycle; the exact retention horizon will be set during planning.

## Out of Scope (v1)

- Multi-currency cost tracking and display.
- Per-workspace time-zone budgets and reports.
- Reconciliation of platform-computed cost against external provider invoices.
- Predictive budget recommendations (auto-tuning suggested budgets).
- Cross-tenant chargeback (B2B reseller scenarios).
- Cost-aware scheduling (e.g., automatically routing executions to cheaper models to stay within budget).

## Dependencies and Brownfield Touchpoints

This feature is additive to the existing platform. The relevant existing capabilities the new bounded context relies on or extends:

- **Workflow execution**: emits the per-step signals from which cost attribution is computed.
- **Policy / governance gateway**: the natural enforcement seam for refusing new execution starts when a workspace's hard cap has been reached.
- **Analytics**: existing usage-event pipeline and ClickHouse rollups are extended (not replaced) with cost-typed events to support drill-down and anomaly evaluation.
- **Notifications**: soft-alert and anomaly delivery reuse the platform's multi-channel notification subsystem.
- **Workspaces and RBAC**: budget configuration, override authority, and report visibility derive from existing workspace roles and policy attachments.
- **Operator dashboard**: the cost dashboard is a new surface in the existing operator UI rather than a separate application.

The implementation strategy (specific tables, services, schemas, and code-level integration points) is intentionally deferred to the planning phase. The brownfield input that motivated this spec is preserved in the feature folder as a planning input.
