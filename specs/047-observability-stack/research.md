# Research: Observability Stack

**Phase**: Phase 0 — Research  
**Feature**: [spec.md](spec.md)

## Decision 1: Helm Chart Architecture — Umbrella vs. Individual Charts

**Decision**: Single umbrella chart at `deploy/helm/observability/` that declares sub-chart dependencies (OTEL Collector, kube-prometheus-stack, Jaeger). Custom templates (Grafana dashboards as ConfigMaps, PrometheusRule CRDs, namespace manifest) live inside the umbrella chart's `templates/`.

**Rationale**: The platform already uses one chart per component. An umbrella chart lets operators deploy the entire observability stack with one `helm upgrade --install` command while still being able to override individual sub-chart values through the top-level `values.yaml`. This matches the pattern of `kube-prometheus-stack` which itself bundles Prometheus + Grafana + Alertmanager. Keeping dashboards and alert rules as templates inside the umbrella (not in sub-charts) gives us full control over their content without forking upstream charts.

**Chart dependencies**:
- `opentelemetry-collector` — `open-telemetry/opentelemetry-helm-charts` (OTEL Collector agent/gateway mode)
- `kube-prometheus-stack` — `prometheus-community/kube-prometheus-stack` (Prometheus + Grafana + Alertmanager, includes CRDs)
- `jaeger` — `jaegertracing/jaeger` (all-in-one mode for moderate scale)

**Alternatives considered**:
- Individual charts per component (separate `deploy/helm/prometheus/`, `deploy/helm/grafana/`, etc.) — more flexibility but requires coordinating 4+ separate deployments and managing cross-chart config (e.g., Grafana data source pointing to Prometheus)
- VictoriaMetrics stack — more memory-efficient than Prometheus but less ubiquitous; Prometheus is the standard

---

## Decision 2: OpenTelemetry Collector Mode

**Decision**: Deploy as a **Deployment** (gateway mode, 2 replicas) rather than a DaemonSet. Services in all namespaces export directly to the collector via OTLP gRPC/HTTP through a Kubernetes Service.

**Rationale**: The platform services are already configured to export to an OTLP endpoint (`OTEL_EXPORTER_ENDPOINT` setting). A gateway deployment behind a ClusterIP Service works with the existing service configuration without requiring DaemonSet scheduling complexity. Two replicas provide basic availability without requiring a load balancer. Gateway mode also allows centralizing pipeline configuration (batching, sampling, memory limits) without touching each service.

**Collector pipeline**:
```
receivers:       otlp (gRPC :4317, HTTP :4318)
processors:      memory_limiter → batch → resource_detection (k8s metadata)
exporters:       prometheus_exporter (:8889) + otlp/jaeger (jaeger-collector:4317)
```

**Service endpoints** (ClusterIP, accessible from all platform namespaces):
- `otel-collector.platform-observability.svc.cluster.local:4317` (gRPC)
- `otel-collector.platform-observability.svc.cluster.local:4318` (HTTP)

**Alternatives considered**:
- DaemonSet (agent mode) — sends per-node but adds scheduler complexity; not needed since services export directly
- Sidecar per pod — very fine-grained but multiplies resource usage; not justified at this platform scale

---

## Decision 3: Prometheus Deployment and Service Discovery

**Decision**: Use `kube-prometheus-stack` which provisions Prometheus Operator alongside Prometheus. Service discovery uses **PodMonitor** and **ServiceMonitor** CRDs that the operator reconciles. The OTEL Collector's prometheus_exporter endpoint is added as a ServiceMonitor.

**Rationale**: `kube-prometheus-stack` is the de-facto Kubernetes Prometheus deployment. The Prometheus Operator's PodMonitor/ServiceMonitor CRD pattern decouples scrape config from the Prometheus deployment — adding a new service to monitoring only requires creating a ServiceMonitor in the right namespace, no Prometheus config file changes. The `metricRelabelings` feature allows filtering high-cardinality labels at the scrape level.

**Namespaces scraped**: `platform-control`, `platform-execution`, `platform-simulation`, `platform-data`, `platform-observability` (self-monitoring)

**Scrape interval**: 15s (overriding the kube-prometheus-stack default of 30s for better dashboard granularity)

**Retention**: 15 days (local Prometheus storage, PVC-backed, sufficient for operational lookback)

