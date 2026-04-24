from __future__ import annotations

from platform.common.rate_limiter.models import (
    RateLimitConfig,
    RateLimitPrincipalType,
    SubscriptionTier,
)
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


class RateLimiterRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_tier_by_name(self, name: str) -> SubscriptionTier | None:
        result = await self.session.execute(
            select(SubscriptionTier).where(SubscriptionTier.name == name)
        )
        return result.scalar_one_or_none()

    async def get_rate_limit_config(
        self,
        principal_type: RateLimitPrincipalType,
        principal_id: UUID,
    ) -> RateLimitConfig | None:
        result = await self.session.execute(
            select(RateLimitConfig)
            .options(selectinload(RateLimitConfig.subscription_tier))
            .where(
                RateLimitConfig.principal_type == principal_type,
                RateLimitConfig.principal_id == principal_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_rate_limit_config(
        self,
        *,
        principal_type: RateLimitPrincipalType,
        principal_id: UUID,
        subscription_tier: SubscriptionTier,
        requests_per_minute_override: int | None,
        requests_per_hour_override: int | None,
        requests_per_day_override: int | None,
    ) -> RateLimitConfig:
        config = await self.get_rate_limit_config(principal_type, principal_id)
        if config is None:
            config = RateLimitConfig(
                principal_type=principal_type,
                principal_id=principal_id,
                subscription_tier=subscription_tier,
                requests_per_minute_override=requests_per_minute_override,
                requests_per_hour_override=requests_per_hour_override,
                requests_per_day_override=requests_per_day_override,
            )
            self.session.add(config)
        else:
            config.subscription_tier = subscription_tier
            config.subscription_tier_id = subscription_tier.id
            config.requests_per_minute_override = requests_per_minute_override
            config.requests_per_hour_override = requests_per_hour_override
            config.requests_per_day_override = requests_per_day_override
        await self.session.flush()
        await self.session.refresh(config, attribute_names=["subscription_tier"])
        return config
