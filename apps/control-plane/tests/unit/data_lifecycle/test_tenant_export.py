"""Unit tests for ExportService.request_tenant_export + run_tenant_export."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime, timedelta
from platform.common.config import DataLifecycleSettings
from platform.data_lifecycle.exceptions import ExportRateLimitExceededError
from platform.data_lifecycle.models import DataExportJob, ExportStatus, ScopeType
from platform.data_lifecycle.services.export_service import ExportService
from typing import Any
from uuid import UUID, uuid4

import pytest

# Reuse the stubs from the workspace test by replicating the minimum.


class _StubRepo:
    def __init__(self) -> None:
        self.created: list[DataExportJob] = []
        self._active: DataExportJob | None = None
        self._recent_count = 0
        self.status_updates: list[dict[str, Any]] = []

    async def find_active_export_for_scope(
        self, *, scope_type: str, scope_id: UUID
    ) -> DataExportJob | None:
        return self._active

    async def count_recent_exports_for_scope(
        self, *, scope_type: str, scope_id: UUID, within: timedelta
    ) -> int:
        return self._recent_count

    async def create_export_job(self, **kwargs: Any) -> DataExportJob:
        job = DataExportJob(
            tenant_id=kwargs["tenant_id"],
            scope_type=kwargs["scope_type"],
            scope_id=kwargs["scope_id"],
            requested_by_user_id=kwargs["requested_by_user_id"],
            status=ExportStatus.pending.value,
        )
        object.__setattr__(job, "id", uuid4())
        object.__setattr__(job, "created_at", datetime.now(UTC))
        self.created.append(job)
        return job

    async def update_export_status(self, **kwargs: Any) -> None:
        self.status_updates.append(kwargs)


class _StubProducer:
    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []

    async def publish(self, **kwargs: Any) -> None:
        self.published.append(kwargs)


class _StubAudit:
    def __init__(self) -> None:
        self.appended: list[bytes] = []

    async def append(self, *args: Any, **kwargs: Any) -> None:
        self.appended.append(args[2] if len(args) >= 3 else b"")


class _StubObjectStorage:
    def __init__(self) -> None:
        self.uploads: list[tuple[str, str, bytes]] = []

    async def create_bucket_if_not_exists(self, bucket: str) -> None:
        return None

    async def put_object(
        self, bucket: str, key: str, body: bytes, *, content_type: str = ""
    ) -> None:
        self.uploads.append((bucket, key, body))

    async def get_presigned_url(
        self, bucket: str, key: str, operation: str = "get_object", expires_in_seconds: int = 3600
    ) -> str:
        return f"https://stub.local/{bucket}/{key}?ttl={expires_in_seconds}"


class _StubRedis:
    async def set(
        self, name: str, value: str, *, nx: bool = False, ex: int | None = None
    ) -> bool | None:
        return True

    async def delete(self, *names: str) -> int:
        return len(names)


def _build(
    *,
    repo: _StubRepo | None = None,
    serializers: dict | None = None,
) -> tuple[ExportService, _StubRepo, _StubObjectStorage, _StubProducer]:
    repo = repo or _StubRepo()
    storage = _StubObjectStorage()
    producer = _StubProducer()
    service = ExportService(
        repository=repo,  # type: ignore[arg-type]
        settings=DataLifecycleSettings(),
        object_storage=storage,  # type: ignore[arg-type]
        audit_chain=_StubAudit(),  # type: ignore[arg-type]
        event_producer=producer,  # type: ignore[arg-type]
        redis_client=_StubRedis(),  # type: ignore[arg-type]
        tenant_serializers=serializers or {},
    )
    return service, repo, storage, producer


@pytest.mark.asyncio
async def test_request_tenant_export_creates_pending_job() -> None:
    service, _repo, _, producer = _build()
    job = await service.request_tenant_export(
        tenant_id=uuid4(), requested_by_user_id=uuid4()
    )
    assert job.scope_type == ScopeType.tenant.value
    assert job.status == ExportStatus.pending.value
    types = [p["event_type"] for p in producer.published]
    assert "data_lifecycle.export.requested" in types


@pytest.mark.asyncio
async def test_tenant_export_rate_limit_enforced() -> None:
    service, repo, _, _ = _build()
    repo._recent_count = 5
    with pytest.raises(ExportRateLimitExceededError):
        await service.request_tenant_export(
            tenant_id=uuid4(), requested_by_user_id=uuid4()
        )


@pytest.mark.asyncio
async def test_run_tenant_export_uploads_zip_and_completes() -> None:
    async def _meta(*, scope_id: UUID, tenant_id: UUID):
        yield "tenant/tenant.json", b'{"id": "fake"}'

    service, repo, storage, producer = _build(serializers={"meta": _meta})
    job = DataExportJob(
        tenant_id=uuid4(),
        scope_type=ScopeType.tenant.value,
        scope_id=uuid4(),
        status=ExportStatus.pending.value,
    )
    object.__setattr__(job, "id", uuid4())
    object.__setattr__(job, "created_at", datetime.now(UTC))

    await service.run_tenant_export(job=job, worker_id="test", correlation_ctx=None)

    assert len(storage.uploads) == 1
    _bucket, key, body = storage.uploads[0]
    assert key.startswith(f"tenant/{job.scope_id}/")
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        names = set(zf.namelist())
        assert "metadata.json" in names
        assert "README.md" in names
        assert "tenant/tenant.json" in names
        meta = json.loads(zf.read("metadata.json"))
        assert meta["scope_type"] == "tenant"

    statuses = [u.get("status") for u in repo.status_updates]
    assert "completed" in statuses
    final = repo.status_updates[-1]
    # Tenant TTL is 30 days vs workspace 7.
    assert final["output_url"].startswith("https://stub.local/")
    types = [p["event_type"] for p in producer.published]
    assert "data_lifecycle.export.completed" in types


@pytest.mark.asyncio
async def test_run_tenant_export_handles_storage_failure() -> None:
    class _BoomStorage(_StubObjectStorage):
        async def put_object(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("S3ConnectionError")

    repo = _StubRepo()
    storage = _BoomStorage()
    producer = _StubProducer()
    service = ExportService(
        repository=repo,  # type: ignore[arg-type]
        settings=DataLifecycleSettings(),
        object_storage=storage,  # type: ignore[arg-type]
        audit_chain=_StubAudit(),  # type: ignore[arg-type]
        event_producer=producer,  # type: ignore[arg-type]
        redis_client=_StubRedis(),  # type: ignore[arg-type]
        tenant_serializers={},
    )
    job = DataExportJob(
        tenant_id=uuid4(),
        scope_type=ScopeType.tenant.value,
        scope_id=uuid4(),
        status=ExportStatus.pending.value,
    )
    object.__setattr__(job, "id", uuid4())
    object.__setattr__(job, "created_at", datetime.now(UTC))

    await service.run_tenant_export(job=job, worker_id="test", correlation_ctx=None)

    statuses = [u.get("status") for u in repo.status_updates]
    assert "failed" in statuses
    types = [p["event_type"] for p in producer.published]
    assert "data_lifecycle.export.failed" in types
