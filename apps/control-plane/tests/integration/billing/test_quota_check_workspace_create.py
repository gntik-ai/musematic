from __future__ import annotations

from platform.billing.quotas.enforcer import QuotaEnforcer
from platform.common.config import PlatformSettings

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.billing_quota_support import create_workspace_subscription

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_free_workspace_create_cap_is_enforced_before_insert(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        fixture = await create_workspace_subscription(session)
        enforcer = QuotaEnforcer(session=session, settings=PlatformSettings())

        result = await enforcer.check_workspace_create(fixture.owner_id)

        assert result.decision == "HARD_CAP_EXCEEDED"
        assert result.quota_name == "max_workspaces"
        assert result.current == 2
        assert result.limit == 1
        assert result.plan_slug == "free"
        assert result.upgrade_url == f"/workspaces/{fixture.workspace_id}/billing/upgrade"

        await session.rollback()
