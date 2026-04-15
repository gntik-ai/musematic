# Tasks: Runtime Controller

**Input**: Design documents from `specs/009-runtime-controller/`  
**Branch**: `009-runtime-controller`  
**Prerequisites**: plan.md ✅ spec.md ✅ research.md ✅ data-model.md ✅ contracts/ ✅ quickstart.md ✅

**Organization**: Tasks grouped by user story (8 stories: US1–US3 P1, US4–US8 P2). Unit tests included per spec SC-012 (≥95% coverage required).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to
- Exact file paths included in every description

---

## Phase 1: Setup (Project Initialization)

**Purpose**: Go module, proto source, and directory scaffold before any story work.

- [X] T001 Initialize Go module `services/runtime-controller/go.mod` with all dependencies: `google.golang.org/grpc v1.67+`, `k8s.io/client-go v0.31+`, `github.com/jackc/pgx/v5`, `github.com/redis/go-redis/v9`, `github.com/confluentinc/confluent-kafka-go/v2`, `github.com/aws/aws-sdk-go-v2`, `go.opentelemetry.io/otel v1.29+`, `github.com/testcontainers/testcontainers-go`, `github.com/stretchr/testify v1.9`
- [X] T002 [P] Write protobuf definition `services/runtime-controller/proto/runtime_controller.proto` — all enums (RuntimeState, RuntimeEventType), all messages (CorrelationContext, ResourceLimits, RuntimeContract, RuntimeInfo, RuntimeEvent, ArtifactEntry, all 14 request/response types), and 7 RPC declarations per data-model.md §3
- [X] T003 [P] Create directory skeleton: `services/runtime-controller/{cmd/runtime-controller,internal/{launcher,reconciler,warmpool,heartbeat,events,state,artifacts},api/grpc/v1,pkg/{k8s,config,health},proto,testdata,deploy/helm/runtime-controller/templates}` with `.gitkeep` placeholder files

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Config, state store, Kubernetes client, gRPC stubs, server bootstrap, and health — ALL user stories depend on these.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Implement `services/runtime-controller/pkg/config/config.go` — Config struct with all fields from data-model.md §5: `GRPCPort`, `HTTPPort`, `PostgresDSN`, `RedisAddr`, `KafkaBrokers`, `MinIOEndpoint`, `MinioBucket`, `K8sNamespace`, `ReconcileInterval`, `HeartbeatTimeout`, `HeartbeatCheckInterval`, `WarmPoolIdleTimeout`, `WarmPoolReplenishInterval`, `StopGracePeriod`, `AgentPackagePresignTTL`, `K8sDryRun`; load from environment variables with defaults
- [X] T005 Implement SQL migration runner and state store in `services/runtime-controller/internal/state/`: `migrations.go` (golang-migrate embedded runner for 4 table schemas from data-model.md §2), `store.go` (pgxpool setup with `pgx/v5`), `queries.go` (typed functions: InsertRuntime, GetRuntimeByExecutionID, UpdateRuntimeState, ListActiveRuntimes, InsertWarmPoolPod, GetReadyWarmPod, UpdateWarmPoolPodStatus, InsertTaskPlanRecord, InsertRuntimeEvent, GetRuntimeEventsSince)
- [X] T006 [P] Implement Kubernetes client wrappers in `services/runtime-controller/pkg/k8s/`: `client.go` (in-cluster config with `rest.InClusterConfig()`, fallback to `clientcmd.BuildConfigFromFlags` for local dev), `pods.go` (CreatePod, GetPod, ListPodsByLabel, DeletePod, GetPodLogs, ExecInPod — all wrapping `client-go` CoreV1 interface)
- [X] T007 [P] Generate gRPC Go stubs from proto into `services/runtime-controller/api/grpc/v1/` with `protoc --go_out --go-grpc_out`; document `Makefile` target `make proto`; implement `services/runtime-controller/api/grpc/server.go` skeleton — `RuntimeControlServiceServer` struct embedding `UnimplementedRuntimeControlServiceServer`, stub method bodies returning `codes.Unimplemented`, gRPC unary + stream interceptors for OTel trace context and slog request logging
- [X] T008 [P] Implement health handlers `services/runtime-controller/pkg/health/handler.go` — `LivezHandler` (always 200), `ReadyzHandler` (checks PostgreSQL ping, Redis ping, Kafka metadata request, Kubernetes API server `/healthz`); expose as HTTP handlers
- [X] T009 Implement `services/runtime-controller/cmd/runtime-controller/main.go` — load config; init pgxpool (run migrations), Redis client, Kafka producer, k8s clientset, MinIO S3 client, OTel SDK; start HTTP server (port 8080: /healthz, /readyz, /metrics); start gRPC server (port 50051) with registered `RuntimeControlServiceServer`; manage all goroutines via `context.WithCancel`; handle SIGTERM/SIGINT for graceful shutdown (drain gRPC, stop goroutines, close connections)

