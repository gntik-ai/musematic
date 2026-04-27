from __future__ import annotations

from platform.common.clients.redis import AsyncRedisClient
from platform.common.dependencies import get_db
from platform.two_person_approval.service import TwoPersonApprovalService
from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_two_person_approval_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> TwoPersonApprovalService:
    redis_client = cast(AsyncRedisClient | None, request.app.state.clients.get("redis"))
    return TwoPersonApprovalService(session, redis_client)
