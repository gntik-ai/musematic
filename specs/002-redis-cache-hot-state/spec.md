# Feature Specification: Redis Cache and Hot State Deployment

**Feature Branch**: `002-redis-cache-hot-state`  
**Created**: 2026-04-09  
**Status**: Draft  
**Input**: User description: "Deploy Redis 7+ in Cluster mode for session caching, reasoning budget tracking, hypothesis tournament leaderboards, distributed locks, rate-limit counters, and lightweight pub/sub notifications."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Platform Operator Deploys Redis Cluster (Priority: P1)

A platform operator deploys a highly available Redis cluster to provide the platform's hot state layer. In production, the cluster runs 6 nodes (3 masters, 3 replicas) with automatic failover, persistent storage, and monitoring. A single deploy command brings up the entire cluster in the designated namespace.

**Why this priority**: Without the cache layer running, no other hot state features (sessions, budget tracking, locks, rate limits) can operate. This is the infrastructure prerequisite for all downstream stories.

**Independent Test**: Deploy the cluster, run `SET test_key test_value` and `GET test_key`, verify the response. Delete a master node and confirm a replica is promoted within 10 seconds. Verify Prometheus metrics endpoint returns `redis_up 1`.

**Acceptance Scenarios**:

1. **Given** a Kubernetes cluster, **When** the operator deploys the Redis chart, **Then** a 6-node Redis Cluster is created in the `platform-data` namespace with 3 masters and 3 replicas.
2. **Given** a running Redis Cluster, **When** a master node pod is deleted, **Then** the corresponding replica is promoted to master within 10 seconds and the cluster continues serving requests.
3. **Given** a running cluster, **When** a pod is restarted, **Then** AOF-persisted data survives the restart without loss.
4. **Given** a running cluster, **When** Prometheus scrapes the metrics endpoint, **Then** key metrics (connected clients, memory usage, commands processed, replication lag) are available.
5. **Given** the network policy is in place, **When** a pod outside `platform-control` and `platform-execution` namespaces attempts to connect, **Then** the connection is refused.

---

### User Story 2 - Control Plane Manages User Sessions (Priority: P1)

The control plane stores and retrieves user session data in the cache with automatic expiry. Sessions are created on login, validated on each request, and removed on logout or timeout.

**Why this priority**: Session management is a security-critical path that directly impacts every authenticated user. Without it, the platform cannot authenticate requests.

**Independent Test**: Store a session record with a 30-minute TTL, retrieve it, wait for expiry, and confirm it is no longer accessible. Verify that explicit logout removes the session immediately.

**Acceptance Scenarios**:

1. **Given** a user has logged in, **When** the control plane stores session data, **Then** the session is accessible by key and expires automatically after the configured TTL.
2. **Given** an active session, **When** the user logs out, **Then** the session is immediately removed from the cache.
3. **Given** a session TTL has elapsed, **When** the system attempts to retrieve the session, **Then** no data is returned.
4. **Given** multiple sessions exist for a user, **When** the user's account is suspended, **Then** all sessions for that user can be invalidated in a single operation.

---

### User Story 3 - Reasoning Engine Tracks Budget in Real Time (Priority: P1)

The reasoning engine atomically decrements budget counters (tokens, rounds, cost, time) before each reasoning step. If any budget dimension is exhausted, the engine halts the step immediately. Budget enforcement must complete in sub-millisecond time to avoid blocking the reasoning pipeline.

**Why this priority**: Budget tracking is the financial and operational safety guard for the platform's most compute-intensive workload. Incorrect enforcement could result in runaway costs or resource exhaustion.

**Independent Test**: Initialize a budget with known limits, run a sequence of atomic decrements, and verify that each decrement returns the correct remaining balance. Attempt a decrement that exceeds the remaining budget and verify it is rejected. Run 1000 concurrent decrements and confirm no race conditions (final used count equals the sum of all decrements).

**Acceptance Scenarios**:

1. **Given** a budget hash with defined limits, **When** the reasoning engine decrements tokens atomically, **Then** the used count is updated and the remaining balance is returned accurately.
2. **Given** a budget with only 100 tokens remaining, **When** a step requests 150 tokens, **Then** the decrement is rejected and the budget remains unchanged.
3. **Given** 100 concurrent decrement requests, **When** all execute simultaneously, **Then** the final used count equals the exact sum of all successful decrements with no over-allocation.
4. **Given** a budget with a time limit, **When** the elapsed time exceeds `max_time_ms`, **Then** the budget check returns "exceeded" and the reasoning step is halted.

---

