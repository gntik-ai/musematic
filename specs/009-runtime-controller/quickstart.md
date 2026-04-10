# Quickstart: Runtime Controller Deployment and Testing

**Feature**: 009-runtime-controller  
**Date**: 2026-04-10

---

## Prerequisites

- Go 1.22+ installed
- Kubernetes cluster (1.28+) with `platform-execution` namespace
- PostgreSQL, Redis, Kafka, MinIO deployed (features 001–004)
- `kubectl`, `helm`, `protoc` with `protoc-gen-go` and `protoc-gen-go-grpc` installed
- Docker (for building the container image)

Install the Go protobuf plugins if they are not already available:

```bash
go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest
export PATH="$(go env GOPATH)/bin:$PATH"
```

---

## 1. Build and Run Locally (Without Kubernetes)

```bash
cd services/runtime-controller

# Download dependencies
go mod download

# Generate gRPC stubs from proto
make proto

# Run with local kubeconfig (will NOT create actual pods — set K8S_DRY_RUN=true)
K8S_DRY_RUN=true \
POSTGRES_DSN="postgres://user:pass@localhost:5432/musematic" \
REDIS_ADDR="localhost:6379" \
KAFKA_BROKERS="localhost:9092" \
MINIO_ENDPOINT="http://localhost:9000" \
go run ./cmd/runtime-controller/...
```

Expected output:
```
{"level":"INFO","msg":"runtime controller starting","grpc_port":50051,"http_port":8080}
{"level":"INFO","msg":"reconciler started","interval":"30s"}
{"level":"INFO","msg":"heartbeat scanner started","check_interval":"10s"}
{"level":"INFO","msg":"gRPC server listening","addr":":50051"}
```

---

## 2. Run Unit Tests

```bash
cd services/runtime-controller

# Run all tests with coverage
go test ./... -coverprofile=coverage.out

# View coverage report
go tool cover -html=coverage.out

# Expected: ≥95% coverage
go tool cover -func=coverage.out | grep total
```

---

## 3. Run Integration Tests (requires running dependencies)

```bash
cd services/runtime-controller

# Start test dependencies (PostgreSQL, Redis, Kafka) via docker compose
docker compose -f testdata/docker-compose.yml up -d --wait

# Run integration tests
go test ./... -tags=integration -v -timeout 120s

# Cleanup
docker compose -f testdata/docker-compose.yml down
```

---

## 4. Build Container Image

```bash
cd services/runtime-controller

# Build multi-stage distroless image
docker build -t ghcr.io/yourorg/musematic/runtime-controller:latest .

# Verify image size is under 100 MB
docker image ls ghcr.io/yourorg/musematic/runtime-controller:latest
# Expected: SIZE < 100MB

# Verify distroless (no shell — this command should fail)
docker run --rm ghcr.io/yourorg/musematic/runtime-controller:latest /bin/sh || echo "No shell — PASS"
```

---

## 5. Deploy to Kubernetes (Development)

```bash
# Create namespace if not exists
kubectl create namespace platform-execution --dry-run=client -o yaml | kubectl apply -f -

# Create required secrets
kubectl create secret generic runtime-controller-config \
  -n platform-execution \
  --from-literal=POSTGRES_DSN="postgres://user:pass@musematic-postgres-rw.platform-data:5432/musematic" \
  --from-literal=REDIS_ADDR="musematic-redis-cluster.platform-data:6379" \
  --from-literal=KAFKA_BROKERS="musematic-kafka.platform-data:9092" \
  --from-literal=MINIO_ENDPOINT="http://musematic-minio.platform-data:9000"

# Deploy with Helm
helm install musematic-runtime-controller deploy/helm/runtime-controller \
  -n platform-execution \
  --set image.tag=latest \
  --wait --timeout 2m
```

---

## 6. Verify Health Endpoints

```bash
kubectl port-forward svc/musematic-runtime-controller 8080:8080 -n platform-execution &

curl http://localhost:8080/healthz
# Expected: {"status":"ok"}

curl http://localhost:8080/readyz
# Expected: {"status":"ok","checks":{"postgres":"ok","redis":"ok","kafka":"ok","k8s":"ok"}}

curl http://localhost:8080/metrics | grep runtime_controller
# Expected: Prometheus metrics including runtime_controller_active_runtimes, runtime_controller_launch_duration_seconds
```

---

## 7. Test LaunchRuntime via gRPC

```bash
# Install grpcurl
# brew install grpcurl (macOS) or go install github.com/fullstorydev/grpcurl/cmd/grpcurl@latest

kubectl port-forward svc/musematic-runtime-controller 50051:50051 -n platform-execution &

# Launch a runtime (dry-run: K8S_DRY_RUN=true prevents actual pod creation in dev)
grpcurl -plaintext -d '{
  "contract": {
    "agent_revision": "test-agent-v1",
    "model_binding": "{\"provider\":\"anthropic\",\"model\":\"claude-sonnet-4-6\"}",
    "correlation_context": {
      "workspace_id": "ws-test",
      "execution_id": "exec-00000000-0000-0000-0000-000000000001"
    },
    "resource_limits": {
      "cpu_request": "500m",
      "cpu_limit": "1",
      "memory_request": "256Mi",
      "memory_limit": "512Mi"
    }
  }
}' localhost:50051 runtime_controller.v1.RuntimeControlService/LaunchRuntime

# Expected:
# {
#   "runtimeId": "rt-uuid",
#   "state": "RUNTIME_STATE_PENDING",
#   "warmStart": false
# }
```

---

