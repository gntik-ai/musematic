# Operations Health

Operations health pages summarize control-plane status, runtime profiles, incidents, maintenance windows, queue depth, and dependency health.

## Common Admin Workflows

### Review Platform Health

Open health status, check control-plane runtime profiles, confirm Redis/Kafka/PostgreSQL connectivity, and inspect recent incident summaries.

### Schedule Maintenance

Create a maintenance window with scope, owner, start, end, and user-facing message. Require super admin approval for global or multi-region maintenance.

### Triage a Service Degradation

Open the linked dashboard, identify affected workspaces, and hand off to the operator runbook if remediation requires cluster access.

### Disable a Problem Integration

Temporarily disable the integration, preserve delivery state, notify impacted workspaces, and file follow-up work before re-enabling.
