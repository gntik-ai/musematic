# Tasks: Redis Cache and Hot State Deployment

**Input**: Design documents from `specs/002-redis-cache-hot-state/`  
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US6)
- All paths relative to repo root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create directory skeleton and Helm chart manifest so all phases can begin.

- [X] T001 Create directory structure: `deploy/helm/redis/templates/`, `lua/`, `apps/control-plane/src/platform/common/clients/`, `apps/control-plane/tests/integration/`
- [X] T002 [P] Create `deploy/helm/redis/Chart.yaml` with name `musematic-redis`, version `0.1.0`, and Bitnami `redis-cluster` v14.3.3 as a dependency
- [X] T003 [P] Create `apps/control-plane/src/platform/common/clients/__init__.py` (empty package marker)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Helm chart values and templates that all user story phases depend on.

**⚠️ CRITICAL**: US1 tasks cannot start until this phase is complete.

- [X] T004 Create `deploy/helm/redis/values.yaml` (shared base): `redis-cluster.image.tag: "7.2"`, `auth.enabled: true`, `auth.existingSecret: redis-credentials`, `auth.existingSecretPasswordKey: password`, `persistence.enabled: true`, `persistence.appendonly: "yes"`, `persistence.appendfsync: "everysec"`, `redis.maxmemoryPolicy: "allkeys-lru"`, `redis.extraFlags: ["--cluster-node-timeout", "15000", "--cluster-require-full-coverage", "no"]`, `service.type: ClusterIP`, `service.port: 6379`
- [X] T005 [P] Create `deploy/helm/redis/values-prod.yaml`: `redis-cluster.cluster.nodes: 6`, `cluster.replicas: 1`, `redis.maxmemory: "4Gi"`, `persistence.size: 100Gi`, `resources.requests.cpu: 1000m`, `resources.requests.memory: 2Gi`, `resources.limits.cpu: 2000m`, `resources.limits.memory: 5Gi`, `metrics.enabled: true`, `metrics.serviceMonitor.enabled: true`, `podDisruptionBudget.enabled: true`, `podDisruptionBudget.maxUnavailable: 1`, `networkPolicy.enabled: true`
- [X] T006 [P] Create `deploy/helm/redis/values-dev.yaml`: `redis-cluster.architecture: standalone`, `cluster.nodes: 1`, `cluster.replicas: 0`, `redis.maxmemory: "1Gi"`, `persistence.size: 10Gi`, `resources.requests.cpu: 250m`, `resources.requests.memory: 512Mi`, `resources.limits.cpu: 500m`, `resources.limits.memory: 1Gi`, `metrics.enabled: false`, `podDisruptionBudget.enabled: false`, `networkPolicy.enabled: false`
- [X] T007 [P] Create `deploy/helm/redis/templates/secret.yaml` templating the `redis-credentials` Kubernetes Secret with `password` key (value injected via `auth.password` Helm value or external secret operator)
- [X] T008 [P] Create `deploy/helm/redis/templates/namespace.yaml` ensuring the `platform-data` namespace exists (idempotent, with `helm.sh/resource-policy: keep` annotation)
- [X] T009 Create `apps/control-plane/src/platform/common/clients/redis.py` with `AsyncRedisClient` class skeleton: class definition, `__init__` accepting `nodes: list[str]` and optional `password: str` from env `REDIS_PASSWORD`, `asyncio.Lock` for lazy init, `_lua_scripts: dict[str, str]` cache, stub methods for all contract operations returning `NotImplementedError`

**Checkpoint**: Helm chart base ready — US1 can start; Python client skeleton ready — US2+ can start populating methods.

---

## Phase 3: User Story 1 — Platform Operator Deploys Redis Cluster (Priority: P1) 🎯 MVP

**Goal**: Single `helm install -f values-prod.yaml` creates a 6-node Redis Cluster in `platform-data` with monitoring, PDB, and network policy. Single `helm install -f values-dev.yaml` creates a standalone node.

**Independent Test**: Deploy with `values-prod.yaml`, run `redis-cli cluster info` and verify `cluster_state:ok` and `cluster_size:3`. Delete a master pod and confirm re-election within 10 seconds. `curl :9121/metrics | grep redis_up` returns `redis_up 1`.