**Checkpoint**: Server starts cleanly, /readyz passes all dependency checks, gRPC server listening. All RPCs return `Unimplemented`.

---

## Phase 3: User Story 1 — Launch and Manage Agent Runtime Lifecycle (Priority: P1) 🎯 MVP

**Goal**: `LaunchRuntime`, `GetRuntime`, `PauseRuntime`, `ResumeRuntime`, `StopRuntime` RPCs fully implemented — cold-start pod launch under 10 seconds, state persisted to PostgreSQL, lifecycle events emitted to Kafka.

**Independent Test**: Launch a runtime with a valid RuntimeContract, verify pod created in `platform-execution` namespace with correct labels and volumes, verify state=RUNNING in DB, stop it with 5s grace period, verify state=STOPPED and pod deleted.

- [X] T010 [US1] Implement `services/runtime-controller/internal/launcher/podspec.go` — `BuildPodSpec(contract RuntimeContract, presignedURL string) *v1.Pod`: set pod name as `runtime-{execution_id[:8]}`, labels (execution_id, workspace_id, agent_fqn sanitized, managed_by=runtime-controller), init container (curl presigned URL → extract to emptyDir `/agent-package`), main container with `contract.ResourceLimits` + env vars from `contract.EnvVars` + `EXECUTION_ID` + `WORKSPACE_ID` + `SANITIZER_PATTERNS_URL`, emptyDir volume (read-only mount at `/agent`), projected secrets volume from data-model.md §6 pod spec template
- [X] T011 [P] [US1] Implement `services/runtime-controller/internal/launcher/secrets.go` — `ResolveSecrets(ctx, k8sClient, namespace string, secretRefs []string) ([]v1.VolumeProjection, []v1.EnvVar, error)`: for each secret name in secretRefs, call `k8sClient.CoreV1().Secrets(namespace).Get(name)`, build projected volume source with all keys mapped to paths, build `SECRETS_REF_{KEY_UPPER}=/run/secrets/{key}` env vars (path pointers only); return hard error if any secret not found
- [X] T012 [US1] Implement `services/runtime-controller/internal/launcher/launcher.go` — `Launcher.Launch(ctx, contract) (RuntimeInfo, error)`: (1) check execution_id uniqueness in DB → return ALREADY_EXISTS if duplicate; (2) call `InsertRuntime` state=PENDING; (3) persist TaskPlanRecord if `contract.TaskPlanJSON` non-empty; (4) generate MinIO presigned URL for agent package; (5) resolve secrets; (6) build pod spec; (7) create pod via k8s client; (8) update runtime state to RUNNING; (9) emit `runtime.launched` Kafka event; return RuntimeInfo
- [X] T013 [US1] Implement `services/runtime-controller/internal/events/emitter.go` — `EventEmitter`: Kafka producer wrapping `confluent-kafka-go/v2`; `EmitLifecycle(event RuntimeEvent)` synchronous produce to `runtime.lifecycle`; `EmitDrift(event RuntimeEvent)` async produce to `monitor.alerts`; `services/runtime-controller/internal/events/envelope.go` — build canonical event envelope with CorrelationContext + event_type + payload + OTel trace_id
- [X] T014 [US1] Implement StopRuntime handler in `services/runtime-controller/api/grpc/server.go` — `StopRuntime(req)`: validate runtime in stoppable state; send SIGTERM via `ExecInPod`; poll pod status every 1s until terminated or `grace_period_seconds` elapsed; if timeout → `DeletePod` with grace=0 (force kill); update state to STOPPED or FORCE_STOPPED; emit lifecycle event; return `force_killed=true` if force-killed
- [X] T015 [US1] Implement PauseRuntime and ResumeRuntime handlers in `services/runtime-controller/api/grpc/server.go` — send SIGTSTP/SIGCONT via `ExecInPod`; update DB state to PAUSED/RUNNING; emit lifecycle events; if pod doesn't support pause signals, leave state RUNNING and return current state (no error)
- [X] T016 [US1] Implement GetRuntime handler in `services/runtime-controller/api/grpc/server.go` — call `state.GetRuntimeByExecutionID`, map to `RuntimeInfo` proto; return NOT_FOUND if execution_id unknown
- [X] T017 [US1] Unit tests `services/runtime-controller/internal/launcher/launcher_test.go` — table-driven tests with fake k8s client (`k8s.io/client-go/kubernetes/fake`): verify pod spec labels/volumes match contract; verify ALREADY_EXISTS on duplicate execution_id; verify FAILED_PRECONDITION when secret not found; verify state machine: PENDING→RUNNING on successful launch
- [X] T018 [P] [US1] Unit tests `services/runtime-controller/internal/launcher/podspec_test.go` and `secrets_test.go` — verify projected volume sources built correctly for multiple secrets; verify SECRETS_REF env vars contain paths not values; verify resource limits applied correctly to container spec

