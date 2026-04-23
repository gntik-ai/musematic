# Quickstart & Test Scenarios: Generic S3 Storage

**Feature**: `specs/057-generic-s3-storage/spec.md`
**Date**: 2026-04-18

---

## Setup Prerequisites

```python
# Local MinIO (dev stack)
S3_ENDPOINT_URL = "http://localhost:9000"
S3_ACCESS_KEY   = "minioadmin"
S3_SECRET_KEY   = "minioadmin"
S3_REGION       = "us-east-1"
S3_BUCKET_PREFIX = "platform"
S3_USE_PATH_STYLE = True
S3_PROVIDER     = "minio"
```

---

## US1 — Operator installs with external S3 provider

### Scenario 1 — Client connects to provider when endpoint URL is set

```python
# Settings: S3_ENDPOINT_URL="https://fsn1.your-objectstorage.com", S3_USE_PATH_STYLE=True
client = AsyncObjectStorageClient(settings)
# verify _client_kwargs has endpoint_url set and addressing_style="path"
assert client._client_kwargs["endpoint_url"] == "https://fsn1.your-objectstorage.com"
s3_config = client._client_kwargs["config"]
assert s3_config.s3["addressing_style"] == "path"
```

### Scenario 2 — Client uses AWS default when endpoint URL is empty

```python
# Settings: S3_ENDPOINT_URL="", S3_USE_PATH_STYLE=False
client = AsyncObjectStorageClient(settings)
assert "endpoint_url" not in client._client_kwargs
s3_config = client._client_kwargs["config"]
assert s3_config.s3["addressing_style"] == "virtual"
```

### Scenario 3 — Region is passed to client

```python
# Settings: S3_REGION="eu-central-1"
client = AsyncObjectStorageClient(settings)
assert client._client_kwargs["region_name"] == "eu-central-1"
```

### Scenario 4 — Bucket operations work end-to-end against local MinIO (smoke test)

```python
client = AsyncObjectStorageClient(settings)  # pointed at local MinIO
await client.create_bucket_if_not_exists("platform-agent-packages")
await client.upload_object("platform-agent-packages", "test-key", b"hello", "text/plain")
data = await client.download_object("platform-agent-packages", "test-key")
assert data == b"hello"
```

---

## US2 — Existing installation continues on self-hosted MinIO

### Scenario 5 — MINIO_* env vars still work via backward-compat aliases

```python
# Deploy scenario: MINIO_ENDPOINT is set, no S3_ENDPOINT_URL
import os
os.environ["MINIO_ENDPOINT"] = "http://legacy-minio:9000"
os.environ["MINIO_ACCESS_KEY"] = "admin"
os.environ["MINIO_SECRET_KEY"] = "password"

settings = PlatformSettings()
assert settings.s3.endpoint_url == "http://legacy-minio:9000"
assert settings.s3.access_key == "admin"
# client is created without error
client = AsyncObjectStorageClient(settings)
assert client._client_kwargs["endpoint_url"] == "http://legacy-minio:9000"
```

### Scenario 6 — S3_* takes precedence over MINIO_* when both are set

```python
os.environ["MINIO_ENDPOINT"] = "http://old-endpoint:9000"
os.environ["S3_ENDPOINT_URL"] = "https://new-endpoint.example.com"

settings = PlatformSettings()
assert settings.s3.endpoint_url == "https://new-endpoint.example.com"
```

---

## US4 — Operator observes S3 backend health

### Scenario 7 — Health check reports healthy with provider info

```python
# Local MinIO running; platform-agent-packages bucket exists
result = await client.health_check()
assert result["status"] == "ok"
assert result["provider"] == "minio"
assert result["endpoint"] == "http://localhost:9000"
assert "access_key" not in str(result)
assert "secret" not in str(result)
```

### Scenario 8 — Health check reports unhealthy when endpoint unreachable

```python
# Settings: S3_ENDPOINT_URL="http://nonexistent:9000"
client = AsyncObjectStorageClient(settings)
result = await client.health_check()
assert result["status"] == "error"
assert "error" in result
assert result["provider"] == "generic"
# No credentials in response
assert os.environ.get("S3_ACCESS_KEY", "minioadmin") not in str(result)
```

### Scenario 9 — AWS default endpoint indicator

```python
# Settings: S3_ENDPOINT_URL=""
result = await client.health_check()
assert result["endpoint"] == "aws-default"
```

---

## Config rename — unit tests

### Scenario 10 — ObjectStorageSettings has correct env prefix

