# gRPC Contract: SimulationControlService

**Service**: `musematic.simulation.v1.SimulationControlService`  
**Port**: 50055  
**Namespace**: `platform-simulation`  
**DNS**: `musematic-simulation-controller.platform-simulation:50055`  
**Feature**: 012-simulation-controller

---

## RPC: CreateSimulation

**Pattern**: Unary  
**Called by**: Control plane (`apps/control-plane/src/platform/simulation/`) at test start

### Request

```
CreateSimulationRequest {
  simulation_id: string       // caller-provided UUID
  config {
    agent_image: string       // Docker image to run
    agent_env: map<str,str>   // additional env vars (merged with injected)
    cpu_request: string       // e.g., "500m" (default)
    memory_request: string    // e.g., "512Mi" (default)
    max_duration_seconds: int // activeDeadlineSeconds; 0 = default 3600
  }
}
```

### Response

```
SimulationHandle {
  simulation_id: string
  pod_name: string            // "sim-{simulation_id}"
  status: string              // "CREATING"
  created_at: Timestamp
}
```

### Behavior

1. Insert row to `simulations` table with status=CREATING
2. Create simulation pod in `platform-simulation` namespace with:
   - Labels: `simulation=true`, `simulation-id={simulation_id}`
   - Env vars: `SIMULATION=true`, `SIMULATION_ID`, `SIMULATION_BUCKET=simulation-artifacts`
   - Security context: non-root UID 65534, drop ALL caps, read-only rootfs
   - `activeDeadlineSeconds` set from config
3. Register simulation in in-memory state map
4. Publish CREATED event to fan-out registry and Kafka `simulation.events`
5. Return handle immediately (pod creation is async)

### Error Codes

| Code | Condition |
|------|-----------|
| `ALREADY_EXISTS` | `simulation_id` already exists |
| `INVALID_ARGUMENT` | `simulation_id` or `agent_image` missing |
| `INTERNAL` | Kubernetes pod creation failed |

---

## RPC: GetSimulationStatus

**Pattern**: Unary  
**Called by**: Control plane, monitoring dashboards

### Request

```
GetSimulationStatusRequest {
  simulation_id: string
}
```

### Response

```
SimulationStatus {
  simulation_id: string
  status: string              // CREATING | RUNNING | COMPLETED | FAILED | TERMINATED
  pod_name: string
  pod_phase: string           // Kubernetes pod phase (Pending, Running, Succeeded, Failed)
  elapsed_seconds: int64
  resource_usage {
    cpu_request: string
    memory_request: string
    cpu_limit: string
    memory_limit: string
  }
  error_message: string       // set when FAILED
  created_at: Timestamp
  started_at: Timestamp
  completed_at: Timestamp
}
```

### Behavior

1. Read from in-memory state map (fast path, < 1ms)
2. Return current status with elapsed time computed as `now - started_at`

### Error Codes

| Code | Condition |
|------|-----------|
| `NOT_FOUND` | `simulation_id` does not exist |

---

## RPC: StreamSimulationEvents

**Pattern**: Server-streaming (client subscribes, server pushes)  
**Called by**: Control plane, operator dashboards

### Request

```
StreamSimulationEventsRequest {
  simulation_id: string
}
```

### Stream Message (server → client, repeated)

```
SimulationEvent {
  simulation_id: string
  event_type: string          // POD_CREATED | POD_RUNNING | POD_COMPLETED | POD_FAILED
                              // | POD_OOM | ARTIFACT_COLLECTED | TERMINATED
                              // | ATE_SCENARIO_COMPLETED
  detail: string              // human-readable event detail
  simulation: bool            // always true
  occurred_at: Timestamp
  metadata: map<string, string>  // e.g., {"exit_code": "0", "scenario_id": "..."}
}
```

### Behavior

