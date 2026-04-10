# Implementation Plan: Sandbox Manager

**Branch**: `010-sandbox-manager` | **Date**: 2026-04-10 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/010-sandbox-manager/spec.md`

## Summary

Build and deploy the Go Sandbox Manager satellite service that creates isolated code execution pods on Kubernetes. The implementation delivers: a gRPC service (`SandboxService`) with 5 RPCs (create sandbox, execute step, stream logs, terminate, collect artifacts), a template registry (python3.12, node20, go1.22, code-as-reasoning), code execution via `remotecommand` pod exec with dual-layer timeout enforcement, maximum security hardening (non-root, read-only rootfs, no capabilities, no network by default, seccomp), artifact collection (pod exec tar → MinIO upload), and a Helm chart deploying the manager as a Kubernetes Deployment in `platform-execution` with deny-all and conditional-allow NetworkPolicies.

## Technical Context

**Language/Version**: Go 1.22+  
**Primary Dependencies**: `google.golang.org/grpc 1.67+` (gRPC server), `k8s.io/client-go 0.31+` (Kubernetes pod management + remotecommand exec), `github.com/jackc/pgx/v5` (PostgreSQL), `github.com/confluentinc/confluent-kafka-go/v2` (event emission), `github.com/aws/aws-sdk-go-v2` (MinIO artifact upload)  
**Storage**: PostgreSQL (sandbox metadata, event log), MinIO (artifacts)  
**Testing**: `testing` + `testify 1.9` (table-driven unit tests), testcontainers-go (integration tests with real PostgreSQL)  
**Target Platform**: Kubernetes 1.28+ (`platform-execution` namespace), Deployment  
**Project Type**: Go satellite service (gRPC server) + Helm chart  
**Performance Goals**: Sandbox creation < 15s; execution overhead < 2s; artifact upload ≥ 10MB/s; 50 concurrent sandboxes  
**Constraints**: Container image < 50 MB (multi-stage distroless); test coverage ≥ 95%; network disabled by default; all pods non-root + read-only rootfs  
**Scale/Scope**: 5 gRPC RPCs, 2 PostgreSQL tables, 2 background goroutines (orphan scanner, idle scanner), 4 sandbox templates

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Check | Status |
|------|-------|--------|
| Go version | Go 1.22+ per constitution §2.2 | PASS |
| gRPC library | `google.golang.org/grpc 1.67+` per constitution §2.2 | PASS |
| Kubernetes client | `client-go 0.31+` per constitution §2.2 | PASS |
| PostgreSQL client | `pgx/v5` per constitution §2.2 | PASS |
| Kafka client | `confluent-kafka-go/v2` per constitution §2.2 | PASS |
| Object storage | `aws-sdk-go-v2` per constitution §2.2 | PASS |
| OpenTelemetry | `go.opentelemetry.io/otel 1.29+` per constitution §2.2 | PASS |
| Logging | `log/slog` stdlib per constitution §2.2 | PASS |
| Testing | `testing` + `testify 1.9` per constitution §2.2 | PASS |
| Go satellite service pattern | `services/sandbox-manager/` per constitution §3.2 | PASS |
| gRPC port | 50053 per constitution gRPC Service Registry | PASS |
| Namespace: service | `platform-execution` per constitution Kubernetes Namespaces | PASS |
| Namespace: callers | `platform-control`, `platform-execution` per gRPC contract | PASS |
| Kafka topic | `sandbox.events` keyed by sandbox_id per constitution Kafka Topics | PASS |
| No PostgreSQL for caching | In-memory state map for hot path, PostgreSQL for metadata only | PASS |
| No Kafka polling | Event-driven via Kafka producer; no polling | PASS |
| Distroless image | Multi-stage: golang:1.22-alpine + gcr.io/distroless/static-debian12 | PASS |

All gates pass. Proceeding to Phase 1.

## Project Structure

### Documentation (this feature)

```text
specs/010-sandbox-manager/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (PostgreSQL schema, proto definition, package layout)
├── quickstart.md        # Phase 1 output (build, deploy, test guide)
├── contracts/
│   └── grpc-service.md  # gRPC service contract (all 5 RPCs)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
services/sandbox-manager/
├── cmd/sandbox-manager/
│   └── main.go                    # Bootstrap: config, deps, goroutines, gRPC server
├── internal/
│   ├── sandbox/
│   │   ├── manager.go             # CreateSandbox orchestration, in-memory state map
│   │   ├── podspec.go             # Build v1.Pod from template + request
│   │   ├── security.go            # SecurityContext, NetworkPolicy label config
│   │   └── lifecycle.go           # Terminate, mark failed, state transitions
│   ├── executor/
│   │   ├── executor.go            # ExecuteSandboxStep: remotecommand exec
│   │   ├── wrapper.go             # Code wrapper script generation (timeout, JSON capture)
│   │   └── output.go              # Parse stdout/stderr, truncation, structured JSON
│   ├── templates/
│   │   ├── registry.go            # Template lookup by name
│   │   ├── python.go              # python3.12 template spec
│   │   ├── node.go                # node20 template spec
│   │   ├── golang.go              # go1.22 template spec
│   │   └── code_as_reasoning.go   # code-as-reasoning template spec + JSON wrapper
│   ├── logs/
│   │   ├── streamer.go            # StreamSandboxLogs: pod log streaming
│   │   └── fanout.go              # Multi-subscriber fan-out for log streams
│   ├── cleanup/
│   │   ├── orphan_scanner.go      # Background goroutine: detect + terminate orphans
│   │   └── idle_scanner.go        # Background goroutine: terminate idle sandboxes
│   ├── events/
│   │   ├── emitter.go             # Kafka producer: sandbox.events topic
│   │   └── envelope.go            # Canonical event envelope builder
│   ├── state/
│   │   ├── store.go               # pgx/v5 pool and typed query functions
│   │   ├── queries.go             # All SQL (INSERT/UPDATE sandboxes, sandbox_events)
│   │   └── migrations.go          # golang-migrate embedded SQL migrations
│   └── artifacts/
│       ├── collector.go           # Exec tar in pod → stream → upload to MinIO
│       └── manifest.go            # Build ArtifactEntry manifest
├── api/grpc/
│   ├── v1/                        # Generated protobuf Go stubs (do not edit)
│   └── server.go                  # SandboxServiceServer — delegates to internal/
├── pkg/
│   ├── k8s/
│   │   ├── client.go              # In-cluster + kubeconfig client-go setup
│   │   ├── pods.go                # Create, get, list, delete pods
│   │   └── exec.go                # remotecommand exec helper
│   ├── config/
│   │   └── config.go              # Config struct + env var loading
│   └── health/
│       └── handler.go             # /healthz, /readyz HTTP handlers
├── proto/
│   └── sandbox_manager.proto      # Source proto (5 RPCs, all messages)
├── deploy/helm/sandbox-manager/
│   ├── Chart.yaml
│   ├── values.yaml                # Defaults: replicas=1, resources, config
│   ├── values-prod.yaml           # Production: replicas=3, larger resources
│   └── templates/
│       ├── deployment.yaml
│       ├── service.yaml           # ClusterIP: 50053 (gRPC) + 8080 (HTTP)
│       ├── serviceaccount.yaml
│       ├── clusterrole.yaml       # pods CRUD + pods/exec in platform-execution
│       ├── clusterrolebinding.yaml
│       ├── networkpolicy-deny.yaml   # Deny-all for sandbox pods
│       ├── networkpolicy-allow.yaml  # Conditional egress for network-enabled sandboxes
│       └── configmap.yaml
├── testdata/
│   └── docker-compose.yml         # PostgreSQL + Kafka for integration tests
├── Dockerfile                     # Multi-stage: golang:1.22-alpine + distroless/static
├── go.mod
└── go.sum
```

**Structure Decision**: Standard Go satellite service layout matching `services/runtime-controller/` per constitution §3.2. `internal/` enforces package privacy. `pkg/k8s/exec.go` adds remotecommand helpers for pod exec (unique to sandbox manager — runtime-controller doesn't exec into pods). Templates are Go structs in `internal/templates/` for simplicity with only 4 known templates. Two NetworkPolicy Helm templates (deny-all + conditional-allow) replace the single networkpolicy.yaml used by runtime-controller.

## Implementation Phases

### Phase 0: Research (Complete)

All technical decisions resolved in [research.md](research.md):
- Go satellite service architecture following `services/runtime-controller/` pattern
- `remotecommand` (SPDY exec) for code execution inside sandbox pods with dual-layer timeout
- Maximum security hardening: UID 65534, drop ALL caps, RuntimeDefault seccomp, deny-all NetworkPolicy
- Label-based NetworkPolicy (deny-all + conditional egress) controlled by pod labels
- emptyDir volumes with sizeLimit for /tmp, /workspace, /output (separate for artifact collection)
- In-memory state + PostgreSQL metadata + Kafka events (no Redis needed)
- Label-based orphan detection on startup + periodic scan
- Pod exec tar + MinIO upload for artifact collection
- Go struct templates for 4 sandbox types

### Phase 1: Design & Contracts (Complete)

Artifacts generated:
- [data-model.md](data-model.md) — Sandbox state machine, PostgreSQL schema (2 tables), protobuf definition (5 RPCs), Go package layout, pod spec template, configuration table
- [contracts/grpc-service.md](contracts/grpc-service.md) — All 5 RPC contracts with request/response fields, error codes, Kafka event schemas, network access table
- [quickstart.md](quickstart.md) — 15-section build, deploy, and test guide

### Phase 2: Implementation (tasks.md — generated by /speckit.tasks)

**P1 — US1**: Sandbox creation + code execution (CreateSandbox, ExecuteSandboxStep, state persistence)  
**P1 — US2**: Resource limits and timeout enforcement (dual-layer timeout, OOM detection)  
**P1 — US3**: Security hardening (SecurityContext, NetworkPolicy, filesystem isolation)  
**P2 — US4**: Code-as-reasoning template (JSON wrapper, structured output parsing)  
**P2 — US5**: Log streaming (StreamSandboxLogs, gRPC server-side streaming, fan-out)  
**P2 — US6**: Artifact collection (CollectSandboxArtifacts, tar exec, MinIO upload)  
**P2 — US7**: Automatic cleanup (orphan scanner, idle scanner, lifecycle management)

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Service architecture | Go satellite binary at `services/sandbox-manager/` | Constitution §3.2 — Go for concurrent pod lifecycle |
| Code execution | `remotecommand` (pod exec via SPDY) | Official k8s exec mechanism; no sidecar needed |
| Timeout enforcement | Dual-layer: controller context.WithTimeout + pod `timeout` command + ActiveDeadlineSeconds | Defense in depth against runaway processes |
| Security context | UID 65534, drop ALL, readOnlyRootFilesystem, RuntimeDefault seccomp | Maximum restriction for untrusted code |
| Network isolation | Label-based NetworkPolicy (deny-all + conditional allow) | Operationally clean; 2 static policies vs N per-pod policies |
| Filesystem | emptyDir with sizeLimit for /tmp, /workspace, /output (separate) | Prevents disk abuse; separate /output simplifies artifact collection |
| State persistence | In-memory map (hot path) + PostgreSQL (metadata/analytics) | Ephemeral sandboxes don't need PostgreSQL on hot path |
| Orphan detection | Label-based pod listing on startup + periodic scan | Simpler than full reconciliation for short-lived pods |
| Artifact collection | Pod exec tar → stream → MinIO upload | No shared volumes needed; sandbox has no MinIO access |
| Templates | Go structs in `internal/templates/` | Simple for 4 known templates; no external config |
| Container image | Multi-stage: golang:1.22-alpine + distroless/static-debian12 | <50 MB; no shell |

## Dependencies

- **Upstream**: Feature 001 (PostgreSQL — metadata persistence), Feature 003 (Kafka — event emission), Feature 004 (MinIO — artifact storage)
- **Downstream**: Python control plane `execution/` bounded context (calls CreateSandbox, ExecuteSandboxStep); Runtime controller (may call for code-as-reasoning execution); Python client stub at `apps/control-plane/src/platform/common/clients/sandbox_manager.py`
- **Parallel with**: Runtime Controller (sibling Go satellite), Reasoning Engine (sibling Go satellite) — no dependency relationship
- **Blocks**: Code-as-reasoning workflows, sandboxed tool execution, agent code validation

## Complexity Tracking

No constitution violations. The 2 background goroutines (orphan scanner, idle scanner) are inherent to the feature requirements — each handles a distinct concern. Unlike the runtime-controller's 4 goroutines, the sandbox manager is simpler: no heartbeat tracking (sandboxes are too short-lived), no warm pool (sandbox creation is fast enough), no full reconciliation loop (label-based scan is sufficient). All goroutines are managed via `context.Context` cancellation in `main.go`.