**Checkpoint**: All 5 lifecycle RPCs functional. Cold launch < 10s verified. US1 independently testable.

---

## Phase 4: User Story 2 — Controller Automatically Reconciles Runtime State Drift (Priority: P1)

**Goal**: Background goroutine (30s interval) that detects and corrects orphaned pods, missing pods, and state mismatches — all drift emitted to `monitor.alerts` Kafka topic.

**Independent Test**: Launch 5 runtimes, externally delete 2 pods, externally create 1 orphaned pod, wait ≤30s, verify: 2 runtimes marked FAILED(pod_disappeared), orphaned pod deleted, 3 drift events on monitor.alerts.

- [X] T019 [US2] Implement `services/runtime-controller/internal/reconciler/drift.go` — `DetectDrift(ctx, stateStore, k8sClient) DriftReport`: (1) list all active runtimes from DB (state IN pending,running,paused); (2) list all pods in `platform-execution` with label `managed_by=runtime-controller`; (3) classify: orphaned (pod with no matching execution_id in DB), missing (DB runtime with no matching pod), mismatch (DB state ≠ derived state from pod phase); return `DriftReport{Orphans, Missing, Mismatches}`
- [X] T020 [US2] Implement `services/runtime-controller/internal/reconciler/repair.go` — `ApplyRepairs(ctx, report DriftReport, stateStore, k8sClient, emitter)`: (1) for each orphan: DeletePod, emit drift event; (2) for each missing: UpdateRuntimeState(FAILED, "pod_disappeared"), emit drift event; (3) for each mismatch: UpdateRuntimeState(correct state), emit drift event; log each action with slog
- [X] T021 [US2] Implement `services/runtime-controller/internal/reconciler/reconciler.go` — `Reconciler.Run(ctx)`: ticker every `config.ReconcileInterval`; call DetectDrift + ApplyRepairs; record cycle duration as OTel metric `runtime_controller_reconciliation_cycle_duration_seconds`; handle context cancellation cleanly; wire `Reconciler.Run` as a goroutine in `main.go`
- [X] T022 [US2] Unit tests `services/runtime-controller/internal/reconciler/` — table-driven tests with fake k8s client and mock state store: test orphan detection (pod exists, no DB entry → orphan), missing detection (DB entry, no pod → missing), state mismatch (DB=running, pod phase=Failed → mismatch); verify correct repair actions applied; verify drift events emitted per classification

**Checkpoint**: Reconciliation loop running, drift events on monitor.alerts. US2 independently testable.

---

