from __future__ import annotations

from datetime import UTC, datetime
from platform.context_engineering.models import (
    AbTestStatus,
    ContextAbTest,
    ContextAssemblyRecord,
    ContextDriftAlert,
    ContextEngineeringProfile,
    ContextProfileAssignment,
    CorrelationClassification,
    CorrelationResult,
    ProfileAssignmentLevel,
)
from typing import Any
from uuid import UUID

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession


class ContextEngineeringRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_profile(
        self,
        *,
        workspace_id: UUID,
        created_by: UUID | None,
        name: str,
        description: str | None,
        is_default: bool,
        source_config: list[dict[str, Any]],
        budget_config: dict[str, Any],
        compaction_strategies: list[str],
        quality_weights: dict[str, float],
        privacy_overrides: dict[str, Any],
    ) -> ContextEngineeringProfile:
        profile = ContextEngineeringProfile(
            workspace_id=workspace_id,
            created_by=created_by,
            updated_by=created_by,
            name=name,
            description=description,
            is_default=is_default,
            source_config=source_config,
            budget_config=budget_config,
            compaction_strategies=compaction_strategies,
            quality_weights=quality_weights,
            privacy_overrides=privacy_overrides,
        )
        self.session.add(profile)
        await self.session.flush()
        return profile

    async def clear_default_profiles(
        self,
        workspace_id: UUID,
        *,
        exclude_profile_id: UUID | None = None,
    ) -> None:
        statement = (
            update(ContextEngineeringProfile)
            .where(ContextEngineeringProfile.workspace_id == workspace_id)
            .values(is_default=False)
        )
        if exclude_profile_id is not None:
            statement = statement.where(ContextEngineeringProfile.id != exclude_profile_id)
        await self.session.execute(statement)
        await self.session.flush()

    async def get_profile(
        self,
        workspace_id: UUID,
        profile_id: UUID,
    ) -> ContextEngineeringProfile | None:
        result = await self.session.execute(
            select(ContextEngineeringProfile).where(
                ContextEngineeringProfile.workspace_id == workspace_id,
                ContextEngineeringProfile.id == profile_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_default_profile(self, workspace_id: UUID) -> ContextEngineeringProfile | None:
        result = await self.session.execute(
            select(ContextEngineeringProfile)
            .where(
                ContextEngineeringProfile.workspace_id == workspace_id,
                ContextEngineeringProfile.is_default.is_(True),
            )
            .order_by(
                ContextEngineeringProfile.created_at.asc(), ContextEngineeringProfile.id.asc()
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_profiles(self, workspace_id: UUID) -> list[ContextEngineeringProfile]:
        result = await self.session.execute(
            select(ContextEngineeringProfile)
            .where(ContextEngineeringProfile.workspace_id == workspace_id)
            .order_by(
                ContextEngineeringProfile.created_at.asc(), ContextEngineeringProfile.id.asc()
            )
        )
        return list(result.scalars().all())

    async def update_profile(
        self,
        profile: ContextEngineeringProfile,
        **fields: Any,
    ) -> ContextEngineeringProfile:
        for key, value in fields.items():
            setattr(profile, key, value)
        await self.session.flush()
        return profile

    async def delete_profile(self, profile: ContextEngineeringProfile) -> None:
        await self.session.delete(profile)
        await self.session.flush()

    async def profile_has_assignments(self, profile_id: UUID) -> bool:
        total = await self.session.scalar(
            select(func.count())
            .select_from(ContextProfileAssignment)
            .where(ContextProfileAssignment.profile_id == profile_id)
        )
        return bool(total)

    async def profile_has_active_ab_tests(self, profile_id: UUID) -> bool:
        total = await self.session.scalar(
            select(func.count())
            .select_from(ContextAbTest)
            .where(
                or_(
                    ContextAbTest.control_profile_id == profile_id,
                    ContextAbTest.variant_profile_id == profile_id,
                ),
                ContextAbTest.status == AbTestStatus.active,
            )
        )
        return bool(total)

    async def create_assignment(
        self,
        *,
        workspace_id: UUID,
        profile_id: UUID,
        assignment_level: ProfileAssignmentLevel,
        agent_fqn: str | None,
        role_type: str | None,
    ) -> ContextProfileAssignment:
        existing: ContextProfileAssignment | None
        if assignment_level is ProfileAssignmentLevel.agent and agent_fqn:
            existing = await self.get_assignment_by_agent_fqn(workspace_id, agent_fqn)
        elif assignment_level is ProfileAssignmentLevel.role_type and role_type:
            existing = await self.get_assignment_by_role_type(workspace_id, role_type)
        elif assignment_level is ProfileAssignmentLevel.workspace:
            existing = await self.get_workspace_default_assignment(workspace_id)
        else:
            existing = None

        if existing is not None:
            existing.profile_id = profile_id
            existing.assignment_level = assignment_level
            existing.agent_fqn = agent_fqn
            existing.role_type = role_type
            await self.session.flush()
            return existing

        assignment = ContextProfileAssignment(
            workspace_id=workspace_id,
            profile_id=profile_id,
            assignment_level=assignment_level,
            agent_fqn=agent_fqn,
            role_type=role_type,
        )
        self.session.add(assignment)
        await self.session.flush()
        return assignment

    async def list_assignments(
        self,
        workspace_id: UUID,
        *,
        profile_id: UUID | None = None,
    ) -> list[ContextProfileAssignment]:
        query = select(ContextProfileAssignment).where(
            ContextProfileAssignment.workspace_id == workspace_id
        )
        if profile_id is not None:
            query = query.where(ContextProfileAssignment.profile_id == profile_id)
        query = query.order_by(
            ContextProfileAssignment.created_at.asc(),
            ContextProfileAssignment.id.asc(),
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_assignment_by_agent_fqn(
        self,
        workspace_id: UUID,
        agent_fqn: str,
    ) -> ContextProfileAssignment | None:
        result = await self.session.execute(
            select(ContextProfileAssignment).where(
                ContextProfileAssignment.workspace_id == workspace_id,
                ContextProfileAssignment.assignment_level == ProfileAssignmentLevel.agent,
                ContextProfileAssignment.agent_fqn == agent_fqn,
            )
        )
        return result.scalar_one_or_none()

    async def get_assignment_by_role_type(
        self,
        workspace_id: UUID,
        role_type: str,
    ) -> ContextProfileAssignment | None:
        result = await self.session.execute(
            select(ContextProfileAssignment).where(
                ContextProfileAssignment.workspace_id == workspace_id,
                ContextProfileAssignment.assignment_level == ProfileAssignmentLevel.role_type,
                ContextProfileAssignment.role_type == role_type,
            )
        )
        return result.scalar_one_or_none()

    async def get_workspace_default_assignment(
        self,
        workspace_id: UUID,
    ) -> ContextProfileAssignment | None:
        result = await self.session.execute(
            select(ContextProfileAssignment).where(
                ContextProfileAssignment.workspace_id == workspace_id,
                ContextProfileAssignment.assignment_level == ProfileAssignmentLevel.workspace,
            )
        )
        return result.scalar_one_or_none()

    async def find_assembly_record_by_execution_step(
        self,
        workspace_id: UUID,
        execution_id: UUID,
        step_id: UUID,
    ) -> ContextAssemblyRecord | None:
        result = await self.session.execute(
            select(ContextAssemblyRecord).where(
                ContextAssemblyRecord.workspace_id == workspace_id,
                ContextAssemblyRecord.execution_id == execution_id,
                ContextAssemblyRecord.step_id == step_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_assembly_record(self, **fields: Any) -> ContextAssemblyRecord:
        record = ContextAssemblyRecord(**fields)
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_assembly_record(
        self,
        workspace_id: UUID,
        record_id: UUID,
    ) -> ContextAssemblyRecord | None:
        result = await self.session.execute(
            select(ContextAssemblyRecord).where(
                ContextAssemblyRecord.workspace_id == workspace_id,
                ContextAssemblyRecord.id == record_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_assembly_records(
        self,
        workspace_id: UUID,
        *,
        agent_fqn: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[ContextAssemblyRecord], int]:
        filters = [ContextAssemblyRecord.workspace_id == workspace_id]
        if agent_fqn is not None:
            filters.append(ContextAssemblyRecord.agent_fqn == agent_fqn)
        total = await self.session.scalar(
            select(func.count()).select_from(ContextAssemblyRecord).where(*filters)
        )
        result = await self.session.execute(
            select(ContextAssemblyRecord)
            .where(*filters)
            .order_by(ContextAssemblyRecord.created_at.desc(), ContextAssemblyRecord.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), int(total or 0)

    async def create_ab_test(self, **fields: Any) -> ContextAbTest:
        ab_test = ContextAbTest(**fields)
        self.session.add(ab_test)
        await self.session.flush()
        return ab_test

    async def get_ab_test(self, workspace_id: UUID, test_id: UUID) -> ContextAbTest | None:
        result = await self.session.execute(
            select(ContextAbTest).where(
                ContextAbTest.workspace_id == workspace_id,
                ContextAbTest.id == test_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_active_ab_test(
        self,
        workspace_id: UUID,
        agent_fqn: str,
    ) -> ContextAbTest | None:
        target_priority = case((ContextAbTest.target_agent_fqn == agent_fqn, 0), else_=1)
        result = await self.session.execute(
            select(ContextAbTest)
            .where(
                ContextAbTest.workspace_id == workspace_id,
                ContextAbTest.status == AbTestStatus.active,
                or_(
                    ContextAbTest.target_agent_fqn.is_(None),
                    ContextAbTest.target_agent_fqn == agent_fqn,
                ),
            )
            .order_by(target_priority.asc(), ContextAbTest.created_at.asc(), ContextAbTest.id.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_ab_tests(
        self,
        workspace_id: UUID,
        *,
        status: AbTestStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[ContextAbTest], int]:
        filters = [ContextAbTest.workspace_id == workspace_id]
        if status is not None:
            filters.append(ContextAbTest.status == status)
        total = await self.session.scalar(
            select(func.count()).select_from(ContextAbTest).where(*filters)
        )
        result = await self.session.execute(
            select(ContextAbTest)
            .where(*filters)
            .order_by(ContextAbTest.created_at.desc(), ContextAbTest.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), int(total or 0)

    async def update_ab_test_metrics(
        self,
        ab_test: ContextAbTest,
        *,
        group: str,
        quality_score: float,
        token_count: int,
    ) -> ContextAbTest:
        if group == "variant":
            count = ab_test.variant_assembly_count + 1
            ab_test.variant_quality_mean = self._rolling_mean(
                ab_test.variant_quality_mean,
                ab_test.variant_assembly_count,
                quality_score,
            )
            ab_test.variant_token_mean = self._rolling_mean(
                ab_test.variant_token_mean,
                ab_test.variant_assembly_count,
                float(token_count),
            )
            ab_test.variant_assembly_count = count
        else:
            count = ab_test.control_assembly_count + 1
            ab_test.control_quality_mean = self._rolling_mean(
                ab_test.control_quality_mean,
                ab_test.control_assembly_count,
                quality_score,
            )
            ab_test.control_token_mean = self._rolling_mean(
                ab_test.control_token_mean,
                ab_test.control_assembly_count,
                float(token_count),
            )
            ab_test.control_assembly_count = count
        await self.session.flush()
        return ab_test

    async def complete_ab_test(self, ab_test: ContextAbTest) -> ContextAbTest:
        ab_test.status = AbTestStatus.completed
        ab_test.ended_at = datetime.now(UTC)
        await self.session.flush()
        return ab_test

    async def create_drift_alert(self, **fields: Any) -> ContextDriftAlert:
        alert = ContextDriftAlert(**fields)
        self.session.add(alert)
        await self.session.flush()
        return alert

    async def find_unresolved_drift_alert(
        self,
        workspace_id: UUID,
        agent_fqn: str,
    ) -> ContextDriftAlert | None:
        result = await self.session.execute(
            select(ContextDriftAlert).where(
                ContextDriftAlert.workspace_id == workspace_id,
                ContextDriftAlert.agent_fqn == agent_fqn,
                ContextDriftAlert.resolved_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_drift_alerts(
        self,
        workspace_id: UUID,
        *,
        resolved: bool | None,
        limit: int,
        offset: int,
    ) -> tuple[list[ContextDriftAlert], int]:
        filters = [ContextDriftAlert.workspace_id == workspace_id]
        if resolved is True:
            filters.append(ContextDriftAlert.resolved_at.is_not(None))
        elif resolved is False:
            filters.append(ContextDriftAlert.resolved_at.is_(None))
        total = await self.session.scalar(
            select(func.count()).select_from(ContextDriftAlert).where(*filters)
        )
        result = await self.session.execute(
            select(ContextDriftAlert)
            .where(*filters)
            .order_by(ContextDriftAlert.created_at.desc(), ContextDriftAlert.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), int(total or 0)

    async def resolve_drift_alert(self, alert: ContextDriftAlert) -> ContextDriftAlert:
        alert.resolved_at = datetime.now(UTC)
        await self.session.flush()
        return alert

    @staticmethod
    def _rolling_mean(current_mean: float | None, current_count: int, value: float) -> float:
        if current_mean is None or current_count <= 0:
            return value
        return ((current_mean * current_count) + value) / (current_count + 1)


    async def upsert_correlation_result(self, result: CorrelationResult) -> CorrelationResult:
        existing = await self.session.execute(
            select(CorrelationResult).where(
                CorrelationResult.workspace_id == result.workspace_id,
                CorrelationResult.agent_fqn == result.agent_fqn,
                CorrelationResult.dimension == result.dimension,
                CorrelationResult.performance_metric == result.performance_metric,
                CorrelationResult.window_start == result.window_start,
                CorrelationResult.window_end == result.window_end,
            )
        )
        item = existing.scalar_one_or_none()
        if item is None:
            self.session.add(result)
            await self.session.flush()
            return result
        item.coefficient = result.coefficient
        item.classification = result.classification
        item.data_point_count = result.data_point_count
        item.computed_at = result.computed_at
        await self.session.flush()
        return item

    async def get_latest_by_agent(
        self,
        workspace_id: UUID,
        agent_fqn: str,
        *,
        window_days: int | None = None,
    ) -> list[CorrelationResult]:
        query = select(CorrelationResult).where(
            CorrelationResult.workspace_id == workspace_id,
            CorrelationResult.agent_fqn == agent_fqn,
        )
        if window_days is not None:
            query = query.where(
                func.date_part('day', CorrelationResult.window_end - CorrelationResult.window_start)
                <= window_days
            )
        query = query.order_by(CorrelationResult.computed_at.desc(), CorrelationResult.id.desc())
        result = await self.session.execute(query)
        rows = list(result.scalars().all())
        latest: dict[tuple[str, str], CorrelationResult] = {}
        for row in rows:
            latest.setdefault((row.dimension, row.performance_metric), row)
        return list(latest.values())

    async def list_fleet_by_classification(
        self,
        workspace_id: UUID,
        *,
        classification: CorrelationClassification | str | None = None,
    ) -> list[CorrelationResult]:
        query = select(CorrelationResult).where(CorrelationResult.workspace_id == workspace_id)
        if classification is not None:
            query = query.where(CorrelationResult.classification == classification)
        query = query.order_by(CorrelationResult.computed_at.desc(), CorrelationResult.id.desc())
        result = await self.session.execute(query)
        rows = list(result.scalars().all())
        latest: dict[tuple[str, str, str], CorrelationResult] = {}
        for row in rows:
            latest.setdefault((row.agent_fqn, row.dimension, row.performance_metric), row)
        return list(latest.values())
