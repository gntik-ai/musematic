from __future__ import annotations

from decimal import Decimal
from platform.billing.quotas.enforcer import QuotaEnforcer
from platform.billing.quotas.overage import OverageService
from platform.common.config import PlatformSettings
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.billing_quota_support import create_workspace_subscription

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class _ResumeSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, object]] = []

    async def resume_paused_quota_exceeded(self, workspace_id: UUID, period_start: object) -> int:
        self.calls.append((workspace_id, period_start))
        return 1


async def test_overage_authorization_resumes_and_allows_subsequent_execution(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        fixture = await create_workspace_subscription(
            session,
            plan_slug="pro",
            minutes=Decimal("2400"),
        )
        spy = _ResumeSpy()

        authorization = await OverageService(
            session=session,
            execution_service=spy,
        ).authorize(
            fixture.workspace_id,
            fixture.period_start,
            Decimal("50"),
            fixture.owner_id,
        )
        result = await QuotaEnforcer(
            session=session,
            settings=PlatformSettings(),
        ).check_execution(fixture.workspace_id)

        assert authorization.workspace_id == fixture.workspace_id
        assert spy.calls == [(fixture.workspace_id, fixture.period_start)]
        assert result.decision == "OVERAGE_AUTHORIZED"

        await session.rollback()
