# Research: Reasoning Engine — Reasoning Orchestration, Budget Tracking, Self-Correction

**Feature**: 011-reasoning-engine  
**Date**: 2026-04-10  
**Phase**: 0 — Pre-design research

---

## Decision 1: Go Service Architecture — Satellite Binary at `services/reasoning-engine/`

**Decision**: The reasoning engine is an independent Go binary at `services/reasoning-engine/`, following the established satellite service pattern. It exposes a gRPC server on port 50052 (`google.golang.org/grpc 1.67+`) per the constitution gRPC Service Registry. Standard Go layout: `cmd/reasoning-engine/main.go`, `internal/` (private packages), `api/grpc/` (gRPC server handler), `pkg/` (shared helpers).

**Rationale**: Constitution §II explicitly establishes `services/reasoning-engine/` as the Go satellite pattern. The reasoning engine requires sub-millisecond budget checks (Redis), concurrent goroutine execution (tree-of-thought branches), and numerical convergence loops — all workloads where Go's goroutine model outperforms Python's async model. The constitution states this service handles "reasoning budget tracking (sub-millisecond via Redis), self-correction convergence detection (tight numerical loops), tree-of-thought branch management (concurrent goroutines)."

**Alternatives considered**:
- Python async implementation: Cannot achieve <1ms p99 budget latency with asyncio overhead. Rejected — constitution §II explicitly mandates Go for this service.
- Extending the Python monolith: Violates constitution §I (no hot-path concurrent computation) and §II. Rejected.

---

## Decision 2: Atomic Budget Operations — Redis Lua Scripts

**Decision**: Budget tracking uses Redis hashes (`budget:{execution_id}:{step_id}`) with atomic operations via embedded Lua scripts (loaded as `EVALSHA` at startup). Two primary scripts:

1. **`budget_decrement.lua`**: Reads current value, checks against max, increments atomically if within bounds, returns -1 if exceeded. Fields: `used_tokens`, `used_rounds`, `used_cost`. Dimensions are tracked independently.

2. **`convergence_check.lua`**: Reads previous two quality scores, updates history, checks if both consecutive deltas are < epsilon, returns 1 for converged, 0 for not converged.

Budget key TTL is set at allocation time (default: execution lifetime + 1 hour buffer) and auto-cleans completed budgets.

**Rationale**: Lua scripts execute atomically in Redis — no other commands can interleave during script execution. This eliminates race conditions without application-level locking. `EVALSHA` (not `EVAL`) caches the compiled script server-side, keeping call overhead minimal. This achieves <1ms p99 budget check latency (SC-001). Constitution §III mandates Redis for hot state.

**Alternatives considered**:
- Redis WATCH/MULTI/EXEC transactions: Requires client-side retry on WATCH failure. More complex, higher retry overhead under contention. Rejected.
- Application-level mutex: Does not work across multiple service replicas. Rejected.
- Redis INCR with separate MAX check: Two separate commands = not atomic. Rejected.

---

## Decision 3: Tree-of-Thought Concurrency — Goroutine Pool with Bounded Semaphore

**Decision**: Each tree branch executes in its own goroutine, bounded by a configurable semaphore (default `MAX_TOT_CONCURRENCY=10`). A `semaphore chan struct{}` limits concurrent branch goroutines. Each branch has its own `context.Context` derived from the parent, allowing individual branch cancellation (pruning) without affecting siblings.

Branch state is stored in Redis (`branch:{tree_id}:{branch_id}` hash) for cross-goroutine visibility. When a branch's individual budget is exhausted, the goroutine calls `context.CancelCauseFunc` with a "budget_exceeded" cause, updates branch status in Redis to "pruned", and exits.

Evaluation uses `sync.WaitGroup` to wait for all branches to complete (or be pruned), then runs the scoring function over all non-pruned results.

**Rationale**: Goroutine-per-branch is idiomatic Go for concurrent work with independent cancellation semantics. Bounded semaphore prevents unbounded resource consumption. Redis branch state provides visibility across replicas and survives branch goroutine termination.

