"""Unit tests for BackupPurgeService."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.config import DataLifecycleSettings
from platform.data_lifecycle.services.backup_purge_service import (
    BackupPurgeService,
)
from typing import Any
from uuid import UUID, uuid4

import pytest


class _Result:
    def __init__(self, rows: list[dict] | None = None) -> None:
        self._rows = rows or []

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)


class _SessionStub:
    def __init__(self, due_rows: list[dict] | None = None) -> None:
        self.due_rows = due_rows or []
        self.queries: list[tuple[str, dict]] = []

    async def execute(self, sql_text, params=None):
        self.queries.append((str(sql_text), params or {}))
        return _Result(self.due_rows)


class _KMSStub:
    def __init__(self, *, raises: Exception | None = None) -> None:
        self.raises = raises
        self.destroyed: list[UUID] = []

    async def destroy_tenant_data_key(self, *, tenant_id: UUID) -> dict[str, Any]:
        if self.raises is not None:
            raise self.raises
        self.destroyed.append(tenant_id)
        return {"kms_key_id": "kms/test-key", "kms_key_version": 7}


class _AuditStub:
    def __init__(self) -> None:
        self.appended: list[bytes] = []

    async def append(self, audit_event_id, namespace, canonical_payload):
        self.appended.append(canonical_payload)


class _ProducerStub:
    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []

    async def publish(self, **kwargs: Any) -> None:
        self.published.append(kwargs)


def _build(*, due_rows=None, kms=None):
    session = _SessionStub(due_rows or [])
    kms = kms if kms is not None else _KMSStub()
    audit = _AuditStub()
    producer = _ProducerStub()
    service = BackupPurgeService(
        session=session,  # type: ignore[arg-type]
        settings=DataLifecycleSettings(),
        kms_destroyer=kms,
        audit_chain=audit,
        event_producer=producer,
    )
    return service, session, kms, audit, producer


@pytest.mark.asyncio
async def test_schedule_purge_emits_audit_entry() -> None:
    service, _, _, audit, _ = _build()
    await service.schedule_purge_for_tenant(
        tenant_id=uuid4(),
        cascade_completed_at=datetime.now(UTC),
        deletion_job_id=uuid4(),
    )
    assert any(b"backup_purge_scheduled" in p for p in audit.appended)


@pytest.mark.asyncio
async def test_run_due_purges_destroys_kms_key() -> None:
    tenant_id = uuid4()
    job_id = uuid4()
    service, _, kms, audit, producer = _build(
        due_rows=[
            {
                "deletion_job_id": str(job_id),
                "tenant_id": str(tenant_id),
                "cascade_completed_at": datetime.now(UTC) - timedelta(days=31),
            }
        ]
    )

    purged = await service.run_due_purges()

    assert purged == 1
    assert kms.destroyed == [tenant_id]
    types = [p["event_type"] for p in producer.published]
    assert "data_lifecycle.backup.purge_completed" in types
    assert any(b"backup_purge_completed" in p for p in audit.appended)


@pytest.mark.asyncio
async def test_run_due_purges_no_kms_logs_and_skips() -> None:
    service, _, _, audit, producer = _build(
        due_rows=[
            {
                "deletion_job_id": str(uuid4()),
                "tenant_id": str(uuid4()),
                "cascade_completed_at": datetime.now(UTC) - timedelta(days=31),
            }
        ],
        kms=None,
    )
    # KMS is None -> _purge_one returns early; we still process the row.
    # In this stub setup, kms=None passed via kwarg works because _build
    # treats None specially via "kms if kms is not None else _KMSStub()".
    # Rebuild with explicit None:
    from platform.data_lifecycle.services.backup_purge_service import (
        BackupPurgeService,
    )

    session = _SessionStub(
        [
            {
                "deletion_job_id": str(uuid4()),
                "tenant_id": str(uuid4()),
                "cascade_completed_at": datetime.now(UTC) - timedelta(days=31),
            }
        ]
    )
    audit = _AuditStub()
    producer = _ProducerStub()
    service = BackupPurgeService(
        session=session,  # type: ignore[arg-type]
        settings=DataLifecycleSettings(),
        kms_destroyer=None,
        audit_chain=audit,
        event_producer=producer,
    )
    await service.run_due_purges()
    # We treated each row as 1 (the loop counts attempts); but no KMS
    # destruction means no completed event.
    types = [p["event_type"] for p in producer.published]
    assert "data_lifecycle.backup.purge_completed" not in types


@pytest.mark.asyncio
async def test_run_due_purges_kms_failure_does_not_abort_loop() -> None:
    rows = [
        {
            "deletion_job_id": str(uuid4()),
            "tenant_id": str(uuid4()),
            "cascade_completed_at": datetime.now(UTC) - timedelta(days=31),
        },
        {
            "deletion_job_id": str(uuid4()),
            "tenant_id": str(uuid4()),
            "cascade_completed_at": datetime.now(UTC) - timedelta(days=32),
        },
    ]
    service, _, _, _, _ = _build(
        due_rows=rows,
        kms=_KMSStub(raises=RuntimeError("KMS unavailable")),
    )
    # Both rows attempt; both fail; loop completes without raising.
    purged = await service.run_due_purges()
    assert purged == 0
