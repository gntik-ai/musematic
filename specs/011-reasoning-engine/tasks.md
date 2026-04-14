---
description: "Task list for Reasoning Engine implementation"
---

# Tasks: Reasoning Engine

**Input**: Design documents from `/specs/011-reasoning-engine/`  
**Branch**: `011-reasoning-engine`  
**Service**: `services/reasoning-engine/`

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no shared dependencies)
- **[Story]**: User story this task belongs to (US1–US6)
- Exact file paths included in every description

---

## Phase 1: Setup (Project Initialization)

**Purpose**: Go module, directory structure, proto stub generation, Makefile

- [X] T001 Initialize Go module at `services/reasoning-engine/go.mod` with module path `github.com/musematic/reasoning-engine` and Go 1.22 directive
- [X] T002 Add all dependencies to `services/reasoning-engine/go.mod`: `google.golang.org/grpc v1.67+`, `google.golang.org/protobuf v1.34+`, `github.com/redis/go-redis/v9`, `github.com/jackc/pgx/v5`, `github.com/confluentinc/confluent-kafka-go/v2`, `github.com/aws/aws-sdk-go-v2`, `go.opentelemetry.io/otel v1.29+`, `github.com/stretchr/testify v1.9`
- [X] T003 [P] Create full directory skeleton: `services/reasoning-engine/{cmd/reasoning-engine,api/grpc/v1,internal/{mode_selector,budget_tracker,cot_coordinator,tot_manager,correction_loop,quality_evaluator,code_bridge,escalation},pkg/{lua,metrics,persistence},proto}` with `.gitkeep` in each
- [X] T004 [P] Write protobuf definition to `services/reasoning-engine/proto/reasoning_engine.proto` with all 9 RPCs, all message types, and enums per `specs/011-reasoning-engine/contracts/grpc-service.md`
- [X] T005 Write `services/reasoning-engine/Makefile` with targets: `proto` (runs `protoc`), `build` (`go build ./cmd/reasoning-engine/...`), `docker` (multi-stage build), `test` (`go test ./...`), `test-integration` (`go test -tags=integration ./...`), `lint` (`golangci-lint run`)
- [X] T006 Run `make proto` to generate Go stubs from proto into `services/reasoning-engine/api/grpc/v1/` — verify `reasoning_engine_grpc.pb.go` and `reasoning_engine.pb.go` are created

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Persistence adapters, Lua scripts, metrics, gRPC server wiring — required by ALL user stories

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T007 [P] Write `services/reasoning-engine/pkg/lua/budget_decrement.lua` — exact script: read `KEYS[1]` hash field `ARGV[1]`, compare `current + ARGV[2]` against `max_{field}`, return -1 if exceeded, else `HINCRBYFLOAT` and return new value
- [X] T008 [P] Write `services/reasoning-engine/pkg/lua/convergence_check.lua` — exact script: read `prev_quality` and `prev_prev_quality` from `KEYS[1]` hash, shift history, compute both deltas, return 1 if both `< ARGV[2]` (epsilon), else 0
- [X] T009 Write `services/reasoning-engine/pkg/lua/loader.go` — `Load(ctx, rdb)` function that calls `SCRIPT LOAD` for both Lua files at startup and returns `map[string]string{"budget_decrement": sha, "convergence_check": sha}` for use with `EVALSHA`
- [X] T010 [P] Write `services/reasoning-engine/pkg/persistence/redis.go` — `NewRedisClient(addr string) *redis.ClusterClient` using `go-redis/v9`; single-node fallback when `REDIS_TEST_MODE=standalone`
- [X] T011 [P] Write `services/reasoning-engine/pkg/persistence/postgres.go` — `NewPostgresPool(dsn string) *pgxpool.Pool` using `pgx/v5`; pool config: max 20 conns, min 2 conns
- [X] T012 [P] Write `services/reasoning-engine/pkg/persistence/kafka.go` — `NewKafkaProducer(brokers string) *kafka.Producer` using `confluent-kafka-go/v2`; `Produce(topic, key string, value []byte)` method with delivery report goroutine
- [X] T013 [P] Write `services/reasoning-engine/pkg/persistence/minio.go` — `NewMinIOClient(endpoint, bucket string) *MinIOClient` using `aws-sdk-go-v2`; `Upload(ctx, key string, data []byte) error` and `GetURL(key string) string` methods; S3-compatible path-style addressing
- [X] T014 Write `services/reasoning-engine/pkg/metrics/metrics.go` — define all Prometheus instruments: `budget_decrements_total` (counter, labels: dimension), `budget_check_duration_seconds` (histogram, buckets: 0.0001–0.01), `mode_selections_total` (counter, labels: mode), `tot_branches_total` (counter, labels: status), `correction_iterations_total` (counter, labels: outcome), `trace_events_total` (counter), `trace_dropped_total` (counter)
- [X] T015 Write `services/reasoning-engine/api/grpc/v1/interceptors.go` — UnaryInterceptor and StreamInterceptor chain: (1) OTel trace propagation via `go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc`, (2) panic recovery (log + return `codes.Internal`), (3) request logging via `log/slog`
- [X] T016 Write `services/reasoning-engine/api/grpc/v1/handler.go` skeleton — `Handler` struct holding references to all internal package interfaces; implement `mustEmbedUnimplementedReasoningEngineServiceServer()`; all 9 methods stubbed returning `codes.Unimplemented`
- [X] T017 Write `services/reasoning-engine/cmd/reasoning-engine/main.go` — read env vars (GRPC_PORT, REDIS_ADDR, POSTGRES_DSN, KAFKA_BROKERS, MINIO_ENDPOINT, MINIO_BUCKET, MAX_TOT_CONCURRENCY, TRACE_BUFFER_SIZE, TRACE_PAYLOAD_THRESHOLD, BUDGET_DEFAULT_TTL_SECONDS), initialize all persistence clients, load Lua scripts, build `Handler`, register gRPC health service (`grpc.health.v1`), register `ReasoningEngineService`, start listener on `:50052`, handle `SIGTERM`/`SIGINT` for graceful shutdown
- [X] T018 Write PostgreSQL migration SQL for all 4 tables in `services/reasoning-engine/migrations/001_initial_schema.sql`: `reasoning_traces`, `reasoning_events`, `tot_branches`, `correction_iterations` — exact DDL from `specs/011-reasoning-engine/data-model.md`

