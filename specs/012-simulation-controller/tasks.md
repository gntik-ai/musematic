---
description: "Task list for Simulation Controller implementation"
---

# Tasks: Simulation Controller

**Input**: Design documents from `/specs/012-simulation-controller/`  
**Branch**: `012-simulation-controller`  
**Service**: `services/simulation-controller/`

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no shared dependencies)
- **[Story]**: User story this task belongs to (US1–US5)
- Exact file paths included in every description

---

## Phase 1: Setup (Project Initialization)

**Purpose**: Go module, directory structure, proto stub generation, Makefile

- [X] T001 Initialize Go module at `services/simulation-controller/go.mod` with module path `github.com/musematic/simulation-controller` and Go 1.22 directive
- [X] T002 Add all dependencies to `services/simulation-controller/go.mod`: `google.golang.org/grpc v1.67+`, `google.golang.org/protobuf v1.34+`, `k8s.io/client-go v0.31+`, `k8s.io/api v0.31+`, `k8s.io/apimachinery v0.31+`, `github.com/jackc/pgx/v5`, `github.com/confluentinc/confluent-kafka-go/v2`, `github.com/aws/aws-sdk-go-v2`, `go.opentelemetry.io/otel v1.29+`, `github.com/stretchr/testify v1.9`
- [X] T003 [P] Create full directory skeleton: `services/simulation-controller/{cmd/simulation-controller,api/grpc/v1,internal/{sim_manager,artifact_collector,ate_runner,event_streamer},pkg/{metrics,persistence},proto,migrations}` with `.gitkeep` in each empty directory
- [X] T004 [P] Write protobuf definition to `services/simulation-controller/proto/simulation_controller.proto` with all 6 RPCs, all message types (SimulationConfig, SimulationHandle, SimulationStatus, SimulationEvent, ArtifactRef, ATEScenario, ATEHandle, etc.) per `specs/012-simulation-controller/contracts/grpc-service.md`
- [X] T005 Write `services/simulation-controller/Makefile` with targets: `proto` (runs `protoc` generating into `api/grpc/v1/`), `build` (`go build ./cmd/simulation-controller/...`), `docker` (multi-stage build), `test` (`go test ./...`), `test-integration` (`go test -tags=integration ./...`), `lint` (`golangci-lint run`)
- [X] T006 Run `make proto` to generate Go stubs — verify `simulation_controller_grpc.pb.go` and `simulation_controller.pb.go` are created in `services/simulation-controller/api/grpc/v1/`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Persistence adapters, gRPC server wiring, NetworkPolicy enforcement — required by ALL user stories

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T007 [P] Write `services/simulation-controller/pkg/persistence/postgres.go` — `NewPostgresPool(dsn string) *pgxpool.Pool` using `pgx/v5`; pool config: max 20 conns, min 2 conns; connection health check on startup
- [X] T008 [P] Write `services/simulation-controller/pkg/persistence/kafka.go` — `NewKafkaProducer(brokers string) *kafka.Producer` using `confluent-kafka-go/v2`; `Produce(topic, key string, value []byte) error` with delivery report goroutine; topic=`simulation.events`
- [X] T009 [P] Write `services/simulation-controller/pkg/persistence/minio.go` — `NewMinIOClient(endpoint, bucket string) *MinIOClient` using `aws-sdk-go-v2`; `Upload(ctx, key string, data []byte, metadata map[string]string) error`; `PresignGetURL(key string) string`; bucket always=`simulation-artifacts`; path-style addressing
- [X] T010 Write `services/simulation-controller/pkg/metrics/metrics.go` — define all Prometheus instruments: `simulation_creations_total` (counter), `simulation_terminations_total` (counter, labels: reason), `simulation_duration_seconds` (histogram), `simulation_status_current` (gauge, labels: status), `artifacts_collected_total` (counter), `artifacts_bytes_total` (counter), `ate_sessions_total` (counter), `ate_scenarios_total` (counter, labels: outcome)
- [X] T011 Write `services/simulation-controller/api/grpc/v1/interceptors.go` — UnaryInterceptor and StreamInterceptor chain: (1) OTel trace propagation via `go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc`, (2) panic recovery (log + return `codes.Internal`), (3) request logging via `log/slog` with simulation_id field extraction
- [X] T012 Write `services/simulation-controller/api/grpc/v1/handler.go` skeleton — `Handler` struct holding references to all internal package interfaces (SimManager, ArtifactCollector, ATERunner, EventStreamer); implement `mustEmbedUnimplementedSimulationControlServiceServer()`; all 6 methods stubbed returning `codes.Unimplemented`
- [X] T013 Write PostgreSQL migration at `services/simulation-controller/migrations/001_initial_schema.sql` — create all 4 tables with exact DDL from `specs/012-simulation-controller/data-model.md`: `simulations`, `simulation_artifacts`, `ate_sessions`, `ate_results` including all indexes
- [X] T014 Write `services/simulation-controller/cmd/simulation-controller/main.go` — read env vars (GRPC_PORT=50055, POSTGRES_DSN, KAFKA_BROKERS, MINIO_ENDPOINT, SIMULATION_BUCKET, SIMULATION_NAMESPACE, ORPHAN_SCAN_INTERVAL_SECONDS, DEFAULT_MAX_DURATION_SECONDS, KUBECONFIG), initialize Kubernetes client (`client-go` in-cluster or from KUBECONFIG), initialize persistence clients, build `Handler`, register gRPC health service, register `SimulationControlService`, start listener, handle `SIGTERM`/`SIGINT` for graceful shutdown
- [X] T015 Write `services/simulation-controller/internal/sim_manager/state.go` — `SimulationState` struct (simulation_id, status, pod_name, started_at, resource_usage), `StateRegistry` wrapping `sync.Map`; `Register()`, `Get()`, `UpdateStatus()`, `Delete()`, `List()` methods; `RebuildFromPodList(ctx, client kubernetes.Interface, namespace string) error` — list pods with `simulation=true` label, populate registry from pod metadata on startup