- [X] T010 [US1] Create `deploy/helm/redis/templates/netpol.yaml` guarded by `{{- if .Values.networkPolicy.enabled }}`: `apiVersion: networking.k8s.io/v1` NetworkPolicy selecting `app.kubernetes.io/name: redis-cluster` pods; ingress: TCP 6379 from `platform-control` and `platform-execution` namespaces, TCP 16379 from own pods (gossip), TCP 9121 from `platform-observability` namespace; egress: UDP 53 to `kube-system` (DNS), TCP 6379+16379 to own pods
- [X] T011 [P] [US1] Add `helm lint deploy/helm/redis --strict` step to `.github/workflows/db-check.yml` CI job alongside existing PostgreSQL chart lint
- [X] T012 [P] [US1] Add `helm template deploy/helm/redis -f deploy/helm/redis/values-prod.yaml | kubeconform -strict` manifest validation step to `.github/workflows/db-check.yml`

**Checkpoint**: `helm lint` passes; `helm template` produces valid manifests for both prod and dev profiles.

---

## Phase 4: User Story 2 — Control Plane Manages User Sessions (Priority: P1)

**Goal**: `AsyncRedisClient` can store, retrieve, delete, and bulk-invalidate session records. Sessions expire automatically after TTL.

**Independent Test**: `await client.set_session("u1", "s1", data, ttl_seconds=5)`, retrieve within TTL → data returned; wait >5s → `None` returned. `await client.delete_session("u1", "s1")` → immediate removal. `await client.invalidate_user_sessions("u1")` → all matching sessions deleted.

- [X] T013 [US2] Implement `initialize()` method in `apps/control-plane/src/platform/common/clients/redis.py`: create `redis.asyncio.RedisCluster.from_url()` with `max_connections=32`, `decode_responses=True`, `skip_full_coverage_check=True`; add `close()` method calling `await self.client.close()`
- [X] T014 [US2] Implement session CRUD methods in `apps/control-plane/src/platform/common/clients/redis.py`: `set_session(user_id, session_id, data, ttl_seconds=1800)` → `SET session:{user_id}:{session_id} <json> EX ttl`; `get_session(user_id, session_id)` → `GET` + JSON parse, returns None if missing; `delete_session(user_id, session_id)` → `DEL`, returns bool; `invalidate_user_sessions(user_id)` → `SCAN` with pattern `session:{user_id}:*` in batches of 100, `DEL` each batch, returns count deleted
- [X] T015 [US2] Write integration tests for session operations in `apps/control-plane/tests/integration/test_redis_sessions.py` using `testcontainers[redis]`: `test_set_get_session` (store and retrieve); `test_session_ttl_expiry` (set with 1s TTL, sleep, verify None); `test_delete_session` (verify immediate removal); `test_invalidate_user_sessions` (multiple sessions for same user, verify all deleted)

**Checkpoint**: Session tests pass against a real Redis container.

---

## Phase 5: User Story 3 — Reasoning Engine Tracks Budget in Real Time (Priority: P1)

**Goal**: `budget_decrement.lua` atomically enforces token/round/cost/time limits. Python client exposes budget init/decrement/get/delete. Fail-closed: missing key returns `allowed=False`.

**Independent Test**: Initialize budget with `max_tokens=1000`, call `decrement_budget("tokens", 100)` ten times → all succeed, `remaining_tokens=0`. Eleventh call → `allowed=False`. Call on non-existent key → `allowed=False`. 100 concurrent decrements of 10 tokens on 1000-token budget → exactly 100 succeed, none over-allocate.

- [X] T016 [US3] Create `lua/budget_decrement.lua`: `KEYS[1]` = budget hash key; `ARGV[1]` = `current_time_ms` (int); `ARGV[2]` = dimension (`"tokens"` | `"rounds"` | `"cost"`); `ARGV[3]` = amount; `HGETALL` budget, return `{0,-1,-1,-1,-1}` if empty (fail-closed); check elapsed time vs `max_time_ms`; check `used_{dim} + amount <= max_{dim}`; if allowed: `HINCRBY` (or `HINCRBYFLOAT` for cost), return `{1, remaining_tokens, remaining_rounds, remaining_cost, remaining_time_ms}`; if rejected: return `{0, remaining_tokens, remaining_rounds, remaining_cost, remaining_time_ms}`
- [X] T017 [US3] Implement budget methods in `apps/control-plane/src/platform/common/clients/redis.py`: `init_budget(execution_id, step_id, config: BudgetConfig, ttl_seconds: int)` → `HSET budget:{eid}:{sid} max_tokens ... used_tokens 0 start_time <epoch_ms>` then `PEXPIRE`; `decrement_budget(execution_id, step_id, dimension: str, amount: float)` → load `lua/budget_decrement.lua` SHA on first call, `EVALSHA` with `current_time_ms=int(time.time()*1000)`, return `BudgetResult` dataclass; `get_budget(execution_id, step_id)` → `HGETALL`, return dict or None; `delete_budget(execution_id, step_id)` → `DEL`
- [X] T018 [US3] Add `BudgetResult` and `BudgetConfig` dataclasses to `apps/control-plane/src/platform/common/clients/redis.py`: `BudgetResult(allowed: bool, remaining_tokens: int, remaining_rounds: int, remaining_cost: float, remaining_time_ms: int)`; `BudgetConfig(max_tokens: int, max_rounds: int, max_cost: float, max_time_ms: int)`
- [X] T019 [US3] Write integration tests in `apps/control-plane/tests/integration/test_redis_budget.py`: `test_budget_decrement_allowed` (init, decrement within limits, verify `allowed=True` and remaining); `test_budget_decrement_rejected` (decrement exceeding `max_tokens` → `allowed=False`, budget unchanged); `test_budget_missing_key_fail_closed` (decrement on non-existent key → `allowed=False`); `test_budget_time_limit` (init with `max_time_ms=1`, sleep, decrement → `allowed=False`); `test_budget_concurrent_no_race` (100 concurrent decrements of 10 on 1000-token budget using `asyncio.gather`, verify exactly 100 succeed and final `used_tokens=1000`)

