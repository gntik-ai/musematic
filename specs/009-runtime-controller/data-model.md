# Data Model: Runtime Controller — Agent Runtime Pod Lifecycle

**Feature**: 009-runtime-controller  
**Date**: 2026-04-10  
**Phase**: 1 — Design & Contracts

---

## 1. Runtime State Machine

```
PENDING ──────────────────→ RUNNING ──→ PAUSED ──→ RUNNING
   │                           │                      │
   │                           ├──────────────────────┤
   │                           │                      │
   └──→ FAILED                 ├──→ STOPPED           │
                               │                      │
                               ├──→ FORCE_STOPPED      │
                               │                      │
                               └──→ FAILED ←──────────┘
```

**State transitions**:

| From | Event | To |
|------|-------|----|
| — | `LaunchRuntime` requested | `PENDING` |
| `PENDING` | Pod becomes Running | `RUNNING` |
| `PENDING` | Pod fails to start | `FAILED` |
| `RUNNING` | `PauseRuntime` requested | `PAUSED` |
| `PAUSED` | `ResumeRuntime` requested | `RUNNING` |
| `RUNNING` | `StopRuntime` requested + grace period expires cleanly | `STOPPED` |
| `RUNNING` | `StopRuntime` requested + grace period exceeded → force kill | `FORCE_STOPPED` |
| `RUNNING` | Heartbeat timeout | `FAILED` (reason: `heartbeat_timeout`) |
| `RUNNING` | Pod disappeared (reconciler) | `FAILED` (reason: `pod_disappeared`) |
| `PAUSED` | Pod disappeared (reconciler) | `FAILED` (reason: `pod_disappeared`) |
| any | Orphan cleanup | `FAILED` (reason: `orphan_terminated`) |

---

## 2. PostgreSQL Schema

### 2.1 `runtimes` Table

```sql
CREATE TABLE runtimes (
    runtime_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id        UUID NOT NULL UNIQUE,
    step_id             UUID,
    workspace_id        TEXT NOT NULL,
    agent_fqn           TEXT NOT NULL,
    agent_revision      TEXT NOT NULL,
    model_binding       JSONB NOT NULL,
    state               TEXT NOT NULL CHECK (state IN (
                            'pending', 'running', 'paused',
                            'stopped', 'force_stopped', 'failed'
                        )),
    failure_reason      TEXT,
    pod_name            TEXT,
    pod_namespace       TEXT NOT NULL DEFAULT 'platform-execution',
    correlation_context JSONB NOT NULL,
    resource_limits     JSONB NOT NULL,
    secret_refs         TEXT[],
    launched_at         TIMESTAMPTZ,
    stopped_at          TIMESTAMPTZ,
    last_heartbeat_at   TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_runtimes_execution_id ON runtimes (execution_id);
CREATE INDEX idx_runtimes_workspace_state ON runtimes (workspace_id, state);
CREATE INDEX idx_runtimes_state ON runtimes (state) WHERE state IN ('pending', 'running', 'paused');
CREATE INDEX idx_runtimes_pod_name ON runtimes (pod_name) WHERE pod_name IS NOT NULL;
```

### 2.2 `warm_pool_pods` Table

```sql
CREATE TABLE warm_pool_pods (
    pod_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    TEXT NOT NULL,
    agent_type      TEXT NOT NULL,
    pod_name        TEXT NOT NULL UNIQUE,
    pod_namespace   TEXT NOT NULL DEFAULT 'platform-execution',
    status          TEXT NOT NULL CHECK (status IN ('warming', 'ready', 'dispatched', 'recycling')),
    dispatched_to   UUID REFERENCES runtimes(runtime_id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ready_at        TIMESTAMPTZ,
    idle_since      TIMESTAMPTZ,
    dispatched_at   TIMESTAMPTZ
);

CREATE INDEX idx_warm_pool_ready ON warm_pool_pods (workspace_id, agent_type, status)
    WHERE status = 'ready';
```

### 2.3 `task_plan_records` Table

```sql
CREATE TABLE task_plan_records (
    record_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id        UUID NOT NULL,
    step_id             UUID,
    workspace_id        TEXT NOT NULL,
    considered_agents   JSONB,
    selected_agent      TEXT,
    selection_rationale TEXT,
    parameters          JSONB,
    parameter_provenance JSONB,
    payload_object_key  TEXT,          -- object storage path for full payload
    persisted_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_task_plans_execution_id ON task_plan_records (execution_id);
CREATE UNIQUE INDEX idx_task_plans_execution_step ON task_plan_records (execution_id, step_id)
    WHERE step_id IS NOT NULL;
```

