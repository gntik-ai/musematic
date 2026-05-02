from __future__ import annotations

from platform.billing.quotas.enforcer import QuotaEnforcer
from platform.billing.quotas.http import quota_error_body
from platform.common.config import PlatformSettings

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.billing_quota_support import create_workspace_subscription, set_tenant

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_free_execution_monthly_cap_returns_structured_402_body(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        fixture = await create_workspace_subscription(session, executions=100)
        enforcer = QuotaEnforcer(session=session, settings=PlatformSettings())

        result = await enforcer.check_execution(fixture.workspace_id)
        body = quota_error_body(result)
        execution_count = await session.scalar(
            text("SELECT count(*) FROM executions WHERE workspace_id = :workspace_id"),
            {"workspace_id": str(fixture.workspace_id)},
        )

        assert result.decision == "HARD_CAP_EXCEEDED"
        assert body["code"] == "quota_exceeded"
        assert body["details"]["quota_name"] == "executions_per_month"
        assert body["details"]["current"] == 101
        assert body["details"]["limit"] == 100
        assert body["details"]["plan_slug"] == "free"
        assert body["details"]["upgrade_url"] == (
            f"/workspaces/{fixture.workspace_id}/billing/upgrade"
        )
        assert execution_count == 0

        await set_tenant(session, fixture.tenant_id)
        await session.rollback()
