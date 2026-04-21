# Data Model: End-to-End Testing on kind

**Feature**: 071-e2e-kind-testing
**Date**: 2026-04-20

## Overview

No database schema changes. This document captures: (1) the **seeded baseline entities** the harness loads before tests run, (2) the **request/response shapes** for dev-only `/api/v1/_e2e/*` endpoints, (3) the **mock LLM call record** structure, (4) **performance threshold constants**, and (5) **chaos scenario inputs**.

All persistence is in the platform's existing data stores (PostgreSQL + Redis + Kafka + MinIO, etc.). The harness owns no tables.

---

## Seeded Baseline Entities

Every entity is loaded idempotently by `seeders/` modules. Re-running `python -m seeders.base --all` is a no-op; `--reset` wipes only entities matching the E2E-scope filters below.

### Users (`seeders/users.py`)

| Email | Role | Purpose |
|---|---|---|
| `admin@e2e.test` | `platform_admin` | Default test admin; owner of all seeded workspaces |
| `operator1@e2e.test` | `workspace_admin` | Workspace admin for governance + trust suites |
| `operator2@e2e.test` | `workspace_admin` | Second workspace admin for permission-boundary tests |
| `end_user1@e2e.test` | `workspace_member` | Regular workspace member |
| `viewer@e2e.test` | `viewer` | Read-only tester |

**E2E scope filter**: email ends with `@e2e.test`.

### Namespaces (`seeders/namespaces.py`)

- `default` — generic catch-all
- `test-finance` — finance-oriented agents (verdict authority scenarios)
- `test-eng` — engineering-oriented agents (executor + reasoning scenarios)

**E2E scope filter**: name starts with `test-` OR equals `default` (default is shared; reset does NOT delete it).

### Agents (`seeders/agents.py`)

One agent per role type, all with valid FQNs, purposes ≥ 50 chars, visibility patterns, and active certifications:

| FQN | Role type | Namespace |
|---|---|---|
| `default:seeded-executor` | executor | default |
| `test-eng:seeded-planner` | planner | test-eng |
| `test-eng:seeded-orchestrator` | orchestrator | test-eng |
| `test-finance:seeded-observer` | observer | test-finance |
| `test-finance:seeded-judge` | judge | test-finance |
| `test-finance:seeded-enforcer` | enforcer | test-finance |

Each agent also has:
- `purpose`: deterministic 60-character string
- `approach`: deterministic 80-character string
- `visibility_patterns`: `["workspace:test-*/agent:*"]` for test-eng + test-finance agents; `["*"]` for default
- `certification`: valid for 30 days from seed time

### Tools (`seeders/tools.py`)

- `mock-http-tool` — calls a stub HTTP service running in the cluster (returns deterministic JSON)
- `mock-code-tool` — runs a no-op Python snippet in the sandbox

### Policies (`seeders/policies.py`)

- `default-allow` — permissive baseline
- `finance-strict` — denies tool calls matching `secret*` keys
- `test-budget-cap` — enforces `max_tokens ≤ 10000` per execution

### Certifiers (`seeders/certifiers.py`)

- `internal-cert` — built-in platform certifier
- `third-party-cert` — HTTPS endpoint `https://cert.e2e.test/v1/verify` (points at in-cluster stub)

### Fleets (`seeders/fleets.py`)

- `test-eng-fleet` — contains `test-eng:seeded-planner` (leader) + `test-eng:seeded-orchestrator` + `default:seeded-executor`

### Workspace goals (`seeders/workspace_goals.py`)

One goal per lifecycle state, all in a single seeded workspace (`workspace: test-workspace-alpha`):

| GID | State | Title |
|---|---|---|
| `gid-open-001` | `open` | Test open goal |
| `gid-inprogress-001` | `in_progress` | Test in-progress goal |
| `gid-completed-001` | `completed` | Test completed goal |
| `gid-cancelled-001` | `cancelled` | Test cancelled goal |

**E2E scope filter for workspaces**: `name LIKE 'test-%'`.

---

## Dev-Only Endpoint Request/Response Shapes

All endpoints mounted under `/api/v1/_e2e/*` ONLY when `FEATURE_E2E_MODE=true`. All require admin bearer token or service account with `e2e` scope.

### `POST /api/v1/_e2e/seed`

**Request**: `{ "scope": "all" | "users" | "agents" | "policies" | ... }`

**Response 200**: `{ "seeded": { "users": 5, "agents": 6, "workspaces": 1, ... }, "skipped": { "users": 0, ... } }`

**Response 404**: when flag off

**Response 401/403**: missing/insufficient auth

### `POST /api/v1/_e2e/reset`

**Request**: `{ "scope": "all" | "workspaces" | "executions" | ... }`

**Response 200**: `{ "deleted": { "workspaces": 3, "executions": 12, ... } }`

**Response 404/401/403**: as above

### `POST /api/v1/_e2e/chaos/kill-pod`

**Request**: `{ "namespace": "platform-execution", "label_selector": "app.kubernetes.io/name=runtime-controller", "count": 1 }`

**Response 200**: `{ "killed": [{ "pod": "runtime-controller-abc123", "at": "2026-04-20T10:15:00Z" }] }`

**Response 400**: namespace outside allowed list (`platform-execution`, `platform-data` only)

### `POST /api/v1/_e2e/chaos/partition-network`

**Request**: `{ "from_namespace": "platform-execution", "to_namespace": "platform-data", "ttl_seconds": 30 }`

**Response 200**: `{ "network_policy_name": "e2e-partition-abc123", "expires_at": "2026-04-20T10:15:30Z" }`

