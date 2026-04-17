# Data Model: Observability Stack

**Feature**: [spec.md](spec.md)  
**Note**: This feature produces no application database tables. All entities are Kubernetes manifests (Helm chart templates), configuration files, and Prometheus metric definitions.

---

## Helm Chart Structure

### ObservabilityUmbrellaChart

The `deploy/helm/observability/` umbrella chart. One deployment deploys the full stack.

| Field | Value |
|-------|-------|
| `name` | `musematic-observability` |
| `namespace` | `platform-observability` |
| `chart_version` | `0.1.0` |
| `type` | `application` (umbrella) |
| `dependencies` | opentelemetry-collector, kube-prometheus-stack, jaeger |

**Directory layout**:
```
deploy/helm/observability/
├── Chart.yaml                   # Umbrella chart + dependency declarations
├── Chart.lock                   # Locked dependency versions
├── values.yaml                  # Unified override values for all sub-charts
├── templates/
│   ├── namespace.yaml           # platform-observability namespace
│   ├── dashboards/              # Grafana dashboard ConfigMaps (7 files)
│   │   ├── platform-overview.yaml
│   │   ├── workflow-execution.yaml
│   │   ├── reasoning-engine.yaml
│   │   ├── data-stores.yaml
│   │   ├── fleet-health.yaml
│   │   ├── cost-intelligence.yaml
│   │   └── self-correction.yaml
│   └── alerts/                  # PrometheusRule CRDs (5 files)
│       ├── service-alerts.yaml
│       ├── kafka-alerts.yaml
│       ├── execution-alerts.yaml
│       ├── reasoning-alerts.yaml
│       └── fleet-alerts.yaml
└── charts/                      # Downloaded by helm dependency build
```

---

## Sub-Chart Configuration Entities

### OTELCollectorConfig

Configuration values for the OpenTelemetry Collector sub-chart.

| Parameter | Value | Description |
|-----------|-------|-------------|
| `mode` | `deployment` | Gateway mode, not DaemonSet |
| `replicaCount` | `2` | Basic HA |
| `receivers.otlp.grpc.endpoint` | `0.0.0.0:4317` | gRPC OTLP receiver |
| `receivers.otlp.http.endpoint` | `0.0.0.0:4318` | HTTP OTLP receiver |
| `processors.memory_limiter.limit_mib` | `400` | Hard memory cap |
| `processors.batch.send_batch_size` | `1000` | Batch export size |
| `processors.batch.timeout` | `10s` | Max batch wait |
| `exporters.prometheus.endpoint` | `0.0.0.0:8889` | Metrics scrape endpoint |
| `exporters.otlp_jaeger.endpoint` | `musematic-observability-jaeger-collector:4317` | Trace export |
| `service.pipelines.traces` | `otlp → [memory_limiter, batch] → otlp_jaeger` | Trace pipeline |
| `service.pipelines.metrics` | `otlp → [memory_limiter, batch] → prometheus` | Metrics pipeline |

---

### PrometheusConfig

Configuration values for kube-prometheus-stack Prometheus.

| Parameter | Value | Description |
|-----------|-------|-------------|
| `scrapeInterval` | `15s` | Metric collection frequency |
| `retention` | `15d` | Local storage retention |
| `storageSize` | `20Gi` | PVC size |
| `ruleSelector` | label: `prometheus: musematic` | PrometheusRule CRD selector |
| `podMonitorNamespaceSelector` | all platform namespaces | Namespace scope |
| `serviceMonitorNamespaceSelector` | all platform namespaces | Namespace scope |

---

### GrafanaConfig

Configuration values for the Grafana instance included in kube-prometheus-stack.

| Parameter | Value | Description |
|-----------|-------|-------------|
| `defaultDatasource` | Prometheus (built-in) | Default query source |
| `jaeger_datasource.url` | `http://musematic-observability-jaeger-query:16686` | Trace drill-down |
| `sidecar.dashboards.enabled` | `true` | Watch ConfigMaps for dashboards |
| `sidecar.dashboards.label` | `grafana_dashboard: "1"` | ConfigMap label to watch |
| `sidecar.dashboards.searchNamespace` | `platform-observability` | Dashboard namespace |
| `adminUser` | `admin` | Default admin user |
| `adminPassword` | (via Kubernetes Secret) | Not in values.yaml |

---

## Dashboard Entity

Each dashboard is a Grafana JSON model stored as a Kubernetes ConfigMap.

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Dashboard display name |
| `uid` | string | Stable dashboard UID for linking |
| `panels` | Panel[] | Visualization panels |
| `templating.list` | Variable[] | Filter dropdowns (time range, namespace, workspace) |
| `refresh` | string | Auto-refresh interval (e.g., `30s`) |
| `time.from` | string | Default time range start (e.g., `now-1h`) |

### Dashboard Definitions

