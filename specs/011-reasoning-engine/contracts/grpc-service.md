# gRPC Contract: ReasoningEngineService

**Service**: `musematic.reasoning.v1.ReasoningEngineService`  
**Port**: 50052  
**Namespace**: `platform-execution`  
**DNS**: `musematic-reasoning-engine.platform-execution:50052`  
**Feature**: 011-reasoning-engine

---

## RPC: SelectReasoningMode

**Pattern**: Unary  
**Called by**: Control plane (`apps/control-plane/src/platform/reasoning/`) at execution start

### Request

```
SelectReasoningModeRequest {
  execution_id: string          // UUID of the reasoning execution
  task_brief: string            // Natural language task description
  forced_mode: string           // Optional: force DIRECT/CHAIN_OF_THOUGHT/etc.
  budget_constraints {
    max_tokens: int64           // Total token budget available
    max_rounds: int64           // Maximum reasoning rounds
    max_cost: double            // Maximum cost in USD
    max_time_ms: int64          // Maximum elapsed time
  }
}
```

### Response

```
ReasoningModeConfig {
  mode: ReasoningMode           // Selected mode enum value
  complexity_score: int32       // 0–9 heuristic score
  recommended_budget {
    tokens: int64
    rounds: int64
    cost: double
    time_ms: int64
  }
  rationale: string             // Human-readable selection reason
}
```

### Behavior

1. If `forced_mode` is set → return it immediately (skip heuristic)
2. Compute complexity score from task brief (word count, multi-step keywords, question count, code indicators)
3. Eliminate modes that exceed `budget_constraints`
4. Map score to mode: 0–2→DIRECT, 3–5→COT, 6–8→TOT, 9+→TOT (high branch count)
5. Special keywords: code/script/function→CODE_AS_REASONING; compare/debate→DEBATE
6. Return selected mode with proportional budget allocation

### Error Codes

| Code | Condition |
|------|-----------|
| `INVALID_ARGUMENT` | `execution_id` or `task_brief` is empty |
| `RESOURCE_EXHAUSTED` | No mode fits within budget constraints |

---

## RPC: AllocateReasoningBudget

**Pattern**: Unary  
**Called by**: Control plane after mode selection

### Request

```
AllocateReasoningBudgetRequest {
  execution_id: string
  step_id: string               // Identifies the specific step within execution
  limits {
    tokens: int64
    rounds: int64
    cost: double
    time_ms: int64
  }
  ttl_seconds: int64            // 0 = default (execution_lifetime + 3600)
}
```

### Response

```
ReasoningBudgetEnvelope {
  execution_id: string
  step_id: string
  limits: BudgetAllocation
  used: BudgetAllocation        // All zeros at allocation
  status: string                // "ALLOCATED"
  allocated_at: Timestamp
}
```

### Behavior

1. Write Redis hash `budget:{execution_id}:{step_id}` with all limit fields and `used_*=0`
2. Set TTL from request (or default)
3. Register budget in fan-out registry for event streaming
4. Return envelope with zero usage

### Error Codes

| Code | Condition |
|------|-----------|
| `ALREADY_EXISTS` | Budget for this `execution_id:step_id` already exists |
| `INVALID_ARGUMENT` | Any limit is negative or zero |

---

## RPC: StreamReasoningTrace

**Pattern**: Client-streaming (client sends many events, server returns one ack)  
**Called by**: Runtime Controller during chain-of-thought execution

### Stream Message (client → server, repeated)

```
ReasoningTraceEvent {
  execution_id: string
  step_id: string
  event_id: string              // UUID, unique per event
  event_type: string            // e.g., "reasoning_step", "conclusion", "token_count"
  sequence_num: int32           // Monotonic per execution
  payload: bytes                // Raw event data; >64KB → routed to MinIO
  occurred_at: Timestamp
}
```

### Response (server → client, once)

```
ReasoningTraceAck {
  execution_id: string
  total_received: int32
  total_persisted: int32
  total_dropped: int32          // Buffer overflow count
  failed_event_ids: []string    // Events that failed persistence
}
```

### Behavior

1. Stream reader goroutine reads events from gRPC stream into buffered channel (capacity: `TRACE_BUFFER_SIZE`)
2. Worker pool goroutines process events from channel:
   - If `len(payload) > TRACE_PAYLOAD_THRESHOLD (64KB)`: upload to MinIO at `reasoning-traces/{execution_id}/{step_id}/{event_id}`, store object key in metadata
   - Insert metadata row to `reasoning_events` table
   - Produce Kafka message to `runtime.reasoning` topic, keyed by `execution_id`
3. Buffer overflow: drop oldest event, increment dropped counter
4. On stream EOF: send final ack with totals

### Error Codes

| Code | Condition |
|------|-----------|
| `NOT_FOUND` | No active budget for `execution_id:step_id` |
| `INVALID_ARGUMENT` | Missing `execution_id`, `event_id`, or `sequence_num` |
| `RESOURCE_EXHAUSTED` | Internal buffer full and circuit breaker open |

---

## RPC: GetReasoningBudgetStatus

**Pattern**: Unary  
**Called by**: Control plane, monitoring systems

