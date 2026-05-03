"""UPD-050 — SuspensionService unit tests."""

from __future__ import annotations

from platform.security.abuse_prevention.exceptions import SuspensionAlreadyLiftedError
from platform.security.abuse_prevention.suspension import SuspensionService
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


def _build_service():
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    audit = MagicMock()
    audit.append = AsyncMock()
    producer = MagicMock()
    producer.publish = AsyncMock()
    alerts = MagicMock()
    alerts.create_admin_alert = AsyncMock()
    return SuspensionService(
        session=session,
        audit_chain=audit,
        event_producer=producer,
        alert_service=alerts,
    )


@pytest.mark.asyncio
async def test_suspend_audits_and_publishes() -> None:
    service = _build_service()
    user_id = uuid4()
    tenant_id = uuid4()
    row = await service.suspend(
        user_id=user_id,
        tenant_id=tenant_id,
        reason="manual",
        evidence={"test": True},
        suspended_by="super_admin",
        suspended_by_user_id=uuid4(),
    )
    service._session.add.assert_called_once()
    service._session.flush.assert_awaited_once()
    service._session.commit.assert_awaited_once()
    service._audit.append.assert_awaited_once()
    service._producer.publish.assert_awaited_once()
    assert row.user_id == user_id
    assert row.reason == "manual"


@pytest.mark.asyncio
async def test_lift_idempotency_refuses_double_lift() -> None:
    service = _build_service()
    suspension_id = uuid4()
    existing = MagicMock()
    existing.id = suspension_id
    existing.user_id = uuid4()
    existing.tenant_id = uuid4()
    from datetime import UTC, datetime
    existing.lifted_at = datetime.now(tz=UTC)
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=existing)
    service._session.execute = AsyncMock(return_value=result)

    with pytest.raises(SuspensionAlreadyLiftedError):
        await service.lift(
            suspension_id=suspension_id,
            actor_user_id=uuid4(),
            reason="False positive",
        )


@pytest.mark.asyncio
async def test_lift_records_audit_kafka_alert() -> None:
    service = _build_service()
    suspension_id = uuid4()
    existing = MagicMock()
    existing.id = suspension_id
    existing.user_id = uuid4()
    existing.tenant_id = uuid4()
    existing.lifted_at = None
    select_result = MagicMock()
    select_result.scalar_one_or_none = MagicMock(return_value=existing)
    update_result = MagicMock()
    service._session.execute = AsyncMock(side_effect=[select_result, update_result])
    actor = uuid4()

    await service.lift(
        suspension_id=suspension_id,
        actor_user_id=actor,
        reason="Reviewed evidence",
    )
    service._audit.append.assert_awaited_once()
    service._producer.publish.assert_awaited_once()
    service._alerts.create_admin_alert.assert_awaited_once()