**Checkpoint**: All budget integration tests pass; no over-allocation under concurrency.

---

## Phase 6: User Story 4 — Platform Enforces Rate Limits (Priority: P2)

**Goal**: `rate_limit_check.lua` enforces sliding window rate limits. Requests within the window succeed; excess requests return `retry_after_ms`.

**Independent Test**: Configure limit=5 per 10-second window. Send 5 requests → all `allowed=True`. Send 6th → `allowed=False` with `retry_after_ms > 0`. Advance time past window start of oldest entry → next request `allowed=True`.

- [X] T020 [US4] Create `lua/rate_limit_check.lua`: `KEYS[1]` = sorted set key; `ARGV[1]` = `current_time_ms`; `ARGV[2]` = `window_size_ms`; `ARGV[3]` = `limit`; `ZREMRANGEBYSCORE key -inf (current_time_ms - window_size_ms)`; `ZCARD key`; if under limit: `ZADD key current_time_ms "{current_time_ms}:{random}"`, `PEXPIRE key (window_size_ms + 1000)`, return `{1, limit - new_count, 0}`; if at limit: get oldest entry score, compute `retry_after_ms`, return `{0, 0, retry_after_ms}`
- [X] T021 [US4] Implement `check_rate_limit(resource, key, limit, window_ms)` in `apps/control-plane/src/platform/common/clients/redis.py`: build key `ratelimit:{resource}:{key}`, load `lua/rate_limit_check.lua` SHA on first call, `EVALSHA` with `current_time_ms`, return `RateLimitResult(allowed, remaining, retry_after_ms)` dataclass
- [X] T022 [US4] Add `RateLimitResult` dataclass to `apps/control-plane/src/platform/common/clients/redis.py`: `RateLimitResult(allowed: bool, remaining: int, retry_after_ms: int)`
- [X] T023 [US4] Write integration tests in `apps/control-plane/tests/integration/test_redis_ratelimit.py`: `test_rate_limit_within_limit` (N requests → all `allowed=True`); `test_rate_limit_exceeded` (N+1 request → `allowed=False`, `retry_after_ms > 0`); `test_rate_limit_window_boundary` (send requests, sleep to advance window, verify next request allowed)

**Checkpoint**: Rate limit integration tests pass with correct boundary enforcement.

---

## Phase 7: User Story 5 — Platform Coordinates Work with Distributed Locks (Priority: P2)

**Goal**: `lock_acquire.lua` and `lock_release.lua` provide exclusive distributed locks with TTL. Wrong-token release is rejected. TTL auto-expires to prevent deadlocks.

**Independent Test**: Acquire `lock:scheduler:main` → `success=True, token=<uuid>`. Second acquire → `success=False`. Release with wrong token → `False`. Release with correct token → `True`. Lock auto-expires after TTL.