**Checkpoint**: `go build ./...` succeeds; server starts and health check returns SERVING

---

## Phase 3: US1 — Simulation Environment Creation (Priority: P1) 🎯 MVP

**Goal**: `CreateSimulation` RPC provisions an isolated pod in `platform-simulation` with network controls, simulation flag, and separate resource accounting

**Independent Test**:
```bash
SIM_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
grpcurl -plaintext -d "{\"simulation_id\":\"$SIM_ID\",\"config\":{\"agent_image\":\"busybox:latest\"}}" \
  localhost:50055 musematic.simulation.v1.SimulationControlService/CreateSimulation
kubectl get pod "sim-$SIM_ID" -n platform-simulation
# Expect: pod exists, label simulation=true, env SIMULATION=true
```

- [X] T016 [US1] Write `services/simulation-controller/internal/sim_manager/network_policy.go` — `EnsureNetworkPolicy(ctx, client kubernetes.Interface, namespace string) error`: idempotent create of `simulation-deny-production-egress` NetworkPolicy in `platform-simulation` namespace using exact spec from `specs/012-simulation-controller/data-model.md` (deny all egress to production namespaces, allow `platform-data` on ports 9000+9092); called at server startup
- [X] T017 [US1] Write `services/simulation-controller/internal/sim_manager/pod.go` — `CreatePod(ctx, spec SimulationPodSpec) (*v1.Pod, error)`: build pod spec with name=`sim-{simulation_id}`, namespace=`platform-simulation`, labels=`{simulation:"true","simulation-id":id}`, env vars `SIMULATION=true SIMULATION_ID SIMULATION_BUCKET=simulation-artifacts SIMULATION_ARTIFACTS_PREFIX`, security context (runAsUser=65534, runAsNonRoot=true, allowPrivilegeEscalation=false, readOnlyRootFilesystem=true, drop ALL caps), 3 emptyDir volumes (/output 512Mi, /workspace 1Gi, /tmp 256Mi), `activeDeadlineSeconds` from config; use `client-go` `CoreV1().Pods(namespace).Create()`
- [X] T018 [US1] Write `services/simulation-controller/internal/event_streamer/fanout.go` — `FanoutRegistry` with `sync.RWMutex`-protected `map[string][]chan SimulationEvent`; `Subscribe(simulationID string) <-chan SimulationEvent`; `Unsubscribe(simulationID string, ch <-chan SimulationEvent)`; `Publish(simulationID string, event SimulationEvent)`; `Close(simulationID string)` — close and remove all subscriber channels
- [X] T019 [US1] Implement `CreateSimulation` in `services/simulation-controller/api/grpc/v1/handler.go` — validate request, insert `simulations` row with status=CREATING, call `SimManager.CreatePod()`, register in state map, publish CREATED event to fanout and Kafka, increment `simulation_creations_total`, return `SimulationHandle`
- [X] T020 [US1] Write unit tests in `services/simulation-controller/internal/sim_manager/pod_test.go` — verify pod spec: labels contain `simulation=true` and correct `simulation-id`, env vars include `SIMULATION=true` and `SIMULATION_BUCKET=simulation-artifacts`, security context has runAsUser=65534 and readOnlyRootFilesystem=true, all 3 emptyDir volumes present with correct size limits

