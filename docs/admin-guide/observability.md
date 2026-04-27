# Observability Administration

Observability pages configure dashboard access, alert routes, debug logging sessions, and cross-links into logs, traces, and metrics.

## Common Admin Workflows

### Start a Debug Logging Session

Choose target service, scope, duration, and redaction settings. Stop the session as soon as evidence is collected.

### Validate Alert Routing

Trigger a test alert through the configured channel and confirm delivery state. Use dead-letter views for failed notifications.

### Open a Correlated Trace

Search by GID or correlation ID. Move from the trace to logs and execution events to avoid timestamp-only debugging.

### Review Dashboard Access

Confirm users have the minimum role needed for Grafana and platform dashboards. Remove access after incident response concludes.
