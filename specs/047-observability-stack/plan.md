# Implementation Plan: Observability Stack

**Branch**: `047-observability-stack` | **Date**: 2026-04-17 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/047-observability-stack/spec.md`

## Summary

Deploy a unified observability stack in `platform-observability` namespace using an umbrella Helm chart that bundles OpenTelemetry Collector (gateway mode), Prometheus + Alertmanager + Grafana (via kube-prometheus-stack), and Jaeger All-in-One (badger storage). Services are already instrumented with OpenTelemetry SDKs — this feature wires the collection infrastructure, adds OTLP env vars to service Helm charts, creates 7 Grafana dashboards as provisioned ConfigMaps, defines 8 alert rules as PrometheusRule CRDs, adds Kafka W3C trace context propagation middleware, and initializes OTLP exporters in the 3 Go services that currently have no-op TracerProviders.

## Technical Context

**Language/Version**: YAML (Helm chart templates) + Python 3.12 (kafka_tracing.py) + Go 1.22 (main.go OTLP init) + JSON (Grafana dashboard model)  
**Primary Dependencies**: opentelemetry-collector chart (open-telemetry/opentelemetry-helm-charts), kube-prometheus-stack (prometheus-community), jaeger chart (jaegertracing/jaeger), opentelemetry Python SDK (already in control-plane), go.opentelemetry.io/otel (already in Go services)  
**Storage**: BadgerDB PVC (5 GiB, Jaeger traces 7d), Prometheus PVC (20 GiB, metrics 15d)  
**Testing**: Manual via helm lint + kubeconform; trace propagation verified via integration test in quickstart.md  
**Target Platform**: Kubernetes (primary), local native via ops-cli Jaeger subprocess (local mode)  
**Project Type**: Infrastructure deployment (Helm chart) + configuration-as-code  
**Performance Goals**: Dashboards load in <5s; alerts fire within 5 minutes of condition; <2% overhead on service p99 latency  
**Constraints**: Non-blocking telemetry emission; collector memory limited to 400 MiB  
**Scale/Scope**: 7 dashboards, 8 alert rules, 6 service Helm value updates, 3 Go OTLP exporter initializations, 1 Python Kafka tracing module

## Constitution Check

| Gate | Status | Notes |
|------|--------|-------|
| Python 3.12+ | PASS | kafka_tracing.py uses Python 3.12 type hints |
| Go 1.22+ | PASS | Go main.go updates use Go 1.22 |
| `platform-observability` namespace | PASS | Matches constitution namespace table |
| OTEL + Prometheus + Grafana + Jaeger | PASS | Constitution specifies exactly these tools |
| No cross-boundary database access | PASS | Observability stack does not access application DB tables |
| Non-blocking telemetry (FR-014) | PASS | BatchSpanProcessor drops spans on collector failure |
| Helm chart pattern | PASS | Follows existing `deploy/helm/` chart structure |
| ruff + mypy for Python additions | PASS | kafka_tracing.py must pass existing CI gates |
| go test for Go changes | PASS | main.go OTLP init changes must not break existing tests |

All constitution gates pass.

## Project Structure

### Documentation (this feature)

```text
specs/047-observability-stack/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── contracts/
│   └── observability-interfaces.md   # OTLP, Prometheus, Dashboard, Alert, Kafka contracts
├── quickstart.md        # Deploy + test scenarios
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code Changes

```text
deploy/helm/observability/           # NEW: umbrella chart
├── Chart.yaml
├── values.yaml
└── templates/
    ├── namespace.yaml
    ├── dashboards/                  # 7 dashboard ConfigMaps
    └── alerts/                      # 5 PrometheusRule CRD files

apps/control-plane/src/platform/common/
└── kafka_tracing.py                 # NEW: Kafka W3C trace context injection/extraction

services/runtime-controller/cmd/runtime-controller/main.go   # MODIFIED: OTLP init
services/sandbox-manager/cmd/sandbox-manager/main.go         # MODIFIED: OTLP init
services/simulation-controller/cmd/simulation-controller/main.go  # MODIFIED: OTLP init

deploy/helm/control-plane/values.yaml         # MODIFIED: OTEL_EXPORTER_ENDPOINT
deploy/helm/reasoning-engine/values.yaml      # MODIFIED: OTEL_EXPORTER_OTLP_ENDPOINT
deploy/helm/runtime-controller/values.yaml    # MODIFIED: OTEL_EXPORTER_OTLP_ENDPOINT
deploy/helm/simulation-controller/values.yaml # MODIFIED: OTEL_EXPORTER_OTLP_ENDPOINT
```

**Structure Decision**: Infrastructure-as-code. All deliverables are Helm chart files, ConfigMaps, CRD manifests, and minimal code changes to wire existing OTEL instrumentation to the new collector endpoints.

