# Data Model: Reasoning Engine

**Feature**: 011-reasoning-engine  
**Date**: 2026-04-10  
**Phase**: 1 — Design

---

## State Machines

### BudgetEnvelope Lifecycle

```
ALLOCATED → ACTIVE → EXHAUSTED
                   → COMPLETED (execution ended normally)
```

- **ALLOCATED**: Budget created in Redis, all counters at zero
- **ACTIVE**: Budget decrementing normally; threshold events at 80%, 90%
- **EXHAUSTED**: Any dimension (tokens, rounds, cost, time) hit its limit; further decrements rejected
- **COMPLETED**: Execution ended normally; budget archived to PostgreSQL, Redis key expires via TTL

### TreeBranch Lifecycle

```
CREATED → ACTIVE → COMPLETED
                 → PRUNED    (branch budget exceeded)
                 → FAILED    (goroutine panic recovered)
```

- **CREATED**: Branch state written to Redis; goroutine not yet started
- **ACTIVE**: Goroutine executing; quality score updating
- **COMPLETED**: Goroutine finished; quality score and cost finalized; payload written to MinIO
- **PRUNED**: Branch budget exhausted atomically via Lua; goroutine cancelled via `context.CancelCauseFunc`
- **FAILED**: Goroutine panic recovered; branch marked failed; siblings continue

### SelfCorrectionLoop Lifecycle

```
RUNNING → CONVERGED     (delta < epsilon for 2 consecutive iterations)
        → BUDGET_EXCEEDED (iterations >= max OR cost >= cap)
        → ESCALATED       (budget exhausted + escalation configured)
```

- **RUNNING**: Accepting `SubmitCorrectionIteration` calls
- **CONVERGED**: Convergence detected; loop closed; Kafka event emitted
- **BUDGET_EXCEEDED**: Hard limit reached; loop closed; Kafka event emitted
- **ESCALATED**: Budget exceeded + escalation config present; escalation event emitted to `monitor.alerts`

---

## Redis Key Schemas

| Key Pattern | Type | Fields | TTL |
|-------------|------|--------|-----|
| `budget:{execution_id}:{step_id}` | Hash | `used_tokens`, `max_tokens`, `used_rounds`, `max_rounds`, `used_cost`, `max_cost`, `start_time_ms`, `max_time_ms`, `status` | execution lifetime + 1h |
| `branch:{tree_id}:{branch_id}` | Hash | `hypothesis`, `quality_score`, `token_cost`, `status`, `created_at_ms` | tree execution lifetime + 1h |
| `correction:{loop_id}` | Hash | `max_iterations`, `used_iterations`, `cost_cap`, `used_cost`, `epsilon`, `prev_quality`, `prev_prev_quality`, `status` | loop lifetime + 1h |

---

## PostgreSQL Tables (Cold State)

