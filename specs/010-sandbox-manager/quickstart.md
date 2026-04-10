# Quickstart: Sandbox Manager Deployment and Testing

**Feature**: 010-sandbox-manager  
**Date**: 2026-04-10

---

## Prerequisites

- Go 1.22+ installed
- Kubernetes cluster (1.28+) with `platform-execution` namespace
- PostgreSQL, Kafka, MinIO deployed (features 001, 003, 004)
- `kubectl`, `helm`, `protoc` with `protoc-gen-go` and `protoc-gen-go-grpc` installed
- Docker (for building the container image)

---

## 1. Build and Run Locally (Without Kubernetes)

```bash
cd services/sandbox-manager

# Download dependencies
go mod download

# Generate gRPC stubs from proto
protoc --go_out=./api/grpc/v1 --go-grpc_out=./api/grpc/v1 \
  -I proto proto/sandbox_manager.proto

# Run with local kubeconfig (set K8S_DRY_RUN=true to skip actual pod creation)
K8S_DRY_RUN=true \
POSTGRES_DSN="postgres://user:pass@localhost:5432/musematic" \
KAFKA_BROKERS="localhost:9092" \
MINIO_ENDPOINT="http://localhost:9000" \
go run ./cmd/sandbox-manager/...
```

Expected output:
```
{"level":"INFO","msg":"sandbox manager starting","grpc_port":50053,"http_port":8080}
{"level":"INFO","msg":"orphan scanner started","interval":"60s"}
{"level":"INFO","msg":"gRPC server listening","addr":":50053"}
```

---

## 2. Run Unit Tests

```bash
cd services/sandbox-manager

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
cd services/sandbox-manager

# Start test dependencies (PostgreSQL, Kafka) via docker compose
docker compose -f testdata/docker-compose.yml up -d --wait

# Run integration tests
go test ./... -tags=integration -v -timeout 120s

# Cleanup
docker compose -f testdata/docker-compose.yml down
```

---

## 4. Build Container Image

```bash
cd services/sandbox-manager

# Build multi-stage distroless image
docker build -t ghcr.io/yourorg/musematic/sandbox-manager:latest .

# Verify image size is under 50 MB
docker image ls ghcr.io/yourorg/musematic/sandbox-manager:latest
# Expected: SIZE < 50MB

# Verify distroless (no shell — this command should fail)
docker run --rm ghcr.io/yourorg/musematic/sandbox-manager:latest /bin/sh || echo "No shell — PASS"
```

---

## 5. Deploy to Kubernetes (Development)

```bash
# Create namespace if not exists
kubectl create namespace platform-execution --dry-run=client -o yaml | kubectl apply -f -

# Create required secrets
kubectl create secret generic sandbox-manager-config \
  -n platform-execution \
  --from-literal=POSTGRES_DSN="postgres://user:pass@musematic-postgres-rw.platform-data:5432/musematic" \
  --from-literal=KAFKA_BROKERS="musematic-kafka.platform-data:9092" \
  --from-literal=MINIO_ENDPOINT="http://musematic-minio.platform-data:9000"

# Deploy with Helm
helm install musematic-sandbox-manager deploy/helm/sandbox-manager \
  -n platform-execution \
  --set image.tag=latest \
  --wait --timeout 2m
```

---

## 6. Verify Health Endpoints

```bash
kubectl port-forward svc/musematic-sandbox-manager 8080:8080 -n platform-execution &

curl http://localhost:8080/healthz
# Expected: {"status":"ok"}

curl http://localhost:8080/readyz
# Expected: {"status":"ok","checks":{"postgres":"ok","kafka":"ok","k8s":"ok"}}
```

---

## 7. Test CreateSandbox + ExecuteSandboxStep via gRPC

```bash
kubectl port-forward svc/musematic-sandbox-manager 50053:50053 -n platform-execution &

# Create a Python sandbox
grpcurl -plaintext -d '{
  "template_name": "python3.12",
  "correlation": {
    "workspace_id": "ws-test",
    "execution_id": "exec-00000000-0000-0000-0000-000000000001"
  }
}' localhost:50053 sandbox_manager.v1.SandboxService/CreateSandbox

# Expected:
# { "sandboxId": "sb-uuid", "state": "SANDBOX_STATE_CREATING" }

# Wait for sandbox to become ready (poll until state=READY or stream events)
sleep 10

# Execute code
grpcurl -plaintext -d '{
  "sandbox_id": "sb-uuid",
  "code": "print(\"hello from sandbox\")"
}' localhost:50053 sandbox_manager.v1.SandboxService/ExecuteSandboxStep

# Expected:
# {
#   "result": { "stdout": "hello from sandbox\n", "stderr": "", "exitCode": 0 },
#   "stepNum": 1
# }
```

---

## 8. Test Multi-Step Execution

