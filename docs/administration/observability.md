# Observability

Feature [spec 047][s047] ships the platform's observability stack:
**Prometheus** for metrics, **Jaeger** for distributed traces, and
**Grafana** for unified visualisation, installed via the Helm charts
under `deploy/helm/`. The control plane and Go services emit via
OpenTelemetry.

## Wiring the stack

### Install the backends

TODO(andrea): the Helm chart for the observability stack lives at
`deploy/helm/observability/` per [spec 047][s047], but the current
`main` `deploy/helm/` directory does not show it published there yet.
Until that chart lands, the common approach is to install upstream
charts directly:

```bash
helm install otel open-telemetry/opentelemetry-collector \
  --namespace platform-observability --create-namespace

helm install prom prometheus-community/kube-prometheus-stack \
  --namespace platform-observability

helm install jaeger jaegertracing/jaeger \
  --namespace platform-observability
```

### Point the control plane at the collector

```bash
# Python control plane
OTEL_EXPORTER_ENDPOINT=http://otel-collector.platform-observability:4318
OTEL_SERVICE_NAME=musematic-control-plane

# Go satellite services
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector.platform-observability:4317
```

Both endpoints are optional — services run fine with observability
disabled (they just don't emit).

## What the platform emits

### Metrics

TODO(andrea): the canonical metric-name prefix and per-BC metric catalogue
are not yet consolidated in one place. Known emitters:

- FastAPI request metrics (standard OTEL HTTP metrics).
- aiokafka producer/consumer metrics.
- Runtime controller: pod lifecycle counters (see
  [spec 009][s009]).
- Reasoning engine: budget-tracking histograms
  ([spec 011][s011]).
- Sandbox manager: concurrent sandbox gauge
  ([spec 010][s010]).
- WebSocket hub: connection count, per-channel refcounts
  ([spec 019][s019]).

### Traces

Every request that touches the control plane creates a root span tagged
with the correlation envelope:

- `workspace_id`
- `conversation_id`
- `interaction_id`
- `execution_id`
- `goal_id` (GID — [spec 052][s052])
- `correlation_id`
- `trace_id`

Satellite services (Go) propagate the same tags via
`go.opentelemetry.io/otel/propagation` trace headers.

### Logs

As of the main branch, logs are **not centralised**. They land on pod
stdout and are readable via `kubectl logs`. The constitution's
audit-pass (v1.2.0) introduces structured JSON logging (AD-22) and Loki
aggregation (AD-23) as the `UPD-034` feature; until that lands,
operators use `kubectl logs -f` or a cluster log shipper of their own
choice.

## Recommended dashboards

Feature [spec 047][s047] ships 7 baseline Grafana dashboards as
ConfigMaps:

TODO(andrea): list the exact dashboard JSONs and their ConfigMap names
from `deploy/helm/observability/templates/dashboards/`. The directory
does not yet exist on `main` — reconfirm once UPD-034 ships.

Typical dashboards to start with:

1. **Control-plane overview** — FastAPI p50/p95/p99, error rate, active
   connections.
2. **Kafka pipeline** — per-topic consumer lag, producer error rate.
3. **Execution engine** — running executions, scheduler queue depth,
   checkpoint rate.
4. **Runtime controller** — pod count, warm-pool hit rate, heartbeat
   failures.
5. **Reasoning engine** — budget exhaustion rate, TotT concurrency
   gauge.
6. **Trust & governance** — verdicts per minute, enforcement actions.
7. **Costs & tokens** (from analytics) — token usage rate, cost-per-task.

## Alerts

No alert definitions ship in the main branch. Admins should author
Alertmanager rules based on dashboard signals. Suggested starting set:

- FastAPI error rate > 1% for 5 minutes → page on-call.
- Kafka consumer lag > 5 minutes on any topic → warn.
- Runtime controller heartbeat failures > 0 → warn.
- Reasoning-engine budget exhaustion rate > 5% → warn.
- Warm-pool available pods = 0 for > 2 minutes → warn.

## Correlation with the UI

The operator dashboard ([spec 044][s044]) surfaces:

- Active fleet health.
- Active executions with live WebSocket updates.
- Warm-pool metrics.
- Recent governance verdicts.

Clicking through to an execution shows the reasoning trace and the
execution timeline — the same correlation IDs used in OTEL, so traces
in Jaeger are one click away.

[s009]: https://github.com/gntik-ai/musematic/tree/main/specs/009-runtime-controller
[s010]: https://github.com/gntik-ai/musematic/tree/main/specs/010-sandbox-manager
[s011]: https://github.com/gntik-ai/musematic/tree/main/specs/011-reasoning-engine
[s019]: https://github.com/gntik-ai/musematic/tree/main/specs/019-websocket-realtime-gateway
[s044]: https://github.com/gntik-ai/musematic/tree/main/specs/044-operator-dashboard-diagnostics
[s047]: https://github.com/gntik-ai/musematic/tree/main/specs/047-observability-stack
[s052]: https://github.com/gntik-ai/musematic/tree/main/specs/052-gid-correlation-envelope
