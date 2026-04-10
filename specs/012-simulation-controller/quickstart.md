# Quickstart: Simulation Controller

**Feature**: 012-simulation-controller  
**Service**: `services/simulation-controller/`  
**Port**: 50055  
**Namespace**: `platform-simulation`

---

## Prerequisites

```bash
# Go 1.22+
go version  # go1.22.x

# protoc + Go plugins
brew install protobuf
go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest

# grpcurl for manual testing
brew install grpcurl

# Local Kubernetes (for integration tests)
kind create cluster --name musematic-local
kubectl create namespace platform-simulation
kubectl label namespace platform-simulation kubernetes.io/metadata.name=platform-simulation

# Local dependencies
cd deploy/local && docker compose up -d postgres kafka minio
```

---

## Build

```bash
cd services/simulation-controller

# Generate proto stubs
make proto

# Build binary
make build

# Build Docker image (multi-stage, distroless)
make docker

# Run locally (uses KUBECONFIG from environment)
GRPC_PORT=50055 \
POSTGRES_DSN="postgres://musematic:musematic@localhost:5432/musematic" \
KAFKA_BROKERS=localhost:9092 \
MINIO_ENDPOINT=localhost:9000 \
SIMULATION_BUCKET=simulation-artifacts \
SIMULATION_NAMESPACE=platform-simulation \
./bin/simulation-controller
```

---

## Test: Create and Monitor a Simulation

```bash
SIM_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')

# Create simulation
grpcurl -plaintext -d "{
  \"simulation_id\": \"$SIM_ID\",
  \"config\": {
    \"agent_image\": \"busybox:latest\",
    \"cpu_request\": \"100m\",
    \"memory_request\": \"128Mi\",
    \"max_duration_seconds\": 60
  }
}" localhost:50055 musematic.simulation.v1.SimulationControlService/CreateSimulation

# Expected: status="CREATING"

# Query status
grpcurl -plaintext -d "{\"simulation_id\": \"$SIM_ID\"}" \
  localhost:50055 musematic.simulation.v1.SimulationControlService/GetSimulationStatus

# Expected: status=RUNNING or COMPLETED, pod_name="sim-{SIM_ID}"
```

---

## Test: Network Isolation Verification

```bash
# Create a simulation that tries to curl a production service
SIM_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')

grpcurl -plaintext -d "{
  \"simulation_id\": \"$SIM_ID\",
  \"config\": {
    \"agent_image\": \"curlimages/curl:latest\",
    \"agent_env\": {\"TARGET\": \"http://musematic-api.platform-control:8000/health\"},
    \"max_duration_seconds\": 30
  }
}" localhost:50055 musematic.simulation.v1.SimulationControlService/CreateSimulation

# Wait for completion
sleep 15

grpcurl -plaintext -d "{\"simulation_id\": \"$SIM_ID\"}" \
  localhost:50055 musematic.simulation.v1.SimulationControlService/GetSimulationStatus

# Expected: status=FAILED or COMPLETED with error (curl times out — network blocked)
# Verify in pod logs: connection refused or timeout to platform-control

# Verify network policy is applied
kubectl get networkpolicy -n platform-simulation simulation-deny-production-egress
```

---

## Test: Event Streaming

```bash
SIM_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')

# Terminal 1: Subscribe to events
grpcurl -plaintext -d "{\"simulation_id\": \"$SIM_ID\"}" \
  localhost:50055 musematic.simulation.v1.SimulationControlService/StreamSimulationEvents &

# Terminal 2: Create the simulation
grpcurl -plaintext -d "{
  \"simulation_id\": \"$SIM_ID\",
  \"config\": {
    \"agent_image\": \"busybox:latest\",
    \"max_duration_seconds\": 30
  }
}" localhost:50055 musematic.simulation.v1.SimulationControlService/CreateSimulation

# Expected events in Terminal 1:
# event_type: "POD_CREATED"
# event_type: "POD_RUNNING"
# event_type: "POD_COMPLETED"
# (stream closes after terminal event)
# All events have simulation=true
```

---

## Test: Artifact Collection

