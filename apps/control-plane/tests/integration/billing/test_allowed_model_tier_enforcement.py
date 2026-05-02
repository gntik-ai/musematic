from __future__ import annotations

from platform.billing.quotas.enforcer import QuotaEnforcer
from platform.billing.quotas.http import quota_error_body
from platform.common.config import PlatformSettings

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.billing_quota_support import create_workspace_subscription

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_free_plan_rejects_standard_model_tier(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        fixture = await create_workspace_subscription(session)
        enforcer = QuotaEnforcer(session=session, settings=PlatformSettings())

        result = await enforcer.check_model_tier(
            fixture.workspace_id,
            "standard-model",
            model_tier="tier2",
        )
        body = quota_error_body(result)

        assert result.decision == "MODEL_TIER_NOT_ALLOWED"
        assert body["code"] == "model_tier_not_allowed"
        assert body["details"]["quota_name"] == "allowed_model_tier"
        assert body["details"]["plan_slug"] == "free"

        await session.rollback()