**Checkpoint**: `go build ./...` succeeds; `make proto` generates stubs; server starts and health check returns SERVING

---

## Phase 3: US1 — Reasoning Mode Selection (Priority: P1) 🎯 MVP

**Goal**: `SelectReasoningMode` RPC returns the correct reasoning mode based on task complexity, policy overrides, and budget constraints

**Independent Test**:
```bash
# Simple task → DIRECT; multi-step → COT/TOT; forced_mode → respected; tight budget → downgrade
grpcurl -plaintext -d '{"execution_id":"e1","task_brief":"What is 2+2?","budget_constraints":{"max_tokens":1000}}' \
  localhost:50052 musematic.reasoning.v1.ReasoningEngineService/SelectReasoningMode
# Expect: mode=DIRECT
```

- [X] T019 [US1] Write `services/reasoning-engine/internal/mode_selector/heuristic.go` — `Score(brief string) int` function: +1 per 50 words, +2 for multi-step keywords ("first...then", "finally", "step 1"), +1 per "?" beyond first, +2 for code keywords ("script","function","python","def"); detect CODE_AS_REASONING keywords ("code","script","write a function"); detect DEBATE keywords ("compare","debate","argue both sides","pros and cons")
- [X] T020 [US1] Write `services/reasoning-engine/internal/mode_selector/selector.go` — `ModeSelector` interface + `RuleBasedSelector` implementation: (1) return `forced_mode` if set, (2) eliminate modes exceeding budget constraints (pre-configured costs per mode), (3) compute complexity score, (4) map to mode (0–2→DIRECT, 3–5→CHAIN_OF_THOUGHT, 6–8→TREE_OF_THOUGHT, 9+→TREE_OF_THOUGHT; keyword overrides for CODE_AS_REASONING/DEBATE), (5) compute proportional budget allocation
- [X] T021 [US1] Implement `SelectReasoningMode` in `services/reasoning-engine/api/grpc/v1/handler.go` — call `ModeSelector.Select`, map result to `ReasoningModeConfig` proto message, increment `mode_selections_total` metric
- [X] T022 [US1] Write unit tests in `services/reasoning-engine/internal/mode_selector/selector_test.go` — table-driven: simple task→DIRECT, multi-step→COT, complex→TOT, forced_mode→respected regardless of score, code keywords→CODE_AS_REASONING, debate keywords→DEBATE, tight budget→downgrade to cheaper mode