```sql
-- Trace metadata (one row per reasoning execution)
CREATE TABLE reasoning_traces (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id    UUID NOT NULL,
    mode            TEXT NOT NULL CHECK (mode IN ('DIRECT','CHAIN_OF_THOUGHT','TREE_OF_THOUGHT','REACT','CODE_AS_REASONING','DEBATE')),
    total_events    INTEGER NOT NULL DEFAULT 0,
    dropped_events  INTEGER NOT NULL DEFAULT 0,
    started_at      TIMESTAMPTZ NOT NULL,
    completed_at    TIMESTAMPTZ,
    object_key      TEXT,                    -- MinIO full payload reference
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_reasoning_traces_execution_id ON reasoning_traces (execution_id);

-- Individual trace event metadata (one row per event)
CREATE TABLE reasoning_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id        UUID NOT NULL REFERENCES reasoning_traces(id) ON DELETE CASCADE,
    event_type      TEXT NOT NULL,
    sequence_num    INTEGER NOT NULL,
    occurred_at     TIMESTAMPTZ NOT NULL,
    payload_size    INTEGER NOT NULL DEFAULT 0,
    object_key      TEXT,                    -- MinIO reference if payload > 64KB
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_reasoning_events_trace_id ON reasoning_events (trace_id);
CREATE INDEX idx_reasoning_events_occurred_at ON reasoning_events (occurred_at);

-- Tree-of-thought branch records
CREATE TABLE tot_branches (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tree_id         UUID NOT NULL,
    branch_id       UUID NOT NULL UNIQUE,
    hypothesis      TEXT NOT NULL,
    quality_score   DOUBLE PRECISION,
    token_cost      INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL CHECK (status IN ('CREATED','ACTIVE','COMPLETED','PRUNED','FAILED')),
    object_key      TEXT,                    -- MinIO branch payload reference
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX idx_tot_branches_tree_id ON tot_branches (tree_id);

-- Self-correction iteration history (one row per iteration)
CREATE TABLE correction_iterations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    loop_id         UUID NOT NULL,
    iteration_num   INTEGER NOT NULL,
    quality_score   DOUBLE PRECISION NOT NULL,
    delta           DOUBLE PRECISION,        -- NULL for first iteration
    cost            DOUBLE PRECISION NOT NULL DEFAULT 0,
    duration_ms     INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (loop_id, iteration_num)
);

CREATE INDEX idx_correction_iterations_loop_id ON correction_iterations (loop_id);
```

---

## Protobuf Definition