1. Subscribe channel to fan-out registry for `simulation_id`
2. Start pod Watch goroutine for label selector `simulation-id={simulation_id}`
3. Convert pod Watch events → `SimulationEvent` messages
4. Forward both Watch events and internal lifecycle events to subscriber channel
5. Push events to gRPC stream as they arrive
6. On terminal event (COMPLETED, FAILED, TERMINATED): send final event, close stream
7. Emit all events to Kafka `simulation.events` topic, key=`simulation_id`

### Error Codes

| Code | Condition |
|------|-----------|
| `NOT_FOUND` | `simulation_id` does not exist |

---

## RPC: TerminateSimulation

**Pattern**: Unary  
**Called by**: Control plane on explicit user request or resource reclamation

### Request

```
TerminateSimulationRequest {
  simulation_id: string
  reason: string              // e.g., "user_requested", "timeout", "resource_reclaim"
}
```

### Response

```
TerminateResult {
  simulation_id: string
  success: bool
  message: string
}
```

### Behavior

1. Delete simulation pod from `platform-simulation` namespace (graceful: `terminationGracePeriodSeconds=10`)
2. Delete simulation-specific ConfigMap if ATE (if exists: `ate-{session_id}`)
3. Update `simulations` table: status=TERMINATED, terminated_at=now
4. Update in-memory state map: status=TERMINATED
5. Publish TERMINATED event to fan-out registry and Kafka `simulation.events`
6. Close any active `StreamSimulationEvents` subscriber streams
7. Return result

### Error Codes

| Code | Condition |
|------|-----------|
| `NOT_FOUND` | `simulation_id` does not exist |
| `FAILED_PRECONDITION` | Simulation already in terminal state (TERMINATED, COMPLETED) |

---

## RPC: CollectSimulationArtifacts

**Pattern**: Unary  
**Called by**: Control plane after simulation completion

### Request

```
CollectSimulationArtifactsRequest {
  simulation_id: string
  paths: []string             // directories to collect; empty = ["/output", "/workspace"]
}
```

### Response

```
ArtifactCollectionResult {
  simulation_id: string
  artifacts_collected: int32
  total_bytes: int64
  artifacts: []{
    object_key: string        // simulation-artifacts/{simulation_id}/{filename}
    filename: string
    size_bytes: int64
    content_type: string
  }
  partial: bool               // true if pod was terminated mid-collection
}
```

### Behavior

1. For each path in `paths` (default: `/output`, `/workspace`):
   - Use `remotecommand` (SPDY) to exec `tar -czf - {path}` inside the simulation pod
   - Stream tarball to MinIO at `simulation-artifacts/{simulation_id}/{basename}.tar.gz`
   - Add MinIO object metadata: `x-amz-meta-simulation=true`, `x-amz-meta-simulation-id={simulation_id}`
   - Insert row to `simulation_artifacts` table
2. Publish ARTIFACT_COLLECTED event to fan-out registry and Kafka
3. Return collection result with artifact refs

### Error Codes

| Code | Condition |
|------|-----------|
| `NOT_FOUND` | `simulation_id` does not exist |
| `FAILED_PRECONDITION` | Pod has already been deleted (`partial=true` returned with best effort) |
| `INTERNAL` | MinIO upload failure |

---

## RPC: CreateAccreditedTestEnv

**Pattern**: Unary  
**Called by**: Control plane trust/certification workflow

### Request

```
CreateATERequest {
  session_id: string          // caller-provided UUID
  agent_id: string            // FQN of agent under test (e.g., "finance-ops:kyc-verifier")
  config {
    agent_image: string
    cpu_request: string
    memory_request: string
    max_duration_seconds: int
  }
  scenarios: []{
    scenario_id: string
    name: string
    input_data: bytes         // scenario input payload
    scorer_config: string     // JSON scorer config
    quality_threshold: double
    safety_required: bool
  }
  dataset_refs: []string      // MinIO keys of golden datasets
}
```

### Response