```python
os.environ["S3_ENDPOINT_URL"] = "http://test:9000"
os.environ["S3_REGION"] = "eu-central-1"
os.environ["S3_USE_PATH_STYLE"] = "true"
os.environ["S3_PROVIDER"] = "hetzner"

s3 = ObjectStorageSettings()
assert s3.endpoint_url == "http://test:9000"
assert s3.region == "eu-central-1"
assert s3.use_path_style is True
assert s3.provider == "hetzner"
```

### Scenario 11 — PlatformSettings.s3 replaces PlatformSettings.minio

```python
settings = PlatformSettings()
assert hasattr(settings, "s3")
assert not hasattr(settings, "minio")
assert isinstance(settings.s3, ObjectStorageSettings)
```

### Scenario 12 — Internal client dict key is `object_storage`

```python
# mock FastAPI app startup
from platform.main import create_app
app = create_app()
async with app.lifespan():  # or equivalent startup
    assert "object_storage" in app.state.clients
    assert "minio" not in app.state.clients
```

---

## Go config — unit tests

### Scenario 13 — S3_ENDPOINT_URL takes precedence over MINIO_ENDPOINT

```go
os.Setenv("S3_ENDPOINT_URL", "https://new.example.com")
os.Setenv("MINIO_ENDPOINT", "http://old.example.com")
cfg, err := config.Load()
assert.NoError(t, err)
assert.Equal(t, "https://new.example.com", cfg.S3EndpointURL)
```

### Scenario 14 — Falls back to MINIO_ENDPOINT when S3_ENDPOINT_URL not set

```go
os.Unsetenv("S3_ENDPOINT_URL")
os.Setenv("MINIO_ENDPOINT", "http://minio:9000")
cfg, err := config.Load()
assert.NoError(t, err)
assert.Equal(t, "http://minio:9000", cfg.S3EndpointURL)
```

---

## Helm deployment — manual scenarios

### Scenario 15 — External S3 install: no MinIO workload deployed

```bash
helm install musematic . \
  --set minio.enabled=false \
  --set s3.endpointUrl="https://fsn1.your-objectstorage.com" \
  --set s3.accessKey="key" \
  --set s3.secretKey="secret" \
  --set s3.region="eu-central-1"

# Verify: no minio pods or PVCs
kubectl get pods -n platform-data | grep minio | wc -l  # should be 0
kubectl get pvc -n platform-data | grep minio | wc -l   # should be 0
```

### Scenario 16 — Generic bucket-init Job creates all required buckets

```bash
# After install with external S3, verify bucket-init Job completed
kubectl get job bucket-init -n platform-system -o jsonpath='{.status.succeeded}'  # should be 1

# All 8 buckets exist on external provider
aws s3 ls --endpoint-url https://fsn1.your-objectstorage.com | grep platform-
# Expected: platform-agent-packages, platform-execution-artifacts, etc.
```

### Scenario 17 — MinIO install: minio pods deployed (backward compat)

```bash
helm install musematic . --set minio.enabled=true

kubectl get pods -n platform-data | grep minio  # should show minio pods
```

### Scenario 18 — Simulation-controller secret uses S3_* env vars

```bash
kubectl get secret simulation-controller-secrets -o jsonpath='{.data}' | \
  python3 -c "import sys,json,base64; d=json.load(sys.stdin); print(list(d.keys()))"
# Expected: ['POSTGRES_DSN', 'KAFKA_BROKERS', 'S3_ENDPOINT_URL', 'S3_ACCESS_KEY', 'S3_SECRET_KEY']
# NOT: MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY
```

---

## Backward-compatibility — migration scenarios

### Scenario 19 — Existing install with MINIO_* env vars is unbroken

```bash
# Pre-existing deployment with MINIO_ENDPOINT configured
kubectl set env deployment/musematic-api MINIO_ENDPOINT=http://musematic-minio.platform-data:9000
kubectl set env deployment/musematic-api MINIO_ACCESS_KEY=platform
kubectl set env deployment/musematic-api MINIO_SECRET_KEY=supersecret
# After upgrade, verify platform starts and health check passes
curl http://musematic:8000/health/s3  # status=ok
```

### Scenario 20 — No MinIO vendor strings in application code post-change

```bash
# Run from repo root after applying all changes
grep -r "\"minio\"" apps/control-plane/src/ --include="*.py" | \
  grep -v "MinIOSettings\|__pycache__\|\.pyc" | wc -l  # should be 0

# fleet_learning exception confirmed
grep "pattern_minio_key" apps/control-plane/src/ -r | wc -l  # >=5 (expected, scoped out)
```
