# Planning Input — UPD-034: Log Aggregation and Comprehensive Dashboards

> Verbatim brownfield input that motivated this spec. Preserved here as a
> planning artifact. The implementation strategy (specific Helm chart
> versions, code samples, Promtail pipeline stages, alert rule LogQL
> expressions) is intentionally deferred to the planning phase. This
> file is a planning input, not a contract.

## Brownfield Context

**Extends:** Feature 047-observability-stack (Prometheus, Grafana, Jaeger, Alertmanager, OTEL Collector, 7 existing domain dashboards)
**New subsystem:** Grafana Loki + Promtail for centralized log aggregation
**New dashboards:** 14 additional Grafana dashboards (5 log-based + 9 metric-based for audit-pass bounded contexts)
**FRs:** FR-533 through FR-545 (new)

## Background

Feature 047 explicitly listed **log aggregation** as Out of Scope: the existing stack covers metrics (Prometheus) and traces (Jaeger) but does not collect, index, or search logs. The 7 pre-built dashboards in 047 cover the platform baseline (overview, workflow execution, reasoning engine, data stores, fleet health, cost intelligence, self-correction), but none of the 6 new bounded contexts introduced by the audit pass (UPD-023 through UPD-033) have dedicated dashboards.

This feature closes both gaps in a single coordinated feature:

1. Adds **Grafana Loki** as the log aggregation backend, wired into the existing `platform-observability` namespace.
2. Deploys **Promtail** as a DaemonSet to collect logs from every node.
3. Adds structured-logging discipline across the control plane (Python) and satellite services (Go) so that logs are indexable by `service`, `bounded_context`, `workspace_id`, `goal_id`, `trace_id`, `correlation_id`, and `user_id`.
4. Adds **Grafana log visualization panels** (using the Loki data source) integrated into existing dashboards and as dedicated log dashboards.
5. Adds **14 new Grafana dashboards** covering the 6 new bounded contexts plus 5 log-focused views.
6. Adds **Loki-based alerts** for log patterns (error spikes, security events, DLP hits, audit chain anomalies).

## Non-Goals

- Not replacing Jaeger for traces — Jaeger remains the trace backend; Loki correlates via `trace_id` labels.
- Not adding APM / application performance monitoring beyond what OTEL already provides.
- Not introducing a new tracing backend (no Tempo migration in this feature).
- Not a dedicated log search product outside Grafana — all log querying is via Grafana Explore with LogQL.
- Not building a custom log schema — uses Loki's label + JSON payload model.

---

## User Scenarios

### User Story 1 — Operator investigates a failing execution via logs (Priority: P1)

An operator sees a spike in `execution.failure_spike` alerts. They open the **Platform Overview** dashboard, click on the red service indicator, and a linked panel shows the most recent error logs from that service with their `correlation_id`. Clicking a log entry opens Grafana Explore with the log line pre-filtered by `correlation_id`, and adjacent traces and metrics auto-load. The operator identifies a third-party API timeout as the root cause in under 3 minutes.

**Independent Test:** Trigger a controlled execution failure. Verify the failing log line appears in Loki within 15 seconds with `service`, `workspace_id`, `correlation_id` labels. Verify the Platform Overview dashboard links to filtered logs.

**Acceptance:**
1. Logs from all control plane and Go services reach Loki within 15 seconds of emission.
2. Grafana Explore with `{service="control-plane", level="error"}` returns matching logs within 3 seconds for a 1-hour window.
3. Log entries carry `correlation_id`, `trace_id`, `workspace_id`, `goal_id`, `user_id` as Loki labels or JSON fields.
4. Clicking a log entry with a `trace_id` opens the corresponding trace in Jaeger.

### User Story 2 — Compliance officer audits privacy events (Priority: P1)

A compliance officer opens the **Privacy & Compliance** dashboard. They see: a timeline of data subject requests received/completed, DLP events grouped by classification (PII/PHI/financial/confidential), residency violation attempts, PIA approvals pending review, and a pie chart of consent grants by type. They filter by date range and workspace. Each panel links to Loki for the underlying log stream.

