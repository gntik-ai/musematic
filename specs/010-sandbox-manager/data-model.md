# Data Model: Sandbox Manager — Isolated Code Execution

**Feature**: 010-sandbox-manager  
**Date**: 2026-04-10  
**Phase**: 1 — Design & Contracts

---

## 1. Sandbox State Machine

```
CREATING ──→ READY ──→ EXECUTING ──→ READY (multi-step)
   │            │           │            │
   │            │           │            └──→ COMPLETED
   │            │           │                    │
   └──→ FAILED ←┘───←──────┘                    │
                                                 ↓
                    TERMINATED ←─────────────────┘
```

**State transitions**:

| From | Event | To |
|------|-------|----|
| — | `CreateSandbox` requested | `CREATING` |
| `CREATING` | Pod becomes Running | `READY` |
| `CREATING` | Pod fails to start | `FAILED` |
| `READY` | `ExecuteSandboxStep` submitted | `EXECUTING` |
| `EXECUTING` | Code execution completes (exit code 0 or non-zero) | `READY` |
| `EXECUTING` | Execution timeout | `FAILED` |
| `EXECUTING` | OOM kill | `FAILED` |
| `READY` | `TerminateSandbox` requested | `TERMINATED` |
| `READY` | Idle timeout expired (orphan scanner) | `TERMINATED` |
| `COMPLETED` | `CollectSandboxArtifacts` completed | `TERMINATED` |
| `COMPLETED` | `TerminateSandbox` requested | `TERMINATED` |
| any active | Pod evicted/disappeared | `FAILED` |
| `FAILED` | Cleanup completed | `TERMINATED` |

---

## 2. PostgreSQL Schema

### 2.1 `sandboxes` Table (observability metadata)

```sql
CREATE TABLE sandboxes (
    sandbox_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id    UUID NOT NULL,
    workspace_id    TEXT NOT NULL,
    template        TEXT NOT NULL,
    state           TEXT NOT NULL CHECK (state IN (
                        'creating', 'ready', 'executing',
                        'completed', 'failed', 'terminated'
                    )),
    failure_reason  TEXT,
    pod_name        TEXT,
    pod_namespace   TEXT NOT NULL DEFAULT 'platform-execution',
    resource_limits JSONB NOT NULL,
    network_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    total_steps     INT NOT NULL DEFAULT 0,
    total_duration_ms BIGINT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ready_at        TIMESTAMPTZ,
    terminated_at   TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sandboxes_execution_id ON sandboxes (execution_id);
CREATE INDEX idx_sandboxes_workspace_state ON sandboxes (workspace_id, state);
CREATE INDEX idx_sandboxes_state ON sandboxes (state) WHERE state IN ('creating', 'ready', 'executing');
```

### 2.2 `sandbox_events` Table (event log)

```sql
CREATE TABLE sandbox_events (
    event_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sandbox_id   UUID NOT NULL,
    execution_id UUID NOT NULL,
    event_type   TEXT NOT NULL,
    payload      JSONB NOT NULL,
    emitted_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sandbox_events_sandbox_emitted ON sandbox_events (sandbox_id, emitted_at DESC);
-- Retain 7 days; cleanup via TTL-based deletion or partition
```

---

## 3. Protobuf Service Definition