**Checkpoint**: `CreateSimulation` creates a correctly configured isolated pod; verified independently via grpcurl + `kubectl get pod`

---

## Phase 4: US2 — Simulation Monitoring and Termination (Priority: P1)

**Goal**: `GetSimulationStatus` and `TerminateSimulation` RPCs correctly manage simulation lifecycle with full cleanup and no orphaned resources

**Independent Test**:
```bash
# Create → query status → terminate → verify no orphaned pods
go test ./internal/sim_manager/... -run TestTerminationCleanup -v
kubectl get pods -n platform-simulation -l simulation=true  # expect: none
```

- [X] T021 [US2] Complete `services/simulation-controller/internal/sim_manager/pod.go` with `DeletePod(ctx, podName string) error` — `client-go` `CoreV1().Pods(namespace).Delete()` with `GracePeriodSeconds=10`; `GetPodPhase(ctx, podName string) (string, error)` — returns Kubernetes pod phase string
- [X] T022 [US2] Write `services/simulation-controller/internal/sim_manager/orphan_scanner.go` — `OrphanScanner` struct with `client-go` interface and state registry reference; `Run(ctx context.Context)` goroutine: tick every `ORPHAN_SCAN_INTERVAL_SECONDS`, list all pods in `platform-simulation` with label `simulation=true`, for each pod check if `simulation-id` label value exists in state registry, if not found call `DeletePod()` and log orphan cleanup
- [X] T023 [US2] Implement `GetSimulationStatus` in `services/simulation-controller/api/grpc/v1/handler.go` — read from `StateRegistry.Get()` (fast path, no DB), compute `elapsed_seconds = now - started_at`, return full `SimulationStatus` proto; if not found return `codes.NOT_FOUND`
- [X] T024 [US2] Implement `TerminateSimulation` in `services/simulation-controller/api/grpc/v1/handler.go` — call `SimManager.DeletePod()`, `UPDATE simulations SET status='TERMINATED', terminated_at=NOW() WHERE simulation_id=...` via pgx, `StateRegistry.UpdateStatus(TERMINATED)`, publish TERMINATED event to fanout (which closes subscriber streams) and Kafka, delete ATE ConfigMap if present (check for `ate-{session_id}` in namespace), increment `simulation_terminations_total` with reason label
- [X] T025 [US2] Write unit tests in `services/simulation-controller/internal/sim_manager/state_test.go` — (1) GetSimulationStatus reads from in-memory map without DB call; (2) termination sequence: pod deleted → DB updated → TERMINATED event published → fanout closed; (3) terminating simulation A does not affect simulation B's state; (4) orphan scanner finds pod not in registry → deletes it

**Checkpoint**: Status query, termination, and cleanup work; zero orphaned pods after termination confirmed

---

## Phase 5: US3 — Simulation Artifact Collection (Priority: P2)

**Goal**: `CollectSimulationArtifacts` RPC collects outputs via exec, uploads to `simulation-artifacts` bucket with `simulation=true` tags, inserts metadata rows