**Alternatives considered**:
- Worker pool with channel dispatch: More complex, adds queuing latency. Rejected — branches are independent, not ordered.
- Single goroutine sequential evaluation: Defeats the purpose of ToT. Rejected.
- errgroup from `golang.org/x/sync`: Good for concurrent tasks with shared error, but ToT branches need individual cancellation (not all-cancel-on-first-error). Rejected.

---

## Decision 4: Chain-of-Thought Trace Coordination — Streaming with Dual Persistence

**Decision**: `StreamReasoningTrace` accepts a client-streaming gRPC call (client sends many events, server sends one acknowledgment). Events are processed in a pipeline:
1. Receive event from stream
2. If payload > 64KB: upload to MinIO at `reasoning-traces/{execution_id}/{step_id}/{event_id}`, store reference in metadata
3. Insert metadata row to PostgreSQL (`reasoning_events` table): event_id, execution_id, event_type, sequence_num, occurred_at, payload_size, object_key
4. Produce Kafka message to `runtime.reasoning` topic (keyed by execution_id)

Steps 2-4 are performed asynchronously in a goroutine pool to avoid blocking the stream reader, with a bounded in-memory buffer (default 10,000 events). Buffer overflow drops oldest events and increments a counter.

**Rationale**: Client-streaming gRPC is the correct pattern — the client (runtime) produces many events, the server accumulates and acknowledges. Async processing decouples stream ingestion from persistence latency. Dual persistence (PostgreSQL metadata + MinIO payload) satisfies the spec's large-payload requirement without bloating the database.

**Alternatives considered**:
- Bidirectional streaming: Server doesn't need to push events back in real-time. Rejected — simpler client-streaming suffices.
- Synchronous persistence: Would backpressure the stream. Rejected.
- PostgreSQL-only storage: Large CoT dumps (potentially megabytes) would bloat the database. Rejected per constitution §XII.

---

## Decision 5: Mode Selection — Rule-Based Complexity Heuristic

**Decision**: Mode selection is rule-based in v1 (no ML). The `mode_selector` package implements a decision tree:

1. **Policy override check**: If the request contains `forced_mode`, return it immediately.
2. **Budget feasibility check**: Eliminate modes that cost more than the available budget (mode costs are pre-configured).
3. **Complexity heuristic**: Score task brief by: word count, presence of multi-step keywords ("first... then... finally"), number of questions, presence of code indicators. Map score ranges to modes:
   - Score 0-2: DIRECT
   - Score 3-5: CHAIN_OF_THOUGHT
   - Score 6-8: TREE_OF_THOUGHT
   - Score 9+: TREE_OF_THOUGHT (with higher branch count)
   - Keywords matching "code", "script", "python", "function": CODE_AS_REASONING
   - Keywords matching "compare", "debate", "argue both sides": DEBATE
4. **Budget allocation**: Based on selected mode and available budget, compute recommended token/round allocations.

**Rationale**: Rule-based selection is deterministic, fast (<50ms, SC-004), and testable. ML-based selection is out of scope for v1 (spec assumption). The complexity heuristic is simplistic but sufficient for v1 — it can be replaced without changing the gRPC interface.

**Alternatives considered**:
- ML-based classifier: Higher accuracy but requires training data and introduces a model dependency. Out of scope per spec assumption.
- LLM-based self-selection: Circular dependency — the LLM would be deciding its own reasoning mode. Rejected.

---

## Decision 6: Self-Correction Convergence — Lua-Atomic History with Two-Sample Window

**Decision**: Convergence detection uses `convergence_check.lua` (as specified in the user input). The loop state is stored in Redis (`correction:{loop_id}` hash) with fields: `max_iterations`, `used_iterations`, `cost_cap`, `used_cost`, `epsilon`, `prev_quality`, `prev_prev_quality`, `status`.

`SubmitCorrectionIteration` call flow:
1. Atomically update quality history and check convergence via `convergence_check.lua`
2. Increment `used_iterations` and `used_cost` via `budget_decrement.lua`
3. If converged: update status to "converged", emit Kafka event, return CONVERGED
4. If budget exceeded: update status to "budget_exceeded", check escalation config, emit Kafka event (with escalation if configured), return BUDGET_EXCEEDED or ESCALATE_TO_HUMAN
5. Otherwise: return CONTINUE