```protobuf
syntax = "proto3";

package musematic.reasoning.v1;

option go_package = "github.com/musematic/reasoning-engine/api/grpc/v1;reasoningv1";

import "google/protobuf/timestamp.proto";

service ReasoningEngineService {
  // Mode selection
  rpc SelectReasoningMode(SelectReasoningModeRequest) returns (ReasoningModeConfig);
  
  // Budget lifecycle
  rpc AllocateReasoningBudget(AllocateReasoningBudgetRequest) returns (ReasoningBudgetEnvelope);
  rpc GetReasoningBudgetStatus(GetBudgetStatusRequest) returns (BudgetStatusResponse);
  rpc StreamBudgetEvents(StreamBudgetEventsRequest) returns (stream BudgetEvent);
  
  // Chain-of-thought trace coordination
  rpc StreamReasoningTrace(stream ReasoningTraceEvent) returns (ReasoningTraceAck);
  
  // Tree-of-thought branch management
  rpc CreateTreeBranch(CreateTreeBranchRequest) returns (TreeBranchHandle);
  rpc EvaluateTreeBranches(EvaluateTreeBranchesRequest) returns (BranchSelectionResult);
  
  // Self-correction convergence
  rpc StartSelfCorrectionLoop(StartSelfCorrectionRequest) returns (SelfCorrectionHandle);
  rpc SubmitCorrectionIteration(CorrectionIterationEvent) returns (ConvergenceResult);
}

// ─── Mode Selection ────────────────────────────────────────────────────────

enum ReasoningMode {
  REASONING_MODE_UNSPECIFIED   = 0;
  DIRECT                       = 1;
  CHAIN_OF_THOUGHT             = 2;
  TREE_OF_THOUGHT              = 3;
  REACT                        = 4;
  CODE_AS_REASONING            = 5;
  DEBATE                       = 6;
}

message SelectReasoningModeRequest {
  string execution_id   = 1;
  string task_brief     = 2;
  string forced_mode    = 3;   // empty = auto-select
  BudgetConstraints budget_constraints = 4;
}

message BudgetConstraints {
  int64  max_tokens  = 1;
  int64  max_rounds  = 2;
  double max_cost    = 3;
  int64  max_time_ms = 4;
}

message ReasoningModeConfig {
  ReasoningMode mode             = 1;
  int32         complexity_score = 2;
  BudgetAllocation recommended_budget = 3;
  string        rationale        = 4;
}

message BudgetAllocation {
  int64  tokens  = 1;
  int64  rounds  = 2;
  double cost    = 3;
  int64  time_ms = 4;
}

// ─── Budget Tracking ───────────────────────────────────────────────────────

message AllocateReasoningBudgetRequest {
  string execution_id  = 1;
  string step_id       = 2;
  BudgetAllocation limits = 3;
  int64  ttl_seconds   = 4;   // Redis TTL; 0 = default (exec lifetime + 1h)
}

message ReasoningBudgetEnvelope {
  string execution_id  = 1;
  string step_id       = 2;
  BudgetAllocation limits  = 3;
  BudgetAllocation used    = 4;
  string status        = 5;   // ALLOCATED, ACTIVE, EXHAUSTED, COMPLETED
  google.protobuf.Timestamp allocated_at = 6;
}

message GetBudgetStatusRequest {
  string execution_id = 1;
  string step_id      = 2;
}

message BudgetStatusResponse {
  ReasoningBudgetEnvelope envelope = 1;
}

message StreamBudgetEventsRequest {
  string execution_id = 1;
  string step_id      = 2;
}

message BudgetEvent {
  string execution_id  = 1;
  string step_id       = 2;
  string event_type    = 3;   // THRESHOLD_80, THRESHOLD_90, THRESHOLD_100, ALLOCATED, COMPLETED, EXCEEDED
  string dimension     = 4;   // tokens, rounds, cost, time
  double current_value = 5;
  double max_value     = 6;
  google.protobuf.Timestamp occurred_at = 7;
}

// ─── Chain-of-Thought Trace ────────────────────────────────────────────────

message ReasoningTraceEvent {
  string execution_id  = 1;
  string step_id       = 2;
  string event_id      = 3;
  string event_type    = 4;
  int32  sequence_num  = 5;
  bytes  payload       = 6;   // raw event payload; >64KB → MinIO
  google.protobuf.Timestamp occurred_at = 7;
}

message ReasoningTraceAck {
  string execution_id   = 1;
  int32  total_received = 2;
  int32  total_persisted = 3;
  int32  total_dropped  = 4;
  repeated string failed_event_ids = 5;
}

// ─── Tree-of-Thought ───────────────────────────────────────────────────────

message CreateTreeBranchRequest {
  string tree_id    = 1;
  string branch_id  = 2;
  string hypothesis = 3;
  BudgetAllocation branch_budget = 4;
}

message TreeBranchHandle {
  string tree_id   = 1;
  string branch_id = 2;
  string status    = 3;   // CREATED, ACTIVE, COMPLETED, PRUNED, FAILED
  google.protobuf.Timestamp created_at = 4;
}

message EvaluateTreeBranchesRequest {
  string tree_id         = 1;
  string scoring_function = 2;   // "quality_cost_ratio" (default), "quality_only"
}

message BranchSelectionResult {
  string selected_branch_id  = 1;
  double selected_quality    = 2;
  int64  selected_token_cost = 3;
  repeated BranchSummary all_branches = 4;
  bool   no_viable_branches  = 5;
  string best_partial_branch_id = 6;   // set when no_viable_branches = true
}

message BranchSummary {
  string branch_id    = 1;
  string hypothesis   = 2;
  double quality_score = 3;
  int64  token_cost   = 4;
  string status       = 5;
  double score        = 6;   // computed scoring function value
}

// ─── Self-Correction ───────────────────────────────────────────────────────

message StartSelfCorrectionRequest {
  string loop_id        = 1;
  string execution_id   = 2;
  int32  max_iterations = 3;
  double cost_cap       = 4;
  double epsilon        = 5;   // convergence threshold
  bool   escalate_on_budget_exceeded = 6;
}

message SelfCorrectionHandle {
  string loop_id   = 1;
  string status    = 2;   // RUNNING
  google.protobuf.Timestamp started_at = 3;
}

message CorrectionIterationEvent {
  string loop_id       = 1;
  double quality_score = 2;
  double cost          = 3;
  int64  duration_ms   = 4;
}

enum ConvergenceStatus {
  CONVERGENCE_STATUS_UNSPECIFIED = 0;
  CONTINUE                       = 1;
  CONVERGED                      = 2;
  BUDGET_EXCEEDED                = 3;
  ESCALATE_TO_HUMAN              = 4;
}

message ConvergenceResult {
  ConvergenceStatus status        = 1;
  int32             iteration_num = 2;
  double            delta         = 3;
  string            loop_id       = 4;
}
```

