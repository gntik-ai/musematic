# Tasks: Sandbox Manager — Isolated Code Execution

**Input**: Design documents from `specs/010-sandbox-manager/`  
**Branch**: `010-sandbox-manager`  
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓, quickstart.md ✓

**Tests**: Included — SC-010 mandates ≥95% coverage.

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no unresolved dependencies)
- **[Story]**: Maps to user story from spec.md
- Paths relative to repo root; all source under `services/sandbox-manager/`

---

## Phase 1: Setup (Project Initialization)

**Purpose**: Create the Go module, directory layout, and proto source.

- [ ] T001 Initialize Go module at `services/sandbox-manager/go.mod` with module path `github.com/yourorg/musematic/services/sandbox-manager` and all dependencies: `google.golang.org/grpc v1.67+`, `google.golang.org/protobuf v1.34+`, `k8s.io/client-go v0.31+`, `k8s.io/api v0.31+`, `github.com/jackc/pgx/v5`, `github.com/confluentinc/confluent-kafka-go/v2`, `github.com/aws/aws-sdk-go-v2`, `go.opentelemetry.io/otel v1.29+`, `github.com/stretchr/testify v1.9`
- [X] T002 Create directory skeleton per plan.md: `cmd/sandbox-manager/`, `internal/sandbox/`, `internal/executor/`, `internal/templates/`, `internal/logs/`, `internal/cleanup/`, `internal/events/`, `internal/state/`, `internal/artifacts/`, `api/grpc/v1/`, `pkg/k8s/`, `pkg/config/`, `pkg/health/`, `proto/`, `deploy/helm/sandbox-manager/templates/`, `testdata/`
- [X] T003 Write proto source at `services/sandbox-manager/proto/sandbox_manager.proto` — include all enums (SandboxState 6 values, SandboxEventType 8 values), core messages (SandboxTemplate, ResourceLimits, CorrelationContext, SandboxInfo, ExecutionResult, SandboxEvent, ArtifactEntry), all RPC request/response messages, and the SandboxService with 5 RPCs as defined in `specs/010-sandbox-manager/data-model.md §3`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure required before any user story implementation.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Implement config struct at `services/sandbox-manager/pkg/config/config.go` — env-var-loaded fields: GRPC_PORT (50053), HTTP_PORT (8080), POSTGRES_DSN, KAFKA_BROKERS, MINIO_ENDPOINT, MINIO_BUCKET (musematic-artifacts), K8S_NAMESPACE (platform-execution), DEFAULT_TIMEOUT (30s), MAX_TIMEOUT (300s), MAX_OUTPUT_SIZE (10485760), ORPHAN_SCAN_INTERVAL (60s), IDLE_TIMEOUT (300s), MAX_CONCURRENT_SANDBOXES (50), K8S_DRY_RUN (bool)
- [X] T005 Implement Kubernetes client at `services/sandbox-manager/pkg/k8s/client.go` — return both `*kubernetes.Clientset` and `*rest.Config` (rest.Config is required for remotecommand); implement in-cluster config with kubeconfig fallback; implement `services/sandbox-manager/pkg/k8s/pods.go` with CreatePod, GetPod, ListPodsByLabel, DeletePod typed functions using `platform-execution` namespace
- [X] T006 [P] Implement PostgreSQL state store at `services/sandbox-manager/internal/state/store.go` — pgx/v5 pool setup; implement `services/sandbox-manager/internal/state/queries.go` with InsertSandbox, UpdateSandboxState, InsertSandboxEvent typed query functions matching schema in `specs/010-sandbox-manager/data-model.md §2`; implement embedded SQL migrations at `services/sandbox-manager/internal/state/migrations.go` for `sandboxes` and `sandbox_events` tables
- [X] T007 [P] Implement Kafka event emitter at `services/sandbox-manager/internal/events/emitter.go` — confluent-kafka-go/v2 producer writing to `sandbox.events` topic keyed by sandbox_id; implement canonical event envelope at `services/sandbox-manager/internal/events/envelope.go` matching the JSON schema in `specs/010-sandbox-manager/contracts/grpc-service.md §4`
- [ ] T008 Generate gRPC stubs from proto into `services/sandbox-manager/api/grpc/v1/` (do not edit generated files); implement server skeleton at `services/sandbox-manager/api/grpc/server.go` — SandboxServiceServer struct with all 5 methods stubbed returning `codes.Unimplemented`; include OTel interceptors on gRPC server
- [X] T009 [P] Implement health handlers at `services/sandbox-manager/pkg/health/handler.go` — `/healthz` returns `{"status":"ok"}`; `/readyz` checks PostgreSQL ping, Kafka producer liveness, Kubernetes API reachability; return 200/503 appropriately
- [ ] T010 Implement `services/sandbox-manager/cmd/sandbox-manager/main.go` — load config, init k8s client, init pgx pool + run migrations, init Kafka producer, init MinIO client, init gRPC server with OTel interceptors on port GRPC_PORT, start HTTP server on HTTP_PORT, start background goroutines via `context.Context` with cancel, graceful shutdown on SIGTERM/SIGINT

