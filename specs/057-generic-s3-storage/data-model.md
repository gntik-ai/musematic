# Data Model & Change Map: Generic S3 Storage — Remove MinIO Hard Dependency

**Feature**: `specs/057-generic-s3-storage/spec.md`
**Date**: 2026-04-18

No database schema changes. No Alembic migrations required. This feature is a configuration rename, client update, and deployment refactor.

---

## Configuration Entity: `ObjectStorageSettings`

Replaces `MinIOSettings` in `apps/control-plane/src/platform/common/config.py`.

### Before

```python
class MinIOSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MINIO_", extra="ignore")

    endpoint: str = "http://localhost:9000"
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin"
    default_bucket: str = "platform-artifacts"
    use_ssl: bool = False
```

### After

```python
class ObjectStorageSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="S3_", extra="ignore")

    endpoint_url: str = ""               # Empty = AWS S3 default; set for Hetzner, MinIO, R2, etc.
    access_key: str = "minioadmin"       # Default for local MinIO dev
    secret_key: str = "minioadmin"       # Default for local MinIO dev
    region: str = "us-east-1"           # Required for Hetzner + AWS; MinIO ignores it
    bucket_prefix: str = "platform"     # All bucket names = f"{prefix}-{logical_name}"
    use_path_style: bool = True         # True for MinIO/Hetzner/Wasabi; False for AWS
    provider: str = "generic"           # Informational: generic|minio|aws|hetzner|r2|wasabi
```

### `PlatformSettings` field rename

```python
# Before:
minio: MinIOSettings = Field(default_factory=MinIOSettings)

# After:
s3: ObjectStorageSettings = Field(default_factory=ObjectStorageSettings)
```

### New `_expand_flat_settings` mappings (additive)

```python
# New S3_* primary mappings
"S3_ENDPOINT_URL":   ("s3", "endpoint_url"),
"S3_ACCESS_KEY":     ("s3", "access_key"),
"S3_SECRET_KEY":     ("s3", "secret_key"),
"S3_REGION":         ("s3", "region"),
"S3_BUCKET_PREFIX":  ("s3", "bucket_prefix"),
"S3_USE_PATH_STYLE": ("s3", "use_path_style"),
"S3_PROVIDER":       ("s3", "provider"),
# Keep MINIO_* as backward-compat aliases (existing deployments unbroken)
"MINIO_ENDPOINT":    ("s3", "endpoint_url"),
"MINIO_ACCESS_KEY":  ("s3", "access_key"),
"MINIO_SECRET_KEY":  ("s3", "secret_key"),
# Drop MINIO_DEFAULT_BUCKET (never used by client) and MINIO_USE_SSL (was a no-op)
```

### Removed properties on `PlatformSettings`

Replace `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_DEFAULT_BUCKET`, `MINIO_USE_SSL` properties with `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION`, `S3_BUCKET_PREFIX`, `S3_USE_PATH_STYLE`, `S3_PROVIDER`.

Also: `MINIO_BUCKET_DEAD_LETTERS` property maps to `connectors.dead_letter_bucket` — rename to `S3_BUCKET_DEAD_LETTERS` in both the property name and the `_expand_flat_settings` alias.

---

## Modified Files (Exact Targets)

### Python Control Plane

