from __future__ import annotations

import os
from platform.audit.repository import AuditChainRepository
from platform.audit.service import AuditChainService
from platform.common.config import PlatformSettings
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_AUDIT_CHAIN_INTEGRATION") != "1",
    reason="Set RUN_AUDIT_CHAIN_INTEGRATION=1 to execute DB-backed RTBF audit-chain checks",
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rtbf_nulls_referenced_audit_event_without_breaking_chain(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    event_id = uuid4()
    settings = PlatformSettings()

    async with session_factory() as session:
        repository = AuditChainRepository(session)
        service = AuditChainService(repository, settings)
        entry = await service.append(event_id, "auth", b'{"user_id":"deleted"}')
        await session.commit()
        sequence_number = entry.sequence_number

    async with session_factory() as session:
        repository = AuditChainRepository(session)
        assert await repository.null_audit_event_reference(event_id) == 1
        await session.commit()

    async with session_factory() as session:
        repository = AuditChainRepository(session)
        service = AuditChainService(repository, settings)
        result = await service.verify()
        redacted_entry = await repository.get_by_sequence(sequence_number)

    assert result.valid is True
    assert result.entries_checked == 1
    assert redacted_entry is not None
    assert redacted_entry.audit_event_id is None