**Independent Test:** Submit a test DSR, trigger a DLP event, and create a PIA. Verify all three appear in the Privacy & Compliance dashboard within 1 minute.

**Acceptance:**
1. Privacy & Compliance dashboard shows all 5 required panels with real data.
2. Time range filter applies to all panels simultaneously.
3. Drill-down from any panel opens Loki with appropriate filters.
4. Dashboard loads in under 5 seconds.

### User Story 3 — Security officer reviews supply chain and rotations (Priority: P1)

A security officer opens the **Security Compliance** dashboard. They see: latest SBOM publication status, CVE counts by severity from the last scan, pen test findings grouped by remediation status, upcoming secret rotations (next 30 days), active JIT credential grants, and an audit chain integrity check result. All panels are source-linked (click to open the originating log stream or evidence record).

**Independent Test:** Publish an SBOM, record a scan result with a known CVE, schedule a secret rotation, and issue a JIT grant. Verify each is reflected in the Security Compliance dashboard.

**Acceptance:**
1. Security Compliance dashboard loads with all 6 panels.
2. CVE severity breakdown matches `security_compliance.vulnerability_scan_results` table.
3. Audit chain integrity panel shows ✓ or ✗ reflecting the current verification state.

### User Story 4 — Developer debugs frontend errors (Priority: P2)

A developer investigates a client-side error reported by a user. They open the **Frontend Web Logs** dashboard, filter by the user's `user_id`, and see: client-side JavaScript errors (captured via error reporting), server-side Next.js logs, and correlated API errors from the control plane — all on a single timeline. The dashboard shows the full flow from client action to backend error.

**Independent Test:** Trigger a known frontend error tied to a user action. Verify the error appears in Frontend Web Logs correlated with the corresponding backend API call.

**Acceptance:**
1. Frontend Web Logs dashboard includes panels for client errors, server logs, and correlated API responses.
2. Filtering by `user_id` narrows all panels simultaneously.
3. Source maps are applied to stack traces.

### User Story 5 — Operator responds to governance enforcement storm (Priority: P2)

An operator sees a spike in governance enforcement alerts. They open the **Governance Pipeline** dashboard and see the Observer → Judge → Enforcer flow in real time: signal volume, verdict rate, enforcement action distribution (block, notify, revoke, escalate), and per-chain latency. They drill down on the chain with the most enforcement actions and see individual verdicts with their rationale. The operator identifies a misconfigured observer agent as the cause.

**Independent Test:** Trigger 10 policy violations across 3 workspaces. Verify the Governance Pipeline dashboard reflects the signals → verdicts → actions within 30 seconds.

**Acceptance:**
1. Governance Pipeline dashboard shows real-time (refresh ≤ 15s) signal/verdict/action flow.
2. Per-chain drill-down with verdict detail is available.
3. Top offending agents and workspaces are ranked.

---

### Edge Cases

- **Loki disk full:** Log ingestion is rate-limited, old logs are aged out per retention policy (default 14 days hot / 90 days cold via S3). Ingestion failures are reported on the Platform Overview dashboard.
- **Promtail pod failure:** Kubernetes restarts the DaemonSet pod; in-flight logs may be replayed from journal. Gap indicators appear in dashboards.
- **Structured logging violations:** Services that emit unstructured logs still reach Loki but with limited labels; an alert fires on logs missing required fields (`service`, `timestamp`, `level`).
- **Dashboard panel no-data:** Panels display "no data" rather than errors when their query returns empty.
- **Cross-cluster correlation:** In multi-region deployments (UPD-025), Loki is per-region; Grafana federates across regions using Loki's `{region="primary|secondary"}` label.
- **Sensitive data in logs:** Promtail scrubs known patterns (bearer tokens, API keys, emails, SSNs) before shipping to Loki via `pipeline_stages`. DLP rules (UPD-023) still apply to application-layer outputs.

---

## Requirements

### Functional Requirements