### Request

```
GetBudgetStatusRequest {
  execution_id: string
  step_id: string
}
```

### Response

```
BudgetStatusResponse {
  envelope: ReasoningBudgetEnvelope {
    execution_id: string
    step_id: string
    limits: BudgetAllocation
    used: BudgetAllocation        // Current consumption from Redis
    status: string                // ALLOCATED | ACTIVE | EXHAUSTED | COMPLETED
    allocated_at: Timestamp
  }
}
```

### Error Codes

| Code | Condition |
|------|-----------|
| `NOT_FOUND` | Budget does not exist (expired or never created) |

---

## RPC: StreamBudgetEvents

**Pattern**: Server-streaming (client subscribes, server pushes)  
**Called by**: Control plane, monitoring dashboards

### Request

```
StreamBudgetEventsRequest {
  execution_id: string
  step_id: string
}
```

### Stream Message (server → client, repeated)

```
BudgetEvent {
  execution_id: string
  step_id: string
  event_type: string            // THRESHOLD_80 | THRESHOLD_90 | THRESHOLD_100 | ALLOCATED | COMPLETED | EXCEEDED
  dimension: string             // tokens | rounds | cost | time
  current_value: double
  max_value: double
  occurred_at: Timestamp
}
```

### Behavior

1. Subscribe channel to fan-out registry for `execution_id:step_id`
2. Forward events from channel to gRPC stream
3. When budget is completed or exhausted: send final event, close stream gracefully
4. If `execution_id:step_id` does not exist: return `NOT_FOUND`
5. No replay — only events occurring after subscription are delivered

### Error Codes

| Code | Condition |
|------|-----------|
| `NOT_FOUND` | No active budget for `execution_id:step_id` |

---

## RPC: CreateTreeBranch

**Pattern**: Unary  
**Called by**: Control plane ToT orchestration or runtime

### Request

```
CreateTreeBranchRequest {
  tree_id: string               // UUID of the tree-of-thought execution
  branch_id: string             // UUID of this specific branch
  hypothesis: string            // Natural language hypothesis being explored
  branch_budget {
    tokens: int64               // Individual branch token budget
    rounds: int64
    cost: double
    time_ms: int64
  }
}
```

### Response

```
TreeBranchHandle {
  tree_id: string
  branch_id: string
  status: string                // "CREATED"
  created_at: Timestamp
}
```

### Behavior

1. Write Redis hash `branch:{tree_id}:{branch_id}` with hypothesis, status=CREATED, quality_score=0, token_cost=0
2. Allocate budget Redis hash `budget:{tree_id}:{branch_id}` for individual branch
3. Start goroutine (acquire semaphore from bounded pool, `MAX_TOT_CONCURRENCY`)
4. Insert row to `tot_branches` table with status=CREATED
5. Return handle immediately (goroutine runs async)

### Error Codes

| Code | Condition |
|------|-----------|
| `ALREADY_EXISTS` | Branch with this `branch_id` already exists |
| `RESOURCE_EXHAUSTED` | Semaphore at capacity; `MAX_TOT_CONCURRENCY` reached |

---

## RPC: EvaluateTreeBranches

**Pattern**: Unary  
**Called by**: Control plane after all branches created

### Request

```
EvaluateTreeBranchesRequest {
  tree_id: string
  scoring_function: string      // "quality_cost_ratio" (default) | "quality_only"
}
```

### Response

```
BranchSelectionResult {
  selected_branch_id: string
  selected_quality: double
  selected_token_cost: int64
  all_branches: []{
    branch_id: string
    hypothesis: string
    quality_score: double
    token_cost: int64
    status: string
    score: double               // computed scoring value
  }
  no_viable_branches: bool
  best_partial_branch_id: string  // set when no_viable_branches=true
}
```

### Behavior

1. Wait for all active branch goroutines to complete via `sync.WaitGroup`
2. Read all branch state from Redis for this `tree_id`
3. Filter: include only COMPLETED branches for ranking; PRUNED/FAILED are excluded from winner
4. Apply scoring function (quality_cost_ratio = quality_score / (token_cost + 1)):
   - Tie-break: lower token_cost wins; then earlier `created_at`
5. If no COMPLETED branches: set `no_viable_branches=true`, return best PRUNED branch as partial
6. Update `tot_branches` table with final scores

### Error Codes

| Code | Condition |
|------|-----------|
| `NOT_FOUND` | No branches exist for `tree_id` |

---

## RPC: StartSelfCorrectionLoop

**Pattern**: Unary  
**Called by**: Control plane when quality threshold not met

### Request

```
StartSelfCorrectionRequest {
  loop_id: string               // UUID of this correction loop
  execution_id: string
  max_iterations: int32
  cost_cap: double
  epsilon: double               // Convergence threshold (delta < epsilon for 2 consecutive)
  escalate_on_budget_exceeded: bool
}
```

### Response

```
SelfCorrectionHandle {
  loop_id: string
  status: string                // "RUNNING"
  started_at: Timestamp
}
```

### Behavior