## Phase 5: User Story 3 — Execution Engine Receives Real-Time Runtime Events (Priority: P1)

**Goal**: `StreamRuntimeEvents` server-side streaming RPC delivering lifecycle events within 500ms; missed event replay from `runtime_events` table; fan-out to multiple concurrent subscribers.

**Independent Test**: Open two concurrent subscribers for the same execution_id, launch the runtime, stop it; verify both subscribers receive LAUNCHED and STOPPED events in order within 500ms.

- [X] T023 [US3] Implement `services/runtime-controller/internal/events/fanout.go` — `FanoutRegistry`: `sync.RWMutex`-protected `map[string][]chan *RuntimeEvent`; `Subscribe(executionID) (<-chan *RuntimeEvent, unsubscribe func())` — creates buffered channel (size 64), appends to map, returns channel + closure that removes it; `Publish(event *RuntimeEvent)` — acquires RLock, sends to all channels for execution_id (non-blocking with select+default to drop on full buffer), publishes to terminal-state set that triggers stream close
- [X] T024 [US3] Implement StreamRuntimeEvents RPC handler in `services/runtime-controller/api/grpc/server.go` — subscribe via `FanoutRegistry.Subscribe(req.ExecutionId)`; if `req.Since` set, query `runtime_events` table and send missed events first; then stream from subscription channel until context cancelled or terminal event (STOPPED, FORCE_STOPPED, FAILED) received → send final event and close stream; return NOT_FOUND if execution_id unknown
- [X] T025 [US3] Wire `FanoutRegistry.Publish` into all state transition points: in `launcher.go` after RUNNING transition, in `StopRuntime` handler after STOPPED/FORCE_STOPPED transition, in `reconciler/repair.go` after any state update, in heartbeat scanner after FAILED transition; every DB state change must call `fanout.Publish` with correct event type and new_state
- [X] T026 [US3] Unit tests `services/runtime-controller/internal/events/fanout_test.go` — verify multiple concurrent subscribers each receive published events; verify unsubscribe removes channel cleanly; verify non-blocking publish drops events on full buffer without blocking; verify subscriber channel closes on terminal state event

**Checkpoint**: StreamRuntimeEvents delivers events within 500ms, multiple subscribers supported, missed events replayed. US3 independently testable.

---

## Phase 6: User Story 4 — Warm Pool Enables Sub-2-Second Agent Launches (Priority: P2)

**Goal**: WarmPoolManager with in-memory dispatch, PostgreSQL inventory, background replenisher and idle pod recycler — warm launch completes in under 2 seconds.

**Independent Test**: Pre-warm 3 pods for workspace=ws-test, agent_type=test-agent; request 4 launches; verify first 3 complete in <2s with `warm_start=true`; 4th uses cold start.

- [X] T027 [US4] Implement `services/runtime-controller/internal/warmpool/manager.go` — `WarmPoolManager`: in-memory `sync.Map` keyed `{workspace_id}/{agent_type}` → `[]string` (pod names); `LoadFromDB(ctx, store)` populates map from `warm_pool_pods` WHERE status=ready on startup; `Dispatch(workspace_id, agent_type string) (podName string, ok bool)` — atomically pops first available pod name from slice, updates DB status to dispatched
- [X] T028 [P] [US4] Implement `services/runtime-controller/internal/warmpool/replenisher.go` — `Replenisher.Run(ctx)`: ticker every `config.WarmPoolReplenishInterval`; query DB for warm pool target sizes per (workspace_id, agent_type); compare against in-memory available count; for each shortfall, build a generic warm pod spec (no execution_id, no secrets, minimal env), create pod via k8s client, insert into `warm_pool_pods` table with status=warming; poll pod readiness, update to status=ready when Running; wire into main.go
- [X] T029 [P] [US4] Implement `services/runtime-controller/internal/warmpool/idle_scanner.go` — `IdleScanner.Run(ctx)`: ticker every `config.WarmPoolReplenishInterval`; query `warm_pool_pods` WHERE status=ready AND idle_since < NOW()-config.WarmPoolIdleTimeout; for each idle pod: DeletePod, update DB status to recycling, remove from in-memory map; wire into main.go
- [X] T030 [US4] Integrate warm pool dispatch into `services/runtime-controller/internal/launcher/launcher.go` — before building full pod spec, call `WarmPoolManager.Dispatch(workspace_id, agent_type)`; if warm pod found: skip pod creation, inject runtime-specific env vars via pod Update (patch), update pod labels, set `warm_start=true` in LaunchRuntimeResponse; update `warm_pool_pods.dispatched_to = runtime_id`