### 2.4 `runtime_events` Table (event log for missed-event recovery)

```sql
CREATE TABLE runtime_events (
    event_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    runtime_id      UUID NOT NULL,
    execution_id    UUID NOT NULL,
    event_type      TEXT NOT NULL,
    payload         JSONB NOT NULL,
    emitted_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_runtime_events_runtime_emitted ON runtime_events (runtime_id, emitted_at DESC);
-- Partition by emitted_at or use TTL-based cleanup (retain 7 days)
```

---

## 3. Protobuf Service Definition

```protobuf
syntax = "proto3";
package runtime_controller.v1;
option go_package = "github.com/yourorg/musematic/services/runtime-controller/api/grpc/v1";

import "google/protobuf/timestamp.proto";

// ── Enums ─────────────────────────────────────────────────────────────
enum RuntimeState {
  RUNTIME_STATE_UNSPECIFIED = 0;
  RUNTIME_STATE_PENDING     = 1;
  RUNTIME_STATE_RUNNING     = 2;
  RUNTIME_STATE_PAUSED      = 3;
  RUNTIME_STATE_STOPPED     = 4;
  RUNTIME_STATE_FORCE_STOPPED = 5;
  RUNTIME_STATE_FAILED      = 6;
}

enum RuntimeEventType {
  RUNTIME_EVENT_UNSPECIFIED      = 0;
  RUNTIME_EVENT_LAUNCHED         = 1;
  RUNTIME_EVENT_PAUSED           = 2;
  RUNTIME_EVENT_RESUMED          = 3;
  RUNTIME_EVENT_STOPPED          = 4;
  RUNTIME_EVENT_FORCE_STOPPED    = 5;
  RUNTIME_EVENT_FAILED           = 6;
  RUNTIME_EVENT_HEARTBEAT        = 7;
  RUNTIME_EVENT_ARTIFACT_COLLECTED = 8;
  RUNTIME_EVENT_DRIFT_DETECTED   = 9;
}

// ── Core Messages ──────────────────────────────────────────────────────
message CorrelationContext {
  string workspace_id     = 1;
  string conversation_id  = 2;
  string interaction_id   = 3;
  string execution_id     = 4;
  string fleet_id         = 5;
  string goal_id          = 6;
  string trace_id         = 7;
}

message ResourceLimits {
  string cpu_request    = 1;   // e.g., "500m"
  string cpu_limit      = 2;   // e.g., "2"
  string memory_request = 3;   // e.g., "256Mi"
  string memory_limit   = 4;   // e.g., "1Gi"
}

message RuntimeContract {
  string              agent_revision            = 1;
  string              model_binding             = 2;
  repeated string     policy_ids                = 3;
  CorrelationContext  correlation_context        = 4;
  string              reasoning_config_json     = 5;
  string              context_engineering_profile_id = 6;
  string              reasoning_budget_envelope_json = 7;
  ResourceLimits      resource_limits           = 8;
  repeated string     secret_refs               = 9;
  map<string,string>  env_vars                  = 10;
  string              task_plan_json            = 11;  // serialized TaskPlanRecord payload
  string              step_id                   = 12;
}

message RuntimeInfo {
  string                    runtime_id        = 1;
  string                    execution_id      = 2;
  RuntimeState              state             = 3;
  string                    failure_reason    = 4;
  string                    pod_name          = 5;
  google.protobuf.Timestamp launched_at       = 6;
  google.protobuf.Timestamp last_heartbeat_at = 7;
  CorrelationContext        correlation_context = 8;
}

message RuntimeEvent {
  string                    event_id      = 1;
  string                    runtime_id    = 2;
  string                    execution_id  = 3;
  RuntimeEventType          event_type    = 4;
  google.protobuf.Timestamp occurred_at   = 5;
  string                    details_json  = 6;
  RuntimeState              new_state     = 7;
}

// ── RPC Messages ───────────────────────────────────────────────────────
message LaunchRuntimeRequest  { RuntimeContract contract = 1; }
message LaunchRuntimeResponse { string runtime_id = 1; RuntimeState state = 2; bool warm_start = 3; }

message GetRuntimeRequest  { string execution_id = 1; }
message GetRuntimeResponse { RuntimeInfo runtime = 1; }

message PauseRuntimeRequest  { string execution_id = 1; }
message PauseRuntimeResponse { RuntimeState state = 1; }

message ResumeRuntimeRequest  { string execution_id = 1; }
message ResumeRuntimeResponse { RuntimeState state = 1; }

message StopRuntimeRequest  { string execution_id = 1; int32 grace_period_seconds = 2; }
message StopRuntimeResponse { RuntimeState state = 1; bool force_killed = 2; }

message StreamRuntimeEventsRequest {
  string execution_id      = 1;
  google.protobuf.Timestamp since = 2;  // replay events after this timestamp
}
// Response: stream RuntimeEvent

message CollectRuntimeArtifactsRequest  { string execution_id = 1; }
message CollectRuntimeArtifactsResponse {
  repeated ArtifactEntry artifacts = 1;
  bool complete = 2;
}

message ArtifactEntry {
  string object_key  = 1;   // e.g., "artifacts/{execution_id}/{filename}"
  string filename    = 2;
  int64  size_bytes  = 3;
  string content_type = 4;
  google.protobuf.Timestamp collected_at = 5;
}

// ── Service ────────────────────────────────────────────────────────────
service RuntimeControlService {
  rpc LaunchRuntime             (LaunchRuntimeRequest)              returns (LaunchRuntimeResponse);
  rpc GetRuntime                (GetRuntimeRequest)                 returns (GetRuntimeResponse);
  rpc PauseRuntime              (PauseRuntimeRequest)               returns (PauseRuntimeResponse);
  rpc ResumeRuntime             (ResumeRuntimeRequest)              returns (ResumeRuntimeResponse);
  rpc StopRuntime               (StopRuntimeRequest)                returns (StopRuntimeResponse);
  rpc StreamRuntimeEvents       (StreamRuntimeEventsRequest)        returns (stream RuntimeEvent);
  rpc CollectRuntimeArtifacts   (CollectRuntimeArtifactsRequest)    returns (CollectRuntimeArtifactsResponse);
}
```

