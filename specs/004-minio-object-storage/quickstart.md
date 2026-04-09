# Quickstart: S3-Compatible Object Storage

**Feature**: 004-minio-object-storage  
**Date**: 2026-04-09

---

## Prerequisites

- Kubernetes cluster with `kubectl` configured
- `helm` 3.x
- MinIO Operator pre-installed in the target cluster:
  ```bash
  kubectl apply -k github.com/minio/operator/releases/latest
  kubectl wait --for=condition=Available deployment/minio-operator -n minio-operator --timeout=120s
  ```
- Python 3.12+ with `aioboto3` installed:
  ```bash
  pip install aioboto3
  ```
- Install the control-plane package before running Python tests:
  ```bash
  pip install -e ./apps/control-plane
  ```

---

## 1. Deploy MinIO Cluster (Production)

```bash
helm install musematic-minio deploy/helm/minio \
  -n platform-data \
  -f deploy/helm/minio/values.yaml \
  -f deploy/helm/minio/values-prod.yaml \
  --create-namespace

# Wait for Tenant to be ready (4 nodes)
kubectl wait tenant/musematic-minio \
  --for=condition=Initialized \
  --timeout=300s \
  -n platform-data

# Verify pods (expect 4 server pods)
kubectl get pods -n platform-data -l app=minio

# The post-install Job will create all 8 buckets automatically
kubectl wait job/musematic-minio-bucket-init \
  --for=condition=Complete \
  --timeout=120s \
  -n platform-data
```

---

## 2. Deploy MinIO (Development)

```bash
helm install musematic-minio deploy/helm/minio \
  -n platform-data \
  -f deploy/helm/minio/values.yaml \
  -f deploy/helm/minio/values-dev.yaml \
  --create-namespace

# Wait for single-node deployment
kubectl wait deployment/musematic-minio \
  --for=condition=Available \
  --timeout=60s \
  -n platform-data

# Wait for bucket init
kubectl wait job/musematic-minio-bucket-init \
  --for=condition=Complete \
  --timeout=60s \
  -n platform-data
```

---

## 3. Verify All 8 Buckets Exist

```bash
# Port-forward the S3 API
kubectl port-forward svc/musematic-minio 9000:9000 -n platform-data &

# Get credentials
ACCESS_KEY=$(kubectl get secret minio-platform-credentials -n platform-data -o jsonpath='{.data.MINIO_ACCESS_KEY}' | base64 -d)
SECRET_KEY=$(kubectl get secret minio-platform-credentials -n platform-data -o jsonpath='{.data.MINIO_SECRET_KEY}' | base64 -d)

# List buckets using mc
mc alias set local http://localhost:9000 "$ACCESS_KEY" "$SECRET_KEY"
mc ls local
# Expected: 8 buckets listed

# Verify lifecycle policies
mc ilm rule ls local/sandbox-outputs
# Expected: rule with expire-days 30

mc ilm rule ls local/agent-packages
# Expected: versioning enabled (check via mc version info local/agent-packages)
```

---

## 4. Test Basic S3 Operations

```bash
# Upload a test object
echo "hello world" | mc pipe local/execution-artifacts/test/hello.txt
# Expected: mc: <stdin> -> `local/execution-artifacts/test/hello.txt`

# Download and verify
mc cat local/execution-artifacts/test/hello.txt
# Expected: hello world

# List with prefix
mc ls local/execution-artifacts/test/
# Expected: hello.txt listed

# Delete
mc rm local/execution-artifacts/test/hello.txt
mc cat local/execution-artifacts/test/hello.txt
# Expected: error (object not found)
```

---

## 5. Test Multipart Upload (Large File)

```bash
# Generate a 1 GB test file
dd if=/dev/urandom of=/tmp/test-1gb.bin bs=1M count=1024

# Upload via mc (uses multipart automatically for large files)
mc cp /tmp/test-1gb.bin local/execution-artifacts/test/large-file.bin

# Verify MD5 checksum
md5sum /tmp/test-1gb.bin
mc cat local/execution-artifacts/test/large-file.bin | md5sum
# Expected: checksums match

# Cleanup
mc rm local/execution-artifacts/test/large-file.bin
rm /tmp/test-1gb.bin
```

---

## 6. Test Object Versioning (agent-packages)

```bash
# Verify versioning is enabled
mc version info local/agent-packages
# Expected: Versioning is enabled

# Upload version 1
echo "v1 content" | mc pipe local/agent-packages/finance-ops/kyc/1.0.0.tar.gz

# Upload version 2 (same key)
echo "v2 content" | mc pipe local/agent-packages/finance-ops/kyc/1.0.0.tar.gz

# List all versions
mc ls --versions local/agent-packages/finance-ops/kyc/1.0.0.tar.gz
# Expected: 2 versions listed

# Retrieve version 1 by version ID
VERSION_ID=$(mc ls --versions local/agent-packages/finance-ops/kyc/1.0.0.tar.gz | awk 'NR==2{print $NF}')
mc cat --version-id "$VERSION_ID" local/agent-packages/finance-ops/kyc/1.0.0.tar.gz
# Expected: v1 content
```

