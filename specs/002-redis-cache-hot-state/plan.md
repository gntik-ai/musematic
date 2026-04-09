# Implementation Plan: Redis Cache and Hot State Deployment

**Branch**: `002-redis-cache-hot-state` | **Date**: 2026-04-09 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/002-redis-cache-hot-state/spec.md`

## Summary

Deploy Redis 7+ in Cluster mode as the platform's hot state layer: session caching, reasoning budget tracking (atomic Lua scripts), rate limiting, distributed locks, and tournament leaderboards. Helm chart wraps Bitnami `redis-cluster` with dev/prod profiles. Python async client for the control plane, Go client for the reasoning engine.

## Technical Context

**Language/Version**: Python 3.12+ (control plane client), Go 1.22+ (reasoning engine client)  
**Primary Dependencies**: `redis-py 5.x` (Python async), `go-redis/redis/v9` (Go), Bitnami `redis-cluster` Helm chart  
**Storage**: Redis 7 with AOF persistence (append-only file, fsync every second)  
**Testing**: pytest + pytest-asyncio + `testcontainers[redis]` (Python); Go testing package (Go)  
**Target Platform**: Kubernetes (production), local Docker (development)  
**Project Type**: Infrastructure + client library  
**Performance Goals**: <1ms p99 GET/SET latency; sub-millisecond budget enforcement; <10s failover  
**Constraints**: Redis is hot state only — no persistent business data; fail-closed budget enforcement  
**Scale/Scope**: 6-node production cluster; 6 key namespaces; 4 Lua scripts

## Constitution Check

*GATE: Validated against constitution v1.0.0 (2026-04-09)*

| Principle | Status | Notes |
|-----------|--------|-------|
| III. Dedicated Data Stores | ✅ Pass | Redis used exclusively for caching and hot state |
| IV. No Cross-Boundary DB Access | ✅ Pass | Redis client in `common/clients/`, shared utility |
| II. Go Satellite Service | ✅ Pass | Budget tracking delegated to Go reasoning engine |
| XI. Secrets Never in LLM | ✅ Pass | Redis credentials via K8s Secret |
| VII. Simulation Isolation | ✅ N/A | Infrastructure feature, no simulation concern |

No blocking violations. Proceed.

## Project Structure

### Documentation (this feature)

```text
specs/002-redis-cache-hot-state/
├── plan.md              # This file
├── research.md          # Phase 0 — all unknowns resolved
├── data-model.md        # Phase 1 — key patterns, value structures, TTL policies
├── quickstart.md        # Phase 1 — operator and developer getting-started guide
├── contracts/
│   ├── redis-client.md  # Python + Go client interface contracts
│   └── helm-chart.md    # Chart values and Kubernetes resources contract
└── tasks.md             # Phase 2 — created by /speckit.tasks
```

### Source Code (repository root)

```text
deploy/
└── helm/
    └── redis/
        ├── Chart.yaml
        ├── values.yaml           # Shared base values
        ├── values-prod.yaml      # Production: 6-node cluster, metrics, netpol
        ├── values-dev.yaml       # Development: single standalone node
        └── templates/
            ├── secret.yaml       # Redis credentials
            ├── namespace.yaml    # platform-data namespace (if not exists)
            └── netpol.yaml       # NetworkPolicy (production only)

apps/
└── control-plane/
    └── src/
        └── platform/
            └── common/
                └── clients/
                    ├── __init__.py
                    └── redis.py          # AsyncRedisClient wrapper

lua/                                      # Shared Lua scripts (used by both clients)
├── budget_decrement.lua
├── rate_limit_check.lua
├── lock_acquire.lua
└── lock_release.lua