1. Write Redis hash `correction:{loop_id}` with all config fields, `used_iterations=0`, `used_cost=0`, `prev_quality=-1`, `prev_prev_quality=-1`, `status=RUNNING`
2. Return handle immediately

### Error Codes

| Code | Condition |
|------|-----------|
| `ALREADY_EXISTS` | Loop with this `loop_id` already exists |
| `INVALID_ARGUMENT` | `max_iterations < 1`, `epsilon < 0`, or `cost_cap <= 0` |

---

## RPC: SubmitCorrectionIteration

**Pattern**: Unary (called once per iteration)  
**Called by**: Runtime per correction cycle

### Request

```
CorrectionIterationEvent {
  loop_id: string
  quality_score: double         // 0.0–1.0 quality metric
  cost: double                  // Cost of this iteration
  duration_ms: int64
}
```

### Response

```
ConvergenceResult {
  status: ConvergenceStatus     // CONTINUE | CONVERGED | BUDGET_EXCEEDED | ESCALATE_TO_HUMAN
  iteration_num: int32          // Which iteration this was
  delta: double                 // |current_quality - previous_quality|
  loop_id: string
}
```

### Behavior

1. Call `convergence_check.lua` atomically:
   - Updates `prev_prev_quality`, `prev_quality` in Redis
   - Returns 1 if both deltas < epsilon (converged), 0 otherwise
2. Increment `used_iterations` and `used_cost` via `budget_decrement.lua`
3. Evaluate result:
   - **Converged**: update Redis status=CONVERGED, emit Kafka event, return CONVERGED
   - **Budget exceeded** (iterations ≥ max OR cost ≥ cap): update status, check escalation config, emit Kafka event, return BUDGET_EXCEEDED or ESCALATE_TO_HUMAN
   - **Continue**: return CONTINUE
4. Persist row to `correction_iterations` table with score, delta, cost, duration

### Error Codes

| Code | Condition |
|------|-----------|
| `NOT_FOUND` | Loop `loop_id` does not exist |
| `FAILED_PRECONDITION` | Loop is not in RUNNING status |
| `INVALID_ARGUMENT` | `quality_score` outside [0.0, 1.0] |

---

## Kafka Events

**Topic**: `runtime.reasoning`  
**Key**: `execution_id` (ensures all events for an execution go to the same partition)

### Envelope Schema

```json
{
  "event_type": "reasoning.trace_event | reasoning.budget_threshold | reasoning.convergence | reasoning.branch_pruned | reasoning.branch_completed | reasoning.loop_converged | reasoning.loop_budget_exceeded",
  "version": "1.0",
  "source": "reasoning-engine",
  "execution_id": "<uuid>",
  "occurred_at": "<iso8601>",
  "payload": { ... }
}
```

**Topic**: `monitor.alerts`  
**Key**: `execution_id`

```json
{
  "event_type": "reasoning.escalate_to_human",
  "version": "1.0",
  "source": "reasoning-engine",
  "execution_id": "<uuid>",
  "loop_id": "<uuid>",
  "iterations_used": 10,
  "cost_used": 0.85,
  "last_quality_score": 0.62,
  "occurred_at": "<iso8601>"
}
```

---

## Python Client Stub (Control Plane)

```python
# apps/control-plane/src/platform/common/clients/reasoning_engine.py
import grpc
from generated.reasoning_engine_pb2_grpc import ReasoningEngineServiceStub
from generated.reasoning_engine_pb2 import (
    SelectReasoningModeRequest,
    AllocateReasoningBudgetRequest,
    BudgetAllocation,
)

class ReasoningEngineClient:
    def __init__(self, address: str = "musematic-reasoning-engine.platform-execution:50052"):
        self._channel = grpc.aio.insecure_channel(address)
        self._stub = ReasoningEngineServiceStub(self._channel)

    async def select_mode(self, execution_id: str, task_brief: str, max_tokens: int) -> str:
        request = SelectReasoningModeRequest(
            execution_id=execution_id,
            task_brief=task_brief,
            budget_constraints=BudgetAllocation(max_tokens=max_tokens),
        )
        response = await self._stub.SelectReasoningMode(request)
        return response.mode.name

    async def allocate_budget(self, execution_id: str, step_id: str, tokens: int) -> None:
        request = AllocateReasoningBudgetRequest(
            execution_id=execution_id,
            step_id=step_id,
            limits=BudgetAllocation(tokens=tokens),
        )
        await self._stub.AllocateReasoningBudget(request)
```

---

## Network Access

| Caller | Transport | Address |
|--------|-----------|---------|
| Control plane (`reasoning/` bounded context) | gRPC | `musematic-reasoning-engine.platform-execution:50052` |
| Runtime Controller | gRPC | `musematic-reasoning-engine.platform-execution:50052` |
| Reasoning Engine → Kafka | TCP | `musematic-kafka.platform-data:9092` |
| Reasoning Engine → Redis | TCP | `musematic-redis-cluster.platform-data:6379` |
| Reasoning Engine → PostgreSQL | TCP | `musematic-pooler.platform-data:5432` |
| Reasoning Engine → MinIO | HTTP | `musematic-minio.platform-data:9000` |
