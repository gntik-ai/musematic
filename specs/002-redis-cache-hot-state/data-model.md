# Data Model: Redis Cache and Hot State Deployment

**Feature**: 002-redis-cache-hot-state  
**Date**: 2026-04-09

---

## Key Space Overview

Redis is a key-value store. This data model defines the key naming conventions, value structures, TTL policies, and data type per use case.

```
session:{user_id}:{session_id}     → STRING (JSON)       TTL: configurable (default 30m)
budget:{execution_id}:{step_id}    → HASH                TTL: execution lifetime
ratelimit:{resource}:{key}         → SORTED SET           TTL: window_size + 1s buffer
lock:{resource}:{id}               → STRING (UUID token)  TTL: configurable (default 10s)
leaderboard:{tournament_id}        → SORTED SET           TTL: none (explicit cleanup)
cache:{context}:{key}              → STRING (JSON)        TTL: configurable per context
```

---

## Entity Definitions

### Session Record

**Key pattern**: `session:{user_id}:{session_id}`  
**Redis type**: STRING  
**Value format**: JSON  
**TTL**: Configurable per session (default: 1800s / 30 minutes)

| JSON Field | Type | Description |
|------------|------|-------------|
| `user_id` | `string (UUID)` | User identifier |
| `session_id` | `string (UUID)` | Unique session identifier |
| `email` | `string` | User email (for display) |
| `roles` | `string[]` | User roles in current workspace |
| `workspace_id` | `string (UUID)` | Active workspace |
| `created_at` | `integer (epoch ms)` | Session creation time |
| `last_active` | `integer (epoch ms)` | Last request timestamp |

**Operations**:
- `SET session:{uid}:{sid} <json> EX <ttl>` — create/update
- `GET session:{uid}:{sid}` — retrieve
- `DEL session:{uid}:{sid}` — logout
- `SCAN 0 MATCH session:{uid}:* COUNT 100` — bulk invalidation for user suspension

**Eviction behavior**: If evicted under memory pressure, user re-authenticates. Non-authoritative — authoritative session data is in PostgreSQL.

---

### Budget Hash

**Key pattern**: `budget:{execution_id}:{step_id}`  
**Redis type**: HASH  
**TTL**: Set to execution timeout + buffer (e.g., `max_time_ms + 60000ms`)

| Hash Field | Type | Description |
|------------|------|-------------|
| `max_tokens` | `integer` | Maximum token budget for this step |
| `used_tokens` | `integer` | Tokens consumed so far |
| `max_rounds` | `integer` | Maximum reasoning rounds allowed |
| `used_rounds` | `integer` | Rounds completed so far |
| `max_cost` | `float (as string)` | Maximum cost in currency units |
| `used_cost` | `float (as string)` | Cost accumulated so far |
| `max_time_ms` | `integer` | Maximum wall-clock time in milliseconds |
| `start_time` | `integer (epoch ms)` | When the step began executing |

**Operations**:
- `HSET budget:{eid}:{sid} max_tokens 1000 used_tokens 0 ...` — initialize budget
- `EVALSHA <budget_decrement_sha> 1 budget:{eid}:{sid} <current_time_ms> tokens 100` — atomic decrement
- `HGETALL budget:{eid}:{sid}` — read full budget state
- `DEL budget:{eid}:{sid}` — cleanup after step completion