# Go reasoning engine (separate module, referenced here for context)
# services/reasoning-engine/internal/redis/budget_client.go
```

**Structure Decision**: Lua scripts live in a top-level `lua/` directory because they are shared between the Python and Go clients. Both clients load the same script source files at startup.

## Phase 0: Research — Complete

See [research.md](research.md) for full findings. Key decisions:

| Topic | Decision |
|-------|---------|
| Helm chart | `bitnami/redis-cluster` (not `bitnami/redis`) |
| Dev vs prod | Separate `values-dev.yaml` / `values-prod.yaml` overlay files |
| Proxy/pooler | Not needed — cluster clients handle routing natively |
| Lua scripts | 4 scripts: budget decrement, rate limit, lock acquire, lock release |
| Budget fail mode | Fail-closed: missing key = exhausted |
| Python client | `redis.asyncio.RedisCluster` (redis-py 5.x) |
| Go client | `go-redis/redis/v9` with `NewClusterClient` |
| Network policy | Standalone `NetworkPolicy` resource (not chart built-in) |
| Monitoring | `redis_exporter` sidecar via `metrics.enabled: true` |

## Phase 1: Implementation Steps

### Step 1 — Helm Chart: Chart.yaml and Base Values

**File**: `deploy/helm/redis/Chart.yaml`

```yaml
apiVersion: v2
name: musematic-redis
description: Redis 7+ cluster for session caching, budget tracking, and hot state
type: application
version: 0.1.0
appVersion: "7.2"
dependencies:
  - name: redis-cluster
    version: "14.3.3"
    repository: https://charts.bitnami.com/bitnami
```

**File**: `deploy/helm/redis/values.yaml` (shared base)

```yaml
redis-cluster:
  image:
    tag: "7.2"
  auth:
    enabled: true
    existingSecret: redis-credentials
    existingSecretPasswordKey: password
  persistence:
    enabled: true
    appendonly: "yes"
    appendfsync: "everysec"
  redis:
    maxmemoryPolicy: "allkeys-lru"
    extraFlags:
      - "--cluster-node-timeout"
      - "15000"
      - "--cluster-require-full-coverage"
      - "no"
  service:
    type: ClusterIP
    port: 6379
```

---

### Step 2 — Helm Chart: Production Values

**File**: `deploy/helm/redis/values-prod.yaml`

```yaml
redis-cluster:
  cluster:
    nodes: 6
    replicas: 1
  redis:
    maxmemory: "4Gi"
  persistence:
    size: 100Gi
  resources:
    requests:
      cpu: 1000m
      memory: 2Gi
    limits:
      cpu: 2000m
      memory: 5Gi
  metrics:
    enabled: true
    serviceMonitor:
      enabled: true
  podDisruptionBudget:
    enabled: true
    maxUnavailable: 1
```

---

### Step 3 — Helm Chart: Development Values

**File**: `deploy/helm/redis/values-dev.yaml`

```yaml
redis-cluster:
  architecture: standalone
  cluster:
    nodes: 1
    replicas: 0
  redis:
    maxmemory: "1Gi"
  persistence:
    size: 10Gi
  resources:
    requests:
      cpu: 250m
      memory: 512Mi
    limits:
      cpu: 500m
      memory: 1Gi
  metrics:
    enabled: false
  podDisruptionBudget:
    enabled: false
```

---

### Step 4 — Helm Chart: Secret and Network Policy

**File**: `deploy/helm/redis/templates/secret.yaml`

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: redis-credentials
  namespace: platform-data
type: Opaque
data:
  password: {{ .Values.auth.password | b64enc | quote }}
```

**File**: `deploy/helm/redis/templates/netpol.yaml`

```yaml
{{- if .Values.networkPolicy.enabled }}
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: redis-cluster-netpol
  namespace: platform-data
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: redis-cluster
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              name: platform-control
      ports:
        - protocol: TCP
          port: 6379
    - from:
        - namespaceSelector:
            matchLabels:
              name: platform-execution
      ports:
        - protocol: TCP
          port: 6379
    - from:
        - podSelector:
            matchLabels:
              app.kubernetes.io/name: redis-cluster
      ports:
        - protocol: TCP
          port: 16379
    - from:
        - namespaceSelector:
            matchLabels:
              name: platform-observability
      ports:
        - protocol: TCP
          port: 9121
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              name: kube-system
      ports:
        - protocol: UDP
          port: 53
    - to:
        - podSelector:
            matchLabels:
              app.kubernetes.io/name: redis-cluster
      ports:
        - protocol: TCP
          port: 6379
        - protocol: TCP
          port: 16379
{{- end }}
```

---

### Step 5 — Lua Scripts

**File**: `lua/budget_decrement.lua`

Atomic multi-dimension budget check and decrement. Takes budget hash key, current time, dimension name, and amount. Returns `{allowed, remaining_tokens, remaining_rounds, remaining_cost, remaining_time_ms}`. Returns `{0, -1, -1, -1, -1}` if key doesn't exist (fail-closed).

