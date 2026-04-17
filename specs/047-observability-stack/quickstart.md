# Quickstart: Observability Stack

**Feature**: [spec.md](spec.md)

## What This Feature Creates

```text
deploy/helm/observability/
├── Chart.yaml                   # Umbrella chart with sub-chart dependencies
├── Chart.lock                   # Locked dependency versions
├── values.yaml                  # Unified overrides for all sub-charts
├── templates/
│   ├── namespace.yaml
│   ├── jaeger-badger-pvc.yaml
│   ├── otel-collector-servicemonitor.yaml
│   ├── dashboards/              # 7 Grafana dashboard ConfigMaps
│   │   ├── platform-overview.yaml
│   │   ├── workflow-execution.yaml
│   │   ├── reasoning-engine.yaml
│   │   ├── data-stores.yaml
│   │   ├── fleet-health.yaml
│   │   ├── cost-intelligence.yaml
│   │   └── self-correction.yaml
│   └── alerts/                  # 5 PrometheusRule CRDs
│       ├── service-alerts.yaml
│       ├── kafka-alerts.yaml
│       ├── execution-alerts.yaml
│       ├── reasoning-alerts.yaml
│       └── fleet-alerts.yaml

apps/control-plane/src/platform/common/
├── kafka_tracing.py             # NEW: Kafka W3C trace context propagation
└── events/
    ├── producer.py              # MODIFIED: inject W3C trace headers into Kafka
    └── consumer.py              # MODIFIED: extract context and start consumer spans

services/runtime-controller/
├── cmd/runtime-controller/main.go
└── pkg/telemetry/               # NEW: OTLP trace + metric bootstrap

services/reasoning-engine/
├── cmd/reasoning-engine/main.go
├── pkg/telemetry/               # NEW: OTLP trace + metric bootstrap
└── pkg/metrics/                 # MODIFIED: budget and self-correction metrics

services/sandbox-manager/
└── pkg/telemetry/tracing.go     # MODIFIED: OTLP trace + metric bootstrap

services/simulation-controller/
├── cmd/simulation-controller/main.go
└── pkg/telemetry/               # NEW: OTLP trace + metric bootstrap

deploy/helm/control-plane/
└── values.yaml                  # MODIFIED: add OTEL_EXPORTER_ENDPOINT

deploy/helm/reasoning-engine/
└── values.yaml                  # MODIFIED: add OTEL_EXPORTER_OTLP_ENDPOINT

deploy/helm/runtime-controller/
└── values.yaml                  # MODIFIED: add OTEL_EXPORTER_OTLP_ENDPOINT

deploy/helm/simulation-controller/
└── values.yaml                  # MODIFIED: add OTEL_EXPORTER_OTLP_ENDPOINT

apps/ops-cli/src/platform_cli/installers/
└── local.py                     # MODIFIED: start/stop local Jaeger and export OTEL env
```

---

## Deploying the Observability Stack

### Prerequisites

```bash
# Add Helm repos
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add jaegertracing https://jaegertracing.github.io/helm-charts
helm repo update

# Download chart dependencies
cd deploy/helm/observability
helm dependency build
```

### Deploy

```bash
helm upgrade --install musematic-observability deploy/helm/observability \
  --namespace platform-observability \
  --create-namespace \
  --wait
```

### Verify

```bash
# Check all pods are running
kubectl get pods -n platform-observability

# Expected components:
# otel-collector-*                                        Running
# musematic-observability-grafana-*                       Running
# musematic-observability-jaeger-*                        Running
# prometheus-musematic-observability-kube-prome-*         Running
# alertmanager-musematic-observability-kube-prome-*       Running

# Access Grafana
kubectl port-forward -n platform-observability svc/musematic-observability-grafana 3000:80
# Open http://localhost:3000, login with admin/admin

# Access Jaeger
kubectl port-forward -n platform-observability svc/musematic-observability-jaeger-query 16686:16686
# Open http://localhost:16686
```

### Validate Rendered Manifests

```bash
helm lint deploy/helm/observability --strict

helm template musematic-observability deploy/helm/observability \
  --namespace platform-observability \
  | kubeconform -strict -ignore-missing-schemas -kubernetes-version 1.29.0

helm template musematic-observability deploy/helm/observability \
  --namespace platform-observability \
  --show-only templates/dashboards/platform-overview.yaml \
  --show-only templates/dashboards/workflow-execution.yaml \
  --show-only templates/dashboards/reasoning-engine.yaml \
  --show-only templates/dashboards/data-stores.yaml \
  --show-only templates/dashboards/fleet-health.yaml \
  --show-only templates/dashboards/cost-intelligence.yaml \
  --show-only templates/dashboards/self-correction.yaml \
  | kubectl apply --dry-run=server -n platform-observability -f -
```

