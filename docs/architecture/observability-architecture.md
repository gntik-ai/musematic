# Observability Architecture

Metrics flow to Prometheus, traces flow to Jaeger, and logs flow to Loki through Promtail. Logs intentionally do not route through the OpenTelemetry Collector; that collector remains focused on metrics and traces from the feature 047 pipeline.

Structured logs include service, runtime profile, correlation ID, GID where available, and sanitized context. Dashboards combine service health, runtime lifecycle, data-store state, queue depth, and incident signals.

Operators should move from symptom to evidence in this order: alert, dashboard, trace, log query, audit event, runbook, post-mortem.
