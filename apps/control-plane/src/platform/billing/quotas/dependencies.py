from __future__ import annotations

from platform.billing.quotas.enforcer import QuotaEnforcer
from platform.billing.quotas.usage_repository import UsageRepository
from platform.billing.subscriptions.resolver import SubscriptionResolver
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def build_quota_enforcer(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    redis_client: AsyncRedisClient | None = None,
) -> QuotaEnforcer:
    return QuotaEnforcer(
        session=session,
        settings=settings,
        resolver=SubscriptionResolver(session),
        usage_repository=UsageRepository(session, redis_client),
        redis_client=redis_client,
    )


async def get_quota_enforcer(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> QuotaEnforcer:
    return build_quota_enforcer(
        session=session,
        settings=cast(PlatformSettings, request.app.state.settings),
        redis_client=cast(AsyncRedisClient | None, request.app.state.clients.get("redis")),
    )