**Checkpoint**: Foundation ready — user story implementation can now begin.

---

## Phase 3: User Story 1 — Execute Code in Isolated Sandbox (Priority: P1) 🎯 MVP

**Goal**: Agents can create a Python/Node/Go sandbox pod and execute code snippets, receiving stdout, stderr, and exit code.

**Independent Test**: `CreateSandbox` with template `python3.12`, then `ExecuteSandboxStep` with `print("hello")` — verify stdout is `"hello\n"` and exit_code is 0. Verify sandbox transitions CREATING → READY → EXECUTING → READY.

- [X] T011 [P] [US1] Implement template registry and python3.12/node20/go1.22 templates at `services/sandbox-manager/internal/templates/registry.go`, `python.go`, `node.go`, `golang.go` — each template struct holds: image (python:3.12-slim, node:20-slim, golang:1.22-alpine), default ResourceLimits, default timeout, working directory (`/workspace`), exec command prefix (`python3 -c`, `node -e`, `go run /workspace/main.go`); `Lookup(name string)` returns the template or error for unknown names
- [X] T012 [P] [US1] Implement pod spec builder at `services/sandbox-manager/internal/sandbox/podspec.go` — `BuildPodSpec(sandboxID, tmpl, req)` returns `*v1.Pod` with: name `sandbox-{sandboxID_short}`, labels (app=sandbox, musematic/sandbox=true, sandbox_id, execution_id, workspace_id, managed-by=sandbox-manager), restartPolicy=Never, automountServiceAccountToken=false, hostNetwork/PID/IPC=false, enableServiceLinks=false, dnsPolicy=None, activeDeadlineSeconds=300, pod-level securityContext (runAsNonRoot, runAsUser/Group=65534, fsGroup=65534, seccompProfile=RuntimeDefault), container-level securityContext (allowPrivilegeEscalation=false, readOnlyRootFilesystem=true, capabilities.drop=ALL), resource requests/limits from template, command=["sleep","infinity"], 3 emptyDir volumes (/tmp 256Mi, /workspace 512Mi, /output 128Mi)
- [X] T013 [US1] Implement sandbox manager at `services/sandbox-manager/internal/sandbox/manager.go` — `sync.RWMutex`-protected in-memory map of sandboxID → SandboxEntry; `Create(ctx, req)` method: validate template exists, check MAX_CONCURRENT_SANDBOXES, generate sandbox_id UUID, call InsertSandbox to PostgreSQL (state=creating), call CreatePod via k8s client, emit `sandbox.created` Kafka event, return sandbox_id; background pod-watcher goroutine transitions state to READY when pod phase=Running, updates PostgreSQL, emits `sandbox.ready`; enforce MAX_CONCURRENT_SANDBOXES limit with `RESOURCE_EXHAUSTED` gRPC error
- [ ] T014 [US1] Implement remotecommand exec helper at `services/sandbox-manager/pkg/k8s/exec.go` — `ExecInPod(ctx, cfg, namespace, podName, command []string, stdin io.Reader, stdout io.Writer, stderr io.Writer) error` using `k8s.io/client-go/tools/remotecommand` NewSPDYExecutor; extract exit code from `remotecommand.CodeExitError`; function must accept `*rest.Config` (not just Clientset) for SPDY executor creation
- [X] T015 [US1] Implement code wrapper script generator at `services/sandbox-manager/internal/executor/wrapper.go` — `BuildCommand(template, code string, timeoutSeconds int) []string` wraps user code with `timeout --kill-after=2s {N}s {interpreter} -c {code}` so hard timeout is enforced inside the container; for python3.12: `["timeout", "--kill-after=2s", "30s", "python3", "-c", code]`; for node20: `["timeout", ..., "node", "-e", code]`; for go1.22: writes code to /workspace/main.go then `["timeout", ..., "go", "run", "/workspace/main.go"]`
- [X] T016 [US1] Implement executor at `services/sandbox-manager/internal/executor/executor.go` — `Execute(ctx, sandbox, code string, timeoutSec int) (ExecutionResult, error)`: get sandbox from manager, validate state=READY, transition to EXECUTING, build command via wrapper.go, wrap ctx with `context.WithTimeout(ctx, timeoutSec+5 seconds)`, call ExecInPod piping stdin/stdout/stderr to buffers, transition back to READY on success or FAILED on error; implement `services/sandbox-manager/internal/executor/output.go` with stdout/stderr truncation at MAX_OUTPUT_SIZE and OOM detection (check pod status for OOMKilled reason after exec failure)
- [X] T017 [US1] Implement lifecycle state transitions at `services/sandbox-manager/internal/sandbox/lifecycle.go` — `Transition(sandboxID, fromState, toState, reason string) error` with valid transition guard (no back-transitions); `MarkFailed(sandboxID, reason string)` updates in-memory + PostgreSQL + emits Kafka event; `MarkTerminated(sandboxID string)` deletes pod via k8s, removes from in-memory map, updates PostgreSQL, emits event
- [X] T018 [US1] Wire CreateSandbox and ExecuteSandboxStep RPC handlers in `services/sandbox-manager/api/grpc/server.go` — CreateSandbox delegates to manager.Create(), maps gRPC errors (INVALID_ARGUMENT, RESOURCE_EXHAUSTED, UNAVAILABLE); ExecuteSandboxStep delegates to executor.Execute(), maps gRPC errors (NOT_FOUND, FAILED_PRECONDITION, DEADLINE_EXCEEDED)
- [X] T019 [US1] Write unit tests for template registry (`internal/templates/`), pod spec builder (`internal/sandbox/podspec_test.go`), sandbox manager (`internal/sandbox/manager_test.go` with mock k8s client), executor (`internal/executor/executor_test.go` with mock ExecInPod), and wrapper (`internal/executor/wrapper_test.go`) — table-driven tests with testify; mock k8s client using `k8s.io/client-go/kubernetes/fake`