- **FR-533**: Platform MUST deploy Grafana Loki in the `platform-observability` namespace, configured with S3-compatible object storage backend (reusing the generic S3 client from UPD-019).
- **FR-534**: Platform MUST deploy Promtail as a DaemonSet on every node, with PodMonitor-style autodiscovery of platform namespaces (`platform-control`, `platform-execution`, `platform-simulation`, `platform-data`, `platform-observability`, `platform-ui`).
- **FR-535**: All platform services MUST emit structured JSON logs to stdout with at minimum: `timestamp` (ISO 8601), `level` (debug|info|warn|error|fatal), `service`, `bounded_context`, `message`. Optional but recommended: `trace_id`, `span_id`, `correlation_id`, `workspace_id`, `goal_id`, `user_id`, `execution_id`.
- **FR-536**: Loki MUST retain logs for at least 14 days hot (in-cluster) and 90 days cold (S3 archived). Retention configurable per tenant.
- **FR-537**: Promtail MUST redact known sensitive patterns (bearer tokens, API keys matching common formats, email addresses in error contexts, SSNs) before shipping logs to Loki.
- **FR-538**: Grafana MUST have the Loki data source preconfigured alongside the existing Prometheus and Jaeger data sources.
- **FR-539**: The platform MUST provide 5 new log-focused dashboards: Control Plane Service Logs, Go Satellite Service Logs, Frontend Web Logs, Audit Event Stream, Cross-Service Error Overview.
- **FR-540**: The platform MUST provide 9 new metric-based dashboards covering the audit-pass bounded contexts: Privacy & Compliance, Security Compliance, Cost Governance, Multi-Region Operations, Model Catalog & Fallback, Notifications Delivery, Incident Response & Runbooks, Goal Lifecycle & Agent Responses, Governance Pipeline.
- **FR-541**: All 14 new dashboards MUST support time range selection, workspace filter variable, and auto-refresh. All dashboards MUST load within 5 seconds.
- **FR-542**: The platform MUST define new alert rules based on log patterns via Loki ruler: high error log rate (>100/min for a service), security event spike (DLP violations, failed auth, JIT overuse), audit chain anomaly (gap or hash mismatch), and cost anomaly (from UPD-027 attribution logs).
- **FR-543**: Clicking a log entry with a `trace_id` label in Grafana MUST open the corresponding trace in Jaeger. Clicking a metric data point on a dashboard MUST offer a "View related logs" action that opens Loki filtered by the same time range and service.
- **FR-544**: All new dashboards MUST be provisioned as Kubernetes ConfigMaps with the `grafana_dashboard: "1"` label, consistent with feature 047's dashboard delivery pattern.
- **FR-545**: Log volume MUST be metric-exposed (logs per second per service, bytes per second per service, rejected log count) so operators can detect log flooding and manage cardinality.

### Key Entities

- **Log Stream**: A sequence of log entries from a single Promtail target. Has labels (`service`, `bounded_context`, `namespace`, `pod`, `container`, `level`) and a series of timestamped JSON payload entries. Retained per retention policy.
- **Loki Alert Rule**: A LogQL expression evaluated periodically. Has name, expression, for-duration, severity, alert labels, and annotation template. Managed via `LokiRule` CRD or ConfigMap.
- **Dashboard Variable**: A dropdown filter at the top of a dashboard (e.g., workspace, service, severity). Bound to a data-source query (e.g., `label_values(service)`).
- **Correlated View**: A Grafana dashboard panel that queries both metrics and logs for the same time range with the same label filters, rendering them on a synchronized timeline.

---

## Dashboard Inventory

### Log-based dashboards (5 new — NEW capability enabled by Loki)

| # | Dashboard | Purpose | Key Panels |
|---|---|---|---|
| D8 | **Control Plane Service Logs** | Unified view of logs from all Python bounded contexts | Log volume per bounded_context, error rate per BC, recent errors table, filter by workspace/goal/user, log entries timeline with level color-coding |
| D9 | **Go Satellite Service Logs** | Logs from runtime-controller, sandbox-manager, reasoning-engine, simulation-controller | Log volume per service, error rate per service, pod crash correlation, gRPC error patterns |
| D10 | **Frontend Web Logs** | Next.js server logs + client-side error reporting | Client JS errors over time, server-side 5xx responses, correlated API errors, slow page loads, filter by user_id |
| D11 | **Audit Event Stream** | Formatted view of append-only audit chain entries | Real-time audit feed, entries per hour, top actors, hash chain verification status, entries by event type |
| D12 | **Cross-Service Error Overview** | Aggregated error view across all services | Top errors by frequency, error trend (24h), affected services heatmap, error clustering by message, links to traces |