---

## 4. Internal Package Structure

```
services/runtime-controller/
├── cmd/runtime-controller/
│   └── main.go                    # Server bootstrap: config, dependencies, lifecycle
├── internal/
│   ├── launcher/
│   │   ├── launcher.go            # LaunchRuntime: build pod spec, create pod, persist state
│   │   ├── podspec.go             # Build v1.Pod from RuntimeContract
│   │   ├── secrets.go             # Resolve secret refs → projected volume mounts
│   │   └── warmpool_dispatch.go   # Dispatch from warm pool if available
│   ├── reconciler/
│   │   ├── reconciler.go          # Background goroutine: compare DB vs k8s pod status
│   │   ├── drift.go               # Detect orphans, missing pods, state mismatches
│   │   └── repair.go              # Terminate orphans, update state, emit drift events
│   ├── warmpool/
│   │   ├── manager.go             # In-memory pool + PostgreSQL inventory
│   │   ├── replenisher.go         # Background goroutine: top-up pools
│   │   └── idle_scanner.go        # Background goroutine: recycle idle pods
│   ├── heartbeat/
│   │   ├── tracker.go             # Redis TTL set/reset per heartbeat received
│   │   └── scanner.go             # Background goroutine: detect expired heartbeats
│   ├── events/
│   │   ├── emitter.go             # Kafka producer: lifecycle + drift events
│   │   ├── fanout.go              # In-process fan-out to gRPC stream subscribers
│   │   └── envelope.go            # Build canonical event envelope
│   ├── state/
│   │   ├── store.go               # PostgreSQL operations (pgx/v5 pool)
│   │   ├── queries.go             # All SQL queries as typed functions
│   │   └── migrations.go          # Embedded SQL migrations (golang-migrate)
│   └── artifacts/
│       ├── collector.go           # Collect pod logs + output files → object storage
│       └── manifest.go            # Build artifact manifest
├── api/grpc/
│   ├── v1/                        # Generated protobuf Go stubs (do not edit)
│   └── server.go                  # RuntimeControlServiceServer implementation (delegates to internal/)
├── pkg/
│   ├── k8s/
│   │   ├── client.go              # client-go setup: in-cluster + kubeconfig fallback
│   │   ├── pods.go                # Create, get, list, delete pods
│   │   └── rbac.go                # ServiceAccount / RBAC documentation (not code)
│   ├── config/
│   │   └── config.go              # Viper-based config: env vars, defaults
│   └── health/
│       └── handler.go             # /healthz and /readyz HTTP handlers
├── proto/
│   └── runtime_controller.proto  # Source protobuf definition
├── deploy/helm/runtime-controller/
│   ├── Chart.yaml
│   ├── values.yaml
│   ├── values-prod.yaml
│   └── templates/
│       ├── deployment.yaml
│       ├── service.yaml           # ClusterIP: gRPC 50051
│       ├── serviceaccount.yaml
│       ├── clusterrole.yaml       # Pods CRUD in platform-execution
│       ├── clusterrolebinding.yaml
│       ├── configmap.yaml         # Sanitizer patterns, reconciler config
│       └── network-policy.yaml
├── Dockerfile
├── go.mod
└── go.sum
```