**Checkpoint**: US1 fully functional — create sandbox, execute code, get results.

---

## Phase 4: User Story 2 — Enforce Resource Limits and Timeouts (Priority: P1)

**Goal**: Memory-exceeding code triggers OOMKill detection; time-exceeding code triggers timeout; both are reported in ExecutionResult.

**Independent Test**: Execute memory-hungry code in a 64Mi sandbox → `result.oom_killed=true`. Execute `time.sleep(999)` with timeout=5s → `result.timed_out=true` within ~7 seconds.

- [X] T020 [US2] Extend executor timeout enforcement at `services/sandbox-manager/internal/executor/executor.go` — dual-layer: (1) `timeout --kill-after=2s {N}s` in the wrapper command (T015); (2) `context.WithTimeout(ctx, timeoutSec+5*time.Second)` wrapping the ExecInPod call; when context deadline exceeded, set `ExecutionResult.TimedOut=true`; when exec error matches OOMKilled pattern in pod status, set `ExecutionResult.OOMKilled=true`
- [X] T021 [US2] Implement OOM detection at `services/sandbox-manager/internal/executor/output.go` — `DetectOOM(ctx, k8sClient, namespace, podName string) bool`: after exec failure, call GetPod and inspect `pod.Status.ContainerStatuses[0].LastTerminationState.Terminated.Reason == "OOMKilled"`; also detect from exec error if the exit code is 137 (SIGKILL = OOM signal)
- [X] T022 [US2] Add resource enforcement fields to pod spec at `services/sandbox-manager/internal/sandbox/podspec.go` — `activeDeadlineSeconds` set to `MAX_TIMEOUT` (300s); `ephemeral-storage` limit set to `1Gi` in container resources; emptyDir sizeLimit values (/tmp=256Mi, /workspace=512Mi, /output=128Mi) must be set per Decision 5 in research.md
- [ ] T023 [US2] Write unit tests for timeout detection (`internal/executor/executor_test.go` — mock ExecInPod that returns after delay), OOM detection (`internal/executor/output_test.go` — mock pod with OOMKilled reason), and resource limit fields in pod spec builder