Full iteration history (score, delta, cost, duration) persisted to PostgreSQL `correction_iterations` table for forensic analysis.

**Rationale**: Lua atomicity prevents race conditions when multiple correction steps arrive concurrently. Two-sample window (not one) is less sensitive to noise — one outlier quality score doesn't prematurely signal convergence. PostgreSQL persistence satisfies the spec requirement for forensic analysis.

**Alternatives considered**:
- Application-side history with Redis WATCH: Not atomic under high concurrency. Rejected.
- Single-sample convergence (delta < epsilon once): More noise-sensitive. Rejected per spec requirement for "2 consecutive iterations."

---

## Decision 7: Budget Event Streaming — Fan-Out Registry (Same Pattern as Sandbox/Runtime)

**Decision**: `StreamBudgetEvents` uses the same fan-out registry pattern established in the runtime-controller and sandbox-manager: `sync.RWMutex`-protected map of execution_id → `[]chan BudgetEvent`. The budget_tracker publishes events to the registry when thresholds are crossed. The gRPC stream handler subscribes, receives events from its channel, and sends them to the client.

Budget events are also emitted to Kafka (`runtime.reasoning` topic) for downstream consumers.

**Rationale**: Fan-out registry is already established in the codebase for similar patterns (runtime-controller events, sandbox logs). Consistent pattern reduces cognitive overhead. Kafka emission handles persistence and replay for consumers that connect after events have occurred.

**Alternatives considered**:
- Redis Pub/Sub: Would work but adds Redis dependency for event routing (already used for state, but mixing hot-state reads with pub/sub adds complexity). Rejected — in-process fan-out is simpler for same-binary subscribers.
- gRPC bidirectional streaming: Server doesn't need to receive budget updates via the stream. Rejected — server-side streaming suffices.

---

## Decision 8: Cold State Persistence — PostgreSQL via pgx/v5

**Decision**: Completed reasoning data is persisted to PostgreSQL using `pgx/v5` direct SQL (no ORM). Tables:
- `reasoning_traces`: Trace metadata records (execution_id, mode, total_events, started_at, completed_at, object_key for full payload)
- `reasoning_events`: Individual trace event metadata (event_id, trace_id, event_type, sequence_num, occurred_at, payload_size, object_key)
- `tot_branches`: Tree-of-thought branch records (branch_id, tree_id, hypothesis, quality_score, token_cost, status, object_key for payload)
- `correction_iterations`: Self-correction iteration history (loop_id, iteration_num, quality_score, delta, cost, duration_ms)

**Rationale**: Constitution §2.2 mandates `pgx/v5` for PostgreSQL in Go services. Direct SQL is faster than ORM for the write-heavy, schema-stable workload. Constitution §III mandates PostgreSQL for ACID relational truth; completed reasoning data is a system-of-record.

**Alternatives considered**:
- ClickHouse for traces: Appropriate for analytics queries but overkill for the trace metadata workload. The Python analytics bounded context can project from PostgreSQL events. Rejected for v1.
- GORM: ORM adds reflection overhead. Constitution doesn't mandate it. Rejected.

---

## Decision 9: Code-as-Reasoning Bridge — gRPC Client to Sandbox Manager

**Decision**: The `code_bridge` package is a gRPC client to `musematic-sandbox-manager.platform-execution:50053`. When mode selection returns CODE_AS_REASONING, the runtime calls the sandbox manager directly (not through the reasoning engine). The reasoning engine only:
1. Tracks the budget allocation for code-as-reasoning steps
2. Receives trace events from the code execution result
3. Updates convergence state if applicable

The reasoning engine does NOT proxy code execution — it stays on the hot path for budget and convergence, while code execution goes directly to the sandbox manager.

**Rationale**: Having the reasoning engine proxy sandbox manager calls would add latency on the code execution critical path. The reasoning engine's role is budget tracking and convergence — not code execution orchestration. This keeps each service focused on its bounded context.

**Alternatives considered**:
- Reasoning engine proxies all code-as-reasoning: Adds round-trip latency. Rejected.
- Sandbox manager calls reasoning engine for budget: Circular dependency. Rejected.
