# Data Model: Simulation Controller

**Feature**: 012-simulation-controller  
**Date**: 2026-04-10  
**Phase**: 1 — Design

---

## State Machines

### Simulation Lifecycle

```
CREATING → RUNNING → COMPLETED
                   → FAILED
        → FAILED   (pod creation error)
RUNNING → TERMINATED (explicit termination request)
COMPLETED → TERMINATED (cleanup after collection)
```

- **CREATING**: Pod creation in progress; DB row inserted; not yet running
- **RUNNING**: Pod in Running phase; simulation workload executing
- **COMPLETED**: Pod exited 0; artifacts available for collection
- **FAILED**: Pod exited non-zero, crashed, OOM-killed, or creation error
- **TERMINATED**: Explicit termination requested; pod deleted; resources cleaned up

### AccreditedTestEnv Lifecycle

```
PROVISIONING → RUNNING → COMPLETED
                       → FAILED
```

- **PROVISIONING**: ConfigMap created; ATE pod creation in progress
- **RUNNING**: ATE agent-runner executing scenarios sequentially
- **COMPLETED**: All scenarios executed; report generated and uploaded to MinIO
- **FAILED**: ATE pod crashed or scenario runner error

---

## Kubernetes Resources

### Simulation Pod Spec Template

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: "sim-{simulation_id}"
  namespace: platform-simulation
  labels:
    app: simulation-pod
    simulation: "true"
    simulation-id: "{simulation_id}"
  annotations:
    simulation-created-by: simulation-controller
spec:
  serviceAccountName: simulation-pod-sa   # no RBAC access to cluster API
  automountServiceAccountToken: false
  securityContext:
    runAsNonRoot: true
    runAsUser: 65534
    fsGroup: 65534
  containers:
    - name: simulation
      image: "{agent_image}"
      env:
        - name: SIMULATION
          value: "true"
        - name: SIMULATION_ID
          value: "{simulation_id}"
        - name: SIMULATION_BUCKET
          value: simulation-artifacts
        - name: SIMULATION_ARTIFACTS_PREFIX
          value: "{simulation_id}"
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: ["ALL"]
      resources:
        requests:
          cpu: "{cpu_request}"
          memory: "{memory_request}"
        limits:
          cpu: "{cpu_limit}"
          memory: "{memory_limit}"
      volumeMounts:
        - name: output
          mountPath: /output
        - name: workspace
          mountPath: /workspace
        - name: tmp
          mountPath: /tmp
  volumes:
    - name: output
      emptyDir:
        sizeLimit: 512Mi
    - name: workspace
      emptyDir:
        sizeLimit: 1Gi
    - name: tmp
      emptyDir:
        sizeLimit: 256Mi
  restartPolicy: Never
  activeDeadlineSeconds: "{max_duration_seconds}"
```

### ATE Pod Additional Spec (extends simulation pod template)

```yaml
# Additional volume for ConfigMap-injected scenarios
volumes:
  - name: ate-config
    configMap:
      name: "ate-{session_id}"
volumeMounts:
  - name: ate-config
    mountPath: /ate
    readOnly: true
env:
  - name: ATE_SESSION_ID
    value: "{session_id}"
  - name: ATE_SCENARIOS_PATH
    value: /ate/scenarios.json
```

### NetworkPolicy — Deny All Production Egress

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: simulation-deny-production-egress
  namespace: platform-simulation
spec:
  podSelector:
    matchLabels:
      simulation: "true"
  policyTypes:
    - Egress
  egress:
    # Allow intra-namespace communication only
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: platform-simulation
    # Allow MinIO (simulation-artifacts bucket) and Kafka (simulation.events)
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: platform-data
      ports:
        - port: 9000   # MinIO
        - port: 9092   # Kafka
```

---

## PostgreSQL Tables