Note: the NetworkPolicy auto-deletes after `ttl_seconds` via a scheduled cleanup task.

### `POST /api/v1/_e2e/mock-llm/set-response`

**Request**: `{ "prompt_pattern": "agent_response", "response": "OK", "streaming_chunks": ["O", "K"] }` (chunks optional; if absent, response is returned as single chunk)

**Response 200**: `{ "queue_depth": { "agent_response": 1, ... } }`

### `GET /api/v1/_e2e/kafka/events`

**Query params**: `?topic=execution.events&since=2026-04-20T10:00:00Z&limit=100`

**Response 200**: `{ "events": [{ "topic": "...", "key": "...", "payload": { ... }, "timestamp": "..." }] }`

---

## Mock LLM Call Record

Every LLM call made through `common/llm/mock_provider.py` is recorded for post-test assertion. Records are held in a per-pod ring buffer (size 1000) AND mirrored to Redis list `e2e:mock_llm:calls` for cross-pod inspection.

```python
class MockLLMCallRecord:
    call_id: str            # UUID
    prompt_pattern: str     # Matched template name (e.g., "agent_response")
    prompt: str             # Full prompt text
    model: str              # e.g., "claude-opus-4-7"
    temperature: float
    max_tokens: int
    response: str           # The response returned (from queue or default)
    from_queue: bool        # True if popped from queue, False if default fallback
    streaming: bool
    started_at: str         # ISO 8601
    duration_ms: int
    correlation_context: dict  # workspace_id, execution_id, etc.
```

Tests retrieve records via a helper: `await mock_llm.get_calls(pattern="agent_response", since=test_start)`.

---

## Performance Thresholds (`tests/e2e/performance/thresholds.py`)

```python
# Launch latency (test_launch_latency.py)
WARM_LAUNCH_MAX_SECONDS = 2.0
COLD_LAUNCH_MAX_SECONDS = 10.0

# Round-trip (test_execution_roundtrip.py)
TRIVIAL_AGENT_ROUNDTRIP_MAX_SECONDS = 5.0

# Concurrency (test_concurrent_throughput.py)
CONCURRENT_EXECUTION_COUNT = 10
CONCURRENT_MAX_WALL_CLOCK_SECONDS = 15.0  # generous upper bound

# Reasoning overhead (test_reasoning_overhead.py)
REASONING_OVERHEAD_MAX_MS = 50
REASONING_BASELINE_ITERATIONS = 100  # number of samples for variance control
```

Every threshold exceeded causes a test failure with the message: `f"{test_name}: measured {measured} > threshold {threshold}"`.

---

## Chaos Scenario Inputs/Outputs

Each chaos scenario follows the pattern: (1) set up a workload, (2) inject a failure via the dev endpoint, (3) assert a specific recovery outcome, (4) teardown reverses the failure.

| Scenario | Injection | Recovery assertion | Teardown |
|---|---|---|---|
| `test_runtime_pod_kill` | `POST /_e2e/chaos/kill-pod` targeting runtime-controller mid-execution | Execution resumes from last checkpoint within 30s; final state = `completed` | Pod auto-rescheduled by K8s |
| `test_reasoning_engine_kill` | Kill reasoning-engine pod during streaming CoT | Control plane reconnects; trace replays from last ack; caller receives full trace | Pod auto-rescheduled |
| `test_kafka_broker_restart` | Restart Kafka broker via `kubectl rollout restart statefulset/kafka` wrapped by dev endpoint | All events produced during outage delivered exactly-once post-recovery | Broker comes back automatically |
| `test_s3_credential_revoke` | Rotate MinIO credentials via dev endpoint while upload in flight | Platform surfaces `S3CredentialError` to caller within 10s | Credentials restored in teardown |
| `test_network_partition` | `POST /_e2e/chaos/partition-network` reasoning-engine → postgres | Circuit breaker opens within 15s; requests fail-fast with `ServiceUnavailable` | NetworkPolicy auto-deleted at TTL |
| `test_policy_timeout` | Install a policy with deliberate 60s evaluation delay | Enforcement gate closes at timeout; action denied; audit record captures timeout reason | Policy uninstalled |

---

## Helm Overlay Structure

See [contracts/helm-overlay.md](contracts/helm-overlay.md) for the full schema. Values that must be present:

- `features.e2eMode: true` — toggles the `FEATURE_E2E_MODE` env var in control-plane pods
- `features.zeroTrustVisibility: true` — default ON in E2E to catch regressions
- `mockLLM.enabled: true` — toggles the mock provider in `common/llm/router.py`
- `objectStorage.provider: minio` — uses in-cluster MinIO via generic S3 client
- All stateful workloads `replicaCount: 1` — minimal footprint
- All resources requests/limits scaled down to match 16 GB runner budget
- `autoscaling.enabled: false` — predictable behavior during tests

---

## Artifact Bundle (CI)

On every CI run (pass or fail), the workflow uploads one artifact named `e2e-reports-<run-id>` containing:

```
reports/
├── junit.xml           # pytest JUnit output for suites + chaos + performance
├── report.html         # pytest-html self-contained HTML
├── performance.json    # Per-test measured vs. threshold
└── state-dump.txt      # Pod list + events + helm status + log tails (failure runs only)
pod-logs/
├── control-plane-<pod-id>.log  # Last 500 lines per platform pod
├── runtime-controller-<pod-id>.log
└── …
```

Retention: 30 days (GitHub Actions default); sufficient for post-failure triage.
