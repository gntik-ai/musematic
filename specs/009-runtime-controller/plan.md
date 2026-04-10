# Implementation Plan: Runtime Controller

**Branch**: `009-runtime-controller` | **Date**: 2026-04-10 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/009-runtime-controller/spec.md`

## Summary

Build and deploy the Go Runtime Controller satellite service that manages agent runtime pod lifecycle on Kubernetes. The implementation delivers: a gRPC service (`RuntimeControlService`) with 7 RPCs (launch, get, pause, resume, stop, stream events, collect artifacts), a background reconciliation loop (30s interval, PostgreSQL vs Kubernetes state comparison), a heartbeat tracker (Redis TTL-based, 60s timeout, 10s scanner), a warm pool manager (in-memory + PostgreSQL inventory, configurable per workspace/agent-type), secrets isolation (Kubernetes Secrets → projected pod volumes, never in LLM env), task plan persistence (PostgreSQL metadata + MinIO payload), artifact collection (pod logs + outputs → MinIO), and a Helm chart deploying the controller as a Kubernetes Deployment in `platform-execution`.

## Technical Context

**Language/Version**: Go 1.22+  
**Primary Dependencies**: `google.golang.org/grpc 1.67+` (gRPC server), `k8s.io/client-go 0.31+` (Kubernetes pod management), `github.com/jackc/pgx/v5` (PostgreSQL), `github.com/redis/go-redis/v9` (heartbeat TTL), `github.com/confluentinc/confluent-kafka-go/v2` (event emission), `github.com/aws/aws-sdk-go-v2` (MinIO artifact upload)  
**Storage**: PostgreSQL (runtime state, warm pool inventory, task plan records, event log), Redis (heartbeat TTL keys)  
**Testing**: `testing` + `testify 1.9` (table-driven unit tests), testcontainers-go (integration tests with real PostgreSQL/Redis)  
**Target Platform**: Kubernetes 1.28+ (`platform-execution` namespace), Deployment  
**Project Type**: Go satellite service (gRPC server) + Helm chart  
**Performance Goals**: Cold launch < 10s; warm launch < 2s; reconciliation loop < 5s for 1,000 runtimes; event delivery < 500ms  
**Constraints**: Container image < 100 MB (multi-stage distroless); test coverage ≥ 95%; secrets never in LLM context window (hard constraint); task plan persisted before pod creation  
**Scale/Scope**: 7 gRPC RPCs, 4 PostgreSQL tables, 4 background goroutines (reconciler, heartbeat scanner, warm pool replenisher, idle pod scanner)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Check | Status |
|------|-------|--------|
| Go version | Go 1.22+ per constitution §2.2 | PASS |
| gRPC library | `google.golang.org/grpc 1.67+` per constitution §2.2 | PASS |
| Kubernetes client | `client-go 0.31+` per constitution §2.2 | PASS |
| Redis client | `go-redis/v9` per constitution §2.2 | PASS |
| PostgreSQL client | `pgx/v5` per constitution §2.2 | PASS |
| Kafka client | `confluent-kafka-go/v2` per constitution §2.2 | PASS |
| Object storage | `aws-sdk-go-v2` per constitution §2.2 | PASS |
| OpenTelemetry | `go.opentelemetry.io/otel 1.29+` per constitution §2.2 | PASS |
| Logging | `log/slog` stdlib per constitution §2.2 | PASS |
| Testing | `testing` + `testify 1.9` per constitution §2.2 | PASS |
| Go satellite service pattern | `services/runtime-controller/` per constitution §3.2 | PASS |
| Namespace: service | `platform-execution` (runtime pods namespace) | PASS |
| Namespace: callers | `platform-control`, `platform-execution` per gRPC contract | PASS |
| No PostgreSQL for caching | Heartbeat hot state in Redis, not PostgreSQL | PASS |
| No Kafka polling | Event-driven via Kafka producer; no polling | PASS |
| Secrets not in LLM context | FR-014: projected volumes, not env vars; constitution §XI | PASS |
| Task plans persisted | FR-016: TaskPlanRecord in PostgreSQL + MinIO; constitution §XII | PASS |
| Distroless image | Multi-stage: golang:1.22-alpine + gcr.io/distroless/static-debian12 | PASS |

All gates pass. Proceeding to Phase 1.

## Project Structure

### Documentation (this feature)

```text
specs/009-runtime-controller/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (PostgreSQL schema, proto definition, package layout)
├── quickstart.md        # Phase 1 output (build, deploy, test guide)
├── contracts/
│   └── grpc-service.md  # gRPC service contract (all 7 RPCs)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
services/runtime-controller/
├── cmd/runtime-controller/
│   └── main.go                    # Bootstrap: config, deps, goroutines, gRPC server
├── internal/
│   ├── launcher/
│   │   ├── launcher.go            # LaunchRuntime orchestration
│   │   ├── podspec.go             # Build v1.Pod from RuntimeContract
│   │   ├── secrets.go             # Resolve Kubernetes Secrets → projected volume
│   │   └── warmpool_dispatch.go   # Atomic warm pool dispatch
│   ├── reconciler/
│   │   ├── reconciler.go          # Background goroutine (30s interval)
│   │   ├── drift.go               # Detect orphans, missing, state mismatches
│   │   └── repair.go              # Terminate orphans, update DB, emit drift events
│   ├── warmpool/
│   │   ├── manager.go             # In-memory pool + DB inventory
│   │   ├── replenisher.go         # Background replenishment goroutine
│   │   └── idle_scanner.go        # Background idle pod recycler
│   ├── heartbeat/
│   │   ├── tracker.go             # Redis SET with TTL on heartbeat received
│   │   └── scanner.go             # Background scanner: detect expired heartbeat keys
│   ├── events/
│   │   ├── emitter.go             # Kafka producer (runtime.lifecycle, monitor.alerts)
│   │   ├── fanout.go              # In-process channel fan-out for gRPC stream subscribers
│   │   └── envelope.go            # Canonical event envelope builder
│   ├── state/
│   │   ├── store.go               # pgx/v5 pool and typed query functions
│   │   ├── queries.go             # All SQL (CREATE, GET, UPDATE runtimes/warm_pool/task_plans)
│   │   └── migrations.go          # golang-migrate embedded SQL migrations
│   └── artifacts/
│       ├── collector.go           # Fetch pod logs + output files → aws-sdk-go-v2 upload
│       └── manifest.go            # Build ArtifactEntry manifest
├── api/grpc/
│   ├── v1/                        # Generated protobuf Go stubs (do not edit)
│   └── server.go                  # RuntimeControlServiceServer — delegates to internal/
├── pkg/
│   ├── k8s/
│   │   ├── client.go              # In-cluster + kubeconfig client-go setup
│   │   └── pods.go                # Create, get, list, delete v1.Pod
│   ├── config/
│   │   └── config.go              # Config struct + env var loading
│   └── health/
│       └── handler.go             # /healthz, /readyz, dependency health checks
├── proto/
│   └── runtime_controller.proto  # Source proto (7 RPCs, all messages)
├── deploy/helm/runtime-controller/
│   ├── Chart.yaml
│   ├── values.yaml                # Defaults: replicas=1, resources, config
│   ├── values-prod.yaml           # Production: replicas=3, larger resources
│   └── templates/
│       ├── deployment.yaml
│       ├── service.yaml           # ClusterIP: 50051 (gRPC) + 8080 (HTTP)
│       ├── serviceaccount.yaml
│       ├── clusterrole.yaml       # pods CRUD in platform-execution
│       ├── clusterrolebinding.yaml
│       ├── configmap.yaml         # Reconciler config, sanitizer patterns URL
│       └── network-policy.yaml    # Allow platform-control + platform-execution on 50051
├── testdata/
│   └── docker-compose.yml        # PostgreSQL + Redis for integration tests
├── Dockerfile                     # Multi-stage: golang:1.22-alpine + distroless/static
├── go.mod
└── go.sum
```

**Structure Decision**: Standard Go satellite service layout matching `services/reasoning-engine/` per constitution §3.2. `internal/` enforces package privacy. `api/grpc/` separates generated stubs from the server handler. `pkg/` contains reusable, importable packages (config, k8s client, health). The Helm chart co-located in `deploy/helm/runtime-controller/` follows the established pattern for all infrastructure components.

## Implementation Phases

### Phase 0: Research (Complete)

All technical decisions resolved in [research.md](research.md):
- Go satellite service architecture following `services/reasoning-engine/` pattern
- `client-go 0.31+` with in-cluster config; presigned URL + init container for agent package mounting
- `pgx/v5` direct SQL (no ORM); 4 tables (runtimes, warm_pool_pods, task_plan_records, runtime_events)
- Redis TTL heartbeat tracking + periodic scanner (no keyspace notifications)
- `confluent-kafka-go/v2` for lifecycle + drift Kafka events
- In-memory warm pool + PostgreSQL inventory; background replenishment + idle scanner goroutines
- Server-side gRPC streaming for events (not bidirectional); per-runtime channel fan-out
- Multi-stage distroless Docker image (golang:1.22-alpine + distroless/static-debian12)
- Kubernetes Secrets → projected volume mounts for secret injection (not env var values)

### Phase 1: Design & Contracts (Complete)

Artifacts generated:
- [data-model.md](data-model.md) — Runtime state machine, PostgreSQL schema (4 tables), protobuf definition (7 RPCs), Go package layout, pod spec template, configuration table
- [contracts/grpc-service.md](contracts/grpc-service.md) — All 7 RPC contracts with request/response fields, error codes, Kafka event schemas, network access table
- [quickstart.md](quickstart.md) — 15-section build, deploy, and test guide

### Phase 2: Implementation (tasks.md — generated by /speckit.tasks)

**P1 — US1**: Pod launch + lifecycle (LaunchRuntime, GetRuntime, PauseRuntime, ResumeRuntime, StopRuntime, state persistence)  
**P1 — US2**: Reconciliation loop (background goroutine, drift detection, orphan cleanup, drift events)  
**P1 — US3**: Event streaming (StreamRuntimeEvents, gRPC server-side streaming, channel fan-out)  
**P2 — US4**: Warm pool (manager, replenisher, idle scanner, atomic dispatch)  
**P2 — US5**: Heartbeat tracking (Redis TTL, background scanner, dead-worker handling)  
**P2 — US6**: Secrets isolation (Kubernetes Secret resolution, projected volume injection)  
**P2 — US7**: Task plan persistence (TaskPlanRecord: PostgreSQL metadata + MinIO payload)  
**P2 — US8**: Artifact collection (CollectRuntimeArtifacts, MinIO upload, manifest)

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Service architecture | Go satellite binary at `services/runtime-controller/` | Constitution §3.2 — Go for concurrent pod lifecycle management |
| Pod management | `client-go 0.31+` with in-cluster ServiceAccount | Official Kubernetes Go client; constitution §2.2 |
| Agent package mounting | Presigned S3 URL + init container download | Avoids PVC latency; stateless controller |
| State persistence | `pgx/v5` direct SQL on PostgreSQL | Constitution §2.2; controller owns lifecycle domain |
| Heartbeat tracking | Redis TTL + periodic scanner | Hot state in Redis per constitution; TTL is natural for expiry |
| Event emission | `confluent-kafka-go/v2` to `runtime.lifecycle` | Constitution §2.2; Kafka for all async coordination |
| gRPC streaming | Server-side streaming (not bidirectional) | Correct pattern for event push; client doesn't need to send |
| Warm pool storage | In-memory (sync.Map) + PostgreSQL inventory | Sub-ms dispatch from memory; PostgreSQL for restart recovery |
| Secret injection | Kubernetes Secrets → projected volumes | Values never in pod env; satisfies constitution §XI |
| Container image | Multi-stage: golang:1.22-alpine + distroless/static-debian12 | <50 MB; no shell; SC-011 |
| Task plans | PostgreSQL metadata + MinIO full payload | Satisfies constitution §XII; large payloads bypass DB size limits |

## Dependencies

- **Upstream**: Feature 001 (PostgreSQL — state persistence), Feature 002 (Redis — heartbeat TTL), Feature 003 (Kafka — event emission), Feature 004 (MinIO — agent packages, artifacts, task plan payloads)
- **Downstream**: Python control plane `execution/` bounded context (calls LaunchRuntime, StopRuntime, StreamRuntimeEvents); Python client stub at `apps/control-plane/src/platform/common/clients/runtime_controller.py`
- **Parallel with**: Sandbox Manager (sibling Go satellite), Reasoning Engine (sibling Go satellite) — no dependency relationship
- **Blocks**: Agent execution workflows, multi-step orchestration, fleet operations

## Complexity Tracking

No constitution violations. The 4 background goroutines (reconciler, heartbeat scanner, warm pool replenisher, idle scanner) are inherent to the feature requirements — each handles a distinct concern that cannot be simplified away. The warm pool requires two goroutines (replenisher + idle scanner) to safely separate "add pods" from "remove pods" logic without race conditions. All goroutines are managed via `context.Context` cancellation in `main.go`.
