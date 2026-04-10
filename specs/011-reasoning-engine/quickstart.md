# Quickstart: Reasoning Engine

**Feature**: 011-reasoning-engine  
**Service**: `services/reasoning-engine/`  
**Port**: 50052

---

## Prerequisites

```bash
# Go 1.22+
go version  # go1.22.x

# protoc + Go plugins
brew install protobuf
go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest

# grpcurl for manual testing
brew install grpcurl

# Local dependencies (Docker Compose)
cd deploy/local && docker compose up -d redis postgres kafka minio
```

---

## Build

```bash
cd services/reasoning-engine

# Generate proto stubs
make proto

# Build binary
make build

# Build Docker image (multi-stage, distroless)
make docker

# Run locally
GRPC_PORT=50052 \
REDIS_ADDR=localhost:6379 \
POSTGRES_DSN="postgres://musematic:musematic@localhost:5432/musematic" \
KAFKA_BROKERS=localhost:9092 \
MINIO_ENDPOINT=localhost:9000 \
MINIO_BUCKET=reasoning-traces \
./bin/reasoning-engine
```

---

## Test: Mode Selection

```bash
# Simple task → DIRECT mode
grpcurl -plaintext -d '{
  "execution_id": "exec-001",
  "task_brief": "What is the capital of France?",
  "budget_constraints": {"max_tokens": 1000}
}' localhost:50052 musematic.reasoning.v1.ReasoningEngineService/SelectReasoningMode

# Expected: mode=DIRECT, complexity_score in [0,2]

# Complex multi-step task → CHAIN_OF_THOUGHT or TREE_OF_THOUGHT
grpcurl -plaintext -d '{
  "execution_id": "exec-002",
  "task_brief": "First analyze the market trends, then compare competitors, and finally recommend a strategy with tradeoffs.",
  "budget_constraints": {"max_tokens": 50000, "max_rounds": 20}
}' localhost:50052 musematic.reasoning.v1.ReasoningEngineService/SelectReasoningMode

# Expected: mode=CHAIN_OF_THOUGHT or TREE_OF_THOUGHT, complexity_score >= 3

# Policy override → forced mode returned regardless
grpcurl -plaintext -d '{
  "execution_id": "exec-003",
  "task_brief": "What is 2+2?",
  "forced_mode": "TREE_OF_THOUGHT",
  "budget_constraints": {"max_tokens": 100000}
}' localhost:50052 musematic.reasoning.v1.ReasoningEngineService/SelectReasoningMode

# Expected: mode=TREE_OF_THOUGHT (override honored)

# Budget-constrained: expensive mode unavailable → downgrades
grpcurl -plaintext -d '{
  "execution_id": "exec-004",
  "task_brief": "Compare and debate three architectural approaches for distributed systems.",
  "budget_constraints": {"max_tokens": 500}
}' localhost:50052 musematic.reasoning.v1.ReasoningEngineService/SelectReasoningMode

# Expected: mode=DIRECT (DEBATE/TOT eliminated by budget)
```

---

## Test: Budget Allocation and Tracking

```bash
# Allocate budget
grpcurl -plaintext -d '{
  "execution_id": "exec-100",
  "step_id": "step-1",
  "limits": {"tokens": 1000, "rounds": 10, "cost": 1.0},
  "ttl_seconds": 3600
}' localhost:50052 musematic.reasoning.v1.ReasoningEngineService/AllocateReasoningBudget

# Query status (should show zeros)
grpcurl -plaintext -d '{
  "execution_id": "exec-100",
  "step_id": "step-1"
}' localhost:50052 musematic.reasoning.v1.ReasoningEngineService/GetReasoningBudgetStatus
```

---

## Test: Budget Event Streaming (Threshold Events)

```bash
# Terminal 1: Subscribe to events
grpcurl -plaintext -d '{
  "execution_id": "exec-200",
  "step_id": "step-1"
}' localhost:50052 musematic.reasoning.v1.ReasoningEngineService/StreamBudgetEvents &

# Terminal 2: Allocate budget, then trigger decrements via integration test
# Run the Go budget stress test:
go test ./internal/budget_tracker/... -run TestThresholdEvents -v

# Expected output in Terminal 1:
# event_type: "THRESHOLD_80"  (at 800 tokens used)
# event_type: "THRESHOLD_90"  (at 900 tokens used)
# event_type: "THRESHOLD_100" (at 1000 tokens used)
```

---

## Test: Chain-of-Thought Trace Streaming

```bash
# Stream 10 trace events
# (Use the integration test; grpcurl doesn't support client streaming interactively)
go test ./internal/cot_coordinator/... -run TestStreamTrace -v

# Expected:
# - 10 rows in reasoning_events table
# - Events appear in Kafka runtime.reasoning topic
# - Ack: total_received=10, total_persisted=10, total_dropped=0

# Test large payload (>64KB → MinIO)
go test ./internal/cot_coordinator/... -run TestLargePayloadToMinIO -v
# Expected: object_key set in reasoning_events row, payload NOT in DB
```

---

## Test: Tree-of-Thought Branches