| File | Change |
|---|---|
| `apps/control-plane/src/platform/common/config.py` | Rename `MinIOSettings` → `ObjectStorageSettings`, env prefix `S3_`, new fields, backward-compat aliases in `_expand_flat_settings`, rename `PlatformSettings.minio` → `PlatformSettings.s3` |
| `apps/control-plane/src/platform/common/clients/object_storage.py` | `AsyncObjectStorageClient.__init__`: replace `settings.MINIO_*` with `settings.s3.*`; make endpoint_url conditional; make region and addressing_style configurable; remove `use_ssl`; update `health_check()` to use `head_bucket` + add provider/endpoint to response |
| `apps/control-plane/src/platform/main.py` | Rename `app.state.clients["minio"]` key → `app.state.clients["object_storage"]` in registration (line 161) and all ~27 dereference sites |
| `apps/control-plane/src/platform/execution/dependencies.py:45` | `clients["minio"]` → `clients["object_storage"]` |
| `apps/control-plane/src/platform/evaluation/dependencies.py:48` | `clients["minio"]` → `clients["object_storage"]` |
| `apps/control-plane/src/platform/evaluation/router.py:117,179` | `clients["minio"]` → `clients["object_storage"]` |
| `apps/control-plane/src/platform/context_engineering/dependencies.py:46` | `clients["minio"]` → `clients["object_storage"]` |
| `apps/control-plane/src/platform/simulation/dependencies.py:150` | `clients["minio"]` → `clients["object_storage"]` |
| `apps/control-plane/src/platform/registry/dependencies.py:25` | `clients["minio"]` → `clients["object_storage"]` |
| `apps/control-plane/src/platform/testing/dependencies.py` | `clients["minio"]` → `clients["object_storage"]` |
| `apps/control-plane/src/platform/connectors/dependencies.py` | `clients["minio"]` → `clients["object_storage"]` |
| `apps/control-plane/src/platform/fleet_learning/dependencies.py:41` | `clients["minio"]` → `clients["object_storage"]` |
| `apps/control-plane/src/platform/trust/dependencies.py` | `clients["minio"]` → `clients["object_storage"]` |
| `apps/control-plane/src/platform/composition/dependencies.py` | `clients["minio"]` → `clients["object_storage"]` |

**NOT changed** (scoping decision from Decision 3):
- `fleet_learning/models.py:162` — DB column `pattern_minio_key` remains unchanged
- `fleet_learning/schemas.py:157` — Pydantic field `pattern_minio_key` remains unchanged
- `fleet_learning/transfer.py` — 5 references to `pattern_minio_key` remain unchanged

### Go Satellite Services

| File | Change |
|---|---|
| `services/runtime-controller/pkg/config/config.go` | Rename `MinIOEndpoint` → `S3EndpointURL`, `MinIOBucket` → `S3Bucket`; add `S3AccessKey`, `S3SecretKey`, `S3Region`, `S3UsePathStyle`; read `S3_ENDPOINT_URL` (fall back to `MINIO_ENDPOINT`), `S3_BUCKET` (fall back to `MINIO_BUCKET`), `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION`, `S3_USE_PATH_STYLE` |
| `services/runtime-controller/pkg/config/config_test.go` | Update test cases for renamed fields |
| `services/sandbox-manager/internal/artifacts/minio_uploader.go` → `s3_uploader.go` | Rename file; rename struct `MinIOUploader` → `S3Uploader`; rename constructor `NewMinIOUploader` → `NewS3Uploader`; retain HTTP PUT logic |
| `services/sandbox-manager/internal/artifacts/minio_uploader_test.go` → `s3_uploader_test.go` | Rename file; update struct/constructor references |
| `services/simulation-controller/pkg/persistence/minio.go` → `s3_client.go` | Rename file; rename struct `MinIOClient` → `S3Client`; rename constructor `NewMinIOClient` → `NewS3Client`; retain HTTP PUT logic |
| `services/simulation-controller/cmd/simulation-controller/main.go` | Update `persistence.NewMinIOClient` → `persistence.NewS3Client`; rename local var `minio` → `s3Client`; update env var reads from `MINIO_ENDPOINT` → `S3_ENDPOINT_URL` (with fallback); update error message string "MINIO_ENDPOINT is required" |
| `services/simulation-controller/cmd/simulation-controller/main_test.go` | Update test helper references |
| `services/simulation-controller/pkg/persistence/persistence_test.go` | Update struct references |

### Helm Charts (Deployment)

| File | Change |
|---|---|
| `deploy/helm/minio/values.yaml` | Add `minio.enabled: true` flag at root; keeps existing behavior when `true` |
| `deploy/helm/minio/templates/*.yaml` (all templates except `secret-platform.yaml`) | Wrap in `{{- if .Values.minio.enabled }}...{{- end }}` |
| `deploy/helm/minio/templates/secret-platform.yaml` | Keep unconditional — this secret's keys renamed from `MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY` → `S3_ACCESS_KEY`/`S3_SECRET_KEY` (additive: also emit `S3_ENDPOINT_URL` for the MinIO cluster endpoint) |
| `deploy/helm/minio/templates/bucket-init-job-generic.yaml` | NEW — provider-agnostic bucket-init Job using `amazon/aws-cli`; runs when `minio.enabled: false`; creates `{prefix}-{name}` buckets via `aws s3 mb --endpoint-url` |
| `deploy/helm/simulation-controller/templates/secret.yaml` | Rename `MINIO_ENDPOINT` → `S3_ENDPOINT_URL`, `MINIO_ACCESS_KEY` → `S3_ACCESS_KEY`, `MINIO_SECRET_KEY` → `S3_SECRET_KEY`; update `values.yaml` keys accordingly |