**Checkpoint**: `SelectReasoningMode` responds correctly for all 6 mode branches; US1 independently testable via grpcurl

---

## Phase 4: US2 — Real-Time Budget Tracking and Enforcement (Priority: P1)

**Goal**: `AllocateReasoningBudget` and `GetReasoningBudgetStatus` RPCs correctly manage budget state in Redis with atomic decrements and no race conditions

**Independent Test**:
```bash
grpcurl -plaintext -d '{"execution_id":"e2","step_id":"s1","limits":{"tokens":1000,"rounds":10}}' \
  localhost:50052 musematic.reasoning.v1.ReasoningEngineService/AllocateReasoningBudget
grpcurl -plaintext -d '{"execution_id":"e2","step_id":"s1"}' \
  localhost:50052 musematic.reasoning.v1.ReasoningEngineService/GetReasoningBudgetStatus
# Expect: used=0, status=ALLOCATED
```

- [X] T023 [US2] Write `services/reasoning-engine/internal/budget_tracker/tracker.go` — `BudgetTracker` interface: `Allocate(ctx, execID, stepID string, limits BudgetLimits, ttlSecs int64) error`, `Decrement(ctx, execID, stepID, dimension string, amount float64) (float64, error)`, `GetStatus(ctx, execID, stepID string) (*BudgetStatus, error)`
- [X] T024 [US2] Write `services/reasoning-engine/internal/budget_tracker/redis.go` — implement `BudgetTracker` interface: `Allocate` writes Redis hash `budget:{execID}:{stepID}` with all limit and used fields (zero), sets TTL; `Decrement` calls `EVALSHA` with `budget_decrement.lua` SHA, returns new value or error if exceeded; `GetStatus` reads all hash fields via `HGETALL`; record `budget_check_duration_seconds` histogram on every `Decrement`
- [X] T025 [US2] Write `services/reasoning-engine/internal/budget_tracker/events.go` — `EventRegistry` with `sync.RWMutex`-protected `map[string][]chan BudgetEvent`; `Subscribe(key string) <-chan BudgetEvent`; `Unsubscribe(key string, ch <-chan BudgetEvent)`; `Publish(key string, event BudgetEvent)`; threshold detection: after each `Decrement`, compute percent used per dimension, publish THRESHOLD_80/90/100 events when crossing boundaries
- [X] T026 [US2] Implement `AllocateReasoningBudget` and `GetReasoningBudgetStatus` in `services/reasoning-engine/api/grpc/v1/handler.go` — call `BudgetTracker.Allocate`/`GetStatus`, map to proto response
- [X] T027 [US2] Write integration tests in `services/reasoning-engine/internal/budget_tracker/redis_test.go` (build tag `integration`) — (1) allocate + 10 decrements of 100 tokens → used_tokens=1000; (2) decrement beyond max → returns error; (3) 100 concurrent goroutines each decrement 10 tokens → total used == 1000 (run with `-race`); (4) TTL set correctly via `PTTL`