```bash
# Create 5 branches
for i in 1 2 3 4 5; do
  grpcurl -plaintext -d "{
    \"tree_id\": \"tree-001\",
    \"branch_id\": \"branch-00$i\",
    \"hypothesis\": \"Approach $i: different strategy\",
    \"branch_budget\": {\"tokens\": 500}
  }" localhost:50052 musematic.reasoning.v1.ReasoningEngineService/CreateTreeBranch
done

# Evaluate branches (waits for all goroutines to finish)
grpcurl -plaintext -d '{
  "tree_id": "tree-001",
  "scoring_function": "quality_cost_ratio"
}' localhost:50052 musematic.reasoning.v1.ReasoningEngineService/EvaluateTreeBranches

# Expected: one branch selected, all branches in all_branches list with scores

# Test auto-pruning: create branch with tight budget
grpcurl -plaintext -d '{
  "tree_id": "tree-002",
  "branch_id": "branch-tight",
  "hypothesis": "Will be pruned",
  "branch_budget": {"tokens": 1}
}' localhost:50052 musematic.reasoning.v1.ReasoningEngineService/CreateTreeBranch
# Expected: branch status=PRUNED quickly (budget exhausted on first decrement)
```

---

## Test: Self-Correction Convergence

```bash
# Start loop with epsilon=0.01
grpcurl -plaintext -d '{
  "loop_id": "loop-001",
  "execution_id": "exec-300",
  "max_iterations": 10,
  "cost_cap": 5.0,
  "epsilon": 0.01,
  "escalate_on_budget_exceeded": false
}' localhost:50052 musematic.reasoning.v1.ReasoningEngineService/StartSelfCorrectionLoop

# Submit iterations with converging quality scores
# [0.5, 0.7, 0.78, 0.80, 0.805, 0.808] → converges at iteration 6
for score in 0.5 0.7 0.78 0.80 0.805 0.808; do
  grpcurl -plaintext -d "{
    \"loop_id\": \"loop-001\",
    \"quality_score\": $score,
    \"cost\": 0.1,
    \"duration_ms\": 500
  }" localhost:50052 musematic.reasoning.v1.ReasoningEngineService/SubmitCorrectionIteration
done

# Expected at iteration 6: status=CONVERGED
# (delta between 0.805→0.808 is 0.003 < 0.01; delta between 0.80→0.805 is 0.005 < 0.01)

# Test budget-exceeded path
grpcurl -plaintext -d '{
  "loop_id": "loop-002",
  "execution_id": "exec-301",
  "max_iterations": 3,
  "cost_cap": 100.0,
  "epsilon": 0.0001,
  "escalate_on_budget_exceeded": true
}' localhost:50052 musematic.reasoning.v1.ReasoningEngineService/StartSelfCorrectionLoop

for score in 0.5 0.7 0.9; do
  grpcurl -plaintext -d "{
    \"loop_id\": \"loop-002\",
    \"quality_score\": $score,
    \"cost\": 0.1,
    \"duration_ms\": 100
  }" localhost:50052 musematic.reasoning.v1.ReasoningEngineService/SubmitCorrectionIteration
done

# Expected at iteration 3: status=ESCALATE_TO_HUMAN
# Check monitor.alerts Kafka topic for escalation event
```

---

## Test: Budget Atomicity Under Concurrency

```bash
# Run 100 concurrent decrements — verify no double-counting
go test ./internal/budget_tracker/... -run TestConcurrentDecrements -count=1 -v
# Expected: total used_tokens == sum of all individual decrements

# Run with race detector
go test ./... -race
```

---

## Unit Tests

```bash
cd services/reasoning-engine

# All tests
go test ./...

# With coverage
go test ./... -coverprofile=coverage.out
go tool cover -html=coverage.out

# Specific package
go test ./internal/mode_selector/... -v
go test ./internal/correction_loop/... -v
go test ./internal/tot_manager/... -v
```

---

## Integration Tests

```bash
# Requires: Redis, PostgreSQL, Kafka, MinIO running locally
go test ./... -tags=integration -v

# Or via make
make test-integration
```

---

## Docker Image Size Check

```bash
make docker
docker images musematic/reasoning-engine:latest --format "{{.Size}}"
# Must be < 50MB (distroless base)
```

---

## Verify Health Check

```bash
# gRPC health protocol
grpcurl -plaintext localhost:50052 grpc.health.v1.Health/Check

# Expected:
# { "status": "SERVING" }
```

---

## Prometheus Metrics

Available at `:9090/metrics` (or via OpenTelemetry if configured):

| Metric | Type | Description |
|--------|------|-------------|
| `reasoning_budget_decrements_total` | Counter | Budget decrements by dimension |
| `reasoning_budget_check_duration_seconds` | Histogram | Budget check latency (target p99 < 0.001) |
| `reasoning_mode_selections_total` | Counter | Mode selections by mode |
| `reasoning_tot_branches_total` | Counter | Branches created by status |
| `reasoning_correction_iterations_total` | Counter | Iterations by convergence outcome |
| `reasoning_trace_events_total` | Counter | Trace events by type |
| `reasoning_trace_dropped_total` | Counter | Buffer overflow drops |