## Implementation Phases

### Phase 1: Umbrella Helm Chart Scaffold

**Goal**: Create the `deploy/helm/observability/` chart structure with dependencies declared, namespace template, and verified `helm lint` passing.

**Tasks**:
1. Create `deploy/helm/observability/Chart.yaml` — umbrella chart (apiVersion v2, type application, dependencies: opentelemetry-collector v0.108+, kube-prometheus-stack v65+, jaeger v3.x)
2. Create `deploy/helm/observability/values.yaml` — sub-chart override values: OTel Collector pipeline config, Prometheus scrape interval 15s + retention 15d, Grafana sidecar enabled + Jaeger datasource, Jaeger all-in-one + badger storage
3. Create `deploy/helm/observability/templates/namespace.yaml` — platform-observability namespace manifest
4. Run `helm dependency build deploy/helm/observability/` and verify Chart.lock created; run `helm lint deploy/helm/observability/`

---

### Phase 2: Service Helm Values — OTEL Endpoint Wiring (US1 prerequisite)

**Goal**: All service Helm charts export telemetry to the collector via environment variables. No code changes yet — this is values.yaml additions only for the services that already have working OTLP exporters (control-plane, reasoning-engine).

**Tasks**:
1. Add `OTEL_EXPORTER_ENDPOINT` to `deploy/helm/control-plane/values.yaml` pointing to otel-collector HTTP endpoint
2. Add `OTEL_EXPORTER_OTLP_ENDPOINT` + `OTEL_SERVICE_NAME` to `deploy/helm/reasoning-engine/values.yaml`

---

### Phase 3: Go Service OTLP Exporter Initialization (US1 prerequisite)

**Goal**: Three Go services currently have no-op TracerProviders. Update their `main.go` to initialize an OTLP gRPC trace exporter when `OTEL_EXPORTER_OTLP_ENDPOINT` env var is set, following the pattern already in use in the reasoning-engine.

**Tasks**:
1. Update `services/runtime-controller/cmd/runtime-controller/main.go` — initialize OTLP gRPC TracerProvider + MeterProvider from `OTEL_EXPORTER_OTLP_ENDPOINT` env var; add graceful shutdown
2. Update `services/sandbox-manager/cmd/sandbox-manager/main.go` — same pattern
3. Update `services/simulation-controller/cmd/simulation-controller/main.go` — same pattern
4. Add `OTEL_EXPORTER_OTLP_ENDPOINT` + `OTEL_SERVICE_NAME` to `deploy/helm/runtime-controller/values.yaml`, `deploy/helm/simulation-controller/values.yaml` (sandbox-manager chart values if chart exists)

---

### Phase 4: User Story 1 — Service Health Dashboard (P1)

**Goal**: Prometheus scrapes all services; Platform Overview dashboard shows health, rates, and latency for all services.

**Independent Test**: Deploy the stack. Open Platform Overview dashboard in Grafana. Verify all services appear with health indicators. Stop one service; verify it turns red within 60 seconds.

**Tasks**:
1. Create `deploy/helm/observability/templates/dashboards/platform-overview.yaml` — ConfigMap with Grafana JSON containing: `up` stat panel per service, time-series panels for `http_request_total rate`, `http_request_duration_seconds` histogram (p50/p95/p99), and error rate; label `grafana_dashboard: "1"`
2. Create a `ServiceMonitor` template in the umbrella chart for the OTEL Collector's prometheus endpoint (`:8889`)

---

### Phase 5: User Story 2 — Distributed Tracing (P1)

**Goal**: Jaeger receives traces from the OTEL Collector. Searches by correlation ID return full trace trees.

**Independent Test**: Trigger a workflow execution. Search Jaeger by correlation ID. Verify spans from control-plane and reasoning-engine appear in one trace with correct parent-child relationships.

**Tasks**:
1. Verify Jaeger sub-chart configuration in `values.yaml` — all-in-one mode, OTLP receiver on 4317, badger storage with PVC, Jaeger query UI on 16686
2. Verify OTEL Collector trace pipeline in `values.yaml` exports to Jaeger `otlp` exporter endpoint

---

### Phase 6: User Story 3 — Alerting (P1)

**Goal**: Alert rules fire for all 8 critical conditions; alerts visible in Alertmanager with condition details and dashboard links.

**Independent Test**: Stop a service. Wait 5 minutes. Open Alertmanager. Verify `ServiceDown` alert fires with service name and dashboard link.

