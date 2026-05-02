from __future__ import annotations

from platform.billing.quotas.enforcer import QuotaEnforcer
from platform.common.config import PlatformSettings

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.billing_quota_support import create_workspace_subscription

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_free_user_invite_cap_blocks_next_member(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        fixture = await create_workspace_subscription(session, member_count=3)
        enforcer = QuotaEnforcer(session=session, settings=PlatformSettings())

        result = await enforcer.check_user_invite(fixture.workspace_id)

        assert result.decision == "HARD_CAP_EXCEEDED"
        assert result.quota_name == "max_users_per_workspace"
        assert result.current == 4
        assert result.limit == 3
        assert result.plan_slug == "free"

        await session.rollback()
