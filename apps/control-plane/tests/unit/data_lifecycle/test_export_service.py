"""Unit tests for ExportService.request_workspace_export.

Covers:
* Idempotency — concurrent requests against the same workspace return
  the existing in-flight job (T026).
* Cross-region residency refusal (T027).
* Rate limit enforcement (request endpoint contract).
* Audit + Kafka emission on success.

ExportService.run_workspace_export (worker path) is exercised via a
zip-buffer fake so we can assert the ZIP layout without spinning up
S3/Postgres.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime, timedelta
from platform.common.config import DataLifecycleSettings
from platform.data_lifecycle.exceptions import (
    CrossRegionExportBlockedError,
    ExportRateLimitExceededError,
)
from platform.data_lifecycle.models import DataExportJob, ExportStatus, ScopeType
from platform.data_lifecycle.services.export_service import ExportService
from typing import Any
from uuid import UUID, uuid4

import pytest

# ---------- Stubs ----------


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

    async def create_export_job(
        self,
        *,
        tenant_id: UUID,
        scope_type: str,
        scope_id: UUID,
        requested_by_user_id: UUID | None,
        correlation_id: UUID | None = None,
    ) -> DataExportJob:
        job = DataExportJob(
            tenant_id=tenant_id,
            scope_type=scope_type,
            scope_id=scope_id,
            requested_by_user_id=requested_by_user_id,
            status=ExportStatus.pending.value,
            correlation_id=correlation_id,
        )
        # SQLAlchemy doesn't auto-populate id/created_at without a session;
        # mimic them so callers don't need a real DB.
        object.__setattr__(job, "id", uuid4())
        object.__setattr__(job, "created_at", datetime.now(UTC))
        self.created.append(job)
        return job

    async def update_export_status(self, **kwargs: Any) -> None:
        self.status_updates.append(kwargs)


class _StubProducer:
    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []

    async def publish(
        self,
        *,
        topic: str,
        key: str,
        event_type: str,
        payload: dict[str, Any],
        correlation_ctx: Any,
        source: str,
    ) -> None:
        self.published.append(
            {"topic": topic, "key": key, "event_type": event_type, "payload": payload}
        )


class _StubAudit:
    def __init__(self) -> None:
        self.appended: list[bytes] = []

    async def append(
        self, audit_event_id: UUID, namespace: str, canonical_payload: bytes
    ) -> None:
        self.appended.append(canonical_payload)


class _StubObjectStorage:
    def __init__(self) -> None:
        self.uploads: list[tuple[str, str, bytes]] = []
        self.signed_urls: list[tuple[str, str]] = []

    async def create_bucket_if_not_exists(self, bucket: str) -> None:
        return None

    async def put_object(
        self, bucket: str, key: str, body: bytes, *, content_type: str = ""
    ) -> None:
        self.uploads.append((bucket, key, body))

    async def get_presigned_url(
        self,
        bucket: str,
        key: str,
        operation: str = "get_object",
        expires_in_seconds: int = 3600,
    ) -> str:
        self.signed_urls.append((bucket, key))
        return f"https://stub.local/{bucket}/{key}?ttl={expires_in_seconds}"


class _StubRedis:
    def __init__(self, *, accept_lease: bool = True) -> None:
        self.accept_lease = accept_lease
        self.calls: list[tuple[str, ...]] = []

    async def set(
        self, name: str, value: str, *, nx: bool = False, ex: int | None = None
    ) -> bool | None:
        self.calls.append(("set", name, value))
        return self.accept_lease

    async def delete(self, *names: str) -> int:
        self.calls.append(("delete", *names))
        return len(names)


def _build_service(
    *,
    repo: _StubRepo,
    producer: _StubProducer | None = None,
    audit: _StubAudit | None = None,
    storage: _StubObjectStorage | None = None,
    redis: _StubRedis | None = None,
    serializers: dict[str, Any] | None = None,
) -> ExportService:
    return ExportService(
        repository=repo,  # type: ignore[arg-type]
        settings=DataLifecycleSettings(),
        object_storage=storage or _StubObjectStorage(),  # type: ignore[arg-type]
        audit_chain=audit,  # type: ignore[arg-type]
        event_producer=producer,  # type: ignore[arg-type]
        redis_client=redis,  # type: ignore[arg-type]
        workspace_serializers=serializers or {},
    )


# ---------- Tests ----------


@pytest.mark.asyncio
async def test_request_workspace_export_creates_pending_job() -> None:
    repo = _StubRepo()
    producer = _StubProducer()
    audit = _StubAudit()
    service = _build_service(repo=repo, producer=producer, audit=audit)

    tenant_id = uuid4()
    workspace_id = uuid4()
    user_id = uuid4()
    job = await service.request_workspace_export(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        requested_by_user_id=user_id,
        correlation_ctx=None,
    )

    assert job.status == ExportStatus.pending.value
    assert job.scope_type == ScopeType.workspace.value
    assert job.scope_id == workspace_id
    assert len(repo.created) == 1
    assert len(producer.published) == 1
    assert producer.published[0]["event_type"] == "data_lifecycle.export.requested"
    assert len(audit.appended) == 1


@pytest.mark.asyncio
async def test_request_workspace_export_is_idempotent_against_active_job() -> None:
    """T026 — concurrent requests return the same in-flight job."""

    repo = _StubRepo()
    workspace_id = uuid4()
    tenant_id = uuid4()
    # Pre-seed an active job.
    existing = DataExportJob(
        tenant_id=tenant_id,
        scope_type=ScopeType.workspace.value,
        scope_id=workspace_id,
        status=ExportStatus.processing.value,
        requested_by_user_id=uuid4(),
    )
    object.__setattr__(existing, "id", uuid4())
    object.__setattr__(existing, "created_at", datetime.now(UTC))
    repo._active = existing

    service = _build_service(repo=repo, producer=_StubProducer())

    returned = await service.request_workspace_export(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        requested_by_user_id=uuid4(),
        correlation_ctx=None,
    )

    assert returned is existing
    assert repo.created == []  # no new row created


@pytest.mark.asyncio
async def test_rate_limit_enforced_per_workspace() -> None:
    repo = _StubRepo()
    repo._recent_count = 5  # at the cap by default
    service = _build_service(repo=repo)

    with pytest.raises(ExportRateLimitExceededError):
        await service.request_workspace_export(
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            requested_by_user_id=uuid4(),
            correlation_ctx=None,
        )


@pytest.mark.asyncio
async def test_residency_check_blocks_cross_region() -> None:
    """T027 — cross-region requests are refused before row creation."""

    repo = _StubRepo()
    service = _build_service(repo=repo)

    async def _deny(_t: UUID, _w: UUID) -> bool:
        return False

    with pytest.raises(CrossRegionExportBlockedError):
        await service.request_workspace_export(
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            requested_by_user_id=uuid4(),
            correlation_ctx=None,
            residency_check=_deny,
        )

    assert repo.created == []


@pytest.mark.asyncio
async def test_residency_check_passes_when_allowed() -> None:
    repo = _StubRepo()
    service = _build_service(repo=repo, producer=_StubProducer())

    async def _allow(_t: UUID, _w: UUID) -> bool:
        return True

    job = await service.request_workspace_export(
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        requested_by_user_id=uuid4(),
        correlation_ctx=None,
        residency_check=_allow,
    )
    assert job.status == ExportStatus.pending.value


@pytest.mark.asyncio
async def test_run_workspace_export_uploads_zip_and_completes() -> None:
    repo = _StubRepo()
    producer = _StubProducer()
    audit = _StubAudit()
    storage = _StubObjectStorage()
    redis = _StubRedis(accept_lease=True)

    async def _agents(*, scope_id: UUID, tenant_id: UUID):
        yield "agents/index.json", b'{"items": []}'

    service = _build_service(
        repo=repo,
        producer=producer,
        audit=audit,
        storage=storage,
        redis=redis,
        serializers={"agents": _agents},
    )

    job = DataExportJob(
        tenant_id=uuid4(),
        scope_type=ScopeType.workspace.value,
        scope_id=uuid4(),
        status=ExportStatus.pending.value,
        requested_by_user_id=uuid4(),
    )
    object.__setattr__(job, "id", uuid4())
    object.__setattr__(job, "created_at", datetime.now(UTC))

    await service.run_workspace_export(
        job=job, worker_id="test-worker-1", correlation_ctx=None
    )

    # Lease acquired and released.
    assert any(call[0] == "set" for call in redis.calls)
    assert any(call[0] == "delete" for call in redis.calls)

    # ZIP uploaded.
    assert len(storage.uploads) == 1
    bucket, key, body = storage.uploads[0]
    assert bucket == "data-lifecycle-exports"
    assert key.startswith(f"workspace/{job.scope_id}/")
    # Body is a valid ZIP with the expected layout.
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        names = set(zf.namelist())
        assert "metadata.json" in names
        assert "README.md" in names
        assert "agents/index.json" in names
        meta = json.loads(zf.read("metadata.json"))
        assert meta["scope_type"] == "workspace"

    # Status flipped to completed and signed URL recorded.
    statuses = [u.get("status") for u in repo.status_updates]
    assert "processing" in statuses
    assert "completed" in statuses
    final = repo.status_updates[-1]
    assert final["output_url"].startswith("https://stub.local/")
    assert final["output_size_bytes"] == len(body)

    # Started + completed Kafka events emitted.
    types = [p["event_type"] for p in producer.published]
    assert "data_lifecycle.export.started" in types
    assert "data_lifecycle.export.completed" in types

    # Audit chain entries appended for completion.
    assert any(b"export_completed" in payload for payload in audit.appended)


@pytest.mark.asyncio
async def test_run_workspace_export_records_failure_on_storage_error() -> None:
    repo = _StubRepo()
    producer = _StubProducer()

    class _BoomStorage(_StubObjectStorage):
        async def put_object(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("S3ConnectionError")

    service = _build_service(
        repo=repo,
        producer=producer,
        storage=_BoomStorage(),
        redis=_StubRedis(),
    )

    job = DataExportJob(
        tenant_id=uuid4(),
        scope_type=ScopeType.workspace.value,
        scope_id=uuid4(),
        status=ExportStatus.pending.value,
        requested_by_user_id=uuid4(),
    )
    object.__setattr__(job, "id", uuid4())
    object.__setattr__(job, "created_at", datetime.now(UTC))

    # MUST NOT raise — failures are recorded as status=failed.
    await service.run_workspace_export(
        job=job, worker_id="test-worker", correlation_ctx=None
    )

    statuses = [u.get("status") for u in repo.status_updates]
    assert "failed" in statuses
    types = [p["event_type"] for p in producer.published]
    assert "data_lifecycle.export.failed" in types


@pytest.mark.asyncio
async def test_run_workspace_export_skips_when_lease_unavailable() -> None:
    repo = _StubRepo()
    producer = _StubProducer()
    storage = _StubObjectStorage()
    redis = _StubRedis(accept_lease=False)

    service = _build_service(
        repo=repo, producer=producer, storage=storage, redis=redis
    )

    job = DataExportJob(
        tenant_id=uuid4(),
        scope_type=ScopeType.workspace.value,
        scope_id=uuid4(),
        status=ExportStatus.pending.value,
        requested_by_user_id=uuid4(),
    )
    object.__setattr__(job, "id", uuid4())
    object.__setattr__(job, "created_at", datetime.now(UTC))

    await service.run_workspace_export(
        job=job, worker_id="test-worker", correlation_ctx=None
    )

    # Nothing happened — lease was held elsewhere.
    assert storage.uploads == []
    assert repo.status_updates == []