### User Story 4 - Platform Enforces Rate Limits (Priority: P2)

The platform applies sliding window rate limits to protect resources from abuse. Each resource-key pair has a configured maximum number of requests per window. Requests exceeding the limit are rejected with appropriate feedback.

**Why this priority**: Rate limiting protects the platform from abuse and ensures fair resource allocation, but it is secondary to the core infrastructure and budget tracking.

**Independent Test**: Configure a rate limit of 10 requests per 60-second window. Send 10 requests and verify all succeed. Send an 11th request and verify it is rejected. Wait for the window to slide and verify the next request succeeds.

**Acceptance Scenarios**:

1. **Given** a rate limit of N requests per window, **When** N requests are sent within the window, **Then** all requests succeed.
2. **Given** the rate limit is reached, **When** an additional request is sent, **Then** it is rejected and the caller is informed of the remaining cooldown time.
3. **Given** the sliding window has advanced past the earliest request, **When** a new request is sent, **Then** it succeeds because the window now has capacity.

---

### User Story 5 - Platform Coordinates Work with Distributed Locks (Priority: P2)

The platform uses distributed locks with TTL to coordinate exclusive access to shared resources (scheduler lease, dispatch lease). Locks are acquired atomically, auto-expire to prevent deadlocks, and can be released explicitly by the holder.

**Why this priority**: Distributed locks prevent double-scheduling and duplicate dispatch but depend on the Redis Cluster being operational.

**Independent Test**: Acquire a lock on resource "scheduler-lease", verify a second attempt to acquire the same lock fails. Release the lock and verify the second holder can now acquire it. Let a lock expire by TTL and verify it becomes available automatically.

**Acceptance Scenarios**:

1. **Given** a resource is unlocked, **When** a service acquires a lock with a TTL, **Then** the lock is held exclusively and a unique lock token is returned.
2. **Given** a resource is locked, **When** a second service attempts to acquire the same lock, **Then** the attempt fails immediately with a "lock held" status.
3. **Given** a lock is held, **When** the holder releases it with the correct token, **Then** the lock becomes available.
4. **Given** a lock is held, **When** the TTL expires without release, **Then** the lock becomes available automatically (preventing deadlocks).
5. **Given** a lock is held, **When** a non-holder attempts to release it (wrong token), **Then** the release is rejected and the lock remains held.

---

### User Story 6 - Tournament Service Manages Hypothesis Leaderboards (Priority: P2)

The tournament service maintains sorted leaderboards of hypotheses ranked by Elo score. Hypotheses are added, scores are updated after matches, and rankings can be queried by position range or individual rank.

**Why this priority**: Leaderboards are essential for the hypothesis tournament system but are downstream of core infrastructure and budget tracking.

**Independent Test**: Add 10 hypotheses with initial Elo scores, update scores after simulated matches, query the top 5, and verify the ranking is correct. Remove a hypothesis and verify the leaderboard updates.

**Acceptance Scenarios**:

1. **Given** a tournament exists, **When** hypotheses are added with Elo scores, **Then** they appear in the leaderboard sorted by score (highest first).
2. **Given** a leaderboard with entries, **When** a hypothesis score is updated after a match, **Then** its rank changes accordingly.
3. **Given** a leaderboard, **When** the top N entries are queried, **Then** the correct N entries are returned in descending score order.
4. **Given** a leaderboard, **When** a hypothesis is removed, **Then** it no longer appears in rankings and other entries shift accordingly.
5. **Given** a leaderboard, **When** the rank of a specific hypothesis is queried, **Then** the correct rank is returned.

---

### Edge Cases