---

## 7. Test Simulation Isolation

```bash
# Simulate a production service accessing simulation bucket (should fail)
ACCESS_KEY=$(kubectl get secret minio-platform-credentials -n platform-data -o jsonpath='{.data.MINIO_ACCESS_KEY}' | base64 -d)
SECRET_KEY=$(kubectl get secret minio-platform-credentials -n platform-data -o jsonpath='{.data.MINIO_SECRET_KEY}' | base64 -d)

mc alias set platform http://localhost:9000 "$ACCESS_KEY" "$SECRET_KEY"
mc cp /dev/null platform/simulation-artifacts/test.txt
# Expected: Access Denied (403)

# Simulation credentials can access simulation bucket
SIM_ACCESS=$(kubectl get secret minio-simulation-credentials -n platform-data -o jsonpath='{.data.MINIO_ACCESS_KEY}' | base64 -d)
SIM_SECRET=$(kubectl get secret minio-simulation-credentials -n platform-data -o jsonpath='{.data.MINIO_SECRET_KEY}' | base64 -d)

mc alias set simulation http://localhost:9000 "$SIM_ACCESS" "$SIM_SECRET"
echo "sim artifact" | mc pipe simulation/simulation-artifacts/test.txt
# Expected: success

mc ls simulation/execution-artifacts/
# Expected: Access Denied (403) — simulation cannot access production buckets
```

---

## 8. Verify Network Policy (Production Only)

```bash
# From authorized namespace (should succeed)
kubectl run -n platform-control --rm -it test-minio --image=minio/mc:latest --restart=Never -- \
  mc ls http://musematic-minio.platform-data:9000

# From unauthorized namespace (should timeout/refuse)
kubectl run -n default --rm -it test-minio --image=minio/mc:latest --restart=Never -- \
  mc ls http://musematic-minio.platform-data:9000
# Expected: connection refused or timeout
```

---

## 9. Access Management Console

```bash
# Port-forward the console
kubectl port-forward svc/musematic-minio-console 9001:9001 -n platform-data &

# Open in browser: http://localhost:9001
# Login with root credentials:
kubectl get secret minio-root-credentials -n platform-data -o jsonpath='{.data.MINIO_ROOT_USER}' | base64 -d
kubectl get secret minio-root-credentials -n platform-data -o jsonpath='{.data.MINIO_ROOT_PASSWORD}' | base64 -d

# Verify: 8 buckets are visible, lifecycle policies are shown for each bucket
```

---

## 10. Verify Prometheus Metrics

```bash
# Metrics are served on port 9000 at /minio/v2/metrics/cluster
curl -s http://localhost:9000/minio/v2/metrics/cluster \
  -H "Authorization: Bearer $(mc admin prometheus generate local | grep 'bearer_token' | awk '{print $2}')" \
  | grep minio_cluster_nodes_online
# Expected: minio_cluster_nodes_online{...} 4

curl -s http://localhost:9000/minio/v2/metrics/cluster | grep minio_bucket_objects_count
# Expected: per-bucket object counts
```

---

## 11. Using the Python Client

```python
import asyncio
from pathlib import Path
from platform.common.clients.object_storage import AsyncObjectStorageClient
from platform.common.config import Settings

settings = Settings(
    MINIO_ENDPOINT="http://localhost:9000",
    MINIO_ACCESS_KEY="platform",
    MINIO_SECRET_KEY="<secret>",
)
client = AsyncObjectStorageClient(settings)

async def main():
    # Upload small object
    await client.upload_object(
        bucket="execution-artifacts",
        key="exec-001/step-1/result.json",
        data=b'{"status": "ok"}',
        content_type="application/json",
    )

    # Download
    data = await client.download_object("execution-artifacts", "exec-001/step-1/result.json")
    print(data.decode())  # {"status": "ok"}

    # List objects
    objects = await client.list_objects("execution-artifacts", prefix="exec-001/")
    print([o.key for o in objects])

    # Multipart upload for large file
    await client.upload_multipart(
        bucket="reasoning-traces",
        key="exec-001/trace.json",
        file_path=Path("/tmp/large-trace.json"),
    )

    # Pre-signed URL
    url = await client.get_presigned_url("forensic-exports", "req-001/export.zip", expires_in_seconds=3600)
    print(f"Download URL: {url}")

    # Check health
    health = await client.health_check()
    print(health)  # {"status": "ok", "bucket_count": 8}

asyncio.run(main())
```

---

## 12. Run Object Storage Integration Tests Locally

```bash
# Requires Docker (testcontainers spins up MinIO)
export MINIO_TEST_MODE=testcontainers
python -m pytest apps/control-plane/tests/integration/test_object_storage*.py -v
```
