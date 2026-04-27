# Feature Specification: Log Aggregation and Comprehensive Dashboards

**Feature Branch**: `084-log-aggregation-dashboards`
**Created**: 2026-04-26
**Status**: Draft
**Input**: User description: "Add Grafana Loki + Promtail for centralized log aggregation, structured-logging discipline across the control plane (Python) and satellite services (Go) and the frontend (Next.js), 14 new Grafana dashboards (5 log-focused + 9 metric-based for the audit-pass bounded contexts), Loki-based alerts. Closes the log-aggregation gap explicitly left by feature 047 and the dashboard gap for the audit-pass bounded contexts."

> **Constitutional anchor:** This feature IS the constitutionally-named **UPD-034** ("Observability Extension — Loki + Promtail + 14 new dashboards") declared in Constitution § "Observability Extension (UPD-034 and UPD-035)". The feature flag inventory already reserves `FEATURE_LOKI_ENABLED` (line 893), `FEATURE_PROMTAIL_REDACTION` (line 894), and `FEATURE_STRUCTURED_LOGGING` (line 892 — "always on"). The constitutional rules driving the design — rule 20 (structured JSON logs), rule 22 (Loki labels low-cardinality only), rule 24 (every new BC gets a dashboard), rule 27 (dashboards as ConfigMaps with `grafana_dashboard: "1"` label), AD-22 (structured JSON logs only), AD-23 (Loki for logs / Jaeger for traces / Prometheus for metrics — three separate backends bound by Grafana) — are all already in place; this feature is their canonical implementation.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Operator Investigates a Failing Execution via Logs (Priority: P1)

An operator sees a spike in `execution.failure_spike` alerts on the existing Platform Overview dashboard. From the dashboard, they MUST be able to click into the failing service's most recent error logs (with `correlation_id` already populated as a label or JSON field), pivot from a log entry directly to the corresponding trace in Jaeger via the `trace_id` linkage, and identify a root cause within minutes — without leaving the Grafana shell. The pivot path through metrics → logs → traces is the everyday operational workflow that closes the gap feature 047 explicitly left open ("log aggregation is Out of Scope" — until now).

**Why this priority**: Without log aggregation, the platform has metrics (Prometheus) and traces (Jaeger) but no central place to read what services are saying. Operators today have to `kubectl logs` per pod, which doesn't scale past trivial deployments. P1 is "the metrics-→-logs-→-traces operator workflow exists and is fast enough to use under pressure."

**Independent Test**: Trigger a controlled execution failure on a non-production deployment. Verify (a) the failing log line appears in Loki within 15 seconds with `service`, `bounded_context`, `level=error`, and `correlation_id` populated; (b) Grafana Explore queries against `{service="control-plane", level="error"}` return matches within 3 seconds for a 1-hour window; (c) clicking a log entry that carries `trace_id` opens the corresponding trace in Jaeger; (d) the existing Platform Overview dashboard surfaces a "View related logs" affordance that opens Loki filtered by the same time range and service.

**Acceptance Scenarios**:

1. **Given** a service emits a structured JSON log line at level `error`, **When** Promtail collects and forwards it to Loki, **Then** the line is queryable in Grafana within 15 seconds with `service`, `bounded_context`, and `level` available as Loki labels and `correlation_id` / `trace_id` / `workspace_id` / `goal_id` / `user_id` (when present) available as JSON-payload fields per the constitutional low-cardinality label discipline (rule 22).
2. **Given** an operator is viewing a Prometheus metric data point in Grafana, **When** they click "View related logs," **Then** Loki opens filtered by the same `service` label and the same time range, with no manual query rewriting.
3. **Given** a Loki log entry that carries a `trace_id` JSON field, **When** the operator clicks the trace_id, **Then** the corresponding trace opens in Jaeger via Grafana's derived-field link.
4. **Given** a Loki query for `{service="control-plane", level="error"}` over a 1-hour window, **When** Grafana Explore renders the result, **Then** the response time is ≤ 3 seconds p95 and the matching entries are visible without truncation under typical operational log volumes.
5. **Given** a sustained burst of error logs from one service exceeding the operator-configured threshold, **When** the burst persists for the threshold window, **Then** the Loki ruler fires the `HighErrorLogRate` alert routed through the existing Alertmanager configured by feature 047.
6. **Given** Loki is unreachable (network blip), **When** the platform continues operating, **Then** ingestion is best-effort (constitution: "Log emission is fire-and-forget; Loki unreachability MUST NOT cause application failures") and a structured-log entry to a fallback location records the drop; the platform's request-handling latency is unaffected.

---

### User Story 2 - Compliance Officer Audits Privacy Events (Priority: P1)

A compliance officer MUST be able to open the new **Privacy & Compliance** dashboard (D13) and see, in a single coordinated view: the data subject request queue (received / completed / SLA status), DLP events grouped by classification (PII / PHI / financial / confidential), residency violation attempts, PIA approvals pending review, and consent grants by type. Time range and workspace filters MUST apply to all panels simultaneously. Each panel MUST drill down to the underlying log stream in Loki via a one-click action.

