# Grafana Metrics, Logs, and Traces

Grafana is the shared shell for three backends:

- Prometheus for metrics
- Loki for logs
- Jaeger for traces

Start from a metric panel, use the related log panel or data link to open Loki
for the same service and time range, then open Jaeger from a log row with a
`trace_id`. The Loki data source provisions a derived field named `trace_id`
that links to the Jaeger data source UID `jaeger`.

Default dashboard time ranges are one hour to avoid expensive first-load queries.
For workspace-scoped investigations, use LogQL JSON filters such as:

```logql
{service="api"} | json | workspace_id="workspace-id"
```

Do not put tenant or request identifiers in the label selector. Use the JSON
pipeline filter stage so Loki index cardinality remains bounded.