```bash
# Step 1: define a variable
grpcurl -plaintext -d '{
  "sandbox_id": "sb-uuid",
  "code": "x = 42"
}' localhost:50053 sandbox_manager.v1.SandboxService/ExecuteSandboxStep

# Step 2: use the variable (demonstrates session persistence)
grpcurl -plaintext -d '{
  "sandbox_id": "sb-uuid",
  "code": "print(x * 2)"
}' localhost:50053 sandbox_manager.v1.SandboxService/ExecuteSandboxStep

# Expected: stdout = "84\n", stepNum = 2
```

---

## 9. Test Resource Limits

```bash
# Create sandbox with tight memory limit
grpcurl -plaintext -d '{
  "template_name": "python3.12",
  "correlation": { "workspace_id": "ws-test", "execution_id": "exec-oom-test" },
  "resource_overrides": { "memory_limit": "64Mi" }
}' localhost:50053 sandbox_manager.v1.SandboxService/CreateSandbox

# Execute memory-hungry code
grpcurl -plaintext -d '{
  "sandbox_id": "sb-uuid",
  "code": "x = bytearray(100 * 1024 * 1024)"
}' localhost:50053 sandbox_manager.v1.SandboxService/ExecuteSandboxStep

# Expected: result.oom_killed = true
```

---

## 10. Test Timeout Enforcement

```bash
grpcurl -plaintext -d '{
  "sandbox_id": "sb-uuid",
  "code": "import time; time.sleep(999)",
  "timeout_override": 5
}' localhost:50053 sandbox_manager.v1.SandboxService/ExecuteSandboxStep

# Expected: result.timed_out = true, duration ≈ 5s
```

---

## 11. Test Network Isolation

```bash
# Default sandbox (network disabled)
grpcurl -plaintext -d '{
  "sandbox_id": "sb-uuid",
  "code": "import urllib.request; urllib.request.urlopen(\"http://example.com\")"
}' localhost:50053 sandbox_manager.v1.SandboxService/ExecuteSandboxStep

# Expected: stderr contains connection error, exit_code != 0
```

---

## 12. Test Code-as-Reasoning Template

```bash
# Create code-as-reasoning sandbox
grpcurl -plaintext -d '{
  "template_name": "code-as-reasoning",
  "correlation": { "workspace_id": "ws-test", "execution_id": "exec-reasoning" }
}' localhost:50053 sandbox_manager.v1.SandboxService/CreateSandbox

# Execute computation
grpcurl -plaintext -d '{
  "sandbox_id": "sb-uuid",
  "code": "result = sum(range(100))"
}' localhost:50053 sandbox_manager.v1.SandboxService/ExecuteSandboxStep

# Expected: result.structured_output contains JSON with computed value
```

---

## 13. Test Artifact Collection

```bash
# Execute code that writes to /output
grpcurl -plaintext -d '{
  "sandbox_id": "sb-uuid",
  "code": "with open(\"/output/result.json\", \"w\") as f: f.write(\"{\\\"answer\\\": 42}\")"
}' localhost:50053 sandbox_manager.v1.SandboxService/ExecuteSandboxStep

# Collect artifacts
grpcurl -plaintext -d '{
  "sandbox_id": "sb-uuid"
}' localhost:50053 sandbox_manager.v1.SandboxService/CollectSandboxArtifacts

# Expected:
# { "artifacts": [{ "objectKey": "sandbox-artifacts/exec-uuid/sb-uuid/result.json", ... }], "complete": true }
```

---

## 14. Test TerminateSandbox

```bash
grpcurl -plaintext -d '{
  "sandbox_id": "sb-uuid",
  "grace_period_seconds": 5
}' localhost:50053 sandbox_manager.v1.SandboxService/TerminateSandbox

# Expected: { "state": "SANDBOX_STATE_TERMINATED" }

# Verify pod is gone
kubectl get pods -n platform-execution -l sandbox_id=sb-uuid
# Expected: No resources found
```

---

## 15. Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `CreateSandbox` returns `UNAVAILABLE` | Kubernetes API unreachable | Check ServiceAccount RBAC and network policy |
| `CreateSandbox` returns `RESOURCE_EXHAUSTED` | Concurrent sandbox limit reached | Wait for sandboxes to terminate or increase `MAX_CONCURRENT_SANDBOXES` |
| Pod stuck in `Pending` | Insufficient cluster resources | Check `kubectl describe pod` for resource pressure |
| `ExecuteSandboxStep` returns `FAILED_PRECONDITION` | Sandbox not ready yet | Wait for READY state before executing |
| Network test succeeds (should fail) | NetworkPolicy not applied | Verify CNI supports NetworkPolicy (e.g., Calico, Cilium) |
| OOM not detected | Pod evicted instead of OOMKilled | Check `kubectl describe pod` — ephemeral-storage may have triggered eviction |
| Image size > 50MB | CGO enabled or debug symbols | Ensure `CGO_ENABLED=0` and `go build -ldflags="-s -w"` |
