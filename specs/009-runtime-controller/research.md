# Research: Runtime Controller — Agent Runtime Pod Lifecycle

**Feature**: 009-runtime-controller  
**Date**: 2026-04-10  
**Phase**: 0 — Pre-design research

---

## Decision 1: Go Service Architecture — Satellite Binary at `services/runtime-controller/`

**Decision**: The runtime controller is an independent Go binary at `services/runtime-controller/`, following the same satellite service pattern as `services/reasoning-engine/`. It exposes a gRPC server (`google.golang.org/grpc 1.67+`) and communicates with the Python control plane via gRPC. The service uses the standard Go layout: `cmd/runtime-controller/main.go` (entrypoint), `internal/` (private packages), `api/grpc/` (gRPC server handler), `pkg/k8s/` (Kubernetes client helpers).

**Rationale**: Constitution §3.2 establishes the Go satellite service pattern for components requiring sub-millisecond hot paths and concurrent goroutines. The runtime controller manages concurrent pod lifecycle operations, heartbeat tracking timers, and a reconciliation loop — all workloads that benefit from Go's goroutine model over Python's async model. The constitution explicitly registers `services/reasoning-engine/` as the pattern; `runtime-controller` follows identically.

**Alternatives considered**:
- Python control plane extension: would require blocking async code for Kubernetes pod operations. Rejected — Go satellite service is the mandated pattern for this type of work.
- Kubernetes Operator (controller-runtime): adds CRD management and webhook complexity not needed here. Rejected — the controller manages pods, not CRDs.

---

## Decision 2: Kubernetes Pod Management — `client-go 0.31+` with In-Cluster Config

**Decision**: Pod lifecycle (create, get, delete, list) is managed via `k8s.io/client-go 0.31+` using in-cluster `ServiceAccount` credentials when running in Kubernetes, and a `kubeconfig` file for local development. Agent runtime pods are created in the `platform-execution` namespace. The runtime controller's ServiceAccount is granted RBAC permissions: `create`, `get`, `list`, `watch`, `delete` on `pods` in `platform-execution`. Pod specs are built programmatically from the runtime contract.

**Agent package mounting**: The agent package is stored in MinIO (feature 004). At pod launch, the controller generates a presigned S3 URL (valid for the pod lifetime + 1 hour) and injects it as an environment variable `AGENT_PACKAGE_URL`. The agent pod's init container downloads and extracts the package to a shared volume, which the main container mounts read-only. This avoids PVC provisioning latency.

**Rationale**: `client-go` is the official Kubernetes API client for Go. In-cluster config is the standard production pattern. Presigned URL + init container avoids managing PVCs or volume plugins, keeps the controller stateless with respect to storage, and is compatible with distroless runtime images.

**Alternatives considered**:
- EmptyDir + init container with direct S3 SDK: same approach, init container downloads package. This IS the chosen approach.
- PVC (PersistentVolumeClaim) per runtime: higher latency for PVC provisioning (5–30 seconds), requires storage class configuration. Rejected — presigned URL is faster and simpler.
- hostPath mount from shared NFS: requires NFS setup and shared filesystem. Rejected.

---

## Decision 3: State Persistence — PostgreSQL via `pgx/v5`

**Decision**: Runtime state is persisted in PostgreSQL using `github.com/jackc/pgx/v5` with a connection pool (`pgx/v5/pgxpool`). No ORM is used — raw SQL with typed scan structs. Three tables are defined: `runtimes` (runtime records with state machine), `warm_pool_pods` (warm pool inventory), and `task_plan_records` (pre-execution auditable records). The runtime controller connects directly to PostgreSQL — it does NOT go through the Python control plane for state writes.

**Rationale**: Constitution §2.2 mandates `pgx/v5` for PostgreSQL in Go services. Direct PostgreSQL access from the runtime controller is correct because the controller owns the runtime lifecycle domain — it does not cross bounded context boundaries. The Python control plane's `execution/` bounded context reads runtime state via Kafka events or a read-only query API, not by sharing tables.

**Alternatives considered**:
- GORM: ORM for Go. Constitution does not mandate it; adds reflection overhead. Rejected — raw pgx/v5 is the mandate.
- Going through the Python control plane REST API for state writes: introduces latency and a circular dependency at the hot path. Rejected.

