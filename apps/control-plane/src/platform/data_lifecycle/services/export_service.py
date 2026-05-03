"""Export service — request, archive, and finalize data exports.

The service has two distinct surfaces:

* :meth:`ExportService.request_workspace_export` — synchronous endpoint
  caller path: idempotency check, residency guard, rate-limit, audit
  emission, Kafka event production. Returns a :class:`DataExportJob`
  row in ``pending`` status.

* :meth:`ExportService.run_workspace_export` — worker path: acquires
  a Redis lease, drives the serializers, builds the ZIP, uploads via
  the multipart S3 client, generates a signed URL, and finalizes the
  job to ``completed`` (or ``failed`` on irrecoverable error).

Tenant export reuses the same plumbing with tenant-scope serializers
(implemented in Phase 5 / US3).
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, AsyncIterator, Awaitable, Callable, Protocol
from uuid import UUID, uuid4

from platform.common.config import DataLifecycleSettings
from platform.common.events.envelope import CorrelationContext
from platform.data_lifecycle.events import (
    DataLifecycleEventType,
    ExportCompletedPayload,
    ExportFailedPayload,
    ExportRequestedPayload,
    ExportStartedPayload,
    publish_data_lifecycle_event,
)
from platform.data_lifecycle.exceptions import (
    CrossRegionExportBlocked,
    ExportRateLimitExceeded,
)
from platform.data_lifecycle.models import (
    DataExportJob,
    ExportStatus,
    ScopeType,
)
from platform.data_lifecycle.repository import DataLifecycleRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _ExportContext:
    """Inputs the worker needs to drive an export end-to-end."""

    job_id: UUID
    tenant_id: UUID
    scope_type: str
    scope_id: UUID
    bucket: str
    object_key: str


class _AsyncSerializer(Protocol):
    """Async generator yielding (filepath, bytes) pairs.

    Each entry becomes a file inside the export ZIP. Implementations
    live under ``data_lifecycle/serializers/{workspace,tenant}/``.
    """

    async def __call__(
        self, *, scope_id: UUID, tenant_id: UUID
    ) -> AsyncIterator[tuple[str, bytes]]:
        ...


class _AuditAppender(Protocol):
    """Subset of ``AuditChainService.append`` used by this service."""

    async def append(
        self, audit_event_id: UUID, namespace: str, canonical_payload: bytes
    ) -> Any:
        ...


class _EventProducer(Protocol):
    async def publish(
        self,
        *,
        topic: str,
        key: str,
        event_type: str,
        payload: dict[str, Any],
        correlation_ctx: Any,
        source: str,
    ) -> Any:
        ...


class _RedisLeaseClient(Protocol):
    async def set(
        self, name: str, value: str, *, nx: bool = False, ex: int | None = None
    ) -> bool | None:
        ...

    async def delete(self, *names: str) -> int:
        ...


class _ObjectStorageClient(Protocol):
    async def put_object(
        self,
        bucket: str,
        key: str,
        body: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> None:
        ...

    async def create_bucket_if_not_exists(self, bucket: str) -> None:
        ...

    async def get_presigned_url(
        self,
        bucket: str,
        key: str,
        operation: str = "get_object",
        expires_in_seconds: int = 3600,
    ) -> str:
        ...


class ExportService:
    """Coordinates workspace + tenant export job lifecycle."""

    def __init__(
        self,
        *,
        repository: DataLifecycleRepository,
        settings: DataLifecycleSettings,
        object_storage: _ObjectStorageClient,
        audit_chain: _AuditAppender | None,
        event_producer: _EventProducer | None,
        redis_client: _RedisLeaseClient | None,
        workspace_serializers: dict[str, _AsyncSerializer] | None = None,
        tenant_serializers: dict[str, _AsyncSerializer] | None = None,
    ) -> None:
        self._repo = repository
        self._settings = settings
        self._object_storage = object_storage
        self._audit = audit_chain
        self._producer = event_producer
        self._redis = redis_client
        self._workspace_serializers = workspace_serializers or {}
        self._tenant_serializers = tenant_serializers or {}

    # ====================================================================
    # Request path (sync; called by the API router)
    # ====================================================================

    async def request_workspace_export(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        requested_by_user_id: UUID,
        correlation_ctx: Any,
        residency_check: Callable[[UUID, UUID], Awaitable[bool]] | None = None,
    ) -> DataExportJob:
        """Create or return the in-flight export job for a workspace.

        Idempotency: a second request while a pending/processing job
        already exists for this workspace returns that existing job
        without creating a new row.

        Rate limit: at most ``export_rate_limit_per_workspace_per_24h``
        export requests in the last 24 hours per workspace.

        Residency: optional callable that returns True iff the request
        is permitted by the workspace's data-residency policy. When
        False, raises ``CrossRegionExportBlocked``.
        """

        # 1. Idempotency.
        existing = await self._repo.find_active_export_for_scope(
            scope_type=ScopeType.workspace.value, scope_id=workspace_id
        )
        if existing is not None:
            return existing

        # 2. Rate limit.
        recent = await self._repo.count_recent_exports_for_scope(
            scope_type=ScopeType.workspace.value,
            scope_id=workspace_id,
            within=timedelta(hours=24),
        )
        if recent >= self._settings.export_rate_limit_per_workspace_per_24h:
            raise ExportRateLimitExceeded(
                f"workspace {workspace_id} exceeded "
                f"{self._settings.export_rate_limit_per_workspace_per_24h} "
                f"exports per 24h"
            )

        # 3. Residency.
        if residency_check is not None and not await residency_check(
            tenant_id, workspace_id
        ):
            raise CrossRegionExportBlocked(
                f"workspace {workspace_id} residency policy blocks export"
            )

        # 4. Create the row.
        job = await self._repo.create_export_job(
            tenant_id=tenant_id,
            scope_type=ScopeType.workspace.value,
            scope_id=workspace_id,
            requested_by_user_id=requested_by_user_id,
            correlation_id=getattr(correlation_ctx, "correlation_id", None),
        )

        # 5. Audit + Kafka event.
        await self._emit_audit(
            event_type="data_lifecycle.export_requested",
            payload={
                "job_id": str(job.id),
                "scope_type": ScopeType.workspace.value,
                "scope_id": str(workspace_id),
                "tenant_id": str(tenant_id),
                "actor_user_id": str(requested_by_user_id),
                "requested_at": _utcnow_iso(),
            },
        )
        await publish_data_lifecycle_event(
            self._producer,
            DataLifecycleEventType.export_requested,
            ExportRequestedPayload(
                job_id=job.id,
                scope_type=ScopeType.workspace.value,
                scope_id=workspace_id,
                requested_at=job.created_at,
                correlation_context=_ensure_correlation_ctx(correlation_ctx),
            ),
            _ensure_correlation_ctx(correlation_ctx),
            partition_key=tenant_id,
        )
        return job

    # ====================================================================
    # Worker path (async; called by ExportJobWorker)
    # ====================================================================

    async def request_tenant_export(
        self,
        *,
        tenant_id: UUID,
        requested_by_user_id: UUID,
        correlation_ctx: Any = None,
    ) -> DataExportJob:
        """Create or return the in-flight tenant export job.

        Tenant exports are super-admin or tenant-admin initiated (the
        router gates accordingly). The same idempotency / rate-limit /
        residency guards apply as for workspace exports, but the rate
        limit window is shared with workspace exports against the same
        tenant_id (intentional — operators export rarely).
        """

        existing = await self._repo.find_active_export_for_scope(
            scope_type=ScopeType.tenant.value, scope_id=tenant_id
        )
        if existing is not None:
            return existing

        # Tenant-export rate limit: 5/24h shared with workspace exports.
        recent = await self._repo.count_recent_exports_for_scope(
            scope_type=ScopeType.tenant.value,
            scope_id=tenant_id,
            within=timedelta(hours=24),
        )
        if recent >= self._settings.export_rate_limit_per_workspace_per_24h:
            raise ExportRateLimitExceeded(
                f"tenant {tenant_id} exceeded "
                f"{self._settings.export_rate_limit_per_workspace_per_24h} "
                f"exports per 24h"
            )

        job = await self._repo.create_export_job(
            tenant_id=tenant_id,
            scope_type=ScopeType.tenant.value,
            scope_id=tenant_id,
            requested_by_user_id=requested_by_user_id,
            correlation_id=getattr(correlation_ctx, "correlation_id", None),
        )
        await self._emit_audit(
            event_type="data_lifecycle.export_requested",
            payload={
                "job_id": str(job.id),
                "scope_type": ScopeType.tenant.value,
                "scope_id": str(tenant_id),
                "tenant_id": str(tenant_id),
                "actor_user_id": str(requested_by_user_id),
                "requested_at": _utcnow_iso(),
            },
        )
        await publish_data_lifecycle_event(
            self._producer,
            DataLifecycleEventType.export_requested,
            ExportRequestedPayload(
                job_id=job.id,
                scope_type=ScopeType.tenant.value,
                scope_id=tenant_id,
                requested_at=job.created_at,
                correlation_context=_ensure_correlation_ctx(correlation_ctx),
            ),
            _ensure_correlation_ctx(correlation_ctx),
            partition_key=tenant_id,
        )
        return job

    async def run_workspace_export(
        self,
        *,
        job: DataExportJob,
        worker_id: str,
        correlation_ctx: Any,
    ) -> None:
        """Drive the workspace export job to completion.

        Acquires a Redis lease so a re-balancing consumer doesn't run
        the same job twice. Releases the lease in finally.
        """

        lease_key = f"data_lifecycle:export_lease:{job.id}"
        if self._redis is not None:
            acquired = await self._redis.set(
                lease_key,
                worker_id,
                nx=True,
                ex=self._settings.export_lease_ttl_seconds,
            )
            if not acquired:
                logger.info(
                    "data_lifecycle.export_lease_held_elsewhere",
                    extra={"job_id": str(job.id), "worker_id": worker_id},
                )
                return

        try:
            await self._do_run_workspace_export(
                job=job, worker_id=worker_id, correlation_ctx=correlation_ctx
            )
        finally:
            if self._redis is not None:
                await self._redis.delete(lease_key)

    async def _do_run_workspace_export(
        self,
        *,
        job: DataExportJob,
        worker_id: str,
        correlation_ctx: Any,
    ) -> None:
        started = datetime.now(UTC)
        await self._repo.update_export_status(
            job_id=job.id,
            status=ExportStatus.processing.value,
            started_at=started,
        )
        await publish_data_lifecycle_event(
            self._producer,
            DataLifecycleEventType.export_started,
            ExportStartedPayload(
                job_id=job.id,
                worker_id=worker_id,
                started_at=started,
                correlation_context=_ensure_correlation_ctx(correlation_ctx),
            ),
            _ensure_correlation_ctx(correlation_ctx),
            partition_key=job.tenant_id,
        )

        bucket = self._settings.export_bucket
        object_key = f"workspace/{job.scope_id}/{job.id}.zip"
        try:
            zip_bytes = await self._build_workspace_zip(
                workspace_id=job.scope_id, tenant_id=job.tenant_id
            )
            await self._object_storage.create_bucket_if_not_exists(bucket)
            await self._object_storage.put_object(
                bucket,
                object_key,
                zip_bytes,
                content_type="application/zip",
            )
            ttl = self._settings.workspace_export_url_ttl_days * 86_400
            output_url = await self._object_storage.get_presigned_url(
                bucket,
                object_key,
                operation="get_object",
                expires_in_seconds=ttl,
            )
            completed = datetime.now(UTC)
            expires = completed + timedelta(
                days=self._settings.workspace_export_url_ttl_days
            )
            await self._repo.update_export_status(
                job_id=job.id,
                status=ExportStatus.completed.value,
                completed_at=completed,
                output_url=output_url,
                output_size_bytes=len(zip_bytes),
                output_expires_at=expires,
            )
            await self._emit_audit(
                event_type="data_lifecycle.export_completed",
                payload={
                    "job_id": str(job.id),
                    "scope_type": job.scope_type,
                    "scope_id": str(job.scope_id),
                    "tenant_id": str(job.tenant_id),
                    "output_size_bytes": len(zip_bytes),
                    "completed_at": completed.isoformat(),
                },
            )
            await publish_data_lifecycle_event(
                self._producer,
                DataLifecycleEventType.export_completed,
                ExportCompletedPayload(
                    job_id=job.id,
                    output_size_bytes=len(zip_bytes),
                    output_url_expires_at=expires,
                    completed_at=completed,
                    correlation_context=_ensure_correlation_ctx(correlation_ctx),
                ),
                correlation_ctx,
                partition_key=job.tenant_id,
            )
        except Exception as exc:
            logger.error(
                "data_lifecycle.export_failed",
                extra={"job_id": str(job.id), "error": str(exc)},
                exc_info=True,
            )
            failed_at = datetime.now(UTC)
            failure_code = _classify_failure(exc)
            await self._repo.update_export_status(
                job_id=job.id,
                status=ExportStatus.failed.value,
                completed_at=failed_at,
                error_message=_redact_error(str(exc)),
            )
            await self._emit_audit(
                event_type="data_lifecycle.export_failed",
                payload={
                    "job_id": str(job.id),
                    "tenant_id": str(job.tenant_id),
                    "failure_reason_code": failure_code,
                    "failed_at": failed_at.isoformat(),
                },
            )
            await publish_data_lifecycle_event(
                self._producer,
                DataLifecycleEventType.export_failed,
                ExportFailedPayload(
                    job_id=job.id,
                    failure_reason_code=failure_code,
                    retries_remaining=0,
                    failed_at=failed_at,
                    correlation_context=_ensure_correlation_ctx(correlation_ctx),
                ),
                correlation_ctx,
                partition_key=job.tenant_id,
            )

    async def _build_workspace_zip(
        self, *, workspace_id: UUID, tenant_id: UUID
    ) -> bytes:
        """Build the workspace export ZIP in memory.

        The MVP path holds the ZIP in memory because workspace exports
        are bounded at 10 GB per SC-001. For larger inputs the
        serializers MUST be revisited to stream into a multipart upload.
        """

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            # metadata.json — always first.
            metadata = {
                "scope_type": ScopeType.workspace.value,
                "workspace_id": str(workspace_id),
                "tenant_id": str(tenant_id),
                "exported_at": _utcnow_iso(),
                "format_version": 1,
            }
            zf.writestr(
                "metadata.json",
                json.dumps(metadata, sort_keys=True, indent=2).encode("utf-8"),
            )
            zf.writestr(
                "README.md",
                _README_BYTES,
            )
            for name, serializer in self._workspace_serializers.items():
                async for filepath, chunk in serializer(
                    scope_id=workspace_id, tenant_id=tenant_id
                ):
                    zf.writestr(filepath, chunk)
            # If no serializers were registered (initial scaffold), write a
            # placeholder so the ZIP is non-empty and the manifest is valid.
            if not self._workspace_serializers:
                zf.writestr(
                    "WARNING.txt",
                    b"No serializers registered; this archive contains only "
                    b"metadata. See specs/104-data-lifecycle/contracts/"
                    b"workspace-export-rest.md for the expected layout.",
                )
        return buffer.getvalue()

    async def run_tenant_export(
        self,
        *,
        job: DataExportJob,
        worker_id: str,
        correlation_ctx: Any = None,
    ) -> None:
        """Drive a tenant export job to completion.

        Mirrors :meth:`run_workspace_export` but uses the tenant
        serializers and a 30-day signed URL TTL per FR-753.3. Lease
        handling and failure recording are identical.
        """

        lease_key = f"data_lifecycle:export_lease:{job.id}"
        if self._redis is not None:
            acquired = await self._redis.set(
                lease_key,
                worker_id,
                nx=True,
                ex=self._settings.export_lease_ttl_seconds,
            )
            if not acquired:
                logger.info(
                    "data_lifecycle.export_lease_held_elsewhere",
                    extra={"job_id": str(job.id), "worker_id": worker_id},
                )
                return
        try:
            await self._do_run_tenant_export(
                job=job, worker_id=worker_id, correlation_ctx=correlation_ctx
            )
        finally:
            if self._redis is not None:
                await self._redis.delete(lease_key)

    async def _do_run_tenant_export(
        self,
        *,
        job: DataExportJob,
        worker_id: str,
        correlation_ctx: Any,
    ) -> None:
        started = datetime.now(UTC)
        await self._repo.update_export_status(
            job_id=job.id,
            status=ExportStatus.processing.value,
            started_at=started,
        )
        await publish_data_lifecycle_event(
            self._producer,
            DataLifecycleEventType.export_started,
            ExportStartedPayload(
                job_id=job.id,
                worker_id=worker_id,
                started_at=started,
                correlation_context=_ensure_correlation_ctx(correlation_ctx),
            ),
            _ensure_correlation_ctx(correlation_ctx),
            partition_key=job.tenant_id,
        )
        bucket = self._settings.export_bucket
        object_key = f"tenant/{job.scope_id}/{job.id}.zip"
        try:
            zip_bytes = await self._build_tenant_zip(tenant_id=job.scope_id)
            await self._object_storage.create_bucket_if_not_exists(bucket)
            await self._object_storage.put_object(
                bucket, object_key, zip_bytes, content_type="application/zip"
            )
            ttl = self._settings.tenant_export_url_ttl_days * 86_400
            output_url = await self._object_storage.get_presigned_url(
                bucket,
                object_key,
                operation="get_object",
                expires_in_seconds=ttl,
            )
            completed = datetime.now(UTC)
            expires = completed + timedelta(
                days=self._settings.tenant_export_url_ttl_days
            )
            await self._repo.update_export_status(
                job_id=job.id,
                status=ExportStatus.completed.value,
                completed_at=completed,
                output_url=output_url,
                output_size_bytes=len(zip_bytes),
                output_expires_at=expires,
            )
            await self._emit_audit(
                event_type="data_lifecycle.export_completed",
                payload={
                    "job_id": str(job.id),
                    "scope_type": job.scope_type,
                    "scope_id": str(job.scope_id),
                    "tenant_id": str(job.tenant_id),
                    "output_size_bytes": len(zip_bytes),
                    "completed_at": completed.isoformat(),
                },
            )
            await publish_data_lifecycle_event(
                self._producer,
                DataLifecycleEventType.export_completed,
                ExportCompletedPayload(
                    job_id=job.id,
                    output_size_bytes=len(zip_bytes),
                    output_url_expires_at=expires,
                    completed_at=completed,
                    correlation_context=_ensure_correlation_ctx(correlation_ctx),
                ),
                _ensure_correlation_ctx(correlation_ctx),
                partition_key=job.tenant_id,
            )
        except Exception as exc:
            logger.error(
                "data_lifecycle.tenant_export_failed",
                extra={"job_id": str(job.id), "error": str(exc)},
                exc_info=True,
            )
            failed_at = datetime.now(UTC)
            failure_code = _classify_failure(exc)
            await self._repo.update_export_status(
                job_id=job.id,
                status=ExportStatus.failed.value,
                completed_at=failed_at,
                error_message=_redact_error(str(exc)),
            )
            await self._emit_audit(
                event_type="data_lifecycle.export_failed",
                payload={
                    "job_id": str(job.id),
                    "tenant_id": str(job.tenant_id),
                    "failure_reason_code": failure_code,
                    "failed_at": failed_at.isoformat(),
                },
            )
            await publish_data_lifecycle_event(
                self._producer,
                DataLifecycleEventType.export_failed,
                ExportFailedPayload(
                    job_id=job.id,
                    failure_reason_code=failure_code,
                    retries_remaining=0,
                    failed_at=failed_at,
                    correlation_context=_ensure_correlation_ctx(correlation_ctx),
                ),
                _ensure_correlation_ctx(correlation_ctx),
                partition_key=job.tenant_id,
            )

    async def _build_tenant_zip(self, *, tenant_id: UUID) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            metadata = {
                "scope_type": ScopeType.tenant.value,
                "tenant_id": str(tenant_id),
                "exported_at": _utcnow_iso(),
                "format_version": 1,
            }
            zf.writestr(
                "metadata.json",
                json.dumps(metadata, sort_keys=True, indent=2).encode("utf-8"),
            )
            zf.writestr("README.md", _README_BYTES)
            for name, serializer in self._tenant_serializers.items():
                async for filepath, chunk in serializer(
                    scope_id=tenant_id, tenant_id=tenant_id
                ):
                    zf.writestr(filepath, chunk)
            if not self._tenant_serializers:
                zf.writestr(
                    "WARNING.txt",
                    b"No tenant serializers registered; this archive contains "
                    b"only metadata. See specs/104-data-lifecycle/contracts/"
                    b"tenant-export-rest.md for the expected layout.",
                )
        return buffer.getvalue()

    # ====================================================================
    # Internal helpers
    # ====================================================================

    async def _emit_audit(
        self,
        *,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        if self._audit is None:
            return
        canonical = json.dumps(
            {"event_type": event_type, **payload},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        try:
            await self._audit.append(uuid4(), "data_lifecycle", canonical)
        except Exception:
            logger.exception(
                "data_lifecycle.audit_emission_failed",
                extra={"event_type": event_type},
            )


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _ensure_correlation_ctx(ctx: Any) -> CorrelationContext:
    """Return a non-None CorrelationContext.

    The Kafka event payloads require a CorrelationContext; if the caller
    didn't propagate one (e.g. a worker startup tick), synthesize a
    fresh one so the event still publishes with a unique correlation id.
    """

    if isinstance(ctx, CorrelationContext):
        return ctx
    return CorrelationContext(correlation_id=uuid4())


def _classify_failure(exc: Exception) -> str:
    """Return a stable failure code from a raw exception.

    Avoids leaking internal error text into the Kafka event payload.
    """

    name = type(exc).__name__.lower()
    if "s3" in name or "objectstorage" in name:
        return "s3_unreachable"
    if "timeout" in name:
        return "source_query_timeout"
    return "internal_error"


def _redact_error(message: str) -> str:
    """Truncate and strip newlines/PII from an error message before storage."""

    flat = message.replace("\n", " ").replace("\r", " ")
    return flat[:512]


_README_BYTES = (
    "# Workspace data export\n\n"
    "This archive contains a structured snapshot of your workspace data,\n"
    "organized as JSON files per resource type plus raw artifact blobs.\n\n"
    "## Layout\n\n"
    "- metadata.json - manifest with workspace identity and export timestamp\n"
    "- agents/ - registered agents (one JSON per agent)\n"
    "- executions/ - execution records and task plans\n"
    "- audit/ - workspace-scoped audit chain entries\n"
    "- costs/ - cost attribution rollups\n"
    "- members/ - workspace member roster (privacy-redacted)\n\n"
    "## Privacy\n\n"
    "Member email addresses appear only for users who have opted in to\n"
    "cross-context exposure. Other members are represented by opaque user\n"
    "identifiers.\n"
).encode("utf-8")
