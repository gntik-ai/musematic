from __future__ import annotations

from datetime import datetime
from platform.testing.models import (
    AdversarialCategory,
    AdversarialTestCase,
    CoordinationTestResult,
    DriftAlert,
    GeneratedTestSuite,
    SuiteType,
)
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


class TestingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_next_suite_version(
        self,
        *,
        workspace_id: UUID,
        agent_fqn: str,
        suite_type: SuiteType,
    ) -> int:
        current = await self.session.scalar(
            select(func.max(GeneratedTestSuite.version)).where(
                GeneratedTestSuite.workspace_id == workspace_id,
                GeneratedTestSuite.agent_fqn == agent_fqn,
                GeneratedTestSuite.suite_type == suite_type,
            )
        )
        return int(current or 0) + 1

    async def create_suite(self, suite: GeneratedTestSuite) -> GeneratedTestSuite:
        self.session.add(suite)
        await self.session.flush()
        return suite

    async def get_suite(
        self,
        suite_id: UUID,
        workspace_id: UUID | None = None,
    ) -> GeneratedTestSuite | None:
        query = select(GeneratedTestSuite).where(GeneratedTestSuite.id == suite_id)
        if workspace_id is not None:
            query = query.where(GeneratedTestSuite.workspace_id == workspace_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_suites(
        self,
        workspace_id: UUID,
        *,
        agent_fqn: str | None,
        suite_type: SuiteType | None,
        page: int,
        page_size: int,
    ) -> tuple[list[GeneratedTestSuite], int]:
        filters = [GeneratedTestSuite.workspace_id == workspace_id]
        if agent_fqn is not None:
            filters.append(GeneratedTestSuite.agent_fqn == agent_fqn)
        if suite_type is not None:
            filters.append(GeneratedTestSuite.suite_type == suite_type)
        total = await self.session.scalar(
            select(func.count()).select_from(GeneratedTestSuite).where(*filters)
        )
        result = await self.session.execute(
            select(GeneratedTestSuite)
            .where(*filters)
            .order_by(GeneratedTestSuite.created_at.desc(), GeneratedTestSuite.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), int(total or 0)

    async def update_suite(self, suite: GeneratedTestSuite, **fields: Any) -> GeneratedTestSuite:
        for key, value in fields.items():
            setattr(suite, key, value)
        await self.session.flush()
        return suite

    async def create_adversarial_case(self, case: AdversarialTestCase) -> AdversarialTestCase:
        self.session.add(case)
        await self.session.flush()
        return case

    async def create_adversarial_cases(
        self,
        cases: list[AdversarialTestCase],
    ) -> list[AdversarialTestCase]:
        self.session.add_all(cases)
        await self.session.flush()
        return cases

    async def list_adversarial_cases(
        self,
        suite_id: UUID,
        *,
        category: AdversarialCategory | None,
        page: int,
        page_size: int,
    ) -> tuple[list[AdversarialTestCase], int]:
        filters = [AdversarialTestCase.suite_id == suite_id]
        if category is not None:
            filters.append(AdversarialTestCase.category == category)
        total = await self.session.scalar(
            select(func.count()).select_from(AdversarialTestCase).where(*filters)
        )
        result = await self.session.execute(
            select(AdversarialTestCase)
            .where(*filters)
            .order_by(AdversarialTestCase.created_at.asc(), AdversarialTestCase.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), int(total or 0)

    async def count_cases_by_category(self, suite_id: UUID) -> dict[str, int]:
        result = await self.session.execute(
            select(AdversarialTestCase.category, func.count())
            .where(AdversarialTestCase.suite_id == suite_id)
            .group_by(AdversarialTestCase.category)
        )
        return {str(category.value): int(count) for category, count in result.all()}

    async def create_coordination_result(
        self,
        result_row: CoordinationTestResult,
    ) -> CoordinationTestResult:
        self.session.add(result_row)
        await self.session.flush()
        return result_row

    async def get_coordination_result(
        self,
        result_id: UUID,
        workspace_id: UUID | None = None,
    ) -> CoordinationTestResult | None:
        query = select(CoordinationTestResult).where(CoordinationTestResult.id == result_id)
        if workspace_id is not None:
            query = query.where(CoordinationTestResult.workspace_id == workspace_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_drift_alert(self, alert: DriftAlert) -> DriftAlert:
        self.session.add(alert)
        await self.session.flush()
        return alert

    async def get_drift_alert(
        self,
        alert_id: UUID,
        workspace_id: UUID | None = None,
    ) -> DriftAlert | None:
        query = select(DriftAlert).where(DriftAlert.id == alert_id)
        if workspace_id is not None:
            query = query.where(DriftAlert.workspace_id == workspace_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_drift_alerts(
        self,
        workspace_id: UUID,
        *,
        agent_fqn: str | None,
        eval_set_id: UUID | None,
        acknowledged: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[DriftAlert], int]:
        filters = [DriftAlert.workspace_id == workspace_id]
        if agent_fqn is not None:
            filters.append(DriftAlert.agent_fqn == agent_fqn)
        if eval_set_id is not None:
            filters.append(DriftAlert.eval_set_id == eval_set_id)
        if acknowledged is not None:
            filters.append(DriftAlert.acknowledged.is_(acknowledged))
        total = await self.session.scalar(
            select(func.count()).select_from(DriftAlert).where(*filters)
        )
        result = await self.session.execute(
            select(DriftAlert)
            .where(*filters)
            .order_by(DriftAlert.created_at.desc(), DriftAlert.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), int(total or 0)

    async def acknowledge_drift_alert(
        self,
        alert: DriftAlert,
        *,
        acknowledged_by: UUID,
        acknowledged_at: datetime,
    ) -> DriftAlert:
        alert.acknowledged = True
        alert.acknowledged_by = acknowledged_by
        alert.acknowledged_at = acknowledged_at
        await self.session.flush()
        return alert
