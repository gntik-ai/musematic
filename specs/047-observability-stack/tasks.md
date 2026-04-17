# Tasks: Observability Stack

**Input**: Design documents from `specs/047-observability-stack/`  
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/observability-interfaces.md ✓, quickstart.md ✓

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US6)

---

## Phase 1: Setup (Umbrella Chart Scaffold)

**Purpose**: Create the `deploy/helm/observability/` chart skeleton and verify it lints cleanly before adding any content.

- [X] T001 Create `deploy/helm/observability/Chart.yaml` — apiVersion v2, name musematic-observability, type application, version 0.1.0; dependencies: opentelemetry-collector (open-telemetry/opentelemetry-helm-charts, version ^0.108.0), kube-prometheus-stack (prometheus-community/kube-prometheus-stack, version ^65.0.0), jaeger (jaegertracing/jaeger, version ^3.0.0)
- [X] T002 [P] Create `deploy/helm/observability/values.yaml` — top-level override structure for all sub-charts: opentelemetry-collector.mode=deployment + replicaCount=2 + full pipeline config (OTLP receivers, memory_limiter + batch processors, prometheus exporter :8889 + otlp/jaeger exporter); kube-prometheus-stack.prometheus.prometheusSpec (scrapeInterval:15s, retention:15d, storageSpec.volumeClaimTemplate.spec.resources.requests.storage:20Gi, ruleSelector.matchLabels.prometheus:musematic); kube-prometheus-stack.grafana (sidecar.dashboards.enabled:true, sidecar.dashboards.label:grafana_dashboard, additionalDataSources: Jaeger at http://musematic-observability-jaeger-query:16686); jaeger (allInOne.enabled:true, storage.type:badger, allInOne.options.collector.otlp.grpc.host-port=:4317, persistence.enabled:true, persistence.size:5Gi)
- [X] T003 [P] Create `deploy/helm/observability/templates/namespace.yaml` — Kubernetes Namespace manifest for `platform-observability`
- [X] T004 Run `helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts && helm repo add prometheus-community https://prometheus-community.github.io/helm-charts && helm repo add jaegertracing https://jaegertracing.github.io/helm-charts && helm dependency build deploy/helm/observability/` — verify Chart.lock is created; run `helm lint deploy/helm/observability/` and confirm clean pass

---

## Phase 2: Foundational (Service OTEL Wiring)

**Purpose**: Wire OTEL exporters in all service Helm charts and Go `main.go` files so telemetry flows to the collector once it's deployed. These are prerequisites for all metric-dependent user stories.

**⚠️ CRITICAL**: US1 (dashboards), US2 (traces), and US3 (alerts) all require services to be emitting telemetry. These wiring tasks must complete before testing any observability story.

- [X] T005 [P] Add `OTEL_EXPORTER_ENDPOINT` env var to `deploy/helm/control-plane/values.yaml` — value: `http://otel-collector.platform-observability.svc.cluster.local:4318`; also add `OTEL_SERVICE_NAME: control-plane` and `OTEL_RESOURCE_ATTRIBUTES: deployment.environment=production`
- [X] T006 [P] Add `OTEL_EXPORTER_OTLP_ENDPOINT` + `OTEL_SERVICE_NAME: reasoning-engine` to `deploy/helm/reasoning-engine/values.yaml` — endpoint: `http://otel-collector.platform-observability.svc.cluster.local:4317`
- [X] T007 [P] Update `services/runtime-controller/cmd/runtime-controller/main.go` — replace the no-op `tracesdk.TracerProvider()` initialization with OTLP gRPC exporter wired from `OTEL_EXPORTER_OTLP_ENDPOINT` env var: if env var set, create `otlptracegrpc.NewClient(opts)` + `tracesdk.NewTracerProvider(tracesdk.WithBatcher(exporter))` + `otel.SetTracerProvider(provider)` + defer `provider.Shutdown(ctx)`; also initialize OTLP metric exporter via `otlpmetricgrpc` + `metric.NewMeterProvider` + `otel.SetMeterProvider`; add `OTEL_EXPORTER_OTLP_ENDPOINT` + `OTEL_SERVICE_NAME: runtime-controller` to `deploy/helm/runtime-controller/values.yaml`
- [X] T008 [P] Update `services/sandbox-manager/cmd/sandbox-manager/main.go` — same OTLP gRPC TracerProvider + MeterProvider initialization pattern as T007; add `OTEL_EXPORTER_OTLP_ENDPOINT` + `OTEL_SERVICE_NAME: sandbox-manager` to sandbox-manager helm chart values (if chart exists under `deploy/helm/`)
- [X] T009 [P] Update `services/simulation-controller/cmd/simulation-controller/main.go` — same OTLP gRPC TracerProvider + MeterProvider initialization as T007; add `OTEL_EXPORTER_OTLP_ENDPOINT` + `OTEL_SERVICE_NAME: simulation-controller` to `deploy/helm/simulation-controller/values.yaml`

---

## Phase 3: User Story 1 — Monitor Service Health and Performance (Priority: P1)

**Goal**: Prometheus scrapes metrics from all platform services. The Platform Overview dashboard shows health status, request rate, error rate, and p95 latency for every service. Degraded services turn red within 60 seconds.

**Independent Test**: Deploy the full observability stack (`helm upgrade --install musematic-observability deploy/helm/observability --namespace platform-observability`). Port-forward Grafana to :3000. Open Platform Overview dashboard. Verify all services appear. Stop one service; verify it turns red within 60 seconds.

- [X] T010 [US1] Create `deploy/helm/observability/templates/otel-collector-servicemonitor.yaml` — ServiceMonitor CRD targeting the OTEL Collector's Prometheus endpoint (:8889) with label `prometheus: musematic` to trigger scraping; namespace: platform-observability
- [X] T011 [US1] Create `deploy/helm/observability/templates/dashboards/platform-overview.yaml` — ConfigMap with label `grafana_dashboard: "1"`, data key `platform-overview.json`: Grafana dashboard JSON (uid: platform-overview, title: Platform Overview, refresh: 30s) with panels: `up` stat panel per service (color-coded green/red), `rate(http_server_request_duration_seconds_count[5m])` time-series (request rate), `rate(http_server_request_duration_seconds_count{http_response_status_code=~"5.."}[5m]) / rate(http_server_request_duration_seconds_count[5m])` time-series (error rate), `histogram_quantile(0.95, rate(http_server_request_duration_seconds_bucket[5m]))` time-series (p95 latency); namespace filter variable

---

## Phase 4: User Story 2 — Trace Requests Across Services (Priority: P1)

**Goal**: Jaeger receives traces from the OTEL Collector. Developers can search by correlation ID and see full cross-service trace trees with parent-child span relationships.

**Independent Test**: Trigger a workflow execution. Search Jaeger (port 16686) by correlation ID tag. Verify spans from `control-plane` and `reasoning-engine` appear in one trace with correct parent-child relationships. Verify error spans show error message and type.

- [X] T012 [US2] Verify Jaeger all-in-one configuration in `deploy/helm/observability/values.yaml` — confirm: `jaeger.allInOne.enabled: true`, storage type badger, OTLP gRPC collector receiver on :4317, persistence PVC 5Gi, query UI on :16686; verify OTEL Collector pipeline's `otlp/jaeger` exporter endpoint matches the Jaeger collector ClusterIP service name (`musematic-observability-jaeger-collector:4317`)
- [X] T013 [US2] Add `correlation_id` as a tagged field in the OTEL Collector's span processor config in `deploy/helm/observability/values.yaml` — add `transform` processor that promotes the `correlation_id` attribute from span attributes to a resource attribute so it's indexed and searchable in Jaeger by tag key

---

## Phase 5: User Story 3 — Receive Alerts for Critical Conditions (Priority: P1)

**Goal**: Eight alert rules fire for critical/warning conditions across all domains. Firing alerts appear in Alertmanager with condition details, current metric values, and dashboard links.

**Independent Test**: Stop a platform service (scale deployment to 0 replicas). Wait 5 minutes. Open Alertmanager (port 9093). Verify `ServiceDown` alert is firing with service name and dashboard link. Restore service; verify alert resolves within 5 minutes.

- [X] T014 [P] [US3] Create `deploy/helm/observability/templates/alerts/service-alerts.yaml` — PrometheusRule CRD (label prometheus:musematic), group `platform.services`, interval:1m; rules: `ServiceDown` (expr:`up{job=~".*musematic.*"} == 0`, for:5m, severity:critical, dashboard_url to platform-overview), `HighErrorRate` (expr: `rate(http_server_request_duration_seconds_count{http_response_status_code=~"5.."}[5m]) / rate(http_server_request_duration_seconds_count[5m]) > 0.05`, for:5m, severity:warning)
- [X] T015 [P] [US3] Create `deploy/helm/observability/templates/alerts/kafka-alerts.yaml` — PrometheusRule CRD, group `platform.kafka`; rules: `KafkaConsumerLagHigh` (expr:`kafka_consumer_group_lag_sum > 1000`, for:10m, severity:warning), `KafkaConsumerLagCritical` (expr:`kafka_consumer_group_lag_sum > 10000`, for:5m, severity:critical)
- [X] T016 [P] [US3] Create `deploy/helm/observability/templates/alerts/execution-alerts.yaml` — PrometheusRule CRD, group `platform.execution`; rule: `ExecutionFailureSpike` (expr:`increase(execution_failures_total[5m]) > 10`, for:5m, severity:warning, dashboard_url to workflow-execution)
- [X] T017 [P] [US3] Create `deploy/helm/observability/templates/alerts/reasoning-alerts.yaml` — PrometheusRule CRD, group `platform.reasoning`; rules: `BudgetExhaustionSpike` (expr:`increase(budget_exhaustion_total[5m]) > 5`, for:5m, severity:warning), `SelfCorrectionNonConvergence` (expr:`rate(correction_nonconvergence_total[5m]) > 0.1`, for:15m, severity:warning, dashboard_url to self-correction)
- [X] T018 [P] [US3] Create `deploy/helm/observability/templates/alerts/fleet-alerts.yaml` — PrometheusRule CRD, group `platform.fleet`; rule: `FleetDegradedOperation` (expr:`fleet_status{status="degraded"} > 0`, for:10m, severity:warning, dashboard_url to fleet-health)

---

## Phase 6: User Story 4 — View Domain-Specific Dashboards (Priority: P2)

**Goal**: All 6 remaining domain dashboards provisioned in Grafana, rendering with real data. Each dashboard has working time range filters and auto-refresh.

**Independent Test**: Open each dashboard in Grafana. Verify all panels show data (not "no data"). Change time range to last 15 minutes; verify all panels update within 5 seconds.

- [X] T019 [P] [US4] Create `deploy/helm/observability/templates/dashboards/workflow-execution.yaml` — ConfigMap (grafana_dashboard:1, uid:workflow-execution, refresh:30s) panels: `execution_active_total` stat, step latency histogram (`execution_step_duration_seconds_bucket`), `rate(execution_failures_total[5m])` time-series (failure rate), `rate(execution_completed_total[5m])` time-series (throughput); workspace template variable
- [X] T020 [P] [US4] Create `deploy/helm/observability/templates/dashboards/reasoning-engine.yaml` — ConfigMap (uid:reasoning-engine) panels: budget utilization gauge (`rate(budget_decrements_total[5m])`), `correction_iterations_total` by outcome label piechart, `mode_selections_total` by mode label piechart, `tot_branches_total` rate time-series, convergence rate stat (`1 - rate(correction_nonconvergence_total[5m]) / rate(correction_iterations_total[5m])`)
- [X] T021 [P] [US4] Create `deploy/helm/observability/templates/dashboards/data-stores.yaml` — ConfigMap (uid:data-stores) panels: per-store `up` stat row (pg_up, redis_up, kafka_broker_up, qdrant_up etc.), per-store query latency time-series, per-store connection pool gauge; store template variable for filtering
- [X] T022 [P] [US4] Create `deploy/helm/observability/templates/dashboards/fleet-health.yaml` — ConfigMap (uid:fleet-health) panels: `fleet_status` count by status piechart, `fleet_member_health_count` by health_status bar, `rate(degraded_operations_total[5m])` time-series; fleet_id template variable
- [X] T023 [P] [US4] Create `deploy/helm/observability/templates/dashboards/cost-intelligence.yaml` — ConfigMap (uid:cost-intelligence) panels: `cost_per_agent_total` top-N bar, `cost_per_workspace_total` bar, `cost_per_model_total` piechart, cumulative cost time-series with workspace filter variable
- [X] T024 [P] [US4] Create `deploy/helm/observability/templates/dashboards/self-correction.yaml` — ConfigMap (uid:self-correction) panels: convergence rate gauge (`1 - nonconvergence/total`), `correction_iterations_total` histogram, `correction_cost_per_loop` time-series, average iterations per loop stat

---

## Phase 7: User Story 5 — Kafka Trace Context Propagation (Priority: P2)

**Goal**: Kafka event producers inject W3C Trace Context headers. Consumers extract them and create child spans linked to the producer's trace. Full async request chains are visible in Jaeger.

**Independent Test**: In a traced context, produce a Kafka event (any topic). In the consumer, verify `traceparent` header is present. In Jaeger, verify the consumer's processing span is a child of the producer's publish span. Verify `extract_trace_context({})` (no headers) returns an empty context without error.

- [X] T025 [US5] Create `apps/control-plane/src/platform/common/kafka_tracing.py` — two public functions: `inject_trace_context(headers: dict[str, bytes]) -> dict[str, bytes]` (uses `opentelemetry.propagate.inject()` with a `BytesDictCarrier` adapter that encodes string values to UTF-8 bytes); `extract_trace_context(headers: dict[str, bytes]) -> opentelemetry.context.Context` (uses `opentelemetry.propagate.extract()` with the same BytesDictCarrier adapter that decodes bytes to strings); `BytesDictCarrier` is an inner class implementing `opentelemetry.propagators.textmap.MutableMapping`; both functions are safe when called with no active span (no-op behavior)
- [X] T026 [US5] Integrate `inject_trace_context` into the Kafka producer path in `apps/control-plane/src/platform/common/` — in the existing aiokafka producer wrapper (the `send_event` or equivalent function that all bounded contexts use to emit `EventEnvelope` events), call `headers = inject_trace_context({})` before `await producer.send(topic, value=..., headers=list(headers.items()))`
- [X] T027 [US5] Integrate `extract_trace_context` into the Kafka consumer path — in the base Kafka consumer or `@kafka_consumer` decorator in `apps/control-plane/src/platform/common/`, wrap message handling with: `ctx = extract_trace_context(dict(msg.headers or []))`, `with opentelemetry.context.use_context(ctx):`, `with tracer.start_as_current_span(f"kafka.consume.{topic}"):`, then call the original message handler

---

## Phase 8: User Story 6 — Local Development Mode (Priority: P3)

**Goal**: `platform-cli install local` starts a local Jaeger all-in-one instance. Local services export traces to `localhost:4318`. Traces visible in Jaeger UI at `localhost:16686`.

**Independent Test**: Run `platform-cli install local`. Make any API request. Open `http://localhost:16686`. Verify recent traces appear from `control-plane` service.

- [X] T028 [US6] Add Jaeger all-in-one container management to `apps/ops-cli/src/platform_cli/installers/local.py` — start `jaegertracing/all-in-one:latest` Docker container (or subprocess binary if Docker unavailable) with ports 4317:4317, 4318:4318, 16686:16686; track container ID/PID in the checkpoint file; add stop/status logic to the local mode lifecycle manager; print Jaeger UI URL to the terminal after startup
- [X] T029 [US6] Add `OTEL_EXPORTER_ENDPOINT=http://localhost:4318` to the local mode environment variable map in `apps/ops-cli/src/platform_cli/installers/local.py` alongside the existing `REDIS_TEST_MODE`, `DATABASE_URL`, and other local-mode env overrides

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Validate complete stack deployment, run helm lint on final chart, confirm dashboards load within 5s, and verify 2% latency overhead constraint.

- [X] T030 Run `helm lint deploy/helm/observability/ --strict` and verify clean pass with no warnings; run `helm template musematic-observability deploy/helm/observability/ | kubeconform -strict -ignore-missing-schemas -kubernetes-version 1.29.0` to validate all generated manifests
- [X] T031 [P] Verify all 7 dashboard ConfigMaps have the correct `grafana_dashboard: "1"` label and valid JSON by running `kubectl apply --dry-run=server -n platform-observability -f deploy/helm/observability/templates/dashboards/`

---

## Dependencies

```
T001–T004 (chart scaffold)
├── T005–T009 (service OTEL wiring)       ← CRITICAL path; US1/US2/US3 need metric emission
│   ├── T010–T011 (US1 dashboard)
│   ├── T012–T013 (US2 Jaeger)
│   ├── T014–T018 (US3 alerts)            ← T014–T018 all parallel (separate files)
│   └── T019–T024 (US4 dashboards)        ← T019–T024 all parallel (separate files)
├── T025–T027 (US5 Kafka tracing)         ← independent of infrastructure tasks
└── T028–T029 (US6 local mode)            ← independent of infrastructure tasks

T030–T031 (Polish)                        ← depends on all templates being created
```

**Story completion order**: US1 + US2 + US3 (P1, can be worked in parallel) → US4 + US5 (P2) → US6 (P3)

---

## Parallel Execution

Within Phase 3–8, tasks touching separate files can be executed in parallel:

```
Phase 5 alerts: T014, T015, T016, T017, T018  ← all independent PrometheusRule CRDs
Phase 6 dashboards: T019, T020, T021, T022, T023, T024  ← all independent ConfigMaps
Phase 2 wiring: T005, T006, T007, T008, T009  ← all independent service charts/main.go files
```

---

## Implementation Strategy

**MVP scope** (get observability working end-to-end): Complete Phases 1–3 (T001–T011)
- This delivers a deployable stack with Prometheus scraping all services and a Platform Overview dashboard showing health status and request rates.
- Validates that service OTEL wiring is correct and the collector pipeline is functional.

**Increment 2**: Add Phases 4–5 (T012–T018) — full trace visibility + all alert rules  
**Increment 3**: Add Phase 6 (T019–T024) — all 6 domain dashboards  
**Increment 4**: Add Phase 7 (T025–T027) — Kafka trace propagation  
**Final**: Phases 8–9 (T028–T031) — local dev mode + polish

---

## Summary

| Phase | Tasks | Story | Parallelizable |
|-------|-------|-------|----------------|
| Setup (chart scaffold) | T001–T004 | — | T002, T003 [P] |
| Foundational (OTEL wiring) | T005–T009 | — | T005–T009 all [P] |
| US1 Service Health | T010–T011 | US1 | T010 [P if separate] |
| US2 Distributed Tracing | T012–T013 | US2 | — |
| US3 Alerting | T014–T018 | US3 | T014–T018 all [P] |
| US4 Domain Dashboards | T019–T024 | US4 | T019–T024 all [P] |
| US5 Kafka Tracing | T025–T027 | US5 | — |
| US6 Local Dev Mode | T028–T029 | US6 | — |
| Polish | T030–T031 | — | T031 [P] |
| **Total** | **31** | | **20 parallelizable** |