---

## 5. Key Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `GRPC_PORT` | `50051` | gRPC server port |
| `HTTP_PORT` | `8080` | Health + metrics HTTP port |
| `POSTGRES_DSN` | required | PostgreSQL connection string |
| `REDIS_ADDR` | required | Redis cluster address |
| `KAFKA_BROKERS` | required | Kafka broker list |
| `MINIO_ENDPOINT` | required | MinIO endpoint URL |
| `MINIO_BUCKET` | `musematic-artifacts` | Object storage bucket |
| `K8S_NAMESPACE` | `platform-execution` | Namespace for runtime pods |
| `RECONCILE_INTERVAL` | `30s` | Reconciliation loop interval |
| `HEARTBEAT_TIMEOUT` | `60s` | Heartbeat expiry window |
| `HEARTBEAT_CHECK_INTERVAL` | `10s` | Heartbeat scanner interval |
| `WARM_POOL_IDLE_TIMEOUT` | `5m` | Warm pod idle recycle timeout |
| `WARM_POOL_REPLENISH_INTERVAL` | `30s` | Warm pool replenishment check |
| `STOP_GRACE_PERIOD` | `30s` | Default graceful stop grace period |
| `AGENT_PACKAGE_PRESIGN_TTL` | `2h` | Presigned URL validity for agent package |

---

## 6. Runtime Pod Spec (key fields)

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: runtime-{execution_id_short}
  namespace: platform-execution
  labels:
    app: agent-runtime
    execution_id: "{execution_id}"
    workspace_id: "{workspace_id}"
    agent_fqn: "{agent_fqn_sanitized}"
    managed_by: runtime-controller
spec:
  serviceAccountName: agent-runtime-sa  # minimal SA, no cluster access
  initContainers:
    - name: package-downloader
      image: curlimages/curl:latest
      command: ["/bin/sh", "-c", "curl -o /agent-package/package.tar.gz $AGENT_PACKAGE_URL && tar xzf /agent-package/package.tar.gz -C /agent-package/"]
      env:
        - name: AGENT_PACKAGE_URL
          value: "{presigned_s3_url}"
      volumeMounts:
        - name: agent-package
          mountPath: /agent-package
  containers:
    - name: agent-runtime
      image: "{model_runtime_image}"
      resources:
        requests: { cpu: "{cpu_request}", memory: "{memory_request}" }
        limits:   { cpu: "{cpu_limit}",   memory: "{memory_limit}" }
      env:
        - name: EXECUTION_ID
          value: "{execution_id}"
        - name: WORKSPACE_ID
          value: "{workspace_id}"
        - name: SECRETS_REF_API_KEY        # pointer only, not value
          value: "/run/secrets/api-key"
        - name: SANITIZER_PATTERNS_URL
          value: "{sanitizer_configmap_url}"
      volumeMounts:
        - name: agent-package
          mountPath: /agent
          readOnly: true
        - name: secrets-volume
          mountPath: /run/secrets
          readOnly: true
  volumes:
    - name: agent-package
      emptyDir: {}
    - name: secrets-volume
      projected:
        sources:
          - secret:
              name: "{secret_name}"
              items:
                - key: api-key
                  path: api-key
  restartPolicy: Never
```