### Metric + log dashboards for new bounded contexts (9 new)

| # | Dashboard | Purpose | Key Panels |
|---|---|---|---|
| D13 | **Privacy & Compliance** (UPD-023) | DSR queue + DLP events + PIA approvals + residency | DSR timeline (received/completed), DSR by type, cascade deletion progress, DLP events by classification, residency violations, PIA pending review, consent grants by type |
| D14 | **Security Compliance** (UPD-024) | SBOM + vulns + pentests + rotations + JIT + audit chain | SBOM publication status, CVE counts by severity, pentest findings by remediation status, upcoming rotations (30d), active JIT grants, audit chain integrity check |
| D15 | **Cost Governance** (UPD-027) | Budgets + chargeback + anomalies + forecasts | Spend over time (hourly/daily/monthly), budget consumption gauge per workspace, cost anomalies feed, end-of-period forecast with confidence intervals, top consumers |
| D16 | **Multi-Region Operations** (UPD-025) | Replication + RPO/RTO + maintenance | Replication lag per component (PG/Kafka/S3/ClickHouse), RPO status gauge, RTO readiness, active maintenance windows, scheduled failover tests |
| D17 | **Model Catalog & Fallback** (UPD-026) | Model usage + fallback events + provider health | Model usage distribution (pie), fallback events per minute, provider health status, per-model latency, per-model cost, deprecated model usage alerts |
| D18 | **Notifications Delivery** (UPD-028) | Multi-channel delivery + webhooks + DLQ | Delivery rate per channel (in-app/email/webhook/Slack/Teams/SMS), webhook delivery status, failed deliveries, DLQ size, retry attempts distribution |
| D19 | **Incident Response & Runbooks** (UPD-031) | Incidents + MTTR + runbooks | Active incidents by severity, MTTR trend, post-mortem status, runbook access frequency, incident by category |
| D20 | **Goal Lifecycle & Agent Responses** (UPD-007, UPD-059) | Goals + agent decisions | Goals in READY/WORKING/COMPLETE, goal completion time distribution, agent response decisions (respond/skip rate per strategy), messages per goal, attention requests |
| D21 | **Governance Pipeline** (UPD-005, UPD-061) | Observer → Judge → Enforcer flow | Observer signal volume, verdict rate, verdicts by type (compliant/violation/ambiguous), enforcement actions (block/notify/revoke/escalate), per-chain latency, top offending agents |

---

## Infrastructure Additions

### Helm chart changes

`deploy/helm/observability/Chart.yaml` — add Loki sub-chart dependency:

```yaml
dependencies:
  - name: loki
    version: "6.16.0"
    repository: https://grafana.github.io/helm-charts
  - name: promtail
    version: "6.16.6"
    repository: https://grafana.github.io/helm-charts
```

`deploy/helm/observability/values.yaml` — add Loki + Promtail config:

