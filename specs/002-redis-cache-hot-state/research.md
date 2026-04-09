# Research: Redis Cache and Hot State Deployment

**Feature**: 002-redis-cache-hot-state  
**Date**: 2026-04-09  
**Status**: Complete — all unknowns resolved

---

## Decision 1: Helm Chart Selection

**Decision**: Use **`bitnami/redis-cluster`** chart (not `bitnami/redis`).

**Rationale**: The `redis-cluster` chart deploys Redis in native Cluster mode with hash slot sharding and built-in automatic failover. The `redis` chart only supports standalone or Sentinel-based replication, which is less suitable for high-throughput workloads requiring distributed key space. Cluster mode is necessary for the leaderboard (sorted sets) and budget tracking patterns that require atomic operations at scale.

**Alternatives considered**:
- `bitnami/redis` with Sentinel — slower failover (~30s vs <10s), no sharding, single-node bottleneck for writes. Rejected for production.
- Custom Redis StatefulSet — unnecessary operational complexity when Bitnami chart handles persistence, probes, and exporter.

---

## Decision 2: Dev vs Prod Configuration Strategy

**Decision**: Use separate values files (`values-prod.yaml` / `values-dev.yaml`) overlaying a shared `values.yaml` base.

**Rationale**: Helm's `-f` flag merges values files in order, so `values.yaml` (base) + `values-prod.yaml` (overrides) cleanly separates environment-specific settings. This avoids `{{ if eq .Values.environment }}` conditionals in templates and makes each profile auditable independently.

**Production**: 6 nodes (3 masters + 3 replicas), AOF, LRU eviction, PDB, metrics, network policy.  
**Development**: Single standalone node (`architecture: standalone`), AOF, no PDB, no metrics, no network policy.

---

## Decision 3: PgBouncer-style Pooler — Not Applicable

Redis Cluster handles connection routing natively. No intermediate proxy needed (unlike PostgreSQL where PgBouncer is mandatory). The `go-redis` and `redis-py` cluster clients auto-discover topology and route commands to correct nodes via `MOVED`/`ASK` redirects.

---

## Decision 4: Lua Script Architecture

**Decision**: Three standalone Lua scripts loaded at startup and called via `EVALSHA`:

| Script | Purpose | Atomicity |
|--------|---------|-----------|
| `budget_decrement.lua` | Multi-dimension budget check + decrement | Single hash key, fully atomic |
| `rate_limit_check.lua` | Sliding window via sorted set | Single key, fully atomic |
| `distributed_lock.lua` (acquire + release) | SET NX + token-verified DEL | Single key, fully atomic |

**Rationale**: Lua scripts run atomically within a single Redis node. Since each script operates on a single key, they work correctly in Cluster mode (all operations target the same hash slot). `EVALSHA` avoids sending script source on every call — only the SHA hash is transmitted.

**Alternatives considered**:
- Redis Transactions (`MULTI/EXEC`) — cannot include conditional logic (no "check then act"), so budget checks require Lua.
- Redis Functions (Redis 7+) — more structured than Lua scripts but not yet widely supported by client libraries. Deferred for future iteration.

---

## Decision 5: Budget Decrement — Fail-Closed Semantics

**Decision**: If the budget hash key does not exist in Redis, the Lua script returns `{allowed: false}`. The reasoning engine treats this as "budget exhausted."

**Rationale**: Fail-open (treating missing key as "unlimited") would allow unbounded resource consumption if a key is evicted under memory pressure or if the execution setup step failed silently. Fail-closed is the only safe default for a cost-enforcement mechanism.

**Budget hash structure** (`HGETALL budget:{execution_id}:{step_id}`):
```
max_tokens    → integer
used_tokens   → integer
max_rounds    → integer
used_rounds   → integer
max_cost      → float (stored as string, parsed in Lua via tonumber)
used_cost     → float
max_time_ms   → integer
start_time    → integer (epoch ms)
```

The Lua script checks all dimensions atomically:
1. Time limit: `current_time - start_time >= max_time_ms` → reject
2. Dimension limit: `used_{dim} + amount > max_{dim}` → reject
3. Success: `HINCRBY used_{dim} amount` → return remaining

---

## Decision 6: Python Async Client Pattern

**Decision**: Use `redis.asyncio.RedisCluster` from redis-py 5.x with lazy initialization and script SHA caching.

**Key patterns**:
- Session CRUD: `SET key value EX ttl` / `GET key` / `DEL key`
- Bulk invalidation: `SCAN cursor MATCH session:{user_id}:* COUNT 100` in batches
- Lua script execution: `register_script()` caches SHA; `EVALSHA` used on each call
- Cluster redirects: Handled automatically by the cluster client; explicit retry with backoff for edge cases

---

## Decision 7: Go Client Pattern

**Decision**: Use `github.com/redis/go-redis/v9` with `redis.NewClusterClient()` and `redis.NewScript()` for automatic `EVALSHA` → `EVAL` fallback.

**Key patterns**:
- `redis.NewScript(lua_source)` — creates a reusable script object
- `script.Run(ctx, client, keys, args...)` — automatically attempts `EVALSHA`, falls back to `EVAL` on `NOSCRIPT`
- Context timeout: 10ms for budget operations (sub-millisecond target with margin)
- Connection pool: `PoolSize: 50-100` per node for thousands of ops/sec
- Graceful shutdown: `client.Close()` with context deadline

---

## Decision 8: Network Policy Implementation

**Decision**: Deploy a standalone `NetworkPolicy` resource alongside the Helm chart (not relying on chart's built-in `networkPolicy` settings alone).

**Rationale**: The Bitnami chart's `networkPolicy.enabled` provides basic ingress/egress rules but doesn't template arbitrary namespace selectors cleanly. A standalone manifest gives full control over namespace selectors for `platform-control` and `platform-execution`.

**Policy**:
- Ingress: Allow TCP 6379 from `platform-control` and `platform-execution` namespaces only
- Ingress: Allow TCP 16379 (gossip) from pods within the same `app: redis-cluster` label (inter-cluster)
- Ingress: Allow TCP 9121 from `platform-observability` namespace (Prometheus scrape)
- Egress: Allow UDP 53 to `kube-system` (DNS) + TCP 6379/16379 within cluster

---

## Decision 9: Monitoring and Alerting

**Decision**: Use `oliver006/redis_exporter` sidecar (bundled with Bitnami chart via `metrics.enabled: true`) with a `ServiceMonitor` for Prometheus.

**Key metrics to alert on**:
- `redis_memory_used_bytes / redis_memory_max_bytes > 0.8` → memory 80% warning
- `redis_connected_clients` → connection count trending
- `redis_replication_offset` lag between master and replica
- `redis_up == 0` → node down

---

## Resolved Unknowns Summary

| Unknown | Resolution |
|---------|-----------|
| Helm chart name | `bitnami/redis-cluster` |
| Dev vs prod config | Separate `values-dev.yaml` / `values-prod.yaml` |
| Proxy/pooler needed | No — cluster clients handle routing natively |
| Lua script count | 3 scripts (budget, rate limit, lock acquire+release) |
| Budget fail mode | Fail-closed: missing key = exhausted |
| Python client | `redis.asyncio.RedisCluster` (redis-py 5.x) |
| Go client | `go-redis/redis/v9` with `NewClusterClient` |
| Network policy | Standalone K8s `NetworkPolicy` resource |
| Metrics | `redis_exporter` sidecar via Bitnami chart |