**Checkpoint**: Warm launch < 2s with warm_start=true. Cold launch fallback when pool empty. US4 independently testable.

---

## Phase 7: User Story 5 — Heartbeat Detection and Dead-Worker Handling (Priority: P2)

**Goal**: Redis TTL heartbeat tracking — heartbeat receipt resets TTL; background scanner detects expired keys and marks runtimes as FAILED(heartbeat_timeout) within `HEARTBEAT_TIMEOUT` ± 10s.

**Independent Test**: Launch a runtime, verify heartbeat key set in Redis. Set HEARTBEAT_TIMEOUT=5s, block heartbeats for 5s, verify runtime marked FAILED(heartbeat_timeout) within 15s.

- [X] T031 [US5] Implement `services/runtime-controller/internal/heartbeat/tracker.go` — `HeartbeatTracker`: Redis client wrapper; `ReceiveHeartbeat(ctx, runtimeID string) error` calls `SET heartbeat:{runtimeID} {timestamp} EX {config.HeartbeatTimeout.Seconds()}`; `UpdateLastHeartbeat(ctx, runtimeID string) error` also updates `last_heartbeat_at` in PostgreSQL runtimes table; expose `ReceiveHeartbeat` as an internal gRPC method (add `HeartbeatRuntime(HeartbeatRuntimeRequest) returns (HeartbeatRuntimeResponse)` to proto — called by agent runtime pod at startup and periodically)
- [X] T032 [US5] Implement `services/runtime-controller/internal/heartbeat/scanner.go` — `HeartbeatScanner.Run(ctx)`: ticker every `config.HeartbeatCheckInterval`; call `state.ListActiveRuntimes()` to get all RUNNING runtime_ids; for each, call `Redis.Exists("heartbeat:{runtime_id}")` (pipeline for efficiency); for each missing key: `state.UpdateRuntimeState(FAILED, "heartbeat_timeout")`, `emitter.EmitLifecycle(FAILED event)`, `fanout.Publish(FAILED event)`; log each dead worker detection; wire into main.go
- [X] T033 [US5] Unit tests `services/runtime-controller/internal/heartbeat/` — mock Redis client (miniredis); verify ReceiveHeartbeat sets key with correct TTL; verify scanner identifies expired keys and calls UpdateRuntimeState(FAILED); verify heartbeat before timeout prevents false detection (table-driven: 5s timeout, heartbeat at 4s, verify no false positive)

**Checkpoint**: Dead workers detected within configured timeout window. US5 independently testable.

---

## Phase 8: User Story 6 — Secrets Isolation from Agent LLM Context (Priority: P2)

**Goal**: Complete secrets injection implementation — Kubernetes Secrets resolved at launch, values in projected volumes at `/run/secrets/`, LLM process env contains only `SECRETS_REF_*` path pointers. Launch fails hard on vault (Secret) unavailability.

**Independent Test**: Launch with secret_refs=["test-api-key"]. Inspect pod env — verify no secret value present, only path pointer. Check `/run/secrets/api-key` file — value accessible. Test with non-existent secret — verify launch fails with FAILED_PRECONDITION.

- [X] T034 [US6] Complete `services/runtime-controller/internal/launcher/secrets.go` full implementation — `ResolveSecrets`: iterate secret_refs, GET each Kubernetes Secret, validate non-empty data; build `v1.VolumeProjection` per secret with `KeyToPath` entries for all keys; build env vars `SECRETS_REF_{KEY_UPPER_SNAKE}=/run/secrets/{key}` for each key; inject `SANITIZER_PATTERNS_URL=<configmap-url>` env var; if ANY secret GET fails (not found, API error), return error → LaunchRuntime returns `codes.FailedPrecondition` (no fallback, no partial injection)
- [X] T035 [US6] Integration test `services/runtime-controller/internal/launcher/secrets_integration_test.go` (build tag: integration) — use testcontainers-go for a fake Kubernetes API or envtest; create a test Secret with known values; call ResolveSecrets; assert projected volume contains correct KeyToPath entries; assert env vars contain paths not values; assert missing secret returns non-nil error causing launch failure