```yaml
loki:
  loki:
    auth_enabled: false
    commonConfig:
      replication_factor: 1
    storage:
      type: s3
      s3:
        endpoint: ${S3_ENDPOINT_URL}
        accessKeyId: ${S3_ACCESS_KEY}
        secretAccessKey: ${S3_SECRET_KEY}
        s3ForcePathStyle: true
        bucketnames: platform-loki-chunks
        insecure: ${S3_USE_PATH_STYLE}
    limits_config:
      retention_period: 336h  # 14 days hot
    compactor:
      retention_enabled: true
  singleBinary:
    replicas: 1
    persistence:
      enabled: true
      size: 20Gi

promtail:
  config:
    clients:
      - url: http://observability-loki:3100/loki/api/v1/push
    snippets:
      pipelineStages:
        - cri: {}
        - json:
            expressions:
              timestamp: timestamp
              level: level
              service: service
              bounded_context: bounded_context
              correlation_id: correlation_id
              trace_id: trace_id
              workspace_id: workspace_id
              goal_id: goal_id
              user_id: user_id
              message: message
        - labels:
            level:
            service:
            bounded_context:
        - timestamp:
            source: timestamp
            format: RFC3339
        - replace:
            # Redact bearer tokens
            expression: '(Bearer [A-Za-z0-9\-_]+\.?[A-Za-z0-9\-_]*\.?[A-Za-z0-9\-_]*)'
            replace: '[REDACTED_TOKEN]'
        - replace:
            # Redact API keys matching sk- or similar patterns
            expression: '(sk-[A-Za-z0-9]{32,}|api_key=[A-Za-z0-9]{16,})'
            replace: '[REDACTED_API_KEY]'
  daemonset:
    enabled: true

grafana:
  additionalDataSources:
    - name: Loki
      type: loki
      access: proxy
      url: http://observability-loki:3100
      isDefault: false
      jsonData:
        derivedFields:
          - matcherRegex: 'trace_id=(\\w+)'
            name: TraceID
            url: '$${__value.raw}'
            datasourceUid: jaeger
```

### Structured logging library additions

**Python (control plane):**

`apps/control-plane/src/platform/common/logging.py` — structured JSON logger using `structlog`:

```python
import structlog
from contextvars import ContextVar

# Context variables carrying correlation IDs through async boundaries
_workspace_id: ContextVar[str | None] = ContextVar("workspace_id", default=None)
_goal_id: ContextVar[str | None] = ContextVar("goal_id", default=None)
_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("user_id", default=None)

def configure_logging(service_name: str, bounded_context: str):
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_service_metadata(service_name, bounded_context),
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

def _add_service_metadata(service_name, bounded_context):
    def processor(_, __, event_dict):
        event_dict["service"] = service_name
        event_dict["bounded_context"] = bounded_context
        if v := _workspace_id.get(): event_dict["workspace_id"] = v
        if v := _goal_id.get(): event_dict["goal_id"] = v
        if v := _correlation_id.get(): event_dict["correlation_id"] = v
        if v := _trace_id.get(): event_dict["trace_id"] = v
        if v := _user_id.get(): event_dict["user_id"] = v
        return event_dict
    return processor
```

FastAPI middleware sets the context vars on each request from the EventEnvelope / JWT claims.

**Go (satellite services):**

Use `log/slog` with a custom JSON handler that adds service metadata from an injected context.

```go
// services/runtime-controller/internal/logging/logging.go
package logging

import (
    "context"
    "log/slog"
    "os"
)

type ctxKey string

const (
    workspaceIDKey  ctxKey = "workspace_id"
    goalIDKey       ctxKey = "goal_id"
    correlationKey  ctxKey = "correlation_id"
    traceIDKey      ctxKey = "trace_id"
    userIDKey       ctxKey = "user_id"
)

func Configure(service, boundedContext string) *slog.Logger {
    return slog.New(&ContextHandler{
        Handler: slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
            Level: slog.LevelInfo,
        }),
        service:        service,
        boundedContext: boundedContext,
    })
}

type ContextHandler struct {
    slog.Handler
    service, boundedContext string
}

func (h *ContextHandler) Handle(ctx context.Context, r slog.Record) error {
    r.AddAttrs(
        slog.String("service", h.service),
        slog.String("bounded_context", h.boundedContext),
    )
    for _, key := range []ctxKey{workspaceIDKey, goalIDKey, correlationKey, traceIDKey, userIDKey} {
        if v, ok := ctx.Value(key).(string); ok && v != "" {
            r.AddAttrs(slog.String(string(key), v))
        }
    }
    return h.Handler.Handle(ctx, r)
}
```

**Next.js (frontend):**

`apps/web/lib/logging.ts` — isomorphic structured logger. Server-side writes JSON to stdout. Client-side posts errors to `/api/log/client-error` which writes to stdout server-side with original fields.

