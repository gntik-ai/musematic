from __future__ import annotations

from platform.billing.exceptions import PlanVersionImmutableError
from platform.billing.plans.repository import PlansRepository
from platform.billing.plans.service import PlansService

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_published_plan_versions_are_immutable_in_database_and_service(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        plan_version_id = await session.scalar(
            text(
                """
                SELECT pv.id
                  FROM plan_versions pv
                  JOIN plans p ON p.id = pv.plan_id
                 WHERE p.slug = 'pro' AND pv.version = 1
                 LIMIT 1
                """
            )
        )
        assert plan_version_id is not None

        with pytest.raises(DBAPIError):
            async with session.begin_nested():
                await session.execute(
                    text(
                        """
                        UPDATE plan_versions
                           SET price_monthly = 59.00
                         WHERE id = :plan_version_id
                        """
                    ),
                    {"plan_version_id": str(plan_version_id)},
                )

        await session.rollback()
        repository = PlansRepository(session)
        plan = await repository.get_by_slug("pro")
        assert plan is not None
        version = await repository.get_published_version(plan.id)
        assert version is not None

        service = PlansService(repository)
        with pytest.raises(PlanVersionImmutableError):
            service.guard_published_version_update(version, {"price_monthly": "59.00"})