**Checkpoint**: Budget allocation and status query work; atomicity confirmed under 100-goroutine concurrency

---

## Phase 5: US3 — Chain-of-Thought Trace Coordination (Priority: P1)

**Goal**: `StreamReasoningTrace` RPC receives streaming events, persists metadata to PostgreSQL, routes large payloads to MinIO, emits all events to Kafka

**Independent Test**:
```bash
go test ./internal/cot_coordinator/... -run TestStreamTrace -v
# Expect: 10 events received → 10 rows in reasoning_events → 10 Kafka messages → ack total_received=10
```

- [X] T028 [US3] Write `services/reasoning-engine/internal/cot_coordinator/coordinator.go` — `CoTCoordinator` interface: `ProcessStream(ctx, stream grpc.ClientStreamingServer) (*TraceAck, error)`; `TraceAck` struct with received/persisted/dropped counts and failed IDs
- [X] T029 [US3] Write `services/reasoning-engine/internal/cot_coordinator/pipeline.go` — implement `CoTCoordinator`: stream reader goroutine feeds buffered channel (capacity=`TRACE_BUFFER_SIZE`); worker pool (min(8, runtime.NumCPU()) goroutines) drains channel; per-event: if `len(payload) > TRACE_PAYLOAD_THRESHOLD` upload to MinIO at `reasoning-traces/{execID}/{stepID}/{eventID}`, store object key; insert row to `reasoning_events` via `pgx/v5`; produce Kafka message to `runtime.reasoning` keyed by `execution_id`; on buffer overflow: drop oldest event, increment dropped counter, update `trace_dropped_total` metric; on stream EOF: flush remaining events, build and return `TraceAck`
- [X] T030 [US3] Write PostgreSQL insert helper in `services/reasoning-engine/internal/cot_coordinator/pipeline.go` — upsert `reasoning_traces` row on first event for `execution_id`, then insert `reasoning_events` rows using pgx batch (batch size 100 or flush interval 500ms)
- [X] T031 [US3] Implement `StreamReasoningTrace` in `services/reasoning-engine/api/grpc/v1/handler.go` — call `CoTCoordinator.ProcessStream`, return `ReasoningTraceAck` proto
- [X] T032 [US3] Write unit tests in `services/reasoning-engine/internal/cot_coordinator/pipeline_test.go` — mock Redis/PostgreSQL/Kafka/MinIO: (1) 10 events → ack total_received=10, total_dropped=0; (2) payload > 64KB → MinIO upload called, object_key set; (3) buffer overflow → oldest dropped, total_dropped incremented

**Checkpoint**: Client-streaming trace ingestion works end-to-end; large payloads routed to MinIO; Kafka emission verified

---

## Phase 6: US4 — Tree-of-Thought Branch Management (Priority: P2)

**Goal**: `CreateTreeBranch` and `EvaluateTreeBranches` RPCs manage concurrent branch goroutines, auto-prune over-budget branches, and select the best branch by quality/cost ratio

**Independent Test**:
```bash
# Create 3 branches; one with budget=1 token → gets pruned; evaluate → best of remaining 2 selected
go test ./internal/tot_manager/... -run TestBranchPruning -v
```