**Checkpoint**: Secrets isolation enforced — 100% of secret values in projected volumes, 0% in LLM env. Hard failure on unavailability. US6 testable.

---

## Phase 9: User Story 7 — Task Plan Persistence Before Dispatch (Priority: P2)

**Goal**: Every `LaunchRuntime` call with a task plan persists a `TaskPlanRecord` to PostgreSQL (metadata) and MinIO (full payload if large) BEFORE the pod is created.

**Independent Test**: Launch with task_plan_json=`{...}`. Query `task_plan_records` by execution_id — verify record exists with all fields. Verify record was inserted before pod creation timestamp. Test with large payload (>64KB) — verify object stored in MinIO.

- [X] T036 [US7] Implement task plan persistence logic in `services/runtime-controller/internal/state/queries.go` — `InsertTaskPlanRecord(ctx, record TaskPlanRecord) error`: if `len(record.PayloadJSON) > 65536`, upload full JSON to MinIO at `task-plans/{execution_id}/{step_id}.json` using `aws-sdk-go-v2` S3 client, store the object key in `payload_object_key`; insert metadata row into `task_plan_records` table; this function MUST be called from `launcher.go` BEFORE the Kubernetes pod creation call
- [X] T037 [US7] Unit tests `services/runtime-controller/internal/state/task_plan_test.go` — mock pgx pool and mock S3 client; verify small payload stored entirely in DB row; verify large payload (65537 bytes) uploaded to MinIO and `payload_object_key` populated; verify InsertTaskPlanRecord called before CreatePod in the launcher orchestration (use mock sequence to enforce ordering)

**Checkpoint**: TaskPlanRecord persisted before pod creation for every launch with a plan. US7 testable.

---

## Phase 10: User Story 8 — Collect and Archive Runtime Artifacts (Priority: P2)

**Goal**: `CollectRuntimeArtifacts` RPC fetches pod logs and output files, uploads to MinIO at `artifacts/{execution_id}/`, returns manifest; auto-collects on graceful stop.

**Independent Test**: Launch runtime, collect artifacts, verify upload to MinIO at correct path, verify manifest returned. Simulate stop — verify artifacts collected before pod termination.

- [X] T038 [US8] Implement `services/runtime-controller/internal/artifacts/collector.go` — `Collector.Collect(ctx, executionID string) ([]ArtifactEntry, bool, error)`: (1) get pod name from state store; (2) fetch pod logs via `k8sClient.CoreV1().Pods(namespace).GetLogs(podName, &PodLogOptions{})` → upload to `artifacts/{execution_id}/runtime.log`; (3) exec `ls /agent/outputs/` in pod → for each output file, stream to MinIO; (4) build ArtifactEntry list with object keys, sizes, content types; (5) on partial upload failure, retry 3× with exponential backoff; set `complete=false` if any uploads ultimately fail; return entries + complete flag
- [X] T039 [US8] Implement `services/runtime-controller/internal/artifacts/manifest.go` — `BuildManifest(entries []ArtifactEntry) RuntimeEvent`: build ARTIFACT_COLLECTED event with entries JSON in `details_json`; store in `runtime_events` table via `state.InsertRuntimeEvent`
- [X] T040 [US8] Implement CollectRuntimeArtifacts RPC handler in `services/runtime-controller/api/grpc/server.go` — call `Collector.Collect`, call `BuildManifest`, emit fanout event, return `CollectRuntimeArtifactsResponse`; return NOT_FOUND if execution_id unknown
- [X] T041 [US8] Integrate auto-collect into StopRuntime handler in `services/runtime-controller/api/grpc/server.go` — before deleting the pod, call `Collector.Collect` asynchronously (with timeout = grace period); proceed with pod deletion regardless of collection result (artifact failure MUST NOT block stop); log partial collection warnings