- [X] T024 [P] [US5] Create `lua/lock_acquire.lua`: `KEYS[1]` = lock key; `ARGV[1]` = UUID token; `ARGV[2]` = TTL seconds; if key absent: `SET key token EX ttl`, return `1`; if key exists with same token: `EXPIRE key ttl`, return `1` (renewal); else return `0`
- [X] T025 [P] [US5] Create `lua/lock_release.lua`: `KEYS[1]` = lock key; `ARGV[1]` = token; `GET key`; if not exists: return `0`; if matches token: `DEL key`, return `1`; else return `0`
- [X] T026 [US5] Implement `acquire_lock(resource, id, ttl_seconds=10)` and `release_lock(resource, id, token)` in `apps/control-plane/src/platform/common/clients/redis.py`: build key `lock:{resource}:{id}`; generate `uuid.uuid4()` token on acquire; load both scripts on first call; `EVALSHA lock_acquire.lua` → return `LockResult(success=bool, token=token if acquired else None)`; `EVALSHA lock_release.lua` → return `bool`
- [X] T027 [US5] Add `LockResult` dataclass to `apps/control-plane/src/platform/common/clients/redis.py`: `LockResult(success: bool, token: Optional[str] = None)`
- [X] T028 [US5] Write integration tests in `apps/control-plane/tests/integration/test_redis_locks.py`: `test_acquire_and_release` (acquire → success, release with correct token → True); `test_exclusive_lock` (acquire → success, second acquire → failure); `test_wrong_token_release` (acquire, release with wrong token → False, lock still held); `test_lock_ttl_expiry` (acquire with 1s TTL, sleep, verify key gone); `test_lock_renewal` (acquire, re-acquire with same token → success, TTL renewed)

**Checkpoint**: Lock integration tests pass; deadlock prevention (TTL expiry) verified.

---

## Phase 8: User Story 6 — Tournament Service Manages Hypothesis Leaderboards (Priority: P2)

**Goal**: `AsyncRedisClient` maintains sorted leaderboards via Redis sorted sets. Add, update, query top-N, get rank, remove — all work correctly.

**Independent Test**: Add 5 hypotheses with different Elo scores, query top 3 → correct descending order. Update a score → rank changes. Remove an entry → leaderboard size decreases, others shift.

- [X] T029 [US6] Implement leaderboard methods in `apps/control-plane/src/platform/common/clients/redis.py`: `leaderboard_add(tournament_id, hypothesis_id, score)` → `ZADD leaderboard:{tid} score hypothesis_id` (ZADD overwrites if exists); `leaderboard_top(tournament_id, n)` → `ZREVRANGE leaderboard:{tid} 0 n-1 WITHSCORES`, return `list[tuple[str, float]]`; `leaderboard_rank(tournament_id, hypothesis_id)` → `ZREVRANK leaderboard:{tid} hypothesis_id`, return `Optional[int]` (0-indexed); `leaderboard_score(tournament_id, hypothesis_id)` → `ZSCORE`, return `Optional[float]`; `leaderboard_remove(tournament_id, hypothesis_id)` → `ZREM`, return `bool`; `leaderboard_delete(tournament_id)` → `DEL leaderboard:{tid}`, return `bool`
- [X] T030 [US6] Write integration tests in `apps/control-plane/tests/integration/test_redis_leaderboard.py`: `test_add_and_rank` (add 5 hypotheses, verify ZCARD=5 and descending order); `test_score_update` (add hypothesis, update score with lower value, verify rank moved down); `test_top_n` (add 10 entries, query top 3, verify exactly 3 returned in correct order); `test_remove_entry` (add then remove, verify ZCARD decreases and removed id not in ZRANGE); `test_rank_of_specific` (add 5 entries, query rank of middle one, verify correct 0-indexed position)

**Checkpoint**: All leaderboard integration tests pass; sorted set operations correct under updates and removals.

---

## Final Phase: Polish & Cross-Cutting Concerns

- [X] T031 [P] Implement `health_check()` method in `apps/control-plane/src/platform/common/clients/redis.py` that `PING`s the cluster and returns `True` if successful, `False` on any `RedisError`
- [X] T032 [P] Create Go budget client reference at `services/reasoning-engine/internal/redis/budget_client.go`: `NewClusterClient` with `PoolSize: 50`, `MinIdleConns: 25`; `redis.NewScript(budget_decrement_lua_source)` loaded from `lua/budget_decrement.lua` at startup; `DecrementBudget(ctx, executionID, stepID, dimension, amount)` with 10ms context timeout; `BudgetResult` struct; `Close()` for graceful shutdown
- [X] T033 Add Redis integration test job to `.github/workflows/db-check.yml`: start `redis:7` service container on port 6379; set `REDIS_URL=redis://localhost:6379`; run `pytest apps/control-plane/tests/integration/test_redis_*.py -v`
- [X] T034 Run `helm lint deploy/helm/redis --strict` and `helm template deploy/helm/redis -f deploy/helm/redis/values-prod.yaml` and fix any warnings
- [X] T035 [P] Run `ruff check apps/control-plane/src/platform/common/clients/redis.py` and fix any lint violations
- [X] T036 [P] Run `mypy --strict apps/control-plane/src/platform/common/clients/redis.py` and fix any type errors
- [X] T037 [P] Run `pytest apps/control-plane/tests/integration/test_redis_*.py --cov=platform.common.clients.redis --cov-report=term-missing` and confirm coverage ≥95%
- [X] T038 Update `CLAUDE.md` with Redis client usage patterns: import path, how to initialize for tests vs production, key namespace conventions, when to use each Lua script

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — blocks US1 Helm work; Python skeleton ready for US2+
- **US1 (Phase 3)**: Depends on Phase 2 (chart values/templates) — no Python dependency
- **US2 (Phase 4)**: Depends on T009 (client skeleton) and T013 (initialize/close) — independent of US1
- **US3 (Phase 5)**: Depends on T009, T013 (client init), T017 requires T016 (Lua script first)
- **US4 (Phase 6)**: Depends on T009, T013; T021 requires T020 (Lua script first) — independent of US2/US3
- **US5 (Phase 7)**: Depends on T009, T013; T026 requires T024+T025 (both Lua scripts first)
- **US6 (Phase 8)**: Depends on T009, T013 — no Lua scripts needed (native sorted set commands)
- **Polish (Final)**: Depends on all desired stories complete