```protobuf
syntax = "proto3";
package sandbox_manager.v1;
option go_package = "github.com/yourorg/musematic/services/sandbox-manager/api/grpc/v1";

import "google/protobuf/timestamp.proto";
import "google/protobuf/duration.proto";

// ── Enums ─────────────────────────────────────────────────────────────
enum SandboxState {
  SANDBOX_STATE_UNSPECIFIED = 0;
  SANDBOX_STATE_CREATING    = 1;
  SANDBOX_STATE_READY       = 2;
  SANDBOX_STATE_EXECUTING   = 3;
  SANDBOX_STATE_COMPLETED   = 4;
  SANDBOX_STATE_FAILED      = 5;
  SANDBOX_STATE_TERMINATED  = 6;
}

enum SandboxEventType {
  SANDBOX_EVENT_UNSPECIFIED   = 0;
  SANDBOX_EVENT_CREATED       = 1;
  SANDBOX_EVENT_READY         = 2;
  SANDBOX_EVENT_STEP_STARTED  = 3;
  SANDBOX_EVENT_STEP_COMPLETED = 4;
  SANDBOX_EVENT_COMPLETED     = 5;
  SANDBOX_EVENT_FAILED        = 6;
  SANDBOX_EVENT_TERMINATED    = 7;
  SANDBOX_EVENT_ARTIFACT_COLLECTED = 8;
}

// ── Core Messages ──────────────────────────────────────────────────────
message SandboxTemplate {
  string name           = 1;   // e.g., "python3.12", "node20", "go1.22", "code-as-reasoning"
  string image          = 2;   // container image
  ResourceLimits limits = 3;   // default resource limits
  int32 timeout_seconds = 4;   // default execution timeout
}

message ResourceLimits {
  string cpu_request    = 1;   // e.g., "100m"
  string cpu_limit      = 2;   // e.g., "500m"
  string memory_request = 3;   // e.g., "128Mi"
  string memory_limit   = 4;   // e.g., "256Mi"
}

message CorrelationContext {
  string workspace_id   = 1;
  string execution_id   = 2;
  string interaction_id = 3;
  string trace_id       = 4;
}

message SandboxInfo {
  string                    sandbox_id    = 1;
  string                    execution_id  = 2;
  SandboxState              state         = 3;
  string                    failure_reason = 4;
  string                    template      = 5;
  string                    pod_name      = 6;
  google.protobuf.Timestamp created_at    = 7;
  int32                     total_steps   = 8;
  CorrelationContext        correlation   = 9;
}

message ExecutionResult {
  string stdout       = 1;
  string stderr       = 2;
  int32  exit_code    = 3;
  google.protobuf.Duration duration = 4;
  bool   timed_out    = 5;
  bool   oom_killed   = 6;
  string structured_output = 7;  // parsed JSON for code-as-reasoning template
  bool   output_truncated = 8;   // true if stdout/stderr hit size limit
}

message SandboxEvent {
  string                    event_id     = 1;
  string                    sandbox_id   = 2;
  string                    execution_id = 3;
  SandboxEventType          event_type   = 4;
  google.protobuf.Timestamp occurred_at  = 5;
  string                    details_json = 6;
  SandboxState              new_state    = 7;
}

message ArtifactEntry {
  string object_key   = 1;   // e.g., "sandbox-artifacts/{exec_id}/{sandbox_id}/{filename}"
  string filename     = 2;
  int64  size_bytes   = 3;
  string content_type = 4;
  google.protobuf.Timestamp collected_at = 5;
}

// ── RPC Messages ───────────────────────────────────────────────────────
message CreateSandboxRequest {
  string              template_name       = 1;   // "python3.12", "node20", etc.
  CorrelationContext  correlation         = 2;
  ResourceLimits      resource_overrides  = 3;   // optional: override template defaults
  int32               timeout_override    = 4;   // optional: override default timeout (seconds)
  bool                network_enabled     = 5;   // default false
  repeated string     egress_allowlist    = 6;   // domains/CIDRs allowed if network_enabled
  map<string,string>  env_vars            = 7;   // additional env vars for the sandbox
  repeated string     pip_packages        = 8;   // Python packages to install at creation
  repeated string     npm_packages        = 9;   // Node packages to install at creation
}

message CreateSandboxResponse {
  string       sandbox_id = 1;
  SandboxState state      = 2;
}

message ExecuteSandboxStepRequest {
  string sandbox_id       = 1;
  string code             = 2;   // code to execute
  int32  timeout_override = 3;   // optional per-step timeout
}

message ExecuteSandboxStepResponse {
  ExecutionResult result   = 1;
  int32           step_num = 2;  // sequential step number
}

message StreamSandboxLogsRequest {
  string sandbox_id = 1;
  bool   follow     = 2;   // true = stream as produced; false = return buffered logs
}

message SandboxLogLine {
  string                    line      = 1;
  string                    stream    = 2;   // "stdout" or "stderr"
  google.protobuf.Timestamp timestamp = 3;
}

message TerminateSandboxRequest {
  string sandbox_id          = 1;
  int32  grace_period_seconds = 2;  // default 5s
}

message TerminateSandboxResponse {
  SandboxState state = 1;
}

message CollectSandboxArtifactsRequest {
  string sandbox_id = 1;
}

message CollectSandboxArtifactsResponse {
  repeated ArtifactEntry artifacts = 1;
  bool complete = 2;
}

// ── Service ────────────────────────────────────────────────────────────
service SandboxService {
  rpc CreateSandbox           (CreateSandboxRequest)           returns (CreateSandboxResponse);
  rpc ExecuteSandboxStep      (ExecuteSandboxStepRequest)      returns (ExecuteSandboxStepResponse);
  rpc StreamSandboxLogs       (StreamSandboxLogsRequest)       returns (stream SandboxLogLine);
  rpc TerminateSandbox        (TerminateSandboxRequest)        returns (TerminateSandboxResponse);
  rpc CollectSandboxArtifacts (CollectSandboxArtifactsRequest) returns (CollectSandboxArtifactsResponse);
}
```