**Alternatives considered**:
- Standalone Prometheus with file-based scrape config — brittle; requires Prometheus restart to add new scrape targets
- Thanos for long-term storage — unnecessary overhead for this platform size; 15-day local retention satisfies FR-004's 7-day requirement with headroom

---

## Decision 4: Grafana Dashboard Provisioning

**Decision**: Dashboards are stored as JSON files checked into the repo under `deploy/helm/observability/templates/dashboards/`. They are provisioned via Kubernetes ConfigMaps with the label `grafana_dashboard: "1"` — the Grafana sidecar (`grafana/sidecar`) watches for these ConfigMaps and loads them automatically.

**Rationale**: The `kube-prometheus-stack` chart includes Grafana with the `k8s-sidecar` container that watches for ConfigMaps labeled `grafana_dashboard: "1"` in any namespace and provisions them automatically. This eliminates manual dashboard import and makes dashboards version-controlled. Each of the 7 dashboards is a separate ConfigMap so they can be updated independently.

**Dashboard files** (under `deploy/helm/observability/templates/dashboards/`):
1. `platform-overview.yaml` — service health, request rates, error rates, latency
2. `workflow-execution.yaml` — active executions, step latency, failure rate
3. `reasoning-engine.yaml` — budget utilization, convergence rate, mode distribution, ToT branches
4. `data-stores.yaml` — per-store connection pool, query latency, storage utilization
5. `fleet-health.yaml` — fleet status, member health, degraded operations
6. `cost-intelligence.yaml` — cost per agent/workspace/model, trend lines
7. `self-correction.yaml` — convergence rate, iterations per loop, cost per correction

**Alternatives considered**:
- Grafana Git sync — more flexible but requires additional Git credentials management
- Grafana API provisioning at deploy time — harder to reproduce, requires running Grafana before deploying dashboards

---

## Decision 5: Jaeger Deployment Model

**Decision**: Jaeger All-in-One deployment using the `jaegertracing/jaeger` Helm chart with in-memory storage (for development) and badger storage (for production, persistent PVC). This is a single-pod deployment — not distributed Jaeger.

**Rationale**: Distributed Jaeger (with Cassandra or Elasticsearch backend) is designed for very high trace volumes (millions of spans/day). This platform's expected trace volume at launch is moderate (tens of thousands of spans/day). Jaeger All-in-One with badger persistent storage handles this easily and avoids the operational overhead of a Cassandra or Elasticsearch deployment just for traces. If trace volume exceeds capacity, migrating to a distributed Jaeger with existing OpenSearch (already deployed in `platform-data`) is a clear upgrade path.

**Storage**: BadgerDB with a PersistentVolumeClaim (5 GiB default) — provides 7 days of retention at moderate trace volumes

**Ports**:
- `16686`: Jaeger UI
- `4317` (OTLP gRPC): trace collection from OTEL Collector
- `14269`: health check endpoint

**Alternatives considered**:
- Tempo (Grafana) — excellent for integration with Grafana but requires separate storage; Jaeger is the spec-specified tool
- Distributed Jaeger with OpenSearch backend — reuses existing infrastructure but adds operational coupling between observability and data stores; deferred to future enhancement

---

## Decision 6: Alert Rules Definition Format

**Decision**: Alert rules defined as `PrometheusRule` CRDs in `deploy/helm/observability/templates/alerts/`. Grouped by domain (services, kafka, execution, reasoning, fleet). Managed by Prometheus Operator (part of kube-prometheus-stack).

**Rationale**: `PrometheusRule` CRDs are the standard pattern when using Prometheus Operator. They are version-controlled alongside the chart, can be updated without redeploying Prometheus, and support evaluation intervals and for-durations per rule. The `ruleSelector` in the Prometheus deployment matches rules by namespace and label.

**Alert groups and rules**:
- `platform.services`: service_up (5m for-duration, critical), high_error_rate (>5% for 5m, warning)
- `platform.kafka`: consumer_lag_high (>1000 messages for 10m, warning), consumer_lag_critical (>10000 messages for 5m, critical)
- `platform.execution`: execution_failure_spike (>10 failures/5m for 5m, warning)
- `platform.reasoning`: budget_exhaustion_spike (>5 exhaustion events/5m for 5m, warning), self_correction_nonconvergence (>0.1 non-convergence rate for 15m, warning)
- `platform.fleet`: fleet_degraded_operation (any fleet in degraded state for 10m, warning)