**Checkpoint**: US1 + US2 functional — resource enforcement verified.

---

## Phase 5: User Story 3 — Security Hardening and Network Isolation (Priority: P1)

**Goal**: All sandbox pods run with UID 65534, no capabilities, read-only rootfs, no network (default), and deny-all NetworkPolicy prevents egress.

**Independent Test**: Exec `id` in sandbox → UID=65534. Exec `touch /test` → permission denied. Exec `python3 -c "import urllib.request; urllib.request.urlopen('http://example.com')"` → connection error. Exec `python3 -c "import os; os.setuid(0)"` → permission denied.

- [X] T024 [P] [US3] Implement security context builder at `services/sandbox-manager/internal/sandbox/security.go` — `BuildPodSecurityContext()` returns pod-level `*v1.PodSecurityContext` (runAsNonRoot=true, runAsUser/Group=65534, fsGroup=65534, seccompProfile=RuntimeDefault); `BuildContainerSecurityContext()` returns container-level `*v1.SecurityContext` (allowPrivilegeEscalation=false, readOnlyRootFilesystem=true, capabilities.Drop=["ALL"]); integrate into podspec.go BuildPodSpec
- [X] T025 [P] [US3] Implement network isolation settings in `services/sandbox-manager/internal/sandbox/podspec.go` — when `network_enabled=false`: set dnsPolicy=None, dnsConfig={}, do NOT add label `musematic/network-allowed`; when `network_enabled=true`: set dnsPolicy=ClusterFirst, add label `musematic/network-allowed=true`; set `enableServiceLinks=false` always
- [X] T026 [US3] Create NetworkPolicy Helm templates at `services/sandbox-manager/deploy/helm/sandbox-manager/templates/networkpolicy-deny.yaml` (deny all ingress+egress for pods with label `musematic/sandbox=true`) and `networkpolicy-allow.yaml` (allow egress port 443 for pods with `musematic/sandbox=true` AND `musematic/network-allowed=true`) per research.md Decision 4
- [X] T027 [US3] Verify pod-level hardening settings in `services/sandbox-manager/internal/sandbox/podspec.go` — assert these fields are set: `automountServiceAccountToken: false`, `hostNetwork: false`, `hostPID: false`, `hostIPC: false`, `restartPolicy: Never`, `enableServiceLinks: false`; add RBAC requirements to Helm clusterrole.yaml: `pods` (create, get, list, watch, delete) and `pods/exec` (create) in `platform-execution`
- [X] T028 [US3] Write unit tests for security context (`internal/sandbox/security_test.go` — assert every SecurityContext field), network isolation (`internal/sandbox/podspec_test.go` — test network_enabled=false sets dnsPolicy=None, test network_enabled=true adds label), pod hardening fields (assert all 7 pod-level hardening settings present in generated PodSpec)