```bash
# Run a simulation that writes files to /output
SIM_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')

grpcurl -plaintext -d "{
  \"simulation_id\": \"$SIM_ID\",
  \"config\": {
    \"agent_image\": \"busybox:latest\",
    \"max_duration_seconds\": 30
  }
}" localhost:50055 musematic.simulation.v1.SimulationControlService/CreateSimulation

# Wait for simulation to complete
sleep 20

# Collect artifacts
grpcurl -plaintext -d "{
  \"simulation_id\": \"$SIM_ID\",
  \"paths\": [\"/output\"]
}" localhost:50055 musematic.simulation.v1.SimulationControlService/CollectSimulationArtifacts

# Expected: artifacts_collected > 0, object_key starts with "sim-{SIM_ID}/"

# Verify in MinIO: check simulation-artifacts bucket
# Verify MinIO object metadata: x-amz-meta-simulation=true
# Verify NO artifacts in production buckets
```

---

## Test: Termination and Cleanup

```bash
SIM_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')

grpcurl -plaintext -d "{
  \"simulation_id\": \"$SIM_ID\",
  \"config\": {
    \"agent_image\": \"busybox:latest\",
    \"max_duration_seconds\": 3600
  }
}" localhost:50055 musematic.simulation.v1.SimulationControlService/CreateSimulation

sleep 5

# Terminate
grpcurl -plaintext -d "{
  \"simulation_id\": \"$SIM_ID\",
  \"reason\": \"test_cleanup\"
}" localhost:50055 musematic.simulation.v1.SimulationControlService/TerminateSimulation

# Verify no orphaned pods
kubectl get pods -n platform-simulation -l "simulation-id=$SIM_ID"
# Expected: No resources found

# Verify status is TERMINATED
grpcurl -plaintext -d "{\"simulation_id\": \"$SIM_ID\"}" \
  localhost:50055 musematic.simulation.v1.SimulationControlService/GetSimulationStatus
```

---

## Test: Accredited Testing Environment

```bash
SESSION_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')

grpcurl -plaintext -d "{
  \"session_id\": \"$SESSION_ID\",
  \"agent_id\": \"finance-ops:kyc-verifier\",
  \"config\": {
    \"agent_image\": \"busybox:latest\",
    \"max_duration_seconds\": 300
  },
  \"scenarios\": [
    {
      \"scenario_id\": \"sc-001\",
      \"name\": \"Basic KYC check\",
      \"input_data\": \"eyJuYW1lIjoidGVzdCJ9\",
      \"quality_threshold\": 0.8,
      \"safety_required\": true
    },
    {
      \"scenario_id\": \"sc-002\",
      \"name\": \"Edge case: empty input\",
      \"input_data\": \"e30=\",
      \"quality_threshold\": 0.5,
      \"safety_required\": false
    }
  ]
}" localhost:50055 musematic.simulation.v1.SimulationControlService/CreateAccreditedTestEnv

# Expected: status="PROVISIONING", scenario_count=2

# Subscribe to events for the underlying simulation
# Verify ATE_SCENARIO_COMPLETED events arrive for each scenario
# After completion: check simulation-artifacts bucket for ate-report.json
```

---

## Unit Tests

```bash
cd services/simulation-controller

# All tests
go test ./...

# With race detector
go test -race ./...

# Coverage check (must be ≥ 95%)
go test ./... -coverprofile=coverage.out
go tool cover -func=coverage.out | grep total
```

---

## Integration Tests

```bash
# Requires: local Kubernetes cluster, PostgreSQL, Kafka, MinIO
go test ./... -tags=integration -v

# Or via make
make test-integration
```

---

## Verify Health Check

```bash
grpcurl -plaintext localhost:50055 grpc.health.v1.Health/Check
# Expected: { "status": "SERVING" }
```

---

## Docker Image Size Check

```bash
make docker
docker images musematic/simulation-controller:latest --format "{{.Size}}"
# Must be < 50MB (distroless base)
```

---

## Prometheus Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `simulation_creations_total` | Counter | Simulations created |
| `simulation_terminations_total` | Counter | Simulations terminated by reason |
| `simulation_duration_seconds` | Histogram | Simulation lifetime from create to completion |
| `simulation_status_current` | Gauge | Current simulations by status |
| `artifacts_collected_total` | Counter | Artifacts collected |
| `artifacts_bytes_total` | Counter | Total bytes collected |
| `ate_sessions_total` | Counter | ATE sessions created |
| `ate_scenarios_total` | Counter | ATE scenarios run by outcome (passed/failed) |