**Fail-closed invariant**: If `HGETALL` returns empty (key doesn't exist or was evicted), the Lua script returns `{allowed: false}`. The reasoning engine must treat this as "budget exhausted."

**Concurrency model**: The Lua script is atomic — no race conditions even under 1000+ concurrent decrements. The script reads, checks, and writes within a single Redis command execution (no interleaving).

---

### Rate Limit Counter

**Key pattern**: `ratelimit:{resource}:{key}`  
**Redis type**: SORTED SET  
**TTL**: `window_size_ms + 1000ms` (auto-set by Lua script)

| Sorted Set Member | Score | Description |
|--------------------|-------|-------------|
| `{timestamp_ms}:{random_id}` | `{timestamp_ms}` | Each request is a member scored by its timestamp |

**Operations** (all via Lua script `rate_limit_check.lua`):
1. `ZREMRANGEBYSCORE key -inf (current_time - window_size)` — remove expired entries
2. `ZCARD key` — count entries in current window
3. If count < limit: `ZADD key current_time_ms member` — add entry
4. If count >= limit: compute `retry_after_ms` from oldest entry
5. `PEXPIRE key (window_size + 1000)` — refresh TTL

**Return value**: `{allowed: bool, remaining: int, retry_after_ms: int}`

---

### Distributed Lock

**Key pattern**: `lock:{resource}:{id}`  
**Redis type**: STRING  
**Value**: UUID token (unique per holder)  
**TTL**: Configurable (default: 10s, max: 300s)

**Operations**:
- **Acquire** (Lua script `lock_acquire.lua`):
  - If key doesn't exist: `SET key token EX ttl` → return `1`
  - If key exists with same token (renewal): `EXPIRE key ttl` → return `1`
  - If key exists with different token: return `0`
- **Release** (Lua script `lock_release.lua`):
  - If key value matches token: `DEL key` → return `1`
  - If key doesn't exist or token mismatch: return `0`

**Safety invariants**:
- Only the token holder can release the lock (prevents accidental release by other services)
- TTL auto-releases if holder crashes (prevents deadlocks)
- Renewal by same token extends the TTL (for long operations)

---

### Leaderboard Entry

**Key pattern**: `leaderboard:{tournament_id}`  
**Redis type**: SORTED SET  
**TTL**: None (explicitly deleted when tournament ends)

| Sorted Set Member | Score | Description |
|--------------------|-------|-------------|
| `{hypothesis_id}` | `{elo_score}` | Hypothesis UUID scored by Elo rating |

**Operations**:
- `ZADD leaderboard:{tid} <score> <hypothesis_id>` — add or update score
- `ZREVRANGE leaderboard:{tid} 0 <N-1> WITHSCORES` — top N by score (descending)
- `ZREVRANK leaderboard:{tid} <hypothesis_id>` — rank of a specific hypothesis (0-indexed)
- `ZSCORE leaderboard:{tid} <hypothesis_id>` — score of a specific hypothesis
- `ZREM leaderboard:{tid} <hypothesis_id>` — remove hypothesis
- `ZCARD leaderboard:{tid}` — total entries
- `DEL leaderboard:{tid}` — delete entire leaderboard (tournament cleanup)

---

### Cache Entry

**Key pattern**: `cache:{context}:{key}`  
**Redis type**: STRING  
**Value format**: JSON  
**TTL**: Configurable per context (default: 300s / 5 minutes)

Generic hot-path caching for reducing backend load. The `context` segment groups caches by domain (e.g., `cache:agent-profile:uuid`, `cache:workspace-settings:uuid`).

**Operations**:
- `SET cache:{ctx}:{key} <json> EX <ttl>` — cache with expiry
- `GET cache:{ctx}:{key}` — retrieve (miss returns nil → caller fetches from source)
- `DEL cache:{ctx}:{key}` — explicit invalidation

---

## Memory Management

| Key Type | Eviction Risk | Impact of Eviction |
|----------|---------------|-------------------|
| `session:*` | Medium | User re-authenticates (non-authoritative) |
| `budget:*` | Low (short TTL) | Fail-closed: budget treated as exhausted — safe |
| `ratelimit:*` | Medium | Rate limit temporarily relaxed — acceptable |
| `lock:*` | Low (short TTL) | Lock auto-releases — same as TTL expiry |
| `leaderboard:*` | Low (no TTL, long-lived) | Would require rebuild from PostgreSQL — avoid |
| `cache:*` | High (designed for it) | Cache miss, caller fetches from source — by design |

**Eviction policy**: `allkeys-lru` with `maxmemory` set to 80% of pod memory limit. The 20% headroom prevents OOM kills.