**Independent Test**:
```bash
go test ./internal/artifact_collector/... -run TestArtifactTagging -v
# Expect: MinIO object has x-amz-meta-simulation=true, x-amz-meta-simulation-id set, NOT in production bucket
```

- [X] T026 [US3] Write `services/simulation-controller/internal/artifact_collector/collector.go` — `ArtifactCollector` interface: `Collect(ctx context.Context, simulationID, podName string, paths []string) ([]ArtifactRef, bool, error)` — returns artifact refs, partial flag, error
- [X] T027 [US3] Write `services/simulation-controller/internal/artifact_collector/exec.go` — implement `ArtifactCollector`: for each path, use `k8s.io/client-go/tools/remotecommand` (SPDY executor) to exec `tar -czf - {path}` inside pod container; stream stdout to MinIO `Upload()` at key `{simulation_id}/{basename}.tar.gz` with metadata `{"x-amz-meta-simulation":"true","x-amz-meta-simulation-id":simulation_id,"x-amz-meta-path":path}`; insert row to `simulation_artifacts` via pgx; if pod not found set `partial=true` and continue; return all collected `ArtifactRef` values
- [X] T028 [US3] Implement `CollectSimulationArtifacts` in `services/simulation-controller/api/grpc/v1/handler.go` — default paths to `["/output", "/workspace"]` if empty, call `ArtifactCollector.Collect()`, publish ARTIFACT_COLLECTED event to fanout and Kafka, increment `artifacts_collected_total` and `artifacts_bytes_total`, return `ArtifactCollectionResult`
- [X] T029 [US3] Write unit tests in `services/simulation-controller/internal/artifact_collector/exec_test.go` — mock remotecommand executor and MinIO client: (1) MinIO metadata contains `x-amz-meta-simulation=true` and correct `simulation-id`; (2) object key format is `{simulation_id}/{path_basename}.tar.gz`; (3) `simulation_artifacts` row inserted with correct fields; (4) `partial=true` when pod exec returns "container not found" error

**Checkpoint**: Artifact collection works; MinIO objects tagged with simulation metadata; production bucket untouched

---

## Phase 6: US4 — Real-Time Simulation Event Streaming (Priority: P2)

**Goal**: `StreamSimulationEvents` RPC delivers real-time events to subscribers; all events carry `simulation=true`; events do NOT appear on production Kafka topics

**Independent Test**:
```bash
go test ./internal/event_streamer/... -run TestEventSimulationFlag -v
# Expect: all events have simulation=true, Kafka producer called with topic=simulation.events only
```

- [X] T030 [US4] Write `services/simulation-controller/internal/event_streamer/pod_watch.go` — `PodWatcher` that calls `client-go` `CoreV1().Pods(namespace).Watch()` with `ListOptions{LabelSelector:"simulation-id={id}"}`: convert `watch.EventType` → `SimulationEvent` (ADDED→POD_CREATED, MODIFIED→inspect pod phase and containerStatuses for POD_RUNNING/POD_COMPLETED/POD_FAILED/POD_OOM via `lastState.terminated.reason=OOMKilled`, DELETED→TERMINATED); always set `simulation=true` on every event; publish each event to fanout registry and Kafka producer
- [X] T031 [US4] Write `services/simulation-controller/internal/event_streamer/streamer.go` — `EventStreamer` interface: `Stream(ctx, simulationID string, send func(SimulationEvent) error) error`; implement: subscribe to fanout, start pod Watch goroutine, forward all events to `send` callback, return when context cancelled or terminal event received (POD_COMPLETED, POD_FAILED, TERMINATED); unsubscribe from fanout on exit
- [X] T032 [US4] Implement `StreamSimulationEvents` in `services/simulation-controller/api/grpc/v1/handler.go` — call `EventStreamer.Stream()` with `send` function that calls `stream.Send(event)`; on terminal event: send it, then return `nil` to close stream; if simulation not found return `codes.NOT_FOUND`
- [X] T033 [US4] Write unit tests in `services/simulation-controller/internal/event_streamer/streamer_test.go` — (1) every event has `simulation=true`; (2) Kafka `Produce()` called only with topic=`simulation.events`; (3) stream closes after TERMINATED event; (4) fanout delivers same events to two concurrent subscribers; (5) subscriber disconnects do not affect other subscribers