- [X] T033 [US4] Write `services/reasoning-engine/internal/tot_manager/manager.go` — `ToTManager` interface: `CreateBranch(ctx, treeID, branchID, hypothesis string, budget BudgetLimits) (*BranchHandle, error)`, `EvaluateBranches(ctx, treeID, scoringFn string) (*SelectionResult, error)`; hold semaphore (`chan struct{}`, capacity=`MAX_TOT_CONCURRENCY`), WaitGroup per tree, and branch registry (`sync.Map`)
- [X] T034 [US4] Write `services/reasoning-engine/internal/tot_manager/branch.go` — `CreateBranch` implementation: (1) write Redis hash `branch:{treeID}:{branchID}` with hypothesis, status=CREATED; (2) allocate budget hash `budget:{treeID}:{branchID}`; (3) insert `tot_branches` row; (4) acquire semaphore slot, start goroutine: mark status=ACTIVE in Redis, enter budget-check loop (call `budget_decrement.lua` per step), on budget exceeded call `context.CancelCauseFunc("budget_exceeded")`, set status=PRUNED in Redis and PostgreSQL; wrap goroutine in `recover()` — on panic set status=FAILED; on completion set status=COMPLETED, store final quality_score and token_cost; release semaphore, call `wg.Done()`
- [X] T035 [US4] Write `services/reasoning-engine/internal/tot_manager/evaluator.go` — `EvaluateBranches` implementation: (1) wait on WaitGroup for tree; (2) read all `branch:{treeID}:*` keys from Redis; (3) filter: COMPLETED → ranked, PRUNED/FAILED → excluded from winner; (4) apply scoring function (quality_cost_ratio = quality_score/(token_cost+1), quality_only = quality_score); (5) tie-break: lower token_cost wins, then earlier created_at; (6) if no COMPLETED branches: set no_viable_branches=true, return best PRUNED as partial; (7) update `tot_branches` rows with final scores
- [X] T036 [US4] Implement `CreateTreeBranch` and `EvaluateTreeBranches` in `services/reasoning-engine/api/grpc/v1/handler.go` — call `ToTManager` methods, map to proto responses; `EvaluateTreeBranches` increments `tot_branches_total` metric per branch status
- [X] T037 [US4] Write unit tests in `services/reasoning-engine/internal/tot_manager/manager_test.go` — (1) 5 branches → all execute concurrently (assert semaphore not blocking with capacity 10); (2) branch with budget=1 token → status=PRUNED; (3) 3 completed branches with known quality/cost → correct winner selected; (4) all branches pruned → no_viable_branches=true, best partial returned; (5) branch panic → recovered, status=FAILED, siblings unaffected

**Checkpoint**: ToT branch creation, concurrent execution, auto-pruning, and branch evaluation all work independently

---

## Phase 7: US5 — Self-Correction Convergence Detection (Priority: P2)

**Goal**: `StartSelfCorrectionLoop` and `SubmitCorrectionIteration` RPCs correctly detect convergence, enforce budget limits, and escalate when configured

**Independent Test**:
```bash
# Submit scores [0.5, 0.7, 0.78, 0.80, 0.805, 0.808] with epsilon=0.01 → CONVERGED at iteration 6
go test ./internal/correction_loop/... -run TestConvergenceDetection -v
```