Key implementation details:
- Time check: `current_time - start_time >= max_time_ms` → reject
- Dimension check: `used + amount > max` → reject
- Update: `HINCRBY` for int dimensions, `HINCRBYFLOAT` for cost

**File**: `lua/rate_limit_check.lua`

Sliding window rate limiter using sorted sets. Removes expired entries, counts remaining, adds new entry if under limit. Sets key expiry to `window_size + 1s`. Returns `{allowed, remaining, retry_after_ms}`.

**File**: `lua/lock_acquire.lua`

SET-if-not-exists with TTL. Supports renewal by same token. Returns `1` (acquired) or `0` (held).

**File**: `lua/lock_release.lua`

Token-verified DEL. Returns `1` (released) or `0` (wrong token / not held).

---

### Step 6 — Python Async Redis Client

**File**: `apps/control-plane/src/platform/common/clients/redis.py`

`AsyncRedisClient` class using `redis.asyncio.RedisCluster`:
- Lazy initialization with `asyncio.Lock`
- Script SHA caching via `register_script()` at startup
- Methods per the `contracts/redis-client.md` contract
- Session CRUD with JSON serialization + TTL
- Budget init/decrement/get/delete
- Rate limit check
- Lock acquire/release
- Leaderboard CRUD (ZADD, ZREVRANGE, ZREVRANK, ZREM)
- Cache get/set/delete
- Health check via `PING`

Connection pooling: `max_connections=32` default, configurable. Automatic `MOVED`/`ASK` redirect handling with retry.

---

### Step 7 — Go Budget Client

**File**: `services/reasoning-engine/internal/redis/budget_client.go` (reference — Go module is separate)

`BudgetClient` struct using `redis.NewClusterClient()`:
- `redis.NewScript(lua_source)` for `budget_decrement.lua`
- `script.Run(ctx, client, keys, args...)` with automatic `EVALSHA` → `EVAL` fallback
- Context timeout: 10ms for budget operations
- Connection pool: `PoolSize: 50`, `MinIdleConns: 25`
- Graceful shutdown: `client.Close()` with context deadline

---

### Step 8 — Integration Tests (Python)

**File**: `apps/control-plane/tests/integration/test_redis.py`

Using `testcontainers[redis]` (single Redis node for CI):

| Test | Verifies |
|------|---------|
| `test_session_crud` | SET with TTL, GET, DEL, verify expiry |
| `test_session_bulk_invalidation` | SCAN + DEL for user's sessions |
| `test_budget_decrement_allowed` | Initialize budget, decrement within limits |
| `test_budget_decrement_rejected` | Decrement exceeding budget → `allowed=False` |
| `test_budget_missing_key_fail_closed` | Decrement on missing key → `allowed=False` |
| `test_budget_concurrent_decrements` | 100 concurrent decrements, verify exact sum |
| `test_budget_time_limit` | Budget with expired time → `allowed=False` |
| `test_rate_limit_allowed` | N requests within limit |
| `test_rate_limit_exceeded` | N+1 request → rejected with `retry_after_ms` |
| `test_rate_limit_window_slide` | Wait for window to advance, next request allowed |
| `test_lock_acquire_release` | Acquire, verify exclusive, release, re-acquire |
| `test_lock_wrong_token_release` | Release with wrong token → rejected |
| `test_lock_ttl_expiry` | Lock expires after TTL without release |
| `test_leaderboard_ranking` | Add entries, verify sorted order, update score, verify rank change |
| `test_leaderboard_remove` | Remove entry, verify rankings shift |

---

### Step 9 — CI and Health Check

**File**: `.github/workflows/db-check.yml` (append to existing)

```yaml
redis-tests:
  services:
    redis:
      image: redis:7
      ports:
        - 6379:6379
  steps:
    - run: pytest apps/control-plane/tests/integration/test_redis.py -v
```

Add `helm lint deploy/helm/redis` to existing Helm lint job.

**Health check** (for platform-cli diagnose integration):
- `AsyncRedisClient.health_check()` → `PING` returns `True`/`False`

---

## Complexity Tracking

No constitution violations. Standard patterns: Bitnami Helm chart, Lua scripts for atomicity, cluster-aware clients.

---

## Dependencies

- **Soft dependency on 001-postgresql-schema-foundation**: Session data references user IDs from PostgreSQL. The Redis client can operate independently, but meaningful session payloads require the user table to exist.
- No hard blocking dependencies — Redis can be deployed in parallel with PostgreSQL.