## 8. Test GetRuntime and StreamRuntimeEvents

```bash
# Get runtime state
grpcurl -plaintext -d '{"execution_id": "exec-00000000-0000-0000-0000-000000000001"}' \
  localhost:50051 runtime_controller.v1.RuntimeControlService/GetRuntime

# Stream events (will block and receive events as they occur)
grpcurl -plaintext -d '{"execution_id": "exec-00000000-0000-0000-0000-000000000001"}' \
  localhost:50051 runtime_controller.v1.RuntimeControlService/StreamRuntimeEvents
```

---

## 9. Test StopRuntime

```bash
grpcurl -plaintext -d '{
  "execution_id": "exec-00000000-0000-0000-0000-000000000001",
  "grace_period_seconds": 5
}' localhost:50051 runtime_controller.v1.RuntimeControlService/StopRuntime

# Expected:
# { "state": "RUNTIME_STATE_STOPPED", "forceKilled": false }
```

---

## 10. Test Reconciliation Loop

```bash
# 1. Launch a runtime (creates a pod)
# 2. Externally delete the pod to simulate a crash:
kubectl delete pod runtime-exec-00000000-short -n platform-execution --force

# 3. Wait up to 30 seconds for the next reconciliation cycle
# 4. Query runtime state — expect FAILED with reason "pod_disappeared"
grpcurl -plaintext -d '{"execution_id": "exec-00000000-0000-0000-0000-000000000001"}' \
  localhost:50051 runtime_controller.v1.RuntimeControlService/GetRuntime

# Expected:
# { "runtime": { "state": "RUNTIME_STATE_FAILED", "failureReason": "pod_disappeared" } }

# 5. Check Kafka for drift event on monitor.alerts topic
kubectl exec -n platform-data musematic-kafka-0 -- \
  kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic monitor.alerts --from-beginning --max-messages 1
```

---

## 11. Test Heartbeat Timeout

```bash
# 1. Launch a runtime
# 2. Stop sending heartbeats (or don't send any in test mode)
# 3. Wait 60 seconds (default heartbeat_timeout)
# 4. Query state — expect FAILED with reason "heartbeat_timeout"

# To simulate in integration tests, set HEARTBEAT_TIMEOUT=5s
HEARTBEAT_TIMEOUT=5s go test -run TestHeartbeatTimeout ./internal/heartbeat/... -v
```

---

## 12. Test Warm Pool

```bash
# Configure warm pool for test agent type
grpcurl -plaintext -d '{
  "workspace_id": "ws-test",
  "agent_type": "test-agent-type",
  "target_size": 2
}' localhost:50051 runtime_controller.v1.RuntimeControlService/ConfigureWarmPool

# Wait for warm pool to fill (30s replenishment interval)
sleep 35

# Launch runtime — should use warm pool (<2s)
time grpcurl -plaintext -d '{ "contract": { ... } }' \
  localhost:50051 runtime_controller.v1.RuntimeControlService/LaunchRuntime

# Expected: real time < 2s, "warmStart": true
```

---

## 13. Verify Secret Isolation

```bash
# 1. Create a test Kubernetes Secret
kubectl create secret generic test-api-key -n platform-execution \
  --from-literal=api-key="sk-test-secret-value-12345"

# 2. Launch a runtime with secret ref
grpcurl -plaintext -d '{
  "contract": {
    ...,
    "secret_refs": ["test-api-key"]
  }
}' localhost:50051 runtime_controller.v1.RuntimeControlService/LaunchRuntime

# 3. Inspect the pod environment — should NOT see "sk-test-secret-value-12345"
kubectl exec -n platform-execution runtime-exec-short -- env | grep SECRET
# Expected: SECRETS_REF_API_KEY=/run/secrets/api-key  (path, not value)

# 4. Check the mounted secret volume — value is there for tool execution
kubectl exec -n platform-execution runtime-exec-short -- cat /run/secrets/api-key
# Expected: sk-test-secret-value-12345  (accessible to tool executor, not LLM process)
```

---

## 14. Verify Task Plan Persistence

```bash
# Launch a runtime with a task plan
grpcurl -plaintext -d '{
  "contract": {
    "execution_id": "exec-plan-test-001",
    "step_id": "step-001",
    "task_plan_json": "{\"considered_agents\":[\"agent-a\",\"agent-b\"],\"selected_agent\":\"agent-a\",\"rationale\":\"highest trust score\"}"
  }
}' localhost:50051 runtime_controller.v1.RuntimeControlService/LaunchRuntime

# Verify task plan record in PostgreSQL
psql $POSTGRES_DSN -c \
  "SELECT execution_id, selected_agent, selection_rationale FROM task_plan_records WHERE execution_id='exec-plan-test-001'"
# Expected: row with agent-a and rationale
```

---

## 15. Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `LaunchRuntime` returns `UNAVAILABLE` | Kubernetes API unreachable | Check ServiceAccount RBAC and network policy |
| `FAILED_PRECONDITION` on launch | Secret not found in namespace | Verify Kubernetes Secret name matches `secret_refs` |
| Pod stuck in `PENDING` state | Insufficient cluster resources | Check `kubectl describe pod` for resource pressure |
| Heartbeat scanner not firing | Redis unreachable | Check Redis connection in `/readyz` |
| Reconciliation not detecting drift | PostgreSQL unreachable | Check PostgreSQL connection in `/readyz` |
| Image size > 100MB | CGO enabled or debug symbols | Ensure `CGO_ENABLED=0` and `go build -ldflags="-s -w"` |