**Why this priority**: Compliance reviews are the canonical periodic audit; without a single coherent dashboard, every review is an exercise in cross-referencing per-feature pages. P1 because compliance reviews block organisational risk-acceptance decisions and have hard deadlines (regulatory cycles).

**Independent Test**: Submit a test DSR via the API, trigger a synthetic DLP event, and create a PIA in the privacy-compliance subsystem. Verify all three appear in the Privacy & Compliance dashboard within 1 minute. Apply the workspace filter to confirm scope correctness. Click each of the five panel types and verify the drill-down opens Loki filtered by the right `bounded_context` and time range.

**Acceptance Scenarios**:

1. **Given** the platform has a populated audit history of DSRs, DLP events, residency violations, PIAs, and consent grants, **When** an authorised compliance officer opens the Privacy & Compliance dashboard, **Then** all five panel categories render with real data within the dashboard's stated p95 load budget.
2. **Given** the dashboard is open, **When** the compliance officer changes the time range or workspace filter, **Then** every panel re-queries with the new filter without per-panel refresh.
3. **Given** the compliance officer clicks a panel cell (e.g., a DLP-event count), **When** the drill-down activates, **Then** Loki opens with the appropriate `bounded_context=privacy_compliance` filter and the same time range.
4. **Given** an unauthorised user attempts to open the dashboard, **When** access is checked, **Then** the existing Grafana RBAC refuses the request — the dashboard inherits the operator-RBAC scope from the existing observability surface, no parallel auth path.
5. **Given** the dashboard is loaded with no recent privacy events, **When** the panels query, **Then** each panel renders a clear "no data" empty state rather than an error or a misleading zero-line chart.

---

### User Story 3 - Security Officer Reviews Supply Chain and Rotations (Priority: P1)

A security officer MUST be able to open the new **Security Compliance** dashboard (D14) and see: the latest SBOM publication status, CVE counts by severity from the most recent vulnerability scan, pen-test findings grouped by remediation status, upcoming secret rotations (within the next 30 days), active JIT credential grants, and the audit chain integrity check result (✓ or ✗ with the verifying scope). All panels MUST be source-linked — clicking a panel opens the originating log stream or the evidence record.

**Why this priority**: Security reviews are the second of the two canonical periodic audits (compliance is the first). Same deadline-binding logic as US2.

**Independent Test**: Publish an SBOM, record a scan result with a known CVE, schedule a secret rotation 7 days out, and issue a JIT credential grant. Verify each is reflected in the Security Compliance dashboard within 1 minute. Verify the audit chain integrity panel matches the result of the latest scheduled chain-verify run.

**Acceptance Scenarios**:

1. **Given** the platform has recent SBOM publications, vulnerability scans, pen-test results, scheduled rotations, JIT grants, and audit-chain verifies, **When** the security officer opens the Security Compliance dashboard, **Then** all six panel categories render with real data.
2. **Given** the latest vulnerability scan recorded N critical and M high CVEs, **When** the dashboard's CVE-severity panel renders, **Then** the counts match the source-of-truth table exactly.
3. **Given** the audit chain has been verified within the configured cadence, **When** the integrity panel renders, **Then** it shows ✓ with the timestamp of the last verify; if the latest verify failed, the panel shows ✗ with the broken-at sequence number from the verify result.
4. **Given** the security officer clicks the "active JIT grants" panel, **When** the drill-down activates, **Then** the underlying log stream filtered by `bounded_context=security_compliance` and the JIT issuance event type is presented.
5. **Given** a CVE in a development dependency, **When** the dashboard renders, **Then** the dev-dependency CVEs are clearly distinguished from production-dependency CVEs (constitution Integration Constraint: "critical CVEs in dev dependencies MUST NOT block platform releases" — the dashboard makes the distinction visible).

---

### User Story 4 - Developer Debugs Frontend Errors with Server-Side Correlation (Priority: P2)

A developer investigates a client-side error reported by a user. From the new **Frontend Web Logs** dashboard (D10), they MUST be able to filter by the user's `user_id` and see, on a single coordinated timeline: client-side JavaScript errors (captured via the in-app error reporter), server-side Next.js logs, and correlated control-plane API errors keyed by the same `correlation_id` and `trace_id`. The dashboard MUST show the full flow from client action to backend error in chronological order.

**Why this priority**: Frontend bugs that span client and server are the hardest to debug today because there's no shared context — log streams live in different places. P2 because developer-debugging surfaces are productivity ergonomics; they don't block compliance or security reviews but they pay back daily.