```
ATEHandle {
  session_id: string
  simulation_id: string       // underlying simulation_id
  status: string              // "PROVISIONING"
  scenario_count: int32
  created_at: Timestamp
}
```

### Behavior

1. Generate `simulation_id` for the underlying simulation pod
2. Create ConfigMap `ate-{session_id}` in `platform-simulation` namespace with:
   - `scenarios.json`: JSON array of all ATEScenario objects
   - `scorer_config.json`: merged scorer configurations
   - Dataset references written to ConfigMap metadata (actual datasets fetched from MinIO by the ATE runner)
3. Create simulation pod with ConfigMap mounted at `/ate/` and ATE env vars (`ATE_SESSION_ID`, `ATE_SCENARIOS_PATH`)
4. Insert rows to `simulations` and `ate_sessions` tables
5. Return ATEHandle immediately (ATE execution is async)
6. After pod COMPLETED: collect `/ate/results/` as artifacts, aggregate `ate_results` rows from per-scenario event stream, generate report JSON, upload to `simulation-artifacts/{simulation_id}/ate-report.json`, update `ate_sessions.report_object_key`

### Error Codes

| Code | Condition |
|------|-----------|
| `ALREADY_EXISTS` | `session_id` already exists |
| `INVALID_ARGUMENT` | No scenarios provided, or `agent_id` or `agent_image` missing |
| `INTERNAL` | ConfigMap or pod creation failed |

---

## Kafka Events

**Topic**: `simulation.events`  
**Key**: `simulation_id`

### Envelope Schema

```json
{
  "event_type": "simulation.created | simulation.running | simulation.completed | simulation.failed | simulation.terminated | simulation.artifact_collected | simulation.ate_scenario_completed | simulation.ate_completed",
  "version": "1.0",
  "source": "simulation-controller",
  "simulation_id": "<uuid>",
  "simulation": true,
  "occurred_at": "<iso8601>",
  "payload": { ... }
}
```

---

## Python Client Stub (Control Plane)

```python
# apps/control-plane/src/platform/common/clients/simulation_controller.py
import grpc
from generated.simulation_controller_pb2_grpc import SimulationControlServiceStub
from generated.simulation_controller_pb2 import (
    CreateSimulationRequest, SimulationConfig,
    GetSimulationStatusRequest, TerminateSimulationRequest,
)

class SimulationControllerClient:
    def __init__(self, address: str = "musematic-simulation-controller.platform-simulation:50055"):
        self._channel = grpc.aio.insecure_channel(address)
        self._stub = SimulationControlServiceStub(self._channel)

    async def create_simulation(self, simulation_id: str, image: str) -> str:
        request = CreateSimulationRequest(
            simulation_id=simulation_id,
            config=SimulationConfig(agent_image=image),
        )
        response = await self._stub.CreateSimulation(request)
        return response.status

    async def get_status(self, simulation_id: str) -> str:
        response = await self._stub.GetSimulationStatus(
            GetSimulationStatusRequest(simulation_id=simulation_id)
        )
        return response.status
```

---

## Network Access

| Caller | Transport | Address |
|--------|-----------|---------|
| Control plane (`simulation/` bounded context) | gRPC | `musematic-simulation-controller.platform-simulation:50055` |
| Simulation Controller → Kubernetes API | HTTPS | in-cluster `kubernetes.default.svc` |
| Simulation Controller → Kafka | TCP | `musematic-kafka.platform-data:9092` |
| Simulation Controller → PostgreSQL | TCP | `musematic-pooler.platform-data:5432` |
| Simulation Controller → MinIO | HTTP | `musematic-minio.platform-data:9000` |
| Simulation pods → MinIO (`simulation-artifacts` only) | HTTP | `musematic-minio.platform-data:9000` |
| Simulation pods → Kafka (`simulation.events` only) | TCP | `musematic-kafka.platform-data:9092` |
| Simulation pods → production namespaces | BLOCKED | NetworkPolicy deny-all |