**Checkpoint**: US1 + US2 + US3 functional — security hardening verified. This completes the P1 MVP.

---

## Phase 6: User Story 4 — Code-as-Reasoning Execution (Priority: P2)

**Goal**: The `code-as-reasoning` template wraps output in structured JSON; `ExecutionResult.StructuredOutput` contains the parsed JSON.

**Independent Test**: Create `code-as-reasoning` sandbox, execute `result = 6 * 7` — verify `result.structured_output` contains parseable JSON with the computation result.

- [X] T029 [US4] Implement code-as-reasoning template at `services/sandbox-manager/internal/templates/code_as_reasoning.go` — template spec: image=python:3.12-slim, memoryLimit=128Mi, cpuLimit=250m, timeout=15s; `BuildWrappedCommand(code string) []string` wraps user code in a Python script that captures stdout/stderr via `io.StringIO`, executes in `exec()`, then prints `json.dumps({"result": captured_stdout, "error": captured_stderr, "exit_code": 0})` to stdout; use `timeout --kill-after=2s 15s python3 -c {wrapped_code}`
- [X] T030 [US4] Implement structured JSON output parsing at `services/sandbox-manager/internal/executor/output.go` — `ParseStructuredOutput(stdout string) (string, bool)`: attempt `json.Unmarshal` of raw stdout; if valid JSON, set `ExecutionResult.StructuredOutput = stdout` and `StructuredOutputParsed = true`; if invalid JSON, leave StructuredOutput empty and include stdout in plain `ExecutionResult.Stdout`; integrate into executor.go after execution for sandboxes using the code-as-reasoning template
- [ ] T031 [US4] Write unit tests for code-as-reasoning template (`internal/templates/code_as_reasoning_test.go` — verify BuildWrappedCommand produces correct Python wrapper), structured output parsing (`internal/executor/output_test.go` — valid JSON parsed correctly, invalid JSON falls back to raw stdout), and integration of template + parsing in executor

**Checkpoint**: US4 functional — code-as-reasoning template verified.

---

## Phase 7: User Story 5 — Stream Sandbox Logs (Priority: P2)

**Goal**: Callers receive stdout/stderr lines in real-time as code executes; multiple concurrent subscribers supported.

**Independent Test**: Start long-running code (produces output over 3 seconds), open `StreamSandboxLogs` with `follow=true`, verify lines arrive incrementally (not all at end). Open second subscriber — both receive the same lines.