```typescript
export interface LogEvent {
  timestamp: string
  level: 'debug' | 'info' | 'warn' | 'error' | 'fatal'
  service: 'web'
  bounded_context: 'frontend'
  message: string
  user_id?: string
  workspace_id?: string
  trace_id?: string
  // Client-only
  url?: string
  user_agent?: string
  stack?: string
}

export const log = {
  info: (msg: string, fields?: Record<string, unknown>) => emit('info', msg, fields),
  warn: (msg: string, fields?: Record<string, unknown>) => emit('warn', msg, fields),
  error: (msg: string, fields?: Record<string, unknown>) => emit('error', msg, fields),
}

function emit(level: string, message: string, fields?: Record<string, unknown>) {
  const event: LogEvent = {
    timestamp: new Date().toISOString(),
    level: level as LogEvent['level'],
    service: 'web',
    bounded_context: 'frontend',
    message,
    ...fields,
  }
  if (typeof window === 'undefined') {
    console.log(JSON.stringify(event))
  } else {
    void fetch('/api/log/client-error', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(event),
    }).catch(() => { /* swallow */ })
  }
}

// Global error boundary
if (typeof window !== 'undefined') {
  window.addEventListener('error', (e) => {
    log.error(e.message, { stack: e.error?.stack, url: window.location.href })
  })
  window.addEventListener('unhandledrejection', (e) => {
    log.error(`Unhandled rejection: ${e.reason}`, { url: window.location.href })
  })
}
```

### New Loki alert rules

`deploy/helm/observability/templates/alerts/loki-alerts.yaml`:

```yaml
apiVersion: loki.grafana.com/v1
kind: AlertingRule
metadata:
  name: platform-log-alerts
  labels:
    prometheus: platform
spec:
  tenantID: application
  groups:
    - name: platform.logs
      interval: 1m
      rules:
        - alert: HighErrorLogRate
          expr: |
            sum by (service) (rate({level="error"}[5m])) > 1.67  # ~100/min
          for: 5m
          labels:
            severity: warning
          annotations:
            summary: "Service {{ $labels.service }} emitting >100 errors/min"
        - alert: SecurityEventSpike
          expr: |
            sum(rate({bounded_context=~"auth|privacy_compliance|security_compliance",level="error"}[5m])) > 0.5
          for: 5m
          labels:
            severity: critical
          annotations:
            summary: "Security-related error spike"
        - alert: DLPViolationSpike
          expr: |
            sum(rate({bounded_context="privacy_compliance",dlp_action="block"}[5m])) > 0.2
          for: 5m
          labels:
            severity: warning
          annotations:
            summary: "DLP blocks exceeding threshold"
        - alert: AuditChainAnomaly
          expr: |
            sum(count_over_time({service="audit",level="error",message=~".*chain.*mismatch.*|.*hash.*invalid.*"}[10m])) > 0
          for: 1m
          labels:
            severity: critical
          annotations:
            summary: "Audit chain integrity anomaly detected"
        - alert: CostAnomalyLogged
          expr: |
            sum(count_over_time({bounded_context="cost_governance",message=~".*anomaly.*detected.*"}[15m])) > 0
          for: 0m
          labels:
            severity: warning
          annotations:
            summary: "Cost anomaly detected in logs"
```

---

## Acceptance Criteria

- [ ] Loki + Promtail deployed in `platform-observability` namespace via Helm chart
- [ ] All platform services emit structured JSON logs with required fields
- [ ] Control plane logs (Python) reach Loki within 15s with all required labels
- [ ] Go satellite logs reach Loki within 15s with all required labels
- [ ] Frontend logs (server + client) reach Loki with `user_id` when authenticated
- [ ] Promtail redacts bearer tokens, API keys, and sensitive patterns
- [ ] Loki data source preconfigured in Grafana
- [ ] All 5 log-focused dashboards render with real data (D8–D12)
- [ ] All 9 new metric dashboards render with real data (D13–D21)
- [ ] Clicking a log entry with `trace_id` opens the trace in Jaeger
- [ ] All 14 new dashboards load in under 5 seconds
- [ ] All 5 Loki alerts fire correctly under synthetic conditions
- [ ] Log retention: 14 days hot verified; S3 archive for 90 days verified
- [ ] Log volume metrics exposed via Prometheus
- [ ] No regression in feature 047's 7 existing dashboards