**Independent Test**: Trigger a known frontend error tied to a user action (e.g., the user clicks a button that calls an API endpoint that returns 500 — the failure causes the client to throw an unhandled-promise-rejection). Verify the error appears in Frontend Web Logs correlated with the corresponding backend API call by `correlation_id`. Verify the source map is applied to the client-side stack trace so the trace points at the original TypeScript source line, not the minified bundle.

**Acceptance Scenarios**:

1. **Given** a client-side error is captured by the in-app error reporter, **When** Promtail forwards the resulting server-side log line to Loki, **Then** the entry carries `service=web`, `bounded_context=frontend`, `level=error`, and the originating `user_id` (when authenticated) and `trace_id`.
2. **Given** a developer filters the Frontend Web Logs dashboard by `user_id`, **When** the panels query, **Then** all three panels (client errors, server-side logs, correlated API errors) narrow to that user_id simultaneously.
3. **Given** a client-side stack trace from a minified bundle, **When** the developer opens the log entry detail, **Then** the source map is applied to render the original TypeScript file + line number; the minified-only trace MUST NOT be the only available form.
4. **Given** an unauthenticated client-side error (no user logged in), **When** the entry is forwarded, **Then** the entry is still queryable but without `user_id`; the dashboard's user-filter shows an "anonymous" bucket alongside the per-user entries.
5. **Given** a slow page load reported by the client telemetry, **When** the developer queries the dashboard, **Then** the slow-page-load panel shows it alongside the API response times for the same `correlation_id` so the bottleneck (client JS or server API) is identifiable.

---

### User Story 5 - Operator Responds to Governance Enforcement Storm (Priority: P2)

An operator sees a spike in governance enforcement alerts. From the new **Governance Pipeline** dashboard (D21), they MUST be able to see the Observer → Judge → Enforcer flow in real time: signal volume, verdict rate, verdicts by type (compliant / violation / ambiguous), enforcement actions distribution (block / notify / revoke / escalate), per-chain latency, and a ranked list of top offending agents and workspaces. They MUST be able to drill down on the chain with the most enforcement actions and see individual verdicts with their rationale text. The dashboard MUST refresh in near-real-time (≤ 15-second window).

**Why this priority**: Governance enforcement storms are operational events that need real-time situational awareness — knowing *which* chain is firing, *which* agents are causing it, and *what* the verdict rationale looks like is the only way to triage fast. P2 because governance operations are a smaller user community than P1's compliance/security officers, but the time-criticality is comparable when an incident is in progress.

**Independent Test**: Trigger 10 policy violations across 3 workspaces using a synthetic load. Verify the Governance Pipeline dashboard reflects the signals → verdicts → actions within 30 seconds. Drill down on the chain with the most actions and confirm individual verdicts render with their rationale text. Confirm the top-offending-agents ranking matches the synthetic load's distribution.

**Acceptance Scenarios**:

1. **Given** Observer agents emit signals at a sustained rate, **When** the operator views the Governance Pipeline dashboard, **Then** the signal volume panel updates with refresh ≤ 15 seconds and the verdict rate panel reflects the downstream Judge processing.
2. **Given** Judge agents emit verdicts of mixed types, **When** the verdicts-by-type panel renders, **Then** compliant / violation / ambiguous counts are visible per chain.
3. **Given** Enforcer agents take actions of mixed types, **When** the enforcement-actions panel renders, **Then** block / notify / revoke / escalate counts are visible with the proportion clearly indicated.
4. **Given** the operator clicks a chain in the per-chain-latency panel, **When** the drill-down activates, **Then** individual verdicts for that chain are listed with their rationale text from the originating log stream.
5. **Given** a top-offending-agents ranking, **When** the panel renders, **Then** the agents are ranked by enforcement action count over the active time range; the workspace they belong to is visible alongside.

---

### Edge Cases