### Dev/Test Stack

| File | Change |
|---|---|
| `services/runtime-controller/testdata/docker-compose.yml` | Add `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` env vars to platform service; keep MinIO container |
| `services/sandbox-manager/testdata/docker-compose.yml` | Same pattern |

---

## `AsyncObjectStorageClient.__init__` — Before / After

### Before (lines 40-46)

```python
self._client_kwargs = {
    "endpoint_url": self.settings.MINIO_ENDPOINT,
    "aws_access_key_id": self.settings.MINIO_ACCESS_KEY,
    "aws_secret_access_key": self.settings.MINIO_SECRET_KEY,
    "region_name": "us-east-1",
    "use_ssl": self.settings.MINIO_USE_SSL,
    "config": Config(signature_version="s3v4", s3={"addressing_style": "path"}),
}
```

### After

```python
self._client_kwargs: dict[str, Any] = {
    "aws_access_key_id": self.settings.s3.access_key,
    "aws_secret_access_key": self.settings.s3.secret_key,
    "region_name": self.settings.s3.region,
    "config": Config(
        signature_version="s3v4",
        s3={"addressing_style": "path" if self.settings.s3.use_path_style else "virtual"},
    ),
}
if self.settings.s3.endpoint_url:
    self._client_kwargs["endpoint_url"] = self.settings.s3.endpoint_url
```

---

## `health_check()` — Before / After

### Before (lines 289-296)

```python
async def health_check(self) -> dict[str, Any]:
    try:
        async with self._client() as s3:
            response = await s3.list_buckets()
        buckets = response.get("Buckets", [])
        return {"status": "ok", "bucket_count": len(buckets)}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
```

### After

```python
async def health_check(self) -> dict[str, Any]:
    probe_bucket = f"{self.settings.s3.bucket_prefix}-agent-packages"
    try:
        async with self._client() as s3:
            await s3.head_bucket(Bucket=probe_bucket)
        return {
            "status": "ok",
            "provider": self.settings.s3.provider,
            "endpoint": self.settings.s3.endpoint_url or "aws-default",
        }
    except Exception as exc:
        return {
            "status": "error",
            "provider": self.settings.s3.provider,
            "endpoint": self.settings.s3.endpoint_url or "aws-default",
            "error": str(exc),
        }
```

---

## Bucket Name Convention

All platform buckets are now named `{S3_BUCKET_PREFIX}-{logical_name}`. With `S3_BUCKET_PREFIX=platform` (default):

| Logical name | Full bucket name |
|---|---|
| `agent-packages` | `platform-agent-packages` |
| `execution-artifacts` | `platform-execution-artifacts` |
| `reasoning-traces` | `platform-reasoning-traces` |
| `context-assembly-records` | `platform-context-assembly-records` |
| `trust-evidence` | `platform-trust-evidence` |
| `fleet-patterns` | `platform-fleet-patterns` |
| `simulation-artifacts` | `platform-simulation-artifacts` |
| `connector-dead-letters` | `platform-connector-dead-letters` |

Individual context settings (e.g., `REGISTRY_PACKAGE_BUCKET`, `TRUST_EVIDENCE_BUCKET`) continue to specify the logical bucket name without prefix; the `AsyncObjectStorageClient` resolves the full name. (No change to those settings fields.)

**Note**: The current bucket names in individual context settings (e.g., `REGISTRY_PACKAGE_BUCKET = "agent-packages"`) already match the `{prefix}-{name}` convention when `S3_BUCKET_PREFIX=platform` with a dash separator. However, the `AsyncObjectStorageClient` does NOT currently prepend the prefix — bucket names are passed through as-is. The prefix feature is additive and should be opt-in: if `S3_BUCKET_PREFIX` is set to a non-default value, a utility or the bucket-init job handles it; the Python client does not prepend automatically to avoid breaking existing bucket layouts.