- What happens when the entire Redis Cluster is temporarily unavailable? The system should degrade gracefully: session validation falls back to database lookup, rate limits are temporarily relaxed, and budget enforcement queues retries with a short timeout.
- What happens when a lock holder crashes without releasing? The TTL auto-releases the lock, preventing permanent deadlocks.
- How does the system behave when memory pressure triggers eviction? The `allkeys-lru` policy evicts least-recently-used keys; critical keys (budget, locks) should use short TTLs or be refreshed frequently.
- What happens when a budget hash key is evicted under memory pressure? Budget enforcement must treat a missing hash as "budget exhausted" (fail-closed), not as "unlimited" (fail-open).
- How does the rate limiter handle clock skew across cluster nodes? Sliding window counters use server-side time via command timestamps, not client time.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a highly available cache cluster with automatic failover completing in under 10 seconds upon master node failure.
- **FR-002**: System MUST provide a single-node cache deployment for development environments.
- **FR-003**: System MUST persist cached data across pod restarts using append-only file persistence.
- **FR-004**: System MUST expose monitoring metrics for connected clients, memory usage, commands processed, and replication lag.
- **FR-005**: System MUST enforce network access restrictions so that only authorized platform namespaces can connect.
- **FR-006**: System MUST store session data with configurable time-to-live and support immediate invalidation on logout.
- **FR-007**: System MUST support bulk invalidation of all sessions for a given user in a single operation.
- **FR-008**: System MUST provide atomic budget decrement operations that enforce all budget dimensions (tokens, rounds, cost, time) with no race conditions under concurrent access.
- **FR-009**: System MUST reject budget decrements that would exceed any budget limit, leaving the budget unchanged.
- **FR-010**: System MUST treat a missing budget record as "budget exhausted" (fail-closed behavior).
- **FR-011**: System MUST enforce sliding window rate limits with configurable request count and window duration per resource-key pair.
- **FR-012**: System MUST return remaining cooldown time when a rate limit is exceeded.
- **FR-013**: System MUST provide distributed locks with TTL, atomic acquire, explicit release with token verification, and automatic expiry.
- **FR-014**: System MUST reject lock release attempts from non-holders (wrong token).
- **FR-015**: System MUST maintain sorted leaderboards supporting add, update, remove, rank query, and range query operations.
- **FR-016**: System MUST apply a least-recently-used eviction policy when memory reaches the configured threshold.
- **FR-017**: System MUST warn operators when memory usage exceeds 80% of the configured maximum.
- **FR-018**: System MUST authenticate all connections using credentials stored in a platform secret.

### Key Entities

- **Session Record**: Represents an active user session. Contains user identity, session metadata, and expiry. Keyed by `session:{user_id}:{session_id}`.
- **Budget Hash**: Tracks multi-dimensional consumption limits for a reasoning execution step. Fields: `max_tokens`, `used_tokens`, `max_rounds`, `used_rounds`, `max_cost`, `used_cost`, `max_time_ms`, `start_time`. Keyed by `budget:{execution_id}:{step_id}`.
- **Rate Limit Counter**: Sliding window counter tracking request counts per resource-key pair. Keyed by `ratelimit:{resource}:{key}`.
- **Distributed Lock**: Exclusive hold on a shared resource with TTL and holder token. Keyed by `lock:{resource}:{id}`.
- **Leaderboard Entry**: Hypothesis score in a tournament's sorted set. Keyed by `leaderboard:{tournament_id}`, member is hypothesis ID, score is Elo rating.
- **Cache Entry**: Hot-path query result with TTL for reducing backend load. Keyed by `cache:{context}:{key}`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Platform operators can deploy the complete cache cluster with a single command, completing setup in under 3 minutes.
- **SC-002**: Cache read and write operations complete within 1 millisecond at the 99th percentile under normal load.
- **SC-003**: The system recovers from a single node failure within 10 seconds without manual intervention and without data loss for persisted keys.
- **SC-004**: Budget enforcement operations complete in sub-millisecond time, enabling the reasoning engine to check budgets without measurable pipeline latency.
- **SC-005**: Under 1000 concurrent budget decrement operations, zero over-allocations occur (exact accounting, no race conditions).
- **SC-006**: Rate limiting correctly enforces sliding window boundaries with less than 1% error rate in boundary conditions.
- **SC-007**: Distributed locks prevent double-scheduling: zero duplicate task dispatches occur under concurrent contention.
- **SC-008**: Leaderboard queries return correct rankings after score updates within 1 millisecond.
- **SC-009**: Unauthorized network connections to the cache cluster are rejected 100% of the time.

## Assumptions

- The Kubernetes cluster has sufficient nodes and resources to schedule 6 Redis pods in production (3 masters + 3 replicas).
- The Go reasoning engine is the primary consumer for budget tracking operations; the Python control plane handles sessions, rate limiting, and distributed locks.
- Redis is used exclusively for caching and hot state. No persistent business data resides solely in Redis — all authoritative data lives in PostgreSQL or other durable stores.
- Session data is non-authoritative: if a session key is evicted or lost, the user re-authenticates via the durable store.
- Budget enforcement uses the fail-closed pattern: a missing or unreachable budget hash is treated as "exhausted," not "unlimited."
- The `allkeys-lru` eviction policy is acceptable because all keys have TTLs or are refreshed frequently. Critical keys (budget, locks) are short-lived by design.
- Network policies for `platform-control` and `platform-execution` namespaces are enforced by the cluster's CNI plugin (e.g., Calico, Cilium).
- Development environments use a single Redis node without cluster mode for simplicity.