### User Story Dependencies

| Story | Priority | Depends on | Can run in parallel with |
|-------|----------|-----------|-------------------------|
| US1 | P1 | Phase 2 | US2, US3, US4, US5, US6 (different stack) |
| US2 | P1 | T009, T013 | US1 (different files), US3 (after T013), US4, US5, US6 |
| US3 | P1 | T009, T013, T016 | US1, US4 (different methods), US5, US6 |
| US4 | P2 | T009, T013, T020 | US1, US2, US3, US6 |
| US5 | P2 | T009, T013, T024, T025 | US1, US2, US3, US4, US6 |
| US6 | P2 | T009, T013 | All others (native commands only) |

---

## Parallel Example: Lua Scripts + Helm Chart simultaneously

```bash
# Helm chart (T010) and Lua scripts (T016, T020, T024, T025) all use different files:
Task (Agent A): "Create deploy/helm/redis/templates/netpol.yaml"
Task (Agent B): "Create lua/budget_decrement.lua"
Task (Agent C): "Create lua/rate_limit_check.lua"
Task (Agent D): "Create lua/lock_acquire.lua and lua/lock_release.lua"
```

## Parallel Example: User Story 5 Lua Scripts

```bash
# T024 and T025 use different files, can run in parallel:
Task (Agent A): "Create lua/lock_acquire.lua"
Task (Agent B): "Create lua/lock_release.lua"
```

---

## Implementation Strategy

### MVP First (US1 + US2 + US3 — running cluster with sessions and budget)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (Helm chart base)
3. Complete Phase 3 (US1): Deployable Redis Cluster
4. Complete Phase 4 (US2): Session management live
5. Complete Phase 5 (US3): Budget enforcement live
6. **STOP and VALIDATE**: `helm install`, session CRUD, and budget decrement work end-to-end
7. US4–US6 add rate limiting, locks, and leaderboards incrementally

### Incremental Delivery

1. Phase 1 + 2 → Project scaffold ready
2. US1 → Redis cluster deployable (operators unblocked)
3. US2 → Sessions live (auth flow unblocked)
4. US3 → Budget enforcement live (reasoning engine unblocked)
5. US4 → Rate limiting live (API protection enabled)
6. US5 → Locks live (scheduler/dispatch coordination enabled)
7. US6 → Leaderboards live (tournament system enabled)

### Parallel Team Strategy

After Phase 1 + 2:
- **Dev A**: US1 (Helm chart netpol, CI)
- **Dev B**: US2 (Python client init + session methods)
- **Dev C**: US3 (budget Lua script + decrement methods) — in parallel with Dev B, different methods

---

## Notes

- `[P]` tasks touch different files with no cross-task dependencies — safe to parallelize
- All Lua scripts must be loaded and their SHA cached on first call in `initialize()` or on first use
- Redis Cluster mode requires all keys in a single Lua script to map to the same hash slot — all 4 scripts are single-key, so this is satisfied
- The `testcontainers[redis]` fixture starts a standalone Redis 7 node (not cluster); use `redis.asyncio.Redis` instead of `RedisCluster` in tests by checking `REDIS_TEST_MODE=standalone` env var
- Leaderboard scores are stored as floats; `ZADD` with `XX` flag updates only if member exists (use plain `ZADD` to add-or-update)
- Session bulk invalidation via `SCAN` does not guarantee atomicity across the full scan — this is acceptable since it's non-authoritative data
