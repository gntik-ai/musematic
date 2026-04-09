# Contract: Python Object Storage Client

**Feature**: 004-minio-object-storage  
**Type**: Python Internal Interface Contract  
**Date**: 2026-04-09  
**Location**: `apps/control-plane/src/platform/common/clients/object_storage.py`

---

## AsyncObjectStorageClient

```python
class AsyncObjectStorageClient:
    def __init__(self, settings: Settings) -> None:
        """
        Initialize using MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY,
        MINIO_USE_SSL from Settings. Uses aioboto3 for async S3 operations.
        """

    async def upload_object(
        self,
        bucket: str,
        key: str,
        data: bytes | AsyncIterator[bytes],
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> None:
        """
        Upload an object. For data > 100 MB, use upload_multipart instead.

        Raises:
            ObjectStorageError: On upload failure.
            BucketNotFoundError: If bucket does not exist.
        """

    async def download_object(self, bucket: str, key: str) -> bytes:
        """
        Download an object and return its full content.

        Raises:
            ObjectNotFoundError: If key does not exist.
            ObjectStorageError: On download failure.
        """

    async def delete_object(self, bucket: str, key: str) -> None:
        """
        Delete an object. No-op if the object does not exist.

        Raises:
            ObjectStorageError: On deletion failure.
        """

    async def list_objects(
        self,
        bucket: str,
        prefix: str = "",
        max_keys: int = 1000,
    ) -> list[ObjectInfo]:
        """
        List objects with optional prefix filter.
        Returns up to max_keys results.

        Raises:
            BucketNotFoundError: If bucket does not exist.
            ObjectStorageError: On list failure.
        """

    async def upload_multipart(
        self,
        bucket: str,
        key: str,
        file_path: Path,
        content_type: str = "application/octet-stream",
        part_size_mb: int = 64,
    ) -> None:
        """
        Upload a large file using S3 multipart upload (recommended for >100 MB).
        Reads from file_path in chunks of part_size_mb megabytes.

        Raises:
            ObjectStorageError: On upload failure (aborts multipart on error).
            BucketNotFoundError: If bucket does not exist.
        """

    async def get_presigned_url(
        self,
        bucket: str,
        key: str,
        operation: Literal["get_object", "put_object"] = "get_object",
        expires_in_seconds: int = 3600,
    ) -> str:
        """
        Generate a pre-signed URL for temporary direct access.
        Default expiry: 1 hour.

        Raises:
            ObjectStorageError: On URL generation failure.
        """

    async def object_exists(self, bucket: str, key: str) -> bool:
        """
        Check if an object exists without downloading it (HEAD request).
        Returns False if object does not exist (no exception raised).
        """

    async def get_object_versions(
        self,
        bucket: str,
        key: str,
    ) -> list[ObjectVersion]:
        """
        List all versions of an object (requires versioning enabled on bucket).
        Only valid for agent-packages bucket.

        Raises:
            ObjectStorageError: If versioning not enabled or on failure.
        """

    async def health_check(self) -> dict[str, Any]:
        """
        Check connectivity and bucket availability.
        Returns {"status": "ok", "bucket_count": 8} or {"status": "error", "error": msg}.
        """
```

---

## Data Types

```python
@dataclass(frozen=True)
class ObjectInfo:
    key: str
    size: int              # bytes
    last_modified: datetime
    etag: str

@dataclass(frozen=True)
class ObjectVersion:
    version_id: str
    key: str
    size: int
    last_modified: datetime
    is_latest: bool
```

---

## Exceptions

```python
class ObjectStorageError(Exception): ...
class ObjectNotFoundError(ObjectStorageError): ...
class BucketNotFoundError(ObjectStorageError): ...
```

---

## Settings Entries

Add to `apps/control-plane/src/platform/common/config.py`:

```python
MINIO_ENDPOINT: str = "http://musematic-minio.platform-data:9000"
MINIO_ACCESS_KEY: str = ""        # from minio-platform-credentials secret
MINIO_SECRET_KEY: str = ""        # from minio-platform-credentials secret
MINIO_USE_SSL: bool = False       # True in production with TLS
```

---

## Usage Pattern

```python
from platform.common.clients.object_storage import AsyncObjectStorageClient
from platform.common.config import settings

# Small object upload
client = AsyncObjectStorageClient(settings)
await client.upload_object(
    bucket="execution-artifacts",
    key=f"{execution_id}/step-3/output.json",
    data=json.dumps(result).encode(),
    content_type="application/json",
)

# Large file upload (>100 MB)
await client.upload_multipart(
    bucket="reasoning-traces",
    key=f"{execution_id}/cot/full-trace.json",
    file_path=Path("/tmp/trace.json"),
    content_type="application/json",
)

# Download
data = await client.download_object("execution-artifacts", key)

# List with prefix
objects = await client.list_objects("execution-artifacts", prefix=f"{execution_id}/")

# Pre-signed URL for direct operator download
url = await client.get_presigned_url("forensic-exports", key, expires_in_seconds=86400)

# Version history (agent-packages only)
versions = await client.get_object_versions("agent-packages", "finance-ops/kyc-verifier/1.0.0.tar.gz")
```
