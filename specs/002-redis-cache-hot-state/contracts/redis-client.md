# Contract: Redis Client Interface

**Feature**: 002-redis-cache-hot-state  
**Date**: 2026-04-09  
**Type**: Internal — consumed by control plane (Python) and reasoning engine (Go)

---

## Overview

Two client implementations access the Redis Cluster. Each client wraps the same Lua scripts and key patterns but uses its own language-native Redis library.

---

## Python Client Contract (Control Plane)

**Module**: `apps/control-plane/src/platform/common/clients/redis.py`

### `AsyncRedisClient`

Lazy-initialized async Redis Cluster client. All methods are async.

#### Session Operations

| Method | Signature | Description |
|--------|-----------|-------------|
| `set_session` | `(user_id: str, session_id: str, data: dict, ttl_seconds: int = 1800) → None` | Store session JSON with TTL |
| `get_session` | `(user_id: str, session_id: str) → Optional[dict]` | Retrieve session; returns None if expired/missing |
| `delete_session` | `(user_id: str, session_id: str) → bool` | Delete session; returns True if existed |
| `invalidate_user_sessions` | `(user_id: str) → int` | Delete all sessions for a user via SCAN; returns count |

#### Budget Operations

| Method | Signature | Description |
|--------|-----------|-------------|
| `init_budget` | `(execution_id: str, step_id: str, budget: BudgetConfig, ttl_seconds: int) → None` | Initialize budget hash |
| `decrement_budget` | `(execution_id: str, step_id: str, dimension: str, amount: float) → BudgetResult` | Atomic decrement via Lua script |
| `get_budget` | `(execution_id: str, step_id: str) → Optional[dict]` | Read full budget state |
| `delete_budget` | `(execution_id: str, step_id: str) → bool` | Cleanup after completion |

**`BudgetResult`**: `{allowed: bool, remaining_tokens: int, remaining_rounds: int, remaining_cost: float, remaining_time_ms: int}`

**Fail-closed**: `decrement_budget` returns `BudgetResult(allowed=False)` if the key doesn't exist.

#### Rate Limiting

| Method | Signature | Description |
|--------|-----------|-------------|
| `check_rate_limit` | `(resource: str, key: str, limit: int, window_ms: int) → RateLimitResult` | Check and record request via Lua script |

**`RateLimitResult`**: `{allowed: bool, remaining: int, retry_after_ms: int}`

#### Distributed Locks

| Method | Signature | Description |
|--------|-----------|-------------|
| `acquire_lock` | `(resource: str, id: str, ttl_seconds: int = 10) → LockResult` | Acquire lock with UUID token |
| `release_lock` | `(resource: str, id: str, token: str) → bool` | Release lock (token must match) |

**`LockResult`**: `{success: bool, token: Optional[str]}`

#### Leaderboard Operations

| Method | Signature | Description |
|--------|-----------|-------------|
| `leaderboard_add` | `(tournament_id: str, hypothesis_id: str, score: float) → None` | Add/update Elo score |
| `leaderboard_top` | `(tournament_id: str, n: int) → list[tuple[str, float]]` | Top N entries (id, score) descending |
| `leaderboard_rank` | `(tournament_id: str, hypothesis_id: str) → Optional[int]` | 0-indexed rank of hypothesis |
| `leaderboard_remove` | `(tournament_id: str, hypothesis_id: str) → bool` | Remove from leaderboard |

#### Cache Operations

| Method | Signature | Description |
|--------|-----------|-------------|
| `cache_set` | `(context: str, key: str, value: dict, ttl_seconds: int = 300) → None` | Cache JSON with TTL |
| `cache_get` | `(context: str, key: str) → Optional[dict]` | Retrieve cached value |
| `cache_delete` | `(context: str, key: str) → bool` | Explicit invalidation |

#### Lifecycle

| Method | Signature | Description |
|--------|-----------|-------------|
| `initialize` | `() → None` | Connect to cluster, load Lua scripts |
| `close` | `() → None` | Close connections |
| `health_check` | `() → bool` | PING cluster; True if healthy |

---

## Go Client Contract (Reasoning Engine)

**Package**: `internal/redis` (within the Go reasoning engine module)

### `BudgetClient`

Minimal interface — the Go client only needs budget operations for the reasoning pipeline.

```go
type BudgetClient interface {
    InitBudget(ctx context.Context, executionID, stepID string, config BudgetConfig) error
    DecrementBudget(ctx context.Context, executionID, stepID string, dimension string, amount int64) (BudgetResult, error)
    GetBudget(ctx context.Context, executionID, stepID string) (*BudgetState, error)
    DeleteBudget(ctx context.Context, executionID, stepID string) error
    Close() error
}
```

**`BudgetResult`**: `{Allowed bool, RemainingTokens int64, RemainingRounds int64, RemainingCost float64, RemainingTimeMs int64}`

**Context timeout**: 10ms default for `DecrementBudget` (sub-millisecond target with margin).

**Connection pool**: `PoolSize: 50-100` per cluster node. Pre-warmed at startup.

---

## Lua Script Contract

All Lua scripts operate on a single key (compatible with Redis Cluster hash slot routing).

### `budget_decrement.lua`

- **KEYS[1]**: `budget:{execution_id}:{step_id}`
- **ARGV[1]**: `current_time_ms` (integer)
- **ARGV[2]**: `dimension` (`"tokens"` | `"rounds"` | `"cost"`)
- **ARGV[3]**: `amount` (number)
- **Returns**: `{allowed, remaining_tokens, remaining_rounds, remaining_cost, remaining_time_ms}`
- **Fail-closed**: Returns `{0, -1, -1, -1, -1}` if key doesn't exist

### `rate_limit_check.lua`

- **KEYS[1]**: `ratelimit:{resource}:{key}`
- **ARGV[1]**: `current_time_ms` (integer)
- **ARGV[2]**: `window_size_ms` (integer)
- **ARGV[3]**: `limit` (integer)
- **Returns**: `{allowed, remaining, retry_after_ms}`

### `lock_acquire.lua`

- **KEYS[1]**: `lock:{resource}:{id}`
- **ARGV[1]**: `token` (UUID string)
- **ARGV[2]**: `ttl_seconds` (integer)
- **Returns**: `1` (acquired) or `0` (held by another)

### `lock_release.lua`

- **KEYS[1]**: `lock:{resource}:{id}`
- **ARGV[1]**: `token` (UUID string)
- **Returns**: `1` (released) or `0` (not held or wrong token)

---

## Connection Routing

| Consumer | Target | Notes |
|----------|--------|-------|
| Python control plane | Redis Cluster service (`musematic-redis-cluster:6379`) | All operations except budget |
| Go reasoning engine | Redis Cluster service (`musematic-redis-cluster:6379`) | Budget operations only |
| Prometheus | redis-exporter sidecar (`:9121/metrics`) | Read-only metrics scrape |

Both clients use cluster-aware routing (automatic `MOVED`/`ASK` redirect handling).