**Checkpoint**: Artifacts uploaded to MinIO before pod termination. Partial failures non-blocking. US8 testable.

---

## Phase 11: Polish & Cross-Cutting Concerns

**Purpose**: Docker image, Helm chart, observability, and integration test harness.

- [X] T042 [P] Create `services/runtime-controller/Dockerfile` — stage 1: `golang:1.22-alpine` with `CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /runtime-controller ./cmd/runtime-controller/`; stage 2: `gcr.io/distroless/static-debian12`, copy binary and `/etc/ssl/certs/ca-certificates.crt`; `USER nonroot`; `ENTRYPOINT ["/runtime-controller"]`; verify image size < 100MB
- [X] T043 [P] Create Helm chart `deploy/helm/runtime-controller/` — `Chart.yaml` (runtime-controller, version 0.1.0); `values.yaml` (replicas=1, grpcPort=50051, httpPort=8080, resources, configSecretRef); `values-prod.yaml` (replicas=3, larger resources); `templates/`: Deployment (env from secret + configmap), Service (ClusterIP 50051+8080), ServiceAccount, ClusterRole (pods CRUD + exec + log in platform-execution), ClusterRoleBinding, ConfigMap (reconcilerInterval etc.), NetworkPolicy (allow platform-control + platform-execution on 50051, platform-observability on 8080)
- [X] T044 [P] Add OpenTelemetry instrumentation throughout — gRPC server interceptors in `api/grpc/server.go` (trace context extraction + propagation), Prometheus counter/histogram/gauge metrics: `runtime_controller_launches_total`, `runtime_controller_launch_duration_seconds`, `runtime_controller_active_runtimes` (gauge), `runtime_controller_reconciliation_cycle_duration_seconds`, `runtime_controller_heartbeat_timeouts_total`; expose at `/metrics` on HTTP port
- [X] T045 Create `services/runtime-controller/testdata/docker-compose.yml` (PostgreSQL 16, Redis 7, MinIO latest) for integration tests; add `Makefile` with targets: `make proto` (run protoc), `make test` (unit), `make test-integration` (with docker-compose), `make build` (compile binary), `make docker-build` (build image), `make coverage` (generate coverage report); run `make coverage` and verify ≥95%

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (go.mod must exist) — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2 (needs state store, k8s client, gRPC skeleton, events emitter)
- **US2 (Phase 4)**: Depends on Phase 2 (needs state store, k8s client, events emitter)
- **US3 (Phase 5)**: Depends on US1 (fanout wired into all US1 state transitions)
- **US4 (Phase 6)**: Depends on US1 (LaunchRuntime integration) and Phase 2
- **US5 (Phase 7)**: Depends on Phase 2 (needs Redis, state store) and US1 (needs active runtimes)
- **US6 (Phase 8)**: Depends on US1 (secrets resolution is part of Launch flow)
- **US7 (Phase 9)**: Depends on US1 (task plan inserted inside Launch flow)
- **US8 (Phase 10)**: Depends on US1 (StopRuntime integration) and Phase 2 (k8s client, MinIO)
- **Polish (Phase 11)**: Depends on all user stories complete

### User Story Dependencies

- **US1 → US3** (streaming wired into US1 state transitions)
- **US1 → US4** (warm pool dispatches into Launch flow)
- **US1 → US6** (secrets resolution inside Launch flow)
- **US1 → US7** (task plan persisted inside Launch flow)
- **US1 → US8** (artifact collection on StopRuntime)
- **US2, US5**: depend on Phase 2 only — independently workable after US1 if needed for team parallelism
- **US4, US5, US6, US7, US8**: all depend on US1; mutually independent of each other

### Parallel Opportunities Within Phases