**Tasks**:
1. Create `deploy/helm/observability/templates/alerts/service-alerts.yaml` — PrometheusRule CRD: `ServiceDown` (up==0, for:5m, critical), `HighErrorRate` (5xx rate >5% for 5m, warning)
2. Create `deploy/helm/observability/templates/alerts/kafka-alerts.yaml` — PrometheusRule CRD: `KafkaConsumerLagHigh` (>1000 for 10m, warning), `KafkaConsumerLagCritical` (>10000 for 5m, critical)
3. Create `deploy/helm/observability/templates/alerts/execution-alerts.yaml` — PrometheusRule CRD: `ExecutionFailureSpike` (>10 failures in 5m, warning)
4. Create `deploy/helm/observability/templates/alerts/reasoning-alerts.yaml` — PrometheusRule CRD: `BudgetExhaustionSpike` + `SelfCorrectionNonConvergence`
5. Create `deploy/helm/observability/templates/alerts/fleet-alerts.yaml` — PrometheusRule CRD: `FleetDegradedOperation`

---

### Phase 7: User Story 4 — Domain Dashboards (P2)

**Goal**: All 6 remaining domain dashboards provisioned and rendering with real data.

**Independent Test**: Open each dashboard in Grafana. Verify panels render with data (not "no data"). Change time range; verify all panels update within 5 seconds.

**Tasks**:
1. Create `deploy/helm/observability/templates/dashboards/workflow-execution.yaml` — active executions stat, step latency histogram, failure rate time-series, execution throughput
2. Create `deploy/helm/observability/templates/dashboards/reasoning-engine.yaml` — budget utilization gauge (budget_decrements_total rate), convergence rate stat, mode distribution pie (mode_selections_total by mode label), ToT branches time-series
3. Create `deploy/helm/observability/templates/dashboards/data-stores.yaml` — pg_up/redis/qdrant/neo4j/clickhouse/opensearch/kafka/minio per-store panels; connection pool and query latency per store
4. Create `deploy/helm/observability/templates/dashboards/fleet-health.yaml` — fleet status distribution table, member health count, degraded operations count time-series
5. Create `deploy/helm/observability/templates/dashboards/cost-intelligence.yaml` — cost_per_agent_total bar, cost_per_workspace_total bar, cost_per_model_total pie, trend time-series
6. Create `deploy/helm/observability/templates/dashboards/self-correction.yaml` — convergence rate gauge, iterations per loop histogram, cost per correction trend

---

### Phase 8: User Story 5 — Kafka Trace Context Propagation (P2)

**Goal**: Kafka event producers inject W3C Trace Context headers. Consumers extract them and link their processing spans to the producer's trace.

**Independent Test**: Produce a Kafka event from a traced context. Consume it in another service. Verify in Jaeger that the consumer's span is a child of the producer's publish span.

**Tasks**:
1. Create `apps/control-plane/src/platform/common/kafka_tracing.py` — `inject_trace_context(headers: dict[str, bytes]) -> dict[str, bytes]` using `opentelemetry.propagate.inject()`; `extract_trace_context(headers: dict[str, bytes]) -> opentelemetry.context.Context` using `opentelemetry.propagate.extract()`; W3C TextMapPropagator adapter for bytes-keyed dict
2. Integrate `inject_trace_context` in the canonical event emission path: update `apps/control-plane/src/platform/common/` Kafka producer wrapper to call inject before every `send()`
3. Integrate `extract_trace_context` in the Kafka consumer base class / `@kafka_consumer` decorator used by bounded contexts

---

### Phase 9: User Story 6 — Local Development Mode (P3)

**Goal**: `platform-cli install local` starts a local Jaeger all-in-one process. Services in local mode export traces to `localhost:4318`.

**Tasks**:
1. Add Jaeger all-in-one Docker container management to `apps/ops-cli/src/platform_cli/installers/local.py` — start `jaegertracing/all-in-one:latest` container (or subprocess) on ports 4317, 4318, 16686; track PID; stop on `platform-cli` shutdown
2. Set `OTEL_EXPORTER_ENDPOINT=http://localhost:4318` in the local mode environment variable map alongside other local-mode overrides

---

## Key Decisions Summary

| Decision | Choice | Reference |
|----------|--------|-----------|
| Chart architecture | Umbrella chart + 3 sub-chart dependencies | research.md D1 |
| OTEL Collector mode | Deployment gateway, 2 replicas, ClusterIP | research.md D2 |
| Prometheus deployment | kube-prometheus-stack (includes Grafana + Alertmanager) | research.md D3 |
| Dashboard provisioning | ConfigMaps with `grafana_dashboard: "1"` sidecar | research.md D4 |
| Jaeger model | All-in-One + BadgerDB PVC (5 GiB) | research.md D5 |
| Alert rules | PrometheusRule CRDs, 5 files, 8 rules | research.md D6 |
| Kafka trace context | W3C headers, kafka_tracing.py, inject/extract | research.md D7 |
| Local dev mode | Jaeger via ops-cli subprocess | research.md D8 |
| Go OTLP init | 3 main.go files updated to wire OTLP exporter | research.md D9 |