- **Loki disk full or storage degraded**: Log ingestion is rate-limited at the Loki side; old logs age out per retention policy (14 days hot / 90 days cold via S3); ingestion failures surface on the Platform Overview dashboard via a dedicated panel; the platform's application services are unaffected (constitution Integration Constraint: "Log emission is fire-and-forget; Loki unreachability MUST NOT cause application failures").
- **Promtail pod failure**: Kubernetes restarts the DaemonSet pod; in-flight logs are replayed from the journal where supported; gap indicators appear in dashboards (a known-gap window is rendered as a coloured band on the timeline rather than a silent gap).
- **Structured-logging violations**: A service that emits unstructured logs still reaches Loki via Promtail, but with limited labels (only `namespace`, `pod`, `container`, `level` from the CRI extractor). An alert fires on logs missing required fields (`service`, `timestamp`, `level`) so the offending service is named and fixable.
- **Dashboard panel "no data"**: Panels render an explicit "no data" empty state for queries that return empty rather than an error or a misleading zero-line chart.
- **Cross-cluster correlation in multi-region deployments**: In feature 081's multi-region deployments, Loki is per-region by design; Grafana federates across regions using the Loki `{region="primary|secondary"}` label so a query like `{service="control-plane", region=~"primary|secondary"}` returns logs from both regions on the same timeline.
- **Sensitive data in logs**: Promtail scrubs known patterns (bearer tokens matching `Bearer [A-Za-z0-9...]`, API keys matching `sk-...`, AWS-key formats, email addresses in error contexts, SSNs, credit-card-like sequences) before shipping to Loki via `pipeline_stages`. Constitution rule 23 ("Secrets never reach logs") is the application-layer mandate; Promtail's redaction is the defence-in-depth layer.
- **High-cardinality label leak**: A developer who attempts to add `workspace_id` / `user_id` / `goal_id` as a Loki label (rather than a JSON-payload field) violates constitution rule 22. The CI lint check (a small grep against the Promtail pipeline_stages config) catches the violation at build time so the cardinality explosion never reaches production.
- **Dashboard panel query timeout**: If a panel's LogQL or PromQL query exceeds Grafana's per-query timeout, the panel renders a "query timeout — narrow time range" hint rather than a blank panel; the default 1-hour time range is intentionally narrow per FR-542 to avoid this for everyday operations.
- **Source map availability for frontend errors**: If source maps are not deployed alongside the production bundle (e.g., disabled in a privacy-conscious build), the Frontend Web Logs dashboard renders the minified stack trace with a clear "source maps unavailable" hint rather than a misleading line number.
- **Audit chain anomaly alert**: When the `AuditChainAnomaly` Loki alert fires (chain mismatch or hash invalid pattern in audit-service logs), it auto-routes to feature 080's incident-response system via the existing `IncidentTriggerInterface` so the security incident becomes a tracked incident with the standard runbook surfacing.
- **Cost-anomaly cross-feature integration**: When the `CostAnomalyLogged` Loki alert fires (cost-anomaly pattern in cost-governance logs), it correlates with feature 079's existing cost-anomaly tracking; the dashboard cross-references the two surfaces (the alert is the early-warning signal; the cost-governance BC's anomaly record is the durable artifact).
- **Per-locale dashboard rendering** (cross-feature with 083): dashboard panel titles, descriptions, and labels are rendered server-side by Grafana; user-facing text on the dashboards is currently English-only (Grafana's i18n is limited). The 6-locale promise from feature 083 covers the application UI, NOT Grafana. Documented as out-of-scope here so users don't expect Grafana to be localised.
- **Tenant-scoped retention overrides**: A tenant requiring longer retention (e.g., regulatory 7-year audit) configures their tenant-specific retention via Helm values; the per-tenant override is documented and enforced at the Loki level (Loki supports per-tenant limits).
- **Service that emits to stderr with non-JSON output (e.g., a Python startup error)**: such logs reach Loki tagged `level=error` with a missing-field warning; the operator sees them but the structured-log alert fires so the service's stderr handling is fixed.

## Requirements *(mandatory)*

### Functional Requirements

**Log Aggregation Backend (FR-533)**

- **FR-533.1**: Platform MUST deploy Grafana Loki in the `platform-observability` namespace as the centralized log aggregation backend.
- **FR-533.2**: Loki MUST use S3-compatible object storage (the generic S3 client per constitutional Principle XVI) for chunk storage, enabling retention beyond what in-cluster disk supports.
- **FR-533.3**: Loki MUST be reachable only from within the cluster; external access is exclusively via the Grafana proxy.
- **FR-533.4**: Loki ingestion MUST be best-effort from the application's perspective: a Loki outage MUST NOT cause application service failures (constitution Integration Constraint).

**Log Collection (FR-534)**

- **FR-534.1**: Platform MUST deploy Promtail as a DaemonSet on every node.
- **FR-534.2**: Promtail MUST auto-discover pods in all platform namespaces (`platform-control`, `platform-execution`, `platform-simulation`, `platform-data`, `platform-observability`, plus the namespace where the frontend is deployed — to be confirmed during planning; the brownfield input named `platform-ui` but the canonical namespace list in the constitution does not include this name).
- **FR-534.3**: Promtail MUST run as non-root with read-only access to log paths.
- **FR-534.4**: Promtail MUST be best-effort: a Promtail pod failure MUST NOT crash the node (constitution Integration Constraint).

**Structured Logging Contract (FR-535)**

- **FR-535.1**: All platform services (Python control plane, Go satellites, Next.js frontend) MUST emit structured JSON logs to stdout.
- **FR-535.2**: Required fields per log entry: `timestamp` (ISO 8601), `level` (`debug|info|warn|error|fatal`), `service`, `bounded_context`, `message`.
- **FR-535.3**: Conditionally-required fields (when in scope): `trace_id`, `span_id`, `correlation_id`, `workspace_id`, `goal_id`, `user_id`, `execution_id`.
- **FR-535.4**: `trace_id`, `correlation_id`, `workspace_id`, `goal_id`, `user_id` MUST propagate automatically through async boundaries via Python `ContextVars` (control plane), Go `context.Context` (satellites), Next.js request context (frontend server). Manual passing MUST NOT be required in business logic.
- **FR-535.5**: Per constitution rule 22, only `service`, `bounded_context`, `level`, plus the bounded set of `namespace`, `pod`, `container` (set by Promtail from CRI metadata) MAY be promoted to Loki labels. `workspace_id`, `user_id`, `goal_id`, `correlation_id`, `trace_id` MUST live in the JSON payload, NEVER as labels.
- **FR-535.6**: A CI lint check MUST detect any change that promotes a high-cardinality field to a Loki label (e.g., a Promtail pipeline_stages config that adds `workspace_id` to the `labels:` section); the build MUST fail with a clear error pointing at the offending file.

**Retention (FR-536, FR-537)**

- **FR-536.1**: Loki MUST retain logs for at least 14 days hot (in-cluster) and 90 days cold (S3-archived).
- **FR-536.2**: Retention durations MUST be configurable per tenant via Helm values.
- **FR-536.3**: The hot/cold tier transition MUST be transparent to LogQL query authors — a query over a 60-day window returns from both tiers with unified semantics.

**Sensitive-Data Redaction (FR-538)**

- **FR-538.1**: Promtail MUST apply redaction patterns to incoming log lines before shipping to Loki, masking at minimum: bearer tokens (`Bearer <alphanumeric>`), API keys matching common patterns (`sk-...`, `ghp_...`, AWS-key format), email addresses in error contexts, Social Security Numbers, credit-card-like sequences.
- **FR-538.2**: Redaction patterns MUST be additive via Helm values so deployments can extend without forking.
- **FR-538.3**: Redaction failures MUST NOT block ingestion; failures MUST be counted via a Prometheus metric and reported on the Platform Overview dashboard.
- **FR-538.4**: Promtail redaction is the defence-in-depth layer; constitution rule 23 ("secrets never reach logs in the first place") is the authoritative application-layer mandate.

**Grafana Data Source and Linking (FR-539, FR-543)**

- **FR-539.1**: Grafana MUST have Loki preconfigured as a data source alongside the existing Prometheus and Jaeger data sources from feature 047.
- **FR-539.2**: Loki data source MUST configure derived-field linking: a `trace_id` JSON field in a Loki log entry MUST render as a clickable link that opens the corresponding trace in Jaeger.
- **FR-543.1**: A Prometheus metric data point with a label set MUST offer a "View related logs" action that opens Loki filtered by the same labels and time range — closing the metrics-→-logs pivot path of US1.

**Dashboards (FR-540, FR-541, FR-544)**

- **FR-540.1**: Platform MUST provide 5 new log-focused Grafana dashboards: D8 Control Plane Service Logs, D9 Go Satellite Service Logs, D10 Frontend Web Logs, D11 Audit Event Stream, D12 Cross-Service Error Overview.
- **FR-541.1**: Platform MUST provide 9 new metric+log dashboards covering the audit-pass bounded contexts: D13 Privacy & Compliance, D14 Security Compliance, D15 Cost Governance, D16 Multi-Region Operations, D17 Model Catalog & Fallback, D18 Notifications Delivery, D19 Incident Response & Runbooks, D20 Goal Lifecycle & Agent Responses, D21 Governance Pipeline.
- **FR-541.2**: All 14 new dashboards MUST support time range selection, workspace filter variable, and auto-refresh (default 30 seconds).
- **FR-541.3**: All 14 new dashboards MUST load and render initial data within 5 seconds on seeded demo data.
- **FR-541.4**: Default time range MUST be one hour (prevents accidental expensive 90-day-scope queries on first dashboard load).
- **FR-544.1**: All new dashboards MUST be provisioned as Kubernetes ConfigMaps with the `grafana_dashboard: "1"` label, consistent with feature 047's pattern (constitution rule 27).
- **FR-544.2**: All new dashboards MUST live under `deploy/helm/observability/templates/dashboards/` per the unified Helm bundle pattern.

**Loki-Based Alerts (FR-542)**

- **FR-542.1**: Platform MUST define Loki ruler-based alert rules for: high error log rate (>100/min for a service), security event spike (DLP violations, failed auth, JIT overuse), audit chain anomaly (gap or hash mismatch), cost anomaly (from feature 079's cost-governance attribution logs).
- **FR-542.2**: Alerts MUST route through the existing Alertmanager configuration from feature 047; this feature does NOT introduce a parallel alert pipeline.
- **FR-542.3**: The audit chain anomaly alert MUST integrate with feature 080's `IncidentTriggerInterface` so a chain anomaly produces a tracked incident with a runbook surfacing.
- **FR-542.4**: The cost anomaly alert MUST correlate with feature 079's existing cost-anomaly tracking; both surfaces show the same condition (the alert is the log-pattern early-warning; the cost-governance BC's anomaly record is the durable artifact).

**Log-Volume Observability (FR-545)**

- **FR-545.1**: Log volume MUST be metric-exposed via Prometheus: logs per second per service, bytes per second per service, rejected-log count per service.
- **FR-545.2**: Operators MUST be able to detect log flooding (a service emitting orders of magnitude more than its baseline) on the Platform Overview dashboard.
- **FR-545.3**: Log-volume metrics MUST be kept in Prometheus (NOT in Loki itself) to avoid the meta-logging-pollution loop (Loki's own storage volume is itself observed by Prometheus).

**Cross-Cutting**

- **FR-CC-1**: This feature does NOT replace Jaeger for traces (Jaeger remains the trace backend per constitutional AD-23). Loki correlates to Jaeger via `trace_id`.
- **FR-CC-2**: This feature does NOT introduce APM beyond what OTEL already provides via feature 047.
- **FR-CC-3**: This feature does NOT add a dedicated log-search product outside Grafana — all log querying is via Grafana Explore with LogQL.
- **FR-CC-4**: This feature does NOT build a custom log schema — uses Loki's label + JSON-payload model per constitution rule 22 + AD-22.
- **FR-CC-5**: All 14 new dashboards MUST integrate with the existing Grafana RBAC inherited from feature 047; no parallel auth path.
- **FR-CC-6**: Loki ingestion MUST NOT cause regression in feature 047's 7 existing dashboards (Platform Overview, Workflow Execution, Reasoning Engine, Data Stores, Fleet Health, Cost Intelligence, Self-Correction). Existing dashboards MAY be additively enhanced with log panels but their core metric panels MUST remain functional.
- **FR-CC-7**: The constitutional feature flags `FEATURE_STRUCTURED_LOGGING` (always on per constitution line 892), `FEATURE_LOKI_ENABLED` (line 893, default true, superadmin-toggleable), `FEATURE_PROMTAIL_REDACTION` (line 894, default true, superadmin-toggleable) MUST gate the relevant subsystems so a deployment can disable Loki ingestion or Promtail redaction without code changes.
- **FR-CC-8**: All structured-logging libraries (Python `common/logging.py`, Go `internal/logging/logging.go`, Next.js `lib/logging.ts`) MUST share a common contract — same field names, same level set, same correlation propagation pattern — so a log entry from any service is interpretable uniformly across the three runtimes.

### Key Entities

- **Log Stream**: A sequence of log entries from a single Promtail target. Carries the constitutional low-cardinality labels (`service`, `bounded_context`, `namespace`, `pod`, `container`, `level`) and a series of timestamped JSON-payload entries with the conditionally-required correlation fields (`workspace_id`, `goal_id`, `correlation_id`, `trace_id`, `user_id`, `execution_id` when in scope). Retained per the hot/cold retention policy.
- **Loki Alert Rule**: A LogQL expression evaluated by the Loki ruler periodically. Has name, expression, for-duration, severity, alert labels, and annotation template. Managed via `LokiRule` CRD or ConfigMap.
- **Dashboard Variable**: A dropdown filter at the top of a dashboard (e.g., workspace, service, severity). Bound to a data-source query (e.g., `label_values(service)`) so filters auto-populate from current data.
- **Correlated View**: A Grafana dashboard panel that queries both metrics (Prometheus) and logs (Loki) for the same time range with the same label filters, rendering them on a synchronized timeline.
- **Dashboard ConfigMap**: A Kubernetes ConfigMap with the `grafana_dashboard: "1"` label per constitution rule 27, containing the dashboard JSON. Provisioned via the unified Helm bundle at `deploy/helm/observability/templates/dashboards/`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Loki + Promtail are deployed in `platform-observability` namespace via the existing Helm chart and pass deployment health checks — verified by automated post-install assertion.
- **SC-002**: Logs from all platform services (control plane, all four Go satellites, frontend server + client) reach Loki within 15 seconds of emission with the constitutionally-mandated structured fields populated — verified by an end-to-end synthetic-log test.
- **SC-003**: Grafana Explore queries against `{service=<X>, level="error"}` over a 1-hour window return matching logs in ≤ 3 seconds p95 — verified by automated query-latency assertion.
- **SC-004**: A Loki log entry that carries a `trace_id` JSON field renders the corresponding trace in Jaeger via the derived-field link — verified by automated UI test.
- **SC-005**: A Prometheus metric data point on any dashboard offers a "View related logs" action that opens Loki filtered by the same labels and time range — verified by automated UI test.
- **SC-006**: Promtail redacts the documented sensitive patterns (bearer tokens, API keys, email addresses in error contexts, SSNs, credit-card-like sequences) before logs reach Loki — verified by injecting test patterns and confirming they're masked at the Loki side.
- **SC-007**: All 5 log-focused dashboards (D8–D12) render with real data on a seeded deployment and load in ≤ 5 seconds p95 — verified by automated load-time assertion across all panels.
- **SC-008**: All 9 new metric+log dashboards (D13–D21) render with real data on a seeded deployment and load in ≤ 5 seconds p95 — verified by automated load-time assertion across all panels.
- **SC-009**: All 5 new Loki alert rules fire correctly under synthetic conditions — verified by an automated alert-firing test (inject the trigger condition, assert the alert reaches Alertmanager).
- **SC-010**: Hot retention of 14 days is verified by ingesting a log entry, advancing the test clock 13 days, querying it, advancing 2 more days, querying again and confirming it has aged out per the policy.
- **SC-011**: Cold retention of 90 days is verified by an analogous test against the S3-archived tier.
- **SC-012**: Log-volume metrics (logs per second per service, bytes per second per service, rejected-log count) are exposed via Prometheus and visible on the Platform Overview dashboard — verified by automated metric-presence assertion.
- **SC-013**: No regression in feature 047's 7 existing dashboards — verified by re-running feature 047's existing dashboard tests against the post-feature build.
- **SC-014**: A CI lint check rejects any change that promotes a high-cardinality field (`workspace_id`, `user_id`, `goal_id`, `correlation_id`, `trace_id`) to a Loki label per constitution rule 22 — verified by a deliberate-violation test (the build must fail).
- **SC-015**: The structured-logging contract is consistent across the three runtimes (Python control plane, Go satellites, Next.js frontend) — verified by a cross-runtime log-shape test that emits the same logical event from all three and asserts the resulting Loki entries have identical field shapes.

## Assumptions

- Feature 047 (existing observability stack: Prometheus, Grafana, Jaeger, Alertmanager, OTEL Collector, 7 baseline dashboards) is already deployed; this feature *extends* the existing stack rather than replacing any component.
- The audit-pass bounded contexts whose dashboards this feature delivers (privacy_compliance from UPD-023, security_compliance from UPD-024, cost_governance from UPD-027 / feature 079, multi_region_ops from UPD-025 / feature 081, model_catalog from UPD-026, notifications from UPD-028 / feature 077, incident_response from UPD-031 / feature 080, goals lifecycle from UPD-007/UPD-059, governance pipeline from UPD-005/UPD-061) are merged at the time this feature lands. The plan phase will verify each BC's existence; missing BCs cause their dashboards to ship with `no data` empty states until the BC is delivered (acceptable per FR-541's empty-state handling).
- The platform's existing generic-S3 client (Principle XVI) is the storage backend for Loki chunks; the `platform-loki-chunks` bucket is reserved (constitution § Observability Extension).
- The frontend is `apps/web/` (NOT `apps/ui/` as some brownfield inputs have said in prior features).
- The brownfield input nominated `platform-ui` as the namespace where the frontend is deployed for Promtail's autodiscovery; the constitutional namespace list (Constitution § Kubernetes Namespaces) does not include this name. The plan phase will confirm the actual frontend-deployment namespace and adjust the Promtail autodiscovery list accordingly. If the frontend currently deploys to `platform-control` (BFF-style), no separate `platform-ui` discovery is needed.
- Loki is deployed in single-binary mode for v1 (per the brownfield input's Helm config); HA mode is a future concern. Multi-region deployments use one Loki instance per region per FR-CC discussion + feature 081's contract.
- Grafana's i18n is limited; this feature's dashboards are English-only at v1, NOT one of the six locales delivered by feature 083. Documented loudly in the spec edge cases so users don't expect Grafana to be localised.
- Source maps are deployed alongside the production frontend bundle (so the Frontend Web Logs dashboard's source-map-applied stack traces are meaningful); if a deployment opts out of source maps, the dashboard renders the minified trace with a clear hint.
- The platform's existing CI pipeline (per feature 046 / `cicd-pipeline`) is the host for the new lint check that enforces rule 22 (no high-cardinality Loki labels).
- The audit chain integrity check that drives the D14 panel and the `AuditChainAnomaly` alert is the same scheduled verify run from UPD-024's audit chain BC; this feature reads its result, doesn't compute it.
- The dashboard inventory (D8 through D21) is fixed at v1; adding more dashboards is a future-additive change governed by constitution rule 24.

## Out of Scope (v1)

- **Replacing Jaeger for traces.** Jaeger remains the trace backend per constitutional AD-23. Loki correlates via `trace_id`.
- **APM (application performance monitoring) beyond what OTEL already provides.** The existing Prometheus + Jaeger + Loki triumvirate is the platform's observability primitive set per AD-23.
- **A new tracing backend (Tempo migration).** Out of scope at v1; Jaeger continues unchanged.
- **A dedicated log-search product outside Grafana.** All log querying is via Grafana Explore with LogQL.
- **Custom log schema beyond Loki's label + JSON-payload model.** No proprietary indexing.
- **Loki HA mode.** Single-binary deployment at v1; HA is a future concern.
- **Grafana dashboard localisation across the six locales of feature 083.** Grafana's i18n is limited; dashboards are English-only at v1.
- **Cross-tenant log search.** Each tenant's log data is scoped to that tenant via the existing Loki multi-tenancy mechanism.
- **Alerting on dashboard panels themselves (vs. on Loki ruler rules or Prometheus rules).** Grafana 11+ supports panel-based alerts but this feature uses the Loki ruler + the existing Alertmanager exclusively for consistency with feature 047's pattern.
- **Real user monitoring (RUM) for the frontend beyond the in-app error reporter.** Comprehensive RUM (page load timings, navigation traces, vitals) is a separate scope.
- **A log-replay or log-time-travel surface.** Logs are query-only via LogQL.
- **Log-based cost-attribution.** Cost attribution lives in feature 079's cost-governance BC; the cost-governance dashboard (D15) reads from there, not from logs.
- **Service-mesh sidecar log collection** (e.g., Envoy access logs as a separate Loki stream). Service-mesh logs reach Loki via the same Promtail pod-discovery as application logs; no special path.

## Dependencies and Brownfield Touchpoints

This feature is additive to the existing platform. The relevant existing capabilities the feature relies on or extends:

- **Constitution § "Observability Extension (UPD-034 and UPD-035)"** — explicitly names this feature (UPD-034) as the canonical observability extension; the constitutional definition of "Loki + Promtail + 14 new dashboards + unified Helm bundle" is implemented here.
- **Feature 047 — Observability Stack** — the existing Prometheus + Grafana + Jaeger + Alertmanager + OTEL Collector deployment in `platform-observability`. This feature *extends* feature 047 additively; no replacement.
- **Constitution § Kubernetes Namespaces** — `platform-observability` is the deployment target. The brownfield input mentioned `platform-ui` for frontend log collection; the constitution's canonical namespace list does not include this name — the plan phase will confirm the actual frontend-deployment namespace.
- **Constitution rule 20 (structured JSON logs)** + **AD-22 (structured JSON logs only)** — this feature is the canonical implementation; the rule presumes this exists.
- **Constitution rule 22 (Loki labels low-cardinality only)** — this feature delivers the CI enforcement (a small lint check against the Promtail pipeline_stages config) per FR-535.6 + SC-014.
- **Constitution rule 24 (every new BC dashboard)** — this feature is the canonical fulfilment for the 9 audit-pass bounded contexts (D13–D21).
- **Constitution rule 27 (dashboards as ConfigMaps via unified Helm bundle)** — this feature follows the rule exactly per FR-544.
- **Constitution rule 23 (secrets never reach logs)** — application-layer mandate; Promtail redaction is the defence-in-depth layer per FR-538.4.
- **Constitution AD-23 (Loki for logs / Jaeger for traces / Prometheus for metrics)** — this feature implements the Loki side of AD-23.
- **Constitutional feature flags `FEATURE_STRUCTURED_LOGGING`, `FEATURE_LOKI_ENABLED`, `FEATURE_PROMTAIL_REDACTION`** (lines 892–894) — already declared. This feature wires their runtime gates per FR-CC-7.
- **Feature 077 (notifications)** — `Alertmanager` configuration from feature 047 routes alerts; the cost / DLP / audit-chain alerts can additionally route through the multi-channel notification subsystem if configured.
- **Feature 079 (cost-governance)** — D15 reads from the cost-governance BC's existing storage; the `CostAnomalyLogged` alert correlates with feature 079's anomaly tracking per FR-542.4.
- **Feature 080 (incident-response)** — the `AuditChainAnomaly` alert routes through `IncidentTriggerInterface` per FR-542.3.
- **Feature 081 (multi-region-ops)** — D16 reads from the multi-region-ops BC; multi-region log federation uses the Loki `region` label per the brownfield input + constitution.
- **Feature 083 (accessibility-i18n)** — Grafana dashboards are NOT localised at v1; documented in Out of Scope so the feature 083 promise is not extended into Grafana.
- **Feature 046 (CI/CD pipeline)** — hosts the new lint check enforcing rule 22.
- **Constitutional bucket reservation** — `platform-loki-chunks` is reserved per Constitution § Observability Extension.
- **Existing audit chain (UPD-024)** — D11 (Audit Event Stream) reads from the existing audit-chain entries via Loki; the chain integrity check on D14 reads from the verify result.
- **Existing OTEL Collector (feature 047)** — stays in the path; `trace_id` propagation via OTEL means Loki entries carry the same `trace_id` Jaeger uses, enabling the FR-539.2 derived-field link.

The implementation strategy (specific Helm chart versions, Promtail pipeline stages, Python `structlog` configuration, Go `slog` ContextHandler, Next.js logging API route, Loki alert LogQL expressions, dashboard JSON layouts, the namespace-confirmation for the frontend) is intentionally deferred to the planning phase. The brownfield input's rich technical detail is preserved verbatim in `planning-input.md` as a reference; the spec stays implementation-agnostic per the speckit conventions established by features 079 onwards.