```sql
-- Core simulation records
CREATE TABLE simulations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    simulation_id       UUID NOT NULL UNIQUE,
    agent_image         TEXT NOT NULL,
    agent_config_json   JSONB NOT NULL DEFAULT '{}',
    status              TEXT NOT NULL CHECK (status IN ('CREATING','RUNNING','COMPLETED','FAILED','TERMINATED')),
    namespace           TEXT NOT NULL DEFAULT 'platform-simulation',
    pod_name            TEXT,
    cpu_request         TEXT NOT NULL DEFAULT '500m',
    memory_request      TEXT NOT NULL DEFAULT '512Mi',
    max_duration_seconds INTEGER NOT NULL DEFAULT 3600,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    terminated_at       TIMESTAMPTZ,
    error_message       TEXT
);

CREATE INDEX idx_simulations_status ON simulations (status);
CREATE INDEX idx_simulations_created_at ON simulations (created_at);

-- Simulation artifact references
CREATE TABLE simulation_artifacts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    simulation_id   UUID NOT NULL REFERENCES simulations(simulation_id) ON DELETE CASCADE,
    object_key      TEXT NOT NULL,           -- MinIO key: {simulation_id}/{filename}
    filename        TEXT NOT NULL,
    size_bytes      BIGINT NOT NULL DEFAULT 0,
    content_type    TEXT NOT NULL DEFAULT 'application/octet-stream',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_simulation_artifacts_simulation_id ON simulation_artifacts (simulation_id);

-- ATE sessions (one per CreateAccreditedTestEnv call)
CREATE TABLE ate_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL UNIQUE,
    simulation_id   UUID NOT NULL REFERENCES simulations(simulation_id) ON DELETE CASCADE,
    agent_id        TEXT NOT NULL,
    scenarios_json  JSONB NOT NULL,           -- array of scenario configs
    report_object_key TEXT,                   -- MinIO key for full JSON report
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX idx_ate_sessions_simulation_id ON ate_sessions (simulation_id);

-- Per-scenario ATE results
CREATE TABLE ate_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL REFERENCES ate_sessions(session_id) ON DELETE CASCADE,
    scenario_id     TEXT NOT NULL,
    passed          BOOLEAN NOT NULL,
    quality_score   DOUBLE PRECISION,
    latency_ms      INTEGER,
    cost            DOUBLE PRECISION,
    safety_compliant BOOLEAN,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (session_id, scenario_id)
);

CREATE INDEX idx_ate_results_session_id ON ate_results (session_id);
```

---

## Protobuf Definition

```protobuf
syntax = "proto3";

package musematic.simulation.v1;

option go_package = "github.com/musematic/simulation-controller/api/grpc/v1;simulationv1";

import "google/protobuf/timestamp.proto";

service SimulationControlService {
  rpc CreateSimulation(CreateSimulationRequest) returns (SimulationHandle);
  rpc GetSimulationStatus(GetSimulationStatusRequest) returns (SimulationStatus);
  rpc StreamSimulationEvents(StreamSimulationEventsRequest) returns (stream SimulationEvent);
  rpc TerminateSimulation(TerminateSimulationRequest) returns (TerminateResult);
  rpc CollectSimulationArtifacts(CollectSimulationArtifactsRequest) returns (ArtifactCollectionResult);
  rpc CreateAccreditedTestEnv(CreateATERequest) returns (ATEHandle);
}

// ─── Simulation Lifecycle ─────────────────────────────────────────────────

message SimulationConfig {
  string agent_image      = 1;
  map<string, string> agent_env = 2;     // additional env vars (merged with injected)
  string cpu_request      = 3;           // e.g., "500m"
  string memory_request   = 4;           // e.g., "512Mi"
  int32  max_duration_seconds = 5;       // activeDeadlineSeconds; 0 = default 3600
}

message CreateSimulationRequest {
  string simulation_id    = 1;           // caller-provided UUID
  SimulationConfig config = 2;
}

message SimulationHandle {
  string simulation_id    = 1;
  string pod_name         = 2;
  string status           = 3;           // CREATING
  google.protobuf.Timestamp created_at = 4;
}

message GetSimulationStatusRequest {
  string simulation_id = 1;
}

message SimulationStatus {
  string simulation_id    = 1;
  string status           = 2;           // CREATING | RUNNING | COMPLETED | FAILED | TERMINATED
  string pod_name         = 3;
  string pod_phase        = 4;           // Kubernetes pod phase
  int64  elapsed_seconds  = 5;
  ResourceUsage resource_usage = 6;
  string error_message    = 7;
  google.protobuf.Timestamp created_at = 8;
  google.protobuf.Timestamp started_at = 9;
  google.protobuf.Timestamp completed_at = 10;
}

message ResourceUsage {
  string cpu_request     = 1;
  string memory_request  = 2;
  string cpu_limit       = 3;
  string memory_limit    = 4;
}

message StreamSimulationEventsRequest {
  string simulation_id = 1;
}

message SimulationEvent {
  string simulation_id = 1;
  string event_type    = 2;   // POD_CREATED | POD_RUNNING | POD_COMPLETED | POD_FAILED | POD_OOM | ARTIFACT_COLLECTED | TERMINATED | ATE_SCENARIO_COMPLETED
  string detail        = 3;
  bool   simulation    = 4;   // always true
  google.protobuf.Timestamp occurred_at = 5;
  map<string, string> metadata = 6;
}

message TerminateSimulationRequest {
  string simulation_id = 1;
  string reason        = 2;
}

message TerminateResult {
  string simulation_id = 1;
  bool   success       = 2;
  string message       = 3;
}

// ─── Artifact Collection ──────────────────────────────────────────────────

message CollectSimulationArtifactsRequest {
  string simulation_id  = 1;
  repeated string paths = 2;    // empty = collect /output and /workspace
}

message ArtifactCollectionResult {
  string simulation_id          = 1;
  int32  artifacts_collected    = 2;
  int64  total_bytes            = 3;
  repeated ArtifactRef artifacts = 4;
  bool   partial                = 5;   // true if pod was terminated before full collection
}

message ArtifactRef {
  string object_key    = 1;   // simulation-artifacts/{simulation_id}/{filename}
  string filename      = 2;
  int64  size_bytes    = 3;
  string content_type  = 4;
}

// ─── Accredited Testing Environment ─────────────────────────────────────

message ATEScenario {
  string scenario_id   = 1;
  string name          = 2;
  bytes  input_data    = 3;    // scenario input; large payloads → MinIO reference
  string scorer_config = 4;    // JSON scorer configuration
  double quality_threshold = 5;
  bool   safety_required = 6;
}

message CreateATERequest {
  string session_id       = 1;    // caller-provided UUID
  string agent_id         = 2;    // FQN of agent under test
  SimulationConfig config = 3;    // pod resource config (image, cpu, memory)
  repeated ATEScenario scenarios = 4;
  repeated string dataset_refs   = 5;   // MinIO keys of golden datasets
}

message ATEHandle {
  string session_id     = 1;
  string simulation_id  = 2;   // underlying simulation ID
  string status         = 3;   // PROVISIONING
  int32  scenario_count = 4;
  google.protobuf.Timestamp created_at = 5;
}
```

