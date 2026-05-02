from __future__ import annotations

import asyncio
from decimal import Decimal
from platform.billing.quotas.overage import OverageService

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.billing_quota_support import create_workspace_subscription, set_tenant

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_overage_authorization_is_idempotent_under_concurrency(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as setup_session:
        fixture = await create_workspace_subscription(
            setup_session,
            plan_slug="pro",
            minutes=Decimal("2400"),
        )
        await setup_session.commit()

    semaphore = asyncio.Semaphore(50)

    async def authorize_once() -> str:
        async with semaphore:
            async with session_factory() as session:
                await set_tenant(session, fixture.tenant_id)
                authorization = await OverageService(session=session).authorize(
                    fixture.workspace_id,
                    fixture.period_start,
                    Decimal("50"),
                    fixture.owner_id,
                )
                await session.commit()
                return str(authorization.id)

    authorization_ids = await asyncio.gather(*(authorize_once() for _ in range(1000)))

    async with session_factory() as verify_session:
        await set_tenant(verify_session, fixture.tenant_id)
        count = await verify_session.scalar(
            text(
                """
                SELECT count(*)
                  FROM overage_authorizations
                 WHERE workspace_id = :workspace_id
                   AND billing_period_start = :period_start
                """
            ),
            {
                "workspace_id": str(fixture.workspace_id),
                "period_start": fixture.period_start,
            },
        )
        await verify_session.rollback()

    assert len(set(authorization_ids)) == 1
    assert count == 1