**Checkpoint**: Event streaming delivers real-time updates with simulation flag; stream closes cleanly on terminal event

---

## Phase 7: US5 — Accredited Testing Environment (Priority: P2)

**Goal**: `CreateAccreditedTestEnv` provisions ATE pod with ConfigMap-injected scenarios; ATE results aggregated into structured JSON report

**Independent Test**:
```bash
go test ./internal/ate_runner/... -run TestATEReportSchema -v
# Expect: report JSON has session_id, agent_id, scenarios array with per-scenario pass/fail/quality/latency/cost/safety
```

- [X] T034 [US5] Write `services/simulation-controller/internal/ate_runner/configmap.go` — `CreateATEConfigMap(ctx, client kubernetes.Interface, sessionID string, scenarios []ATEScenario, datasetRefs []string) (*v1.ConfigMap, error)`: build `v1.ConfigMap` with name=`ate-{sessionID}`, namespace=`platform-simulation`, data=`{"scenarios.json": JSON(scenarios), "dataset_refs.json": JSON(datasetRefs)}`; create via `client-go`; `DeleteATEConfigMap(ctx, client, sessionID string) error` for cleanup
- [X] T035 [US5] Write `services/simulation-controller/internal/ate_runner/runner.go` — `ATERunner` interface: `Start(ctx, req ATERequest) (*ATEHandle, error)`; `ATERequest` wraps session_id, agent_id, simulation config, scenarios, dataset_refs
- [X] T036 [US5] Write `services/simulation-controller/internal/ate_runner/results.go` — `ResultsAggregator` that watches the fanout registry for `ATE_SCENARIO_COMPLETED` events on a given simulation_id; for each event, parse per-scenario result from event metadata (`scenario_id`, `passed`, `quality_score`, `latency_ms`, `cost`, `safety_compliant`); insert row to `ate_results` via pgx; after all scenarios complete (count == len(scenarios)): generate JSON report `{session_id, agent_id, scenarios:[...], summary:{total, passed, failed}}`; upload report to MinIO at `{simulation_id}/ate-report.json` with simulation metadata; `UPDATE ate_sessions SET report_object_key=..., completed_at=NOW()` via pgx; increment `ate_scenarios_total` per outcome
- [X] T037 [US5] Implement `CreateAccreditedTestEnv` in `services/simulation-controller/api/grpc/v1/handler.go` — validate request (require ≥1 scenario, non-empty agent_id and agent_image); generate underlying simulation_id; call `ATERunner.Start()`: create ConfigMap, create simulation pod with additional env vars `ATE_SESSION_ID ATE_SCENARIOS_PATH=/ate/scenarios.json` and volumeMount `ate-config` ConfigMap at `/ate/` read-only; insert rows to both `simulations` and `ate_sessions` tables; start `ResultsAggregator` goroutine; return `ATEHandle` with PROVISIONING status; increment `ate_sessions_total`
- [X] T038 [US5] Write unit tests in `services/simulation-controller/internal/ate_runner/results_test.go` — (1) ConfigMap data.scenarios_json is valid JSON matching input scenarios; (2) ATE pod spec includes `/ate` volumeMount from ConfigMap; (3) 2 ATE_SCENARIO_COMPLETED events → 2 `ate_results` rows inserted; (4) report JSON has correct schema (session_id, agent_id, scenarios array, summary.passed + summary.failed = summary.total); (5) report uploaded to MinIO at `{simulation_id}/ate-report.json` with simulation metadata tags

**Checkpoint**: ATE provisions isolated pod with scenarios; structured report generated on completion; all isolation inherited from simulation creation

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Containerization, Helm chart, lint config, RBAC, network isolation integration test, coverage validation