---

## Package Layout

```
services/reasoning-engine/
├── cmd/reasoning-engine/
│   └── main.go                    # server startup, signal handling
├── api/grpc/
│   └── v1/
│       ├── handler.go             # implements ReasoningEngineServiceServer interface
│       └── interceptors.go        # auth, tracing, recovery interceptors
├── internal/
│   ├── mode_selector/
│   │   ├── selector.go            # ModeSelector interface + implementation
│   │   └── heuristic.go          # complexity scoring function
│   ├── budget_tracker/
│   │   ├── tracker.go            # BudgetTracker interface
│   │   ├── redis.go              # Redis hash operations + Lua script calls
│   │   └── events.go            # threshold event detection + fan-out dispatch
│   ├── cot_coordinator/
│   │   ├── coordinator.go        # CoTCoordinator interface
│   │   └── pipeline.go          # async goroutine pool for event processing
│   ├── tot_manager/
│   │   ├── manager.go           # ToTManager interface
│   │   ├── branch.go            # branch goroutine: semaphore acquire, execute, cancel
│   │   └── evaluator.go         # scoring function + branch ranking
│   ├── correction_loop/
│   │   ├── loop.go              # CorrectionLoop interface
│   │   └── convergence.go       # calls convergence_check.lua, escalation routing
│   ├── quality_evaluator/
│   │   └── evaluator.go         # QualityEvaluator interface (scorer abstraction)
│   ├── code_bridge/
│   │   └── bridge.go            # gRPC client to sandbox-manager:50053
│   └── escalation/
│       └── router.go            # Kafka producer → monitor.alerts
├── pkg/
│   ├── lua/
│   │   ├── budget_decrement.lua
│   │   ├── convergence_check.lua
│   │   └── loader.go            # SCRIPT LOAD at startup, returns SHA map
│   ├── metrics/
│   │   └── metrics.go           # Prometheus counters/histograms
│   └── persistence/
│       ├── postgres.go          # pgx/v5 pool setup
│       ├── redis.go             # go-redis/v9 cluster client
│       ├── kafka.go             # confluent-kafka-go producer
│       └── minio.go             # aws-sdk-go-v2 S3 client
└── proto/
    └── reasoning_engine.proto   # source of truth (above)
```

---

## Configuration Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GRPC_PORT` | `50052` | gRPC server port |
| `REDIS_ADDR` | required | Redis cluster address(es) |
| `POSTGRES_DSN` | required | pgx/v5 connection string |
| `KAFKA_BROKERS` | required | Kafka broker list |
| `MINIO_ENDPOINT` | required | MinIO S3-compatible endpoint |
| `MINIO_BUCKET` | `reasoning-traces` | Object storage bucket |
| `MAX_TOT_CONCURRENCY` | `10` | Max concurrent ToT branch goroutines |
| `TRACE_BUFFER_SIZE` | `10000` | In-memory event buffer per trace |
| `TRACE_PAYLOAD_THRESHOLD` | `65536` | Bytes above which payload goes to MinIO |
| `BUDGET_DEFAULT_TTL_SECONDS` | `3600` | Default Redis TTL buffer after execution |
| `SANDBOX_MANAGER_ADDR` | required | gRPC address for code-as-reasoning budget tracking |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | optional | OpenTelemetry collector |
