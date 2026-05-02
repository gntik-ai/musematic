from __future__ import annotations

from decimal import Decimal
from platform.billing.quotas.enforcer import QuotaEnforcer
from platform.billing.quotas.http import quota_error_body
from platform.common.config import PlatformSettings

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.billing_quota_support import create_workspace_subscription

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_pro_workspace_at_minutes_cap_requires_overage_authorization(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        fixture = await create_workspace_subscription(
            session,
            plan_slug="pro",
            minutes=Decimal("2400"),
        )
        result = await QuotaEnforcer(
            session=session,
            settings=PlatformSettings(),
        ).check_execution(fixture.workspace_id)
        body = quota_error_body(result)

        assert result.decision == "OVERAGE_REQUIRED"
        assert result.quota_name == "minutes_per_month"
        assert result.overage_available is True
        assert body["status"] == "paused_quota_exceeded"
        assert body["quota_name"] == "minutes_per_month"

        await session.rollback()