---

## Decision 4: Heartbeat Tracking — Redis TTL with Background Scanner

**Decision**: Each running runtime's heartbeat is tracked in Redis (`github.com/redis/go-redis/v9`) using key `heartbeat:{runtime_id}` with TTL equal to the configured heartbeat timeout (default 60 seconds). When a heartbeat is received, the controller calls `SET heartbeat:{runtime_id} {timestamp} EX {timeout}` to reset the TTL. A background goroutine runs every 10 seconds (`heartbeat_check_interval`), querying PostgreSQL for all active runtimes and checking which ones have no corresponding Redis key (TTL expired). These are marked as `heartbeat_timeout` failed and a dead-worker event is emitted.

**Rationale**: Redis TTL-based expiry is the natural fit for heartbeat tracking — the key disappears automatically when the timeout elapses. The scanner approach (periodic check rather than keyspace notifications) is simpler and more predictable. Redis is already mandated by the constitution for hot state. The scanner interval (10 seconds) is short enough for accurate detection within the 60-second timeout window.

**Alternatives considered**:
- Redis keyspace notifications (subscribe to `__keyevent@0__:expired`): reactive and immediate but requires keyspace notifications enabled on the Redis server. More complex to implement reliably with cluster mode. Rejected — periodic scanner is simpler.
- PostgreSQL-only heartbeat (store last_heartbeat timestamp, scan with SQL): works but adds PostgreSQL query load every 10 seconds. Rejected — Redis is the correct hot-state store.
- In-memory timer per runtime: does not survive controller restart. Rejected.

---

## Decision 5: Event Emission — Kafka via `confluent-kafka-go v2`

**Decision**: Lifecycle events are emitted to the `runtime.lifecycle` Kafka topic. Drift events are emitted to the `monitor.alerts` topic. Both use `github.com/confluentinc/confluent-kafka-go/v2` (constitution §2.2). Events are serialized as JSON matching the canonical event envelope (`CorrelationContext` + `event_type` + `payload`). Lifecycle events are produced synchronously (wait for ACK) to ensure at-least-once delivery. Drift events are produced fire-and-forget for lower latency in the reconciliation loop.

**Rationale**: Constitution §2.2 mandates `confluent-kafka-go/v2` for Kafka in Go. The `runtime.lifecycle` topic is the downstream source for the execution engine event stream subscription. Using the canonical event envelope ensures compatibility with all Kafka consumers in the platform.

**Alternatives considered**:
- `segmentio/kafka-go`: a popular alternative. Not in the constitution. Rejected.
- Direct gRPC push from controller to execution engine: tight coupling, no replay capability. Rejected — Kafka is the mandated async coordination pattern.

---

## Decision 6: Warm Pool — In-Memory Pool with PostgreSQL Inventory

**Decision**: The warm pool is managed as an in-memory `sync.Map` keyed by `{workspace_id}/{agent_type}` containing a slice of available pod identifiers. The pool inventory (pod names, creation timestamps, idle timestamps) is also persisted in the `warm_pool_pods` PostgreSQL table for recovery after restart. On controller startup, existing warm pods are loaded from the database and validated against Kubernetes pod status. A background replenishment goroutine runs every 30 seconds to top up pools that fall below their target size. A separate idle scanner terminates and replaces pods that have been idle beyond `warm_pool_idle_timeout` (default 5 minutes).

**Rationale**: In-memory access gives sub-millisecond dispatch latency. PostgreSQL persistence enables recovery after restart. The replenishment goroutine ensures the pool stays full without synchronous blocking. Separating idle scanning from replenishment simplifies each goroutine's logic.

**Alternatives considered**:
- Redis-backed warm pool (store pod IDs in Redis sets): adds Redis complexity for a use case where PostgreSQL persistence is sufficient. Rejected — warm pool is not a hot-path read after dispatch.
- Kubernetes Deployment with readyReplicas for warm pool: would use a Deployment instead of individual pre-created pods, but warm pods need per-workspace/agent-type differentiation. Rejected — Deployment-based warm pool requires label selectors per workspace which is harder to manage.

---

