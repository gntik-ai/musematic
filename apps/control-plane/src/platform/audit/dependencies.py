from __future__ import annotations

from platform.audit.repository import AuditChainRepository
from platform.audit.service import AuditChainService
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def build_audit_chain_service(
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None = None,
) -> AuditChainService:
    return AuditChainService(
        repository=AuditChainRepository(session),
        settings=settings,
        producer=producer,
    )


async def get_audit_chain_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> AuditChainService:
    return build_audit_chain_service(
        session=session,
        settings=cast(PlatformSettings, request.app.state.settings),
        producer=cast(EventProducer | None, request.app.state.clients.get("kafka")),
    )
