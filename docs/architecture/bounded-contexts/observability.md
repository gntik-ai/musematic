# Observability

Observability owns metrics, traces, logs, dashboards, alert rules, and debug logging sessions.

Primary entities include dashboard ConfigMaps, alert rules, debug sessions, log labels, trace metadata, and service-level indicators. REST APIs expose debug logging controls, while Grafana, Prometheus, Loki, and Jaeger provide operational views.

Observability must preserve correlation IDs and avoid logging sensitive payloads.