- [X] T032 [US5] Implement log fan-out registry at `services/sandbox-manager/internal/logs/fanout.go` — `FanoutRegistry` with `sync.RWMutex`-protected map of sandboxID → []chan SandboxLogLine; `Subscribe(sandboxID string) (<-chan SandboxLogLine, cancel func())` adds a channel; `Publish(sandboxID string, line SandboxLogLine)` sends to all channels; `Close(sandboxID string)` closes and removes all subscriber channels; buffer channels with capacity 100 to prevent slow subscribers from blocking producers
- [X] T033 [US5] Implement pod log streamer at `services/sandbox-manager/internal/logs/streamer.go` — `StreamPodLogs(ctx, k8sClient, namespace, podName string, fanout *FanoutRegistry)` uses `k8sClient.CoreV1().Pods(namespace).GetLogs(podName, &v1.PodLogOptions{Follow: true})` to stream pod logs; parse lines from the stream and publish to fanout; run in a goroutine per sandbox, started when sandbox transitions to READY; stop when context is cancelled or sandbox terminates
- [X] T034 [US5] Wire StreamSandboxLogs RPC handler in `services/sandbox-manager/api/grpc/server.go` — look up sandbox (NOT_FOUND if missing), call fanout.Subscribe(), loop sending SandboxLogLine messages to the gRPC stream until context cancelled or channel closed; for `follow=false`: fetch buffered logs from pod log API, send all, close stream; handle CANCELLED error gracefully
- [ ] T035 [US5] Write unit tests for fan-out registry (`internal/logs/fanout_test.go` — multiple subscribers receive same messages, slow subscriber doesn't block, Close unsubscribes all), log streamer with mock pod log reader, StreamSandboxLogs RPC with mock fanout

**Checkpoint**: US5 functional — real-time log streaming verified.

---

## Phase 8: User Story 6 — Collect Sandbox Artifacts (Priority: P2)

**Goal**: Files written to `/output/` in the sandbox are uploaded to MinIO; a manifest is returned.

**Independent Test**: Execute `open('/output/result.txt', 'w').write('42')`, call `CollectSandboxArtifacts` — verify `result.txt` appears in MinIO at `sandbox-artifacts/{exec_id}/{sandbox_id}/result.txt` and the manifest includes it with correct size.

- [X] T036 [US6] Implement artifact manifest builder at `services/sandbox-manager/internal/artifacts/manifest.go` — `BuildManifest(executionID, sandboxID string, files []FileInfo) []ArtifactEntry`: constructs object keys as `sandbox-artifacts/{executionID}/{sandboxID}/{filename}`, detects content-type from file extension, sets collected_at timestamp; `FileInfo` struct: Name, SizeBytes
- [ ] T037 [US6] Implement artifact collector at `services/sandbox-manager/internal/artifacts/collector.go` — `Collect(ctx, sandbox, k8sExecClient, s3Client, bucket string) ([]ArtifactEntry, error)`: exec `tar czf - -C /output .` in the sandbox pod via remotecommand (from pkg/k8s/exec.go), pipe tar stdout to a streaming reader, decompress and iterate entries, upload each file to MinIO via `s3Client.PutObject` with the object key from manifest builder; return manifest entries; handle empty /output gracefully (return empty slice, not error)
- [X] T038 [US6] Wire CollectSandboxArtifacts RPC handler in `services/sandbox-manager/api/grpc/server.go` — look up sandbox (NOT_FOUND if missing), validate pod still exists (FAILED_PRECONDITION if terminated), call artifacts.Collect(), return ArtifactEntry list and `complete` bool; also call Collect automatically when TerminateSandbox is called on a non-failed sandbox (pre-termination collection)
- [ ] T039 [US6] Write unit tests for manifest builder (`internal/artifacts/manifest_test.go` — correct object key format, content-type detection), collector (`internal/artifacts/collector_test.go` — mock ExecInPod returning tar stream, mock MinIO client), RPC handler with mock collector

**Checkpoint**: US6 functional — artifact collection verified.

---

## Phase 9: User Story 7 — Automatic Sandbox Cleanup (Priority: P2)

**Goal**: Sandboxes auto-terminate after completion/timeout. Orphaned pods from previous controller restarts are detected and deleted within 120 seconds.

**Independent Test**: Create sandbox, let it timeout (set IDLE_TIMEOUT=5s for test), verify pod is deleted and state=TERMINATED. Restart controller with orphaned pod present — verify pod deleted within 60 seconds.

- [X] T040 [P] [US7] Implement orphan scanner at `services/sandbox-manager/internal/cleanup/orphan_scanner.go` — `Run(ctx, k8sClient, manager *SandboxManager, interval time.Duration)` goroutine: on startup, call ListPodsByLabel(managed-by=sandbox-manager), cross-reference against manager's in-memory map, terminate any pod not in the map (these are orphans from previous instance); then tick every `interval` (ORPHAN_SCAN_INTERVAL=60s), repeat the same check; use 5-second grace period for orphan pod deletion
- [X] T041 [P] [US7] Implement idle sandbox scanner at `services/sandbox-manager/internal/cleanup/idle_scanner.go` — `Run(ctx, manager *SandboxManager, idleTimeout time.Duration, interval time.Duration)` goroutine: tick every interval (30s), scan all sandboxes in READY or COMPLETED state, for any sandbox where `last_activity_at + idleTimeout < now`, call lifecycle.MarkTerminated; track `last_activity_at` in the SandboxEntry struct, updated on each ExecuteSandboxStep call
- [X] T042 [US7] Implement TerminateSandbox graceful + forced shutdown at `services/sandbox-manager/internal/sandbox/lifecycle.go` — extend `MarkTerminated` to: call DeletePod with grace period, wait for pod deletion confirmation (poll GetPod with `context.WithTimeout`), emit `sandbox.terminated` Kafka event, update PostgreSQL state; if grace period 0 → immediate force delete
- [X] T043 [US7] Wire cleanup goroutines in `services/sandbox-manager/cmd/sandbox-manager/main.go` — start orphan_scanner.Run and idle_scanner.Run with context-cancellation managed goroutines; wire TerminateSandbox RPC handler in server.go delegating to lifecycle.MarkTerminated with grace period from request
- [ ] T044 [US7] Write unit tests for orphan scanner (`internal/cleanup/orphan_scanner_test.go` — mock ListPodsByLabel returning orphan, verify DeletePod called), idle scanner (`internal/cleanup/idle_scanner_test.go` — advance time past idleTimeout, verify MarkTerminated called), TerminateSandbox RPC handler with mock lifecycle

**Checkpoint**: All 7 user stories complete and independently testable.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Container image, Helm chart, observability, and developer tooling.

- [ ] T045 Write `services/sandbox-manager/Dockerfile` — multi-stage: stage 1 `FROM golang:1.22-alpine AS builder` with `CGO_ENABLED=0 GOARCH=amd64 GOOS=linux go build -ldflags="-s -w" -o /sandbox-manager ./cmd/sandbox-manager/`; stage 2 `FROM gcr.io/distroless/static-debian12` copying binary; verify image size < 50MB
- [X] T046 [P] Create Helm chart at `services/sandbox-manager/deploy/helm/sandbox-manager/` — Chart.yaml (name: sandbox-manager, version: 0.1.0, appVersion: latest); values.yaml (replicas: 1, image, resources, config env vars, K8S_DRY_RUN: false); values-prod.yaml (replicas: 3, larger resource limits); templates: deployment.yaml (pulls config from secret), service.yaml (ClusterIP: 50053 + 8080), serviceaccount.yaml, clusterrole.yaml (pods + pods/exec CRUD in platform-execution), clusterrolebinding.yaml, configmap.yaml, networkpolicy-deny.yaml, networkpolicy-allow.yaml
- [ ] T047 [P] Add OpenTelemetry instrumentation — OTel trace spans on all 5 gRPC handlers in `services/sandbox-manager/api/grpc/server.go` (using `go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc` interceptors); OTel spans for CreatePod, ExecInPod, DeletePod in `services/sandbox-manager/pkg/k8s/`; OTel spans for MinIO upload in `services/sandbox-manager/internal/artifacts/collector.go`; configure OTEL_EXPORTER_OTLP_ENDPOINT from config
- [X] T048 [P] Create `services/sandbox-manager/testdata/docker-compose.yml` — services: postgres:16 (port 5432, database musematic), kafka (Strimzi-compatible, port 9092 with KRaft); add integration test helpers in `services/sandbox-manager/internal/state/store_integration_test.go` (build tag: `//go:build integration`) that run real migrations and INSERT/UPDATE queries against test database
- [ ] T049 Create `services/sandbox-manager/Makefile` — targets: `proto` (runs protoc), `build` (go build), `test` (go test ./... -coverprofile=coverage.out), `test-integration` (docker compose up + go test -tags=integration), `lint` (golangci-lint run), `image` (docker build), `helm-lint` (helm lint deploy/helm/sandbox-manager); verify `go tool cover -func=coverage.out | grep total` shows ≥95%

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2
- **US2 (Phase 4)**: Depends on Phase 3 (timeout enforcement extends executor)
- **US3 (Phase 5)**: Depends on Phase 3 (security extends podspec/sandbox)
- **US4 (Phase 6)**: Depends on Phase 3 (new template + output.go extension)
- **US5 (Phase 7)**: Depends on Phase 3 (fan-out integrates with sandbox manager)
- **US6 (Phase 8)**: Depends on Phase 3 (artifacts uses executor exec helper)
- **US7 (Phase 9)**: Depends on Phase 3 (cleanup uses sandbox manager)
- **Polish (Phase 10)**: Depends on all user stories

### User Story Dependencies (within P1 phase)

- **US2** extends `executor.go` from US1 — must complete US1 first
- **US3** extends `podspec.go` from US1 — can start in parallel with US2

### Parallel Opportunities

Within Phase 2: T006, T007, T009 can run in parallel (different files)  
Within Phase 3: T011, T012 can run in parallel (templates vs podspec)  
After Phase 3: US4 (T029-T031), US5 (T032-T035), US6 (T036-T039), US7 (T040-T044) can run in parallel by different developers  
Within Phase 9: T040 and T041 can run in parallel (different goroutines)  
Within Phase 10: T046, T047, T048 can run in parallel

---

## Parallel Execution Examples

### Parallel: Phase 3 (US1)

```bash
# Launch simultaneously:
Task T011: "Template registry + python/node/go templates in internal/templates/"
Task T012: "Pod spec builder in internal/sandbox/podspec.go"
# Then sequentially:
Task T013: "Sandbox manager in internal/sandbox/manager.go" (needs T011, T012)
Task T014: "remotecommand exec helper in pkg/k8s/exec.go"
Task T015: "Code wrapper in internal/executor/wrapper.go" (needs T011)
```

### Parallel: Phase 9 (US7)

```bash
# Launch simultaneously:
Task T040: "Orphan scanner goroutine in internal/cleanup/orphan_scanner.go"
Task T041: "Idle scanner goroutine in internal/cleanup/idle_scanner.go"
# Then sequentially:
Task T042: "TerminateSandbox lifecycle in internal/sandbox/lifecycle.go"
Task T043: "Wire cleanup goroutines in main.go + server.go"
```

### Parallel: Phase 10 (Polish)

```bash
# Launch simultaneously:
Task T046: "Helm chart in deploy/helm/sandbox-manager/"
Task T047: "OTel instrumentation across all packages"
Task T048: "docker-compose.yml + integration test helpers"
```

---

## Implementation Strategy

### MVP: P1 User Stories Only (Phases 1–5)

1. Complete Phase 1: Setup (T001–T003)
2. Complete Phase 2: Foundational (T004–T010)
3. Complete Phase 3: US1 — sandbox creation + code execution (T011–T019)
4. Complete Phase 4: US2 — resource limits + timeout (T020–T023)
5. Complete Phase 5: US3 — security hardening (T024–T028)
6. **STOP and VALIDATE**: Run `grpcurl` tests from quickstart.md §7–§11
7. Deploy to dev cluster — all acceptance criteria for P1 met

### Incremental Delivery

1. Foundation ready (Phases 1–2) → internal dev use only
2. US1 + US2 + US3 complete (MVP) → Deploy, validate with quickstart.md
3. Add US4 (code-as-reasoning) → Run quickstart.md §12
4. Add US5 (log streaming) → Run quickstart.md §7 with follow=true
5. Add US6 (artifact collection) → Run quickstart.md §13
6. Add US7 (cleanup) → Verify auto-cleanup and orphan detection
7. Polish (Phase 10) → Production-ready

---

## Notes

- `[P]` tasks operate on different files — safe to parallelize
- `[Story]` label maps each task to its user story for traceability
- US2 and US3 both extend code from US1 — keep US1 clean before starting them
- Code-as-reasoning template (US4) extends output.go from US1 — keep interface stable
- Security is P1 co-equal with code execution — never ship US1 without US3
- The remotecommand exec exit code is extracted from `remotecommand.CodeExitError` (not standard `exec.ExitError`)
- RBAC must include `pods/exec` (create) in addition to `pods` CRUD — easy to miss
- `enableServiceLinks: false` prevents cluster topology leakage — required for untrusted code
