# FAQ & Troubleshooting

## General

### What is musematic, in one sentence?
A multi-tenant agent orchestration platform (Python + Go + Next.js)
that manages the lifecycle of AI agents — registration, certification,
fleet coordination, workflow execution, governance, and observability.

### What do I need to run it?
See [Getting Started › Prerequisites](getting-started.md#prerequisites).
Minimum for local dev: Python 3.12, Go 1.25, Node 18+, Docker, 16 GB
RAM.

### Is it hosted, or do I self-host?
Self-host. The repo ships Helm charts under `deploy/helm/` and
docker-compose for local data stores. There is no managed offering.

### How is it different from a workflow engine like Airflow or Temporal?
musematic treats agents as first-class entities (with FQN, visibility,
policies, certification, reasoning budgets) and wraps workflow
execution with governance (Observer → Judge → Enforcer), a reasoning
engine (CoT, ToT, ReAct, scaling inference), and content-aware context
engineering. Airflow/Temporal are lower-level primitives that do not
speak any of these concepts natively.

## Agents and flows

### Why is my agent rejected at upload with "purpose is too short"?
`AgentManifest.purpose` has a minimum length of **50 characters**.
Write a sentence, not a phrase.

### Why does my agent see no other agents when I run it?
Zero-trust visibility is enforced for new deployments (principle IX).
You must explicitly grant visibility via
`PATCH /api/v1/registry/agents/{id}` with `visibility_agents` patterns.
See [Agents › Visibility](agents.md#visibility).

### Can an agent have multiple role types?
Yes. `role_types` is a list. A common pattern is `[judge, enforcer]`
for governance agents.

### Why did my workflow fail with "circular dependency detected"?
The `depends_on` graph forms a cycle. The workflow compiler rejects
cycles at registration time via `_assert_acyclic()`.

### Are workflow steps retryable?
Yes. Configure `retry_config` on a step (`max_retries`,
`backoff_strategy`, `base_delay_seconds`, `max_delay_seconds`).

### What happens if an approval gate times out?
Controlled by `approval_config.timeout_action`:
- `fail` — end the execution with `failed` (default).
- `skip` — continue past the gate.
- `escalate` — TODO(andrea): confirm escalation wiring location.

## Authentication and access

### Why does my login fail with "account locked"?
5 failed attempts (`AUTH_LOCKOUT_THRESHOLD`) lock the account for 15
minutes (`AUTH_LOCKOUT_DURATION`). Admins can clear it with
`POST /api/v1/accounts/{user_id}/unlock`.

### How do I enable MFA for a user?
Users self-enrol via the UI. Admins can reset MFA with
`POST /api/v1/accounts/{user_id}/reset-mfa`. TOTP secrets are
Fernet-encrypted with `AUTH_MFA_ENCRYPTION_KEY`.

### How do I create a service account for CI?
`POST /api/v1/auth/service-accounts` as `platform_admin`. The API key
is returned once (prefix `msk_…`) — store it immediately.

### Where do workspace roles differ from global roles?
Global roles (`platform_admin`, `auditor`, etc.) apply across the
install. Workspace roles (`owner`, `admin`, `member`, `viewer`) are
persisted on the `Membership` row and apply only inside one workspace.
See [RBAC & Permissions](administration/rbac-and-permissions.md).

## Installation and operations

### Which S3 provider do I need?
Any S3-compatible one. The platform uses the generic S3 protocol via
`boto3` / `aws-sdk-go-v2`. Hetzner, AWS S3, Cloudflare R2, Wasabi,
MinIO — all work. MinIO is a dev/self-hosted convenience, never a hard
dependency (principle XVI).

### Can I skip the Go services?
Not in production. The reasoning engine, runtime controller, sandbox
manager, and simulation controller handle latency-critical work that
the Python monolith delegates via gRPC. For dev, you can run them
locally as subprocesses.

### How many Postgres databases does the platform need?
One. All bounded contexts share the same Postgres instance — but each
only queries its own tables (principle IV).

### Does the platform ship a docker-compose for local-dev data stores?
TODO(andrea): not at the repo root as of the current main branch.
Test fixtures include one; a canonical developer-facing compose is on
the backlog.

## Observability

### Where do I find logs for a specific agent?
Pod logs under `kubectl logs -n platform-execution agent-…`. Centralised
log aggregation (Loki) is planned per the audit-pass (UPD-034); the
main branch does not ship it.

### How do I trace a request end-to-end?
If OTEL is configured (`OTEL_EXPORTER_OTLP_ENDPOINT`), every request
produces spans tagged with `workspace_id`, `goal_id`, `correlation_id`,
`execution_id`, etc. Use Jaeger's search by `trace_id` or
`correlation_id`.

### What Prometheus metrics does the platform expose?
Standard FastAPI HTTP metrics, aiokafka producer/consumer metrics,
runtime-controller pod lifecycle counters, reasoning-engine budget
histograms, sandbox-manager concurrent-sandbox gauge, WebSocket
connection gauges. A consolidated metric catalogue is not yet
published — see
[Administration › Observability](administration/observability.md).

## Common failures

### `Connection refused` on migration
Postgres not reachable. Verify the container port mapping (`5432`) and
the `POSTGRES_DSN`. If using docker-compose, check `depends_on` and
healthchecks.

### `KafkaError: Broker not available` on execution POST
The control plane is up but Kafka is not reachable. Check
`KAFKA_BROKERS` and that the Kafka pod is healthy.

### `ValidationError: unknown field` on agent registration
`AgentManifest` uses `ConfigDict(extra="forbid")`. Typos like
`purposee` or `role_type` (singular, should be `role_types`) are
rejected. Remove the extra field.

### `PlatformError: agent invisible` when chaining agents
Zero-trust visibility (principle IX). Grant visibility via
`visibility_agents` / `visibility_tools` patterns.

### WebSocket drops every 30 seconds
Heartbeat timeout. Check `WS_HEARTBEAT_TIMEOUT_SECONDS` (default 10)
and that your client responds to pings. Default interval is 30s.

### Reasoning budget exhausted mid-trace
`BUDGET_DEFAULT_TTL_SECONDS` (default 3600) defines how long budgets
live in Redis. Per-execution budgets are set by the scheduler —
inspect the reasoning engine logs and confirm Redis connectivity from
the Go service.

### Helm upgrade leaves pods crash-looping
Most often a new required env var that is not set. Check the diff in
`deploy/helm/platform/values.yaml` and compare with your overlay.
`kubectl logs --previous` usually shows the `pydantic.ValidationError`.