---

## 4. Internal Package Structure

```
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

**Structure Decision**: Standard Go satellite service layout matching `services/runtime-controller/`. `internal/` enforces package privacy. `pkg/k8s/exec.go` adds remotecommand helpers not present in runtime-controller. Templates are Go structs in `internal/templates/`, not external config. Two NetworkPolicy templates in Helm (deny-all + conditional allow).

---

## 5. Key Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `GRPC_PORT` | `50053` | gRPC server port |
| `HTTP_PORT` | `8080` | Health + metrics HTTP port |
| `POSTGRES_DSN` | required | PostgreSQL connection string |
| `KAFKA_BROKERS` | required | Kafka broker list |
| `MINIO_ENDPOINT` | required | MinIO endpoint URL |
| `MINIO_BUCKET` | `musematic-artifacts` | Object storage bucket |
| `K8S_NAMESPACE` | `platform-execution` | Namespace for sandbox pods |
| `DEFAULT_TIMEOUT` | `30s` | Default execution step timeout |
| `MAX_TIMEOUT` | `300s` | Maximum allowed timeout (ActiveDeadlineSeconds) |
| `MAX_OUTPUT_SIZE` | `10485760` | Maximum stdout/stderr size (10MB) |
| `ORPHAN_SCAN_INTERVAL` | `60s` | Orphan scanner interval |
| `IDLE_TIMEOUT` | `300s` | Idle sandbox auto-termination |
| `MAX_CONCURRENT_SANDBOXES` | `50` | Maximum concurrent sandbox pods |

---

## 6. Sandbox Pod Spec (key fields)

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: sandbox-{sandbox_id_short}
  namespace: platform-execution
  labels:
    app: sandbox
    musematic/sandbox: "true"
    sandbox_id: "{sandbox_id}"
    execution_id: "{execution_id}"
    workspace_id: "{workspace_id}"
    managed-by: sandbox-manager
    # musematic/network-allowed: "true"  # only if network_enabled
spec:
  automountServiceAccountToken: false
  hostNetwork: false
  hostPID: false
  hostIPC: false
  enableServiceLinks: false
  restartPolicy: Never
  activeDeadlineSeconds: 300
  dnsPolicy: None         # or ClusterFirst if network_enabled
  dnsConfig: {}           # empty if network disabled
  securityContext:
    runAsNonRoot: true
    runAsUser: 65534
    runAsGroup: 65534
    fsGroup: 65534
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: sandbox
      image: "{template_image}"    # e.g., python:3.12-slim
      command: ["sleep", "infinity"]
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: ["ALL"]
      resources:
        requests: { cpu: "{cpu_request}", memory: "{memory_request}" }
        limits:   { cpu: "{cpu_limit}",   memory: "{memory_limit}" }
      env:
        - name: SANDBOX_ID
          value: "{sandbox_id}"
        - name: EXECUTION_ID
          value: "{execution_id}"
      volumeMounts:
        - name: tmp
          mountPath: /tmp
        - name: workspace
          mountPath: /workspace
        - name: output
          mountPath: /output
  volumes:
    - name: tmp
      emptyDir: { sizeLimit: 256Mi }
    - name: workspace
      emptyDir: { sizeLimit: 512Mi }
    - name: output
      emptyDir: { sizeLimit: 128Mi }
```