| Dashboard | uid | Primary metrics | Filter variables |
|-----------|-----|-----------------|-----------------|
| Platform Overview | `platform-overview` | service_up, http_request_total, http_request_duration_seconds | namespace |
| Workflow Execution | `workflow-execution` | execution_active_total, execution_step_duration_seconds, execution_failures_total | workspace |
| Reasoning Engine | `reasoning-engine` | budget_decrements_total, correction_iterations_total (outcome), mode_selections_total, tot_branches_total | workspace |
| Data Stores | `data-stores` | pg_up, redis_connected_clients, qdrant_collections_total, kafka_consumer_lag | store |
| Fleet Health | `fleet-health` | fleet_status_count, fleet_member_health_count, degraded_operations_total | fleet_id |
| Cost Intelligence | `cost-intelligence` | cost_per_agent_total, cost_per_workspace_total, cost_per_model_total | workspace, model |
| Self-Correction | `self-correction` | correction_convergence_rate, correction_iterations_avg, correction_cost_total | workspace |

---

## Alert Rule Entity

Each alert rule is a `PrometheusRule` CRD entry.

| Field | Type | Description |
|-------|------|-------------|
| `alert` | string | Alert name |
| `expr` | string | PromQL expression |
| `for` | duration | Time condition must hold before firing |
| `severity` | label | `critical`, `warning`, `info` |
| `summary` | annotation | Human-readable condition description |
| `description` | annotation | Full description with metric values |
| `dashboard_url` | annotation | Link to relevant Grafana dashboard |
| `runbook_url` | annotation | Link to ops runbook (optional) |

### Alert Rule Inventory

| Alert Name | Severity | For | Expression (abbreviated) |
|------------|----------|-----|--------------------------|
| `ServiceDown` | critical | 5m | `up == 0` |
| `HighErrorRate` | warning | 5m | `rate(http_requests_total{code=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.05` |
| `KafkaConsumerLagHigh` | warning | 10m | `kafka_consumer_lag_sum > 1000` |
| `KafkaConsumerLagCritical` | critical | 5m | `kafka_consumer_lag_sum > 10000` |
| `ExecutionFailureSpike` | warning | 5m | `increase(execution_failures_total[5m]) > 10` |
| `BudgetExhaustionSpike` | warning | 5m | `increase(budget_exhaustion_total[5m]) > 5` |
| `SelfCorrectionNonConvergence` | warning | 15m | `rate(correction_nonconvergence_total[5m]) > 0.1` |
| `FleetDegradedOperation` | warning | 10m | `fleet_status{status="degraded"} > 0` |

---

## Kafka Trace Context Entity

Represents the trace propagation structure added to Kafka message headers.

| Header Key | Type | Description |
|------------|------|-------------|
| `traceparent` | string | W3C Trace Context traceparent (version-trace_id-parent_id-flags) |
| `tracestate` | string | W3C Trace Context vendor-specific state (may be empty) |
| `correlation_id` | string | Platform correlation ID (already present in EventEnvelope) |

**New file**: `apps/control-plane/src/platform/common/kafka_tracing.py`  
**Functions**:
- `inject_trace_context(headers: dict[str, bytes]) -> dict[str, bytes]` — injects W3C context into headers dict
- `extract_trace_context(headers: dict[str, bytes]) -> opentelemetry.context.Context` — extracts parent context from headers

---

## Service OTEL Configuration

Each service chart's `values.yaml` needs these environment variables added:

| Service | Helm chart | Env vars to add |
|---------|-----------|-----------------|
| control-plane | `deploy/helm/control-plane/values.yaml` | `OTEL_EXPORTER_ENDPOINT=http://otel-collector.platform-observability.svc.cluster.local:4318` |
| reasoning-engine | `deploy/helm/reasoning-engine/values.yaml` | `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector.platform-observability.svc.cluster.local:4317`, `OTEL_SERVICE_NAME=reasoning-engine` |
| runtime-controller | `deploy/helm/runtime-controller/values.yaml` | `OTEL_EXPORTER_OTLP_ENDPOINT=...`, `OTEL_SERVICE_NAME=runtime-controller` |
| sandbox-manager | (chart exists) | `OTEL_EXPORTER_OTLP_ENDPOINT=...`, `OTEL_SERVICE_NAME=sandbox-manager` |
| simulation-controller | `deploy/helm/simulation-controller/values.yaml` | `OTEL_EXPORTER_OTLP_ENDPOINT=...`, `OTEL_SERVICE_NAME=simulation-controller` |

**Code change required for Go services** (runtime-controller, sandbox-manager, simulation-controller): Each needs its `main.go` updated to initialize an OTLP gRPC exporter when `OTEL_EXPORTER_OTLP_ENDPOINT` is set — replacing the current no-op `tracesdk.TracerProvider()` initialization. The reasoning-engine already uses `otelgrpc.NewServerHandler()` but needs an OTLP metric exporter initialized for its metrics to be collected.