## Decision 7: gRPC Server with Server-Side Streaming for Events

**Decision**: The `StreamRuntimeEvents` RPC uses **server-side streaming** (`returns (stream RuntimeEvent)`) — not bidirectional streaming. The server maintains a per-runtime fan-out channel registry: when a runtime transitions state, the controller fan-outs the event to all active server-side streaming connections for that runtime. Stream lifecycle: opened when a subscriber calls `StreamRuntimeEvents`, closed when the client cancels the context or when the subscription times out. Missed events during disconnection are not replayed from Kafka (the client re-subscribes and resumes from the current state).

**Rationale**: Server-side streaming is the correct gRPC pattern for event delivery (client initiates, server pushes). Bidirectional streaming adds complexity without benefit here — the client does not need to send messages after initial subscription. Fan-out via per-runtime channels is the idiomatic Go pattern for multiplexing events to multiple subscribers.

**Alternatives considered**:
- Polling (client repeatedly calls `GetRuntime`): adds latency and load. Rejected — streaming is the correct pattern.
- Bidirectional streaming: allows client to send filter updates during the stream. Not needed based on spec. Rejected for simplicity.
- Webhook callbacks: requires the client to expose an HTTP endpoint. Not applicable for gRPC service consumers. Rejected.

---

## Decision 8: Container Image — Multi-Stage Distroless under 100 MB

**Decision**: The Dockerfile uses a two-stage build:
1. **Builder**: `golang:1.22-alpine` — compiles the binary with `CGO_ENABLED=0 GOOS=linux GOARCH=amd64`
2. **Runtime**: `gcr.io/distroless/static-debian12` — minimal image with no shell, no package manager, non-root user

The binary is statically linked (no libc dependency, enabling distroless). CA certificates are copied from the builder to the runtime image for TLS connections. The resulting image is expected to be under 50 MB (binary ~20 MB, distroless base ~5 MB).

**Rationale**: Distroless images have no shell and minimal attack surface. Static linking with `CGO_ENABLED=0` is required for distroless compatibility. The <100 MB requirement from SC-011 is easily met — similar Go binaries in distroless images are 30–60 MB.

**Alternatives considered**:
- Alpine base image: ~7 MB base but includes a shell (attack surface). Rejected — distroless is more secure.
- Scratch base image: no CA certificates for TLS. Rejected — gRPC and Kubernetes API require TLS.

---

## Decision 9: Secret Resolution — Kubernetes Secrets at Pod Launch

**Decision**: Secret references in the runtime contract are Kubernetes Secret names in the `platform-execution` namespace. At pod launch, the runtime controller resolves each secret reference by calling the Kubernetes API (`GET /api/v1/namespaces/platform-execution/secrets/{name}`) to retrieve the secret data. Secret values are injected into the runtime pod as a **projected volume** mounted at `/run/secrets/` (read-only, accessible only to tool execution processes). The runtime pod's main container (the LLM process) receives only `SECRETS_REF_*` environment variables listing secret file paths — not the values. The tool execution framework reads secret values from the mounted volume at invocation time.

**Tool output sanitization**: The runtime controller injects a `SANITIZER_PATTERNS_URL` environment variable pointing to a ConfigMap/object-storage location where the tool gateway reads known secret patterns (regex patterns for API keys, tokens). This is a configuration injection — the actual sanitization runs in the tool gateway process within the pod, not in the controller.

**Rationale**: Kubernetes Secrets are the native secret management mechanism for Kubernetes workloads. Projected volumes ensure secret values are written to the pod's filesystem but are not visible in the pod spec (unlike env var injection which appears in pod metadata). This strictly satisfies constitution §XI (secrets never in LLM context). Vault integration (HashiCorp Vault, etc.) can be layered on later by having the controller resolve vault references before creating the Kubernetes Secret — the pod-facing interface remains the projected volume.

**Alternatives considered**:
- HashiCorp Vault Agent: injects secrets via sidecar. Adds a sidecar per pod. More powerful but adds complexity. Can be added as a future enhancement. Rejected for v1.
- Environment variable injection: secret values appear in pod metadata and `kubectl describe pod` output. Security risk. Rejected for secret values (only `SECRETS_REF_*` pointers use env vars).