**Alternatives considered**:
- Alertmanager configuration directly (not as CRDs) — works but requires manual Prometheus reload
- External alerting service (PagerDuty, Opsgenie) — routing rules; out of scope for this feature, handled by Alertmanager routes

---

## Decision 7: Trace Context Propagation Through Kafka

**Decision**: Add W3C Trace Context headers (`traceparent`, `tracestate`) to Kafka message headers when producing via aiokafka. Extract and restore trace context when consuming. Implement via a `TracingKafkaProducer` wrapper and a `tracing_consumer_middleware` function in `apps/control-plane/src/platform/common/kafka_tracing.py`.

**Rationale**: The `EventEnvelope` already carries `correlation_id`. Trace propagation requires additionally injecting the active span's trace context into Kafka headers using the standard W3C format so consumers can link their processing spans to the producer's trace. The `opentelemetry.propagate` module provides `inject()` and `extract()` functions that work with carrier dictionaries — Kafka headers (bytes→bytes dict) need a small adapter. This approach requires no changes to business logic; it wraps the existing aiokafka producer/consumer pattern from the scaffold.

**Implementation**: `platform/common/kafka_tracing.py` with:
- `inject_trace_context(headers: dict) -> dict` — injects current span context into headers
- `extract_trace_context(headers: dict) -> context.Context` — extracts and returns parent context
- Usage: called in the EventEnvelope emit path and in the Kafka consumer base class

**Alternatives considered**:
- Injecting trace context into EventEnvelope fields — coupling tracing to the business event model; W3C headers are the standard and don't pollute the envelope schema
- OpenTelemetry's kafka-python instrumentation — exists but targets kafka-python library, not aiokafka; custom wrapper is required

---

## Decision 8: Local Development Mode

**Decision**: The `ops-cli` `platform-cli diagnose` command (feature 045) starts a Jaeger all-in-one Docker container (or process) on `localhost:4317`/`localhost:16686` when running in local mode. Services in local mode read `OTEL_EXPORTER_ENDPOINT=http://localhost:4318` from the local env config.

**Rationale**: Feature 045 (ops-cli) already manages local process/service lifecycle. Adding local Jaeger as a managed subprocess is consistent with how local Redis and Qdrant are managed. The control plane's `telemetry.py` already checks `OTEL_EXPORTER_ENDPOINT` — if set, it exports; if not set, it's a no-op. The ops-cli just needs to start Jaeger and set the env variable.

**Alternatives considered**:
- Local Prometheus + Grafana — too heavy for developer local mode; traces are more valuable for debugging than metrics dashboards
- OTEL Collector in local mode — extra component; for developer use, direct export to Jaeger is simpler

---

## Decision 9: Existing Instrumentation State

**Decision**: All four Go services and the Python control plane already have OTEL instrumentation in their codebase. This feature does NOT modify service source code. It deploys the collection infrastructure that the services are already configured to export to.

**Current state per service**:
- **control-plane**: `telemetry.py` sets up OTLP HTTP trace exporter when `OTEL_EXPORTER_ENDPOINT` is set; instruments FastAPI, SQLAlchemy, Redis, gRPC clients. Currently no-op (endpoint not configured).
- **reasoning-engine**: `pkg/metrics/metrics.go` has OTEL metrics (counters/histograms); `otelgrpc.NewServerHandler()` instruments gRPC server. TracerProvider not initialized (no OTLP exporter wired).
- **runtime-controller**: `tracesdk.TracerProvider()` initialized with no OTLP exporter; effectively no-op.
- **sandbox-manager, simulation-controller**: OTEL dependency present (go.mod), not verified in main.go.

**Action required**: Set `OTEL_EXPORTER_ENDPOINT` in Helm values for each service chart. This is a values change, not a code change. For Go services with no-op TracerProvider, the Helm values must set `OTEL_EXPORTER_OTLP_ENDPOINT` env var and each service's main.go must be updated to initialize an OTLP exporter (small change to existing code, not new feature code).

**Wait** — this is a code change needed in the Go services. Let me think about the scope. The spec says "All platform services MUST emit telemetry to the observability stack without requiring application-level code changes beyond initial instrumentation." The initial instrumentation is already done. The remaining work is:
1. Deploy infrastructure (charts)
2. Set env variables in service Helm charts (values.yaml changes)
3. For runtime-controller/sandbox-manager/simulation-controller: small OTLP provider initialization (1-5 lines each)

This is in scope as "initial instrumentation" since the OTEL packages are already imported.