---

## Testing US1: Service Health Dashboard

1. Deploy the observability stack
2. Port-forward to Grafana: `kubectl port-forward -n platform-observability svc/musematic-observability-grafana 3000:80`
3. Open http://localhost:3000 → Platform Overview dashboard
4. Verify all platform services appear with green health indicators
5. Stop a service: `kubectl scale deploy/control-plane -n platform-control --replicas=0`
6. Within 60 seconds, verify the service turns red on the dashboard
7. Restart: `kubectl scale deploy/control-plane -n platform-control --replicas=1`

## Testing US2: Distributed Trace

1. Ensure service helm charts have `OTEL_EXPORTER_OTLP_ENDPOINT` set
2. Trigger a workflow execution via the API
3. Note the `X-Correlation-ID` header from the response
4. Open Jaeger UI (port 16686)
5. Search by Service: `control-plane`, or search by Tags: `correlation_id={value}`
6. Verify spans from `control-plane` and `reasoning-engine` appear in the same trace
7. Verify gRPC call spans show parent-child relationship

## Testing US3: Alert Firing

1. Stop a platform service: `kubectl scale deploy/reasoning-engine -n platform-execution --replicas=0`
2. Wait 5 minutes (alert `for` duration)
3. Open Alertmanager: `kubectl port-forward -n platform-observability svc/musematic-observability-alertmanager 9093:9093`
4. Open http://localhost:9093 → verify `ServiceDown` alert is firing with service name
5. Restart the service; verify alert transitions to resolved within 5 minutes

## Testing US4: Domain Dashboards

1. Open Grafana
2. Navigate to each of the 7 dashboards
3. For each, verify: panels render (no "no data" or error), time range selector works, auto-refresh is active

## Testing US5: Kafka Trace Context

1. In a test, produce a Kafka event to any platform topic using a traced context
2. In the consuming service, verify the `traceparent` header is present in the received message
3. In Jaeger, verify the consumer's processing span appears as a child of the producer's publish span

## Testing US6: Local Development Mode

```bash
# Start platform in local mode (feature 045)
platform-cli install local

# The ops-cli starts a local Jaeger instance automatically
# Verify traces appear:
curl http://localhost:16686/api/services
# Should list "control-plane" after any API request

# Make a request to local control-plane
curl http://localhost:8000/api/v1/health

# Verify trace in Jaeger
open http://localhost:16686
# Select service: control-plane, click Find Traces
```

---

## Dashboard JSON Development

To develop or update dashboard JSON:

1. Import the JSON into a running Grafana instance manually (Dashboards → Import)
2. Edit panels and variables in the Grafana UI
3. Export the dashboard JSON (Dashboard settings → JSON Model → Copy to clipboard)
4. Paste into the corresponding ConfigMap YAML under `data.{slug}.json:`
5. Apply: `helm upgrade musematic-observability deploy/helm/observability ...`
6. The Grafana sidecar detects the ConfigMap change and reloads the dashboard within ~30s

## Prometheus Query Reference

Key PromQL expressions used in dashboards and alerts:

```promql
# Service up/down
up{job=~".*platform.*"}

# HTTP error rate by service
rate(http_server_request_duration_seconds_count{http_response_status_code=~"5.."}[5m])
/ rate(http_server_request_duration_seconds_count[5m])

# Kafka consumer lag
kafka_consumer_group_lag_sum

# Budget exhaustion events
increase(budget_exhaustion_total[5m])

# Correction non-convergence rate
rate(correction_nonconvergence_total[5m])

# Fleet degraded status
fleet_status{status="degraded"}

# Active workflow executions
execution_active_total

# ToT branch count over time
rate(tot_branches_total[5m])
```

---

## Notes

- The `kube-prometheus-stack` chart is large (many CRDs). The first `helm dependency build` may take 30–60 seconds.
- Dashboard ConfigMaps must be in the `platform-observability` namespace for the Grafana sidecar to detect them.
- Grafana dashboard UIDs must remain stable — changing a UID breaks alert links and bookmarks.
- The Jaeger All-in-One pod uses an in-memory index on startup — after restart, traces are still stored (badger PVC) but the in-memory index is rebuilt, causing a brief delay before search results appear.
- Alert notification routing (email/Slack/PagerDuty) requires configuring Alertmanager routes in `values.yaml` under `alertmanager.config.receivers` and `alertmanager.config.route`.