- [X] T038 [US5] Write `services/reasoning-engine/internal/correction_loop/loop.go` — `CorrectionLoop` interface: `Start(ctx, loopID, execID string, cfg LoopConfig) (*LoopHandle, error)`, `Submit(ctx, loopID string, quality, cost float64, durationMs int64) (ConvergenceStatus, int, float64, error)`; `LoopConfig`: max_iterations, cost_cap, epsilon, escalate_on_budget_exceeded
- [X] T039 [US5] Write `services/reasoning-engine/internal/correction_loop/convergence.go` — `Start` implementation: write Redis hash `correction:{loopID}` with all config fields, `used_iterations=0`, `used_cost=0`, `prev_quality=-1`, `prev_prev_quality=-1`, `status=RUNNING`; `Submit` implementation: (1) call `convergence_check.lua` via EVALSHA; (2) call `budget_decrement.lua` for `used_iterations` (+1) and `used_cost` (+cost); (3) if converged → set Redis status=CONVERGED, produce Kafka `reasoning.loop_converged` event to `runtime.reasoning`, return CONVERGED; (4) if iterations ≥ max OR cost ≥ cap → set status=BUDGET_EXCEEDED, call escalation router if configured, produce Kafka event, return BUDGET_EXCEEDED or ESCALATE_TO_HUMAN; (5) else return CONTINUE; (6) in all cases insert row to `correction_iterations` with score, delta (|current-prev|), cost, duration_ms
- [X] T040 [US5] Write `services/reasoning-engine/internal/escalation/router.go` — `EscalationRouter` struct with Kafka producer; `Escalate(ctx, loopID, execID string, iterationsUsed int, costUsed, lastQuality float64) error` — produce message to `monitor.alerts` topic with event_type=`reasoning.escalate_to_human` and full payload per `specs/011-reasoning-engine/contracts/grpc-service.md`
- [X] T041 [US5] Implement `StartSelfCorrectionLoop` and `SubmitCorrectionIteration` in `services/reasoning-engine/api/grpc/v1/handler.go` — call `CorrectionLoop` methods, map to `SelfCorrectionHandle` and `ConvergenceResult` proto messages; increment `correction_iterations_total` metric with outcome label
- [X] T042 [US5] Write unit tests in `services/reasoning-engine/internal/correction_loop/convergence_test.go` — (1) scores [0.5, 0.7, 0.78, 0.80, 0.805, 0.808], epsilon=0.01 → CONVERGED at iteration 6; (2) 3 iterations with max_iterations=3, scores never converge → BUDGET_EXCEEDED; (3) cost exceeds cap → BUDGET_EXCEEDED; (4) budget exhausted with escalate=true → ESCALATE_TO_HUMAN + escalation Kafka event; (5) epsilon=0 → loop runs to max_iterations (convergence disabled); (6) each Submit → row inserted to correction_iterations

**Checkpoint**: Convergence detection matches spec example exactly; budget-exceeded and escalation paths work

---

## Phase 8: US6 — Budget Event Streaming (Priority: P2)

**Goal**: `StreamBudgetEvents` RPC pushes threshold events to multiple concurrent subscribers within 100ms of threshold crossing

**Independent Test**:
```bash
# Open 2 subscribers; trigger decrements crossing 80% and 90% → both subscribers receive both events in order
go test ./internal/budget_tracker/... -run TestFanOutRegistry -v
```

- [X] T043 [US6] Complete `services/reasoning-engine/internal/budget_tracker/events.go` — ensure fan-out registry publishes to all subscriber channels for a budget key; after each successful `Decrement`, check all 4 dimensions (tokens, rounds, cost, time elapsed since start_time) for threshold crossings; emit `BudgetEvent` with correct event_type, dimension, current_value, max_value; also emit EXCEEDED event type when `Decrement` returns error; ensure threshold events are not re-emitted if threshold already crossed for that dimension (track emitted thresholds per budget key in a small in-memory map behind the same `sync.RWMutex`)
- [X] T044 [US6] Implement `StreamBudgetEvents` in `services/reasoning-engine/api/grpc/v1/handler.go` — call `EventRegistry.Subscribe` for `{execID}:{stepID}`; forward events from channel to gRPC server stream; on context cancellation call `Unsubscribe`; if budget not found (registry has no key) return `codes.NotFound`; when budget COMPLETED or EXCEEDED event received, send final event then close stream via `return nil`
- [X] T045 [US6] Write unit tests in `services/reasoning-engine/internal/budget_tracker/events_test.go` — (1) single subscriber: decrement to 80% → THRESHOLD_80 event received; continue to 90% → THRESHOLD_90 received; (2) two concurrent subscribers: one decrement crossing 90% → both channels receive event; (3) subscriber connects after threshold already crossed: no replay of past events (only future events delivered); (4) budget closes: all subscriber channels closed; (5) THRESHOLD_80 not re-emitted on second decrement that is still above 80%

**Checkpoint**: Fan-out event delivery confirmed for multiple subscribers; threshold events fire within 100ms (verified in integration test with `-count=5`)

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Containerization, Helm chart, health check wiring, lint config, coverage validation