- [ ] T039 Write `services/simulation-controller/Dockerfile` — Stage 1: `FROM golang:1.22-alpine AS builder` — copy source, `go mod download`, `CGO_ENABLED=0 GOOS=linux go build -o /simulation-controller ./cmd/simulation-controller/`; Stage 2: `FROM gcr.io/distroless/static:nonroot` — copy binary only, `EXPOSE 50055`, `USER nonroot:nonroot`; verify `docker images musematic/simulation-controller:latest --format "{{.Size}}"` < 50MB
- [X] T040 [P] Write Helm chart at `deploy/helm/simulation-controller/Chart.yaml` (name: simulation-controller, version: 0.1.0), `values.yaml` (image, replicaCount: 1, resources limits cpu=500m mem=256Mi, env from ConfigMap/Secret), `templates/deployment.yaml` (with `livenessProbe` and `readinessProbe` via `grpc-health-probe`), `templates/service.yaml` (ClusterIP port 50055), `templates/serviceaccount.yaml`, `templates/clusterrole.yaml` (verbs: get/list/watch/create/delete on pods, configmaps, networkpolicies scoped to `platform-simulation` namespace), `templates/clusterrolebinding.yaml`, `templates/configmap.yaml`
- [ ] T041 [P] Write `services/simulation-controller/.golangci.yml` — enable: `errcheck`, `govet`, `staticcheck`, `unused`, `gosec`, `gocyclo (max 15)`, `dupl`; run `make lint` and fix all warnings
- [X] T042 Write integration test in `services/simulation-controller/internal/sim_manager/network_isolation_test.go` (build tag `integration`) — create a simulation pod that runs `wget -T5 http://musematic-api.platform-control:8000/health -O /dev/null`; wait for pod to complete; verify pod exited with non-zero code (wget timed out — network policy blocked egress to `platform-control`); requires live Kubernetes cluster with NetworkPolicy enforced
- [ ] T043 Run `go test ./... -coverprofile=coverage.out` in `services/simulation-controller/`, open coverage report — verify ≥ 95% coverage; add missing unit tests for any uncovered branches in `sim_manager`, `artifact_collector`, `ate_runner`, `event_streamer` until threshold is met

---

## Dependencies

```
Phase 1 (Setup)
  └── Phase 2 (Foundational)
        ├── Phase 3 (US1 — Simulation Creation)    [unblocked after Phase 2]
        └── Phase 4 (US2 — Monitoring/Termination) [unblocked after Phase 2]
              ├── Phase 5 (US3 — Artifact Collection)  [unblocked after Phase 3+4]
              ├── Phase 6 (US4 — Event Streaming)       [unblocked after Phase 3+4]
              └── Phase 7 (US5 — ATE)                   [unblocked after Phase 3+4+5]
                    └── Phase 8 (Polish)               [after all user stories complete]
```

**Parallel opportunities**:
- T007, T008, T009, T010 can all run in parallel (different files)
- After Phase 2: US1 (T016–T020) and foundational persistence work are independent per file
- After Phase 3+4: US3 (T026–T029), US4 (T030–T033), US5 (T034–T038) can run in parallel
- T039, T040, T041 can run in parallel within Phase 8

---

## Implementation Strategy

**MVP** (deliver working P1 service): Phases 1–4 = Setup + Foundational + US1 + US2
- Satisfies both P1 user stories: simulation creation and lifecycle management
- Fully isolated pods in `platform-simulation` with NetworkPolicy enforcement
- Status query and termination with full cleanup
- Verifiable with grpcurl commands from `quickstart.md`

**Full delivery**: Add Phases 5–8 = US3 + US4 + US5 + Polish (artifact collection, event streaming, ATE, Docker < 50MB, ≥ 95% coverage)

---

## Summary

| Phase | Tasks | User Story | Priority |
|-------|-------|------------|----------|
| 1 — Setup | T001–T006 | — | Blocker |
| 2 — Foundational | T007–T015 | — | Blocker |
| 3 — Simulation Creation | T016–T020 | US1 | P1 |
| 4 — Monitoring & Termination | T021–T025 | US2 | P1 |
| 5 — Artifact Collection | T026–T029 | US3 | P2 |
| 6 — Event Streaming | T030–T033 | US4 | P2 |
| 7 — ATE | T034–T038 | US5 | P2 |
| 8 — Polish | T039–T043 | — | Final |

**Total**: 43 tasks (T001–T043)