**Phase 1**: T002 (proto), T003 (directory structure) in parallel after T001 (go.mod)  
**Phase 2**: T006 (k8s client), T007 (gRPC stubs), T008 (health), T010 (health) in parallel after T005 (state store)  
**Phase 3**: T011 (secrets), T018 (podspec tests) in parallel within US1  
**Phase 4**: T019→T020→T021 sequential; T022 (tests) parallel to T021  
**Phase 6**: T028 (replenisher), T029 (idle scanner) in parallel with T027 (manager)  
**Phase 11**: T042 (Dockerfile), T043 (Helm), T044 (OTel) in parallel

---

## Parallel Example: User Story 1 (Launch Lifecycle)

```
# Foundation complete → start in parallel:
Task T010: "Build pod spec from RuntimeContract in internal/launcher/podspec.go"
Task T011: "Resolve Kubernetes Secrets into projected volumes in internal/launcher/secrets.go"
Task T013: "Implement Kafka EventEmitter in internal/events/emitter.go"

# Then sequentially:
Task T012: "Implement Launcher.Launch orchestration in internal/launcher/launcher.go"
Task T014: "Implement StopRuntime handler in api/grpc/server.go"
Task T015: "Implement PauseRuntime/ResumeRuntime in api/grpc/server.go"
Task T016: "Implement GetRuntime in api/grpc/server.go"

# Tests in parallel:
Task T017: "Unit tests for launcher.go with fake k8s client"
Task T018: "Unit tests for podspec.go and secrets.go"
```

## Parallel Example: P2 User Stories (after US1 complete)

```
# All P2 stories can start simultaneously:
Task T027: "WarmPoolManager in internal/warmpool/manager.go"        → US4
Task T031: "HeartbeatTracker in internal/heartbeat/tracker.go"      → US5
Task T034: "Complete secrets.go full implementation"                 → US6
Task T036: "InsertTaskPlanRecord in internal/state/queries.go"       → US7
Task T038: "Collector.Collect in internal/artifacts/collector.go"   → US8
```

---

## Implementation Strategy

### MVP First (US1 + US2 + US3 Only)

1. Complete Phase 1: Setup (T001–T003)
2. Complete Phase 2: Foundational (T004–T010)
3. Complete Phase 3: US1 — Full lifecycle RPCs (T010–T018)
4. Complete Phase 4: US2 — Reconciliation loop (T019–T022)
5. Complete Phase 5: US3 — Event streaming (T023–T026)
6. **STOP and VALIDATE**: All 5 lifecycle RPCs working, reconciliation running, events streaming
7. Run quickstart.md sections 1–10 to verify

### Incremental Delivery

1. Setup + Foundational → gRPC server skeleton starts (**infra demo**)
2. US1 → runtime pods launch and stop (**pod lifecycle demo**)
3. US2 → orphans cleaned up (**reliability demo**)
4. US3 → event stream works (**real-time monitoring demo — MVP!**)
5. US4 → warm pool dispatches (**performance demo**)
6. US5 → dead workers detected (**resilience demo**)
7. US6 + US7 → secrets isolation + task plans (**compliance + explainability demo**)
8. US8 → artifacts collected (**observability demo**)
9. Polish → Dockerfile + Helm + OTel (**production-ready**)

### Parallel Team Strategy

After Phase 2 (Foundational) completes:
- **Developer A**: US1 (pod lifecycle — largest story, P1 critical)
- **Developer B**: US2 (reconciliation) + US5 (heartbeat) — share state store knowledge
- **Developer C**: US3 (event streaming) — wires into US1 when ready
- **Developer D**: US4 (warm pool) — wires into US1 when Launch flow stable

---

## Notes

- [P] tasks target independent files — safe to parallelize within the same phase
- ALL state transitions (launch→running, running→stopped, etc.) MUST call `fanout.Publish` — verified by US3 integration test
- Task plan MUST be persisted before `k8sClient.CreatePod` — enforced by unit test mock ordering in T037
- Secrets MUST fail hard (no fallback) — verified by T035 test for missing Secret
- Heartbeat scanner uses Redis pipeline for efficiency — avoid N individual EXISTS calls
- Use `go test -race ./...` to detect data races in concurrent goroutines (reconciler, warm pool, heartbeat scanner, fan-out registry)
- `CGO_ENABLED=0` is required for distroless image — verify at T042
- Commit after each phase checkpoint to maintain clean git history per story
