# Interface Contracts: Observability Stack

**Feature**: [spec.md](../spec.md)

---

## 1. OTLP Collector Endpoint Contract

Services export telemetry to these stable endpoints. These are the only URLs services need to know.

**Trace export (gRPC)**:
```
grpc://otel-collector.platform-observability.svc.cluster.local:4317
```
Environment variable: `OTEL_EXPORTER_OTLP_ENDPOINT`

**Trace export (HTTP)**:
```
http://otel-collector.platform-observability.svc.cluster.local:4318
```
Environment variable: `OTEL_EXPORTER_ENDPOINT` (used by control-plane telemetry.py)

**Protocol**: OpenTelemetry Protocol (OTLP) — traces, metrics, and logs all accepted on the same endpoints.

**Failure behavior**: Services MUST NOT fail or degrade if the collector is unavailable. OTLP exporters are configured with a `BatchSpanProcessor` — if the endpoint is unreachable, spans are dropped silently after the export timeout.

---

## 2. Prometheus Scrape Contract

Services that expose Prometheus-format metrics (rather than exporting via OTLP) must:

1. Expose a `/metrics` endpoint on a named port (`http-metrics`, typically `:8080` or `:9090`)
2. Annotate their Kubernetes Pod or Service with standard Prometheus labels:

```yaml
annotations:
  prometheus.io/scrape: "true"
  prometheus.io/port: "8080"
  prometheus.io/path: "/metrics"
```

OR create a `ServiceMonitor` CRD in the `platform-observability` namespace:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: {service-name}-monitor
  namespace: platform-observability
  labels:
    prometheus: musematic
spec:
  namespaceSelector:
    matchNames: [{service-namespace}]
  selector:
    matchLabels:
      app: {service-name}
  endpoints:
    - port: http-metrics
      interval: 15s
      path: /metrics
```

The OTEL Collector itself exposes a Prometheus endpoint at `:8889/metrics` (all metrics exported via OTLP are available here too). A ServiceMonitor is created for it in the umbrella chart.

---

## 3. Grafana Dashboard Provisioning Contract

A dashboard is provisioned by creating a ConfigMap with these labels:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-dashboard-{dashboard-slug}
  namespace: platform-observability
  labels:
    grafana_dashboard: "1"        # Required: triggers sidecar to load
data:
  {dashboard-slug}.json: |
    {
      "__inputs": [],
      "__requires": [],
      "annotations": {"list": []},
      "description": "{Description}",
      "editable": true,
      "fiscalYearStartMonth": 0,
      "graphTooltip": 1,
      "id": null,
      "links": [],
      "panels": [ ... ],
      "refresh": "30s",
      "schemaVersion": 38,
      "tags": ["musematic", "{domain}"],
      "templating": {"list": [...]},
      "time": {"from": "now-1h", "to": "now"},
      "timepicker": {},
      "timezone": "browser",
      "title": "{Dashboard Title}",
      "uid": "{stable-uid}",
      "version": 1
    }
```

**Required panel types**: `timeseries`, `stat`, `gauge`, `barchart`, `piechart`, `table`  
**Required template variables**: At minimum, a `datasource` variable. Domain-specific variables (workspace, namespace, service) are optional per dashboard.  
**Stable UIDs** (must not change — used in alert dashboard links):

| Dashboard | uid |
|-----------|-----|
| Platform Overview | `platform-overview` |
| Workflow Execution | `workflow-execution` |
| Reasoning Engine | `reasoning-engine` |
| Data Stores | `data-stores` |
| Fleet Health | `fleet-health` |
| Cost Intelligence | `cost-intelligence` |
| Self-Correction | `self-correction` |

---

## 4. PrometheusRule Alert Contract

Alert rules are defined as `PrometheusRule` CRDs with this label selector to be picked up by Prometheus Operator:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: platform-{domain}-alerts
  namespace: platform-observability
  labels:
    prometheus: musematic       # Required: matches Prometheus ruleSelector
    role: alert-rules
spec:
  groups:
    - name: platform.{domain}
      interval: 1m              # Evaluation interval
      rules:
        - alert: {AlertName}
          expr: {PromQL expression}
          for: {duration}       # Hold-for duration before firing
          labels:
            severity: critical | warning | info
            team: platform
          annotations:
            summary: "Brief description of condition"
            description: "Full description with {{ $labels }} and {{ $value }}"
            dashboard_url: "http://grafana.platform-observability.svc/d/{dashboard-uid}"
```

**Alert naming convention**: `PascalCase`, domain-prefixed (e.g., `KafkaConsumerLagHigh`, `ServiceDown`)  
**Severity levels**:
- `critical` — requires immediate human action (page on-call)
- `warning` — requires investigation within business hours
- `info` — informational, no action required

---

## 5. Kafka Trace Context Contract

All Kafka message headers MUST include trace context when an active span exists at the producer. The contract for producers and consumers:

**Producer** (inject before `aiokafka.AIOKafkaProducer.send()`):
```python
from platform.common.kafka_tracing import inject_trace_context

headers = inject_trace_context({})  # Returns dict with traceparent (and optionally tracestate)
await producer.send(topic, value=payload, headers=list(headers.items()))
```

**Consumer** (extract at the top of the message handler):
```python
from platform.common.kafka_tracing import extract_trace_context
from opentelemetry import trace, context as otel_context

ctx = extract_trace_context(dict(msg.headers))
with otel_context.use_context(ctx):
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span(f"kafka.consume.{topic}"):
        await handle_message(msg)
```

**Header format** (W3C Trace Context):
```
traceparent: 00-{32-char-trace-id}-{16-char-span-id}-{flags}
# Example: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
```

**Backwards compatibility**: Consumers MUST handle messages without `traceparent` headers — in that case, `extract_trace_context` returns a new empty context and the consumer's span becomes a new root trace.

---

## 6. Local Development Trace Endpoint

When running in local mode via `platform-cli`, traces are exported to:
```
http://localhost:4318
```

The Jaeger All-in-One UI is accessible at:
```
http://localhost:16686
```

Services detect local mode via the `OTEL_EXPORTER_ENDPOINT` environment variable. If it points to `localhost`, no collector is needed between service and Jaeger.

---

## 7. Service Helm Values Contract

Each service chart's `values.yaml` MUST include these OTEL environment variables for telemetry to be collected:

```yaml
# Pattern for all service charts
env:
  OTEL_EXPORTER_OTLP_ENDPOINT: "http://otel-collector.platform-observability.svc.cluster.local:4317"
  OTEL_SERVICE_NAME: "{service-name}"
  OTEL_RESOURCE_ATTRIBUTES: "deployment.environment=production,k8s.namespace.name={{ .Release.Namespace }}"
```

The control plane uses `OTEL_EXPORTER_ENDPOINT` (HTTP, not gRPC) because `telemetry.py` uses the HTTP exporter:
```yaml
env:
  OTEL_EXPORTER_ENDPOINT: "http://otel-collector.platform-observability.svc.cluster.local:4318"
  OTEL_SERVICE_NAME: "control-plane"
```