- [ ] T046 Write `services/reasoning-engine/Dockerfile` — multi-stage: Stage 1 `FROM golang:1.22-alpine AS builder` copies source, runs `go mod download` then `CGO_ENABLED=0 GOOS=linux go build -o /reasoning-engine ./cmd/reasoning-engine/`; Stage 2 `FROM gcr.io/distroless/static:nonroot` copies binary only; `EXPOSE 50052`; `USER nonroot:nonroot`; verify `docker images` shows size < 50MB
- [X] T047 [P] Write Helm chart at `deploy/helm/reasoning-engine/Chart.yaml` (name: reasoning-engine, version: 0.1.0, appVersion: 0.1.0), `values.yaml` (image, replicaCount: 2, resources: limits cpu=500m mem=256Mi, env vars from ConfigMap/Secret), `templates/deployment.yaml` (with `livenessProbe` and `readinessProbe` on gRPC health endpoint via `grpc-health-probe`), `templates/service.yaml` (ClusterIP, port 50052), `templates/configmap.yaml` (non-secret env vars), `templates/hpa.yaml` (min=2, max=10, targetCPU=70%)
- [X] T048 [P] Write `.golangci.yml` at `services/reasoning-engine/.golangci.yml` — enable: `errcheck`, `govet`, `staticcheck`, `unused`, `gosec`, `gocyclo` (max 15), `dupl`; run `make lint` and fix all warnings
- [X] T049 Run `go test ./... -coverprofile=coverage.out` in `services/reasoning-engine/`, open coverage report — verify ≥ 95% coverage; add missing unit tests for any uncovered branches in `mode_selector`, `budget_tracker`, `correction_loop`, `tot_manager` until threshold is met

---

## Dependencies

```
Phase 1 (Setup)
  └── Phase 2 (Foundational)
        ├── Phase 3 (US1 — Mode Selection)      [unblocked after Phase 2]
        ├── Phase 4 (US2 — Budget Tracking)     [unblocked after Phase 2]
        ├── Phase 5 (US3 — CoT Trace)           [unblocked after Phase 2 + Phase 4 for budget check]
        ├── Phase 6 (US4 — ToT Branches)        [unblocked after Phase 2 + Phase 4 for branch budget]
        ├── Phase 7 (US5 — Self-Correction)     [unblocked after Phase 2 + Phase 4 for Lua scripts]
        └── Phase 8 (US6 — Budget Events)       [unblocked after Phase 4 (EventRegistry)]
              └── Phase 9 (Polish)              [after all user stories complete]
```

**Parallel opportunities**:
- After Phase 2: US1 (T019–T022), US2 (T023–T027) can run in parallel
- After Phase 4 complete: US3 (T028–T032), US4 (T033–T037), US5 (T038–T042), US6 (T043–T045) can run in parallel
- T046, T047, T048 can run in parallel within Phase 9

---

## Implementation Strategy

**MVP** (deliver working service): Phases 1–5 = US1 + US2 + US3 (mode selection, budget tracking, CoT traces)
- Satisfies all 3 P1 user stories
- Enables runtime to call SelectReasoningMode, allocate budgets, and stream trace events
- Verifiable with grpcurl commands from quickstart.md

**Full delivery**: Add Phases 6–9 = US4 + US5 + US6 + Polish (ToT branches, self-correction, streaming events, Docker < 50MB, ≥ 95% coverage)

---

## Summary

| Phase | Tasks | User Story | Priority |
|-------|-------|------------|----------|
| 1 — Setup | T001–T006 | — | Blocker |
| 2 — Foundational | T007–T018 | — | Blocker |
| 3 — Mode Selection | T019–T022 | US1 | P1 |
| 4 — Budget Tracking | T023–T027 | US2 | P1 |
| 5 — CoT Trace | T028–T032 | US3 | P1 |
| 6 — ToT Branches | T033–T037 | US4 | P2 |
| 7 — Self-Correction | T038–T042 | US5 | P2 |
| 8 — Budget Events | T043–T045 | US6 | P2 |
| 9 — Polish | T046–T049 | — | Final |

**Total**: 49 tasks (T001–T049)
