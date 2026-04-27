# Log Query Cheatsheet

Common LogQL queries for the platform Loki data source:

- Per-service errors: `{service="api",level="error"}`
- Bounded-context stream: `{bounded_context="cost_governance"} | json`
- Workspace-scoped logs: `{service="api"} | json | workspace_id="workspace-id"`
- Trace correlation: `{trace_id!=""} | json | trace_id="trace-id"`
- Goal-scoped execution: `{bounded_context=~"execution|interactions"} | json | goal_id="goal-id"`
- Recent audit appends: `{service="api",bounded_context="audit"} | json | message="audit.chain.appended"`
- Cost anomalies: `{bounded_context="cost_governance"} | json | message=~".*anomaly.*detected.*"`

Keep `workspace_id`, `user_id`, `goal_id`, `correlation_id`, `trace_id`, and
`execution_id` in the JSON payload filter stage. Do not promote them to Loki
labels.