---

## Package Layout

```
services/simulation-controller/
├── cmd/simulation-controller/
│   └── main.go                    # gRPC server startup, signal handling
├── api/grpc/
│   └── v1/
│       ├── handler.go             # SimulationControlServiceServer implementation
│       └── interceptors.go        # OTel tracing, panic recovery, request logging
├── internal/
│   ├── sim_manager/
│   │   ├── manager.go             # SimManager interface
│   │   ├── pod.go                 # client-go pod create/delete/watch in platform-simulation
│   │   ├── network_policy.go     # NetworkPolicy create/delete
│   │   ├── state.go              # in-memory sync.Map, state rebuild on startup
│   │   └── orphan_scanner.go    # 60s periodic pod scan, orphan cleanup
│   ├── artifact_collector/
│   │   ├── collector.go           # ArtifactCollector interface
│   │   └── exec.go               # remotecommand tar exec → MinIO upload
│   ├── ate_runner/
│   │   ├── runner.go              # ATERunner interface
│   │   ├── configmap.go          # ConfigMap create with scenarios/datasets
│   │   └── results.go            # ATEResult aggregation → JSON report → MinIO
│   └── event_streamer/
│       ├── streamer.go            # EventStreamer interface
│       ├── pod_watch.go          # client-go pod Watch → SimulationEvent
│       └── fanout.go             # fan-out registry (sync.RWMutex map)
├── pkg/
│   ├── metrics/
│   │   └── metrics.go             # Prometheus counters/histograms
│   └── persistence/
│       ├── postgres.go            # pgx/v5 pool
│       ├── kafka.go               # confluent-kafka-go producer
│       └── minio.go               # aws-sdk-go-v2 S3 client
├── proto/
│   └── simulation_controller.proto
├── Dockerfile
└── Makefile
```

---

## Configuration Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GRPC_PORT` | `50055` | gRPC server port |
| `POSTGRES_DSN` | required | pgx/v5 connection string |
| `KAFKA_BROKERS` | required | Kafka broker list |
| `MINIO_ENDPOINT` | required | MinIO S3-compatible endpoint |
| `SIMULATION_BUCKET` | `simulation-artifacts` | Dedicated simulation artifact bucket |
| `SIMULATION_NAMESPACE` | `platform-simulation` | Kubernetes namespace for simulation pods |
| `ORPHAN_SCAN_INTERVAL_SECONDS` | `60` | How often to scan for orphaned pods |
| `DEFAULT_MAX_DURATION_SECONDS` | `3600` | Default pod `activeDeadlineSeconds` |
| `KUBECONFIG` | in-cluster | Kubernetes client config (empty = in-cluster) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | optional | OpenTelemetry collector |
