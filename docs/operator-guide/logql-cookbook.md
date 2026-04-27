# LogQL Cookbook

Use these queries in Loki with a narrow time window and the relevant namespace, service, GID, or correlation ID.

| Goal | Query |
| --- | --- |
| Control-plane errors | `{namespace="platform-control", app="control-plane"} |= "ERROR"` |
| Requests for a correlation ID | `{namespace=~"platform-.*"} |= "correlation_id=abc123"` |
| Logs for a GID | `{namespace=~"platform-.*"} |= "gid=GID-123"` |
| Auth failures | `{app="control-plane"} |= "auth" |= "failed"` |
| OAuth callback errors | `{app="control-plane"} |= "oauth" |= "callback" |= "error"` |
| Signup throttling | `{app="control-plane"} |= "rate_limit" |= "accounts"` |
| Workflow compiler errors | `{app="control-plane"} |= "WORKFLOW_SCHEMA_INVALID"` |
| Execution failures | `{app="control-plane"} |= "execution" |= "failed"` |
| Approval timeouts | `{app="control-plane"} |= "approval_timed_out"` |
| Runtime pod dispatch | `{app="runtime-controller"} |= "dispatch"` |
| Sandbox execution errors | `{app="sandbox-manager"} |= "execution" |= "error"` |
| Reasoning budget events | `{app="reasoning-engine"} |= "budget"` |
| Simulation failures | `{app="simulation-controller"} |= "simulation" |= "failed"` |
| Kafka consumer lag logs | `{namespace="platform-data"} |= "consumer lag"` |
| Redis connection errors | `{namespace=~"platform-.*"} |= "redis" |= "error"` |
| PostgreSQL lock waits | `{namespace="platform-data"} |= "lock" |= "postgres"` |
| MinIO upload failures | `{namespace=~"platform-.*"} |= "s3" |= "upload" |= "failed"` |
| Loki retention errors | `{app=~"observability-loki.*"} |= "retention" |= "error"` |
| Promtail dropped lines | `{app="promtail"} |= "dropped"` |
| Alertmanager delivery failure | `{app=~"alertmanager.*"} |= "notify" |= "failed"` |
| Incident deduplication | `{app="control-plane"} |= "incident:dedup"` |
| Secret rotation | `{app="control-plane"} |= "secret" |= "rotation"` |
