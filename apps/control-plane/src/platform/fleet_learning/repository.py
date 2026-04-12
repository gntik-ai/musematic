from __future__ import annotations

from datetime import datetime
from platform.fleet_learning.models import (
    CrossFleetTransferRequest,
    FleetAdaptationLog,
    FleetAdaptationRule,
    FleetPerformanceProfile,
    FleetPersonalityProfile,
    TransferRequestStatus,
)
from typing import Literal
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession


class FleetPerformanceProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert(self, profile: FleetPerformanceProfile) -> FleetPerformanceProfile:
        self.session.add(profile)
        await self.session.flush()
        return profile

    async def get_latest(self, fleet_id: UUID) -> FleetPerformanceProfile | None:
        result = await self.session.execute(
            select(FleetPerformanceProfile)
            .where(FleetPerformanceProfile.fleet_id == fleet_id)
            .order_by(
                FleetPerformanceProfile.period_end.desc(), FleetPerformanceProfile.created_at.desc()
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_range(
        self,
        fleet_id: UUID,
        *,
        start: datetime,
        end: datetime,
    ) -> FleetPerformanceProfile | None:
        result = await self.session.execute(
            select(FleetPerformanceProfile)
            .where(
                FleetPerformanceProfile.fleet_id == fleet_id,
                FleetPerformanceProfile.period_start <= end,
                FleetPerformanceProfile.period_end >= start,
            )
            .order_by(
                FleetPerformanceProfile.period_end.desc(), FleetPerformanceProfile.created_at.desc()
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_by_range(
        self,
        fleet_id: UUID,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[FleetPerformanceProfile]:
        query = select(FleetPerformanceProfile).where(FleetPerformanceProfile.fleet_id == fleet_id)
        if start is not None:
            query = query.where(FleetPerformanceProfile.period_end >= start)
        if end is not None:
            query = query.where(FleetPerformanceProfile.period_start <= end)
        result = await self.session.execute(
            query.order_by(
                FleetPerformanceProfile.period_end.desc(), FleetPerformanceProfile.created_at.desc()
            )
        )
        return list(result.scalars().all())


class FleetAdaptationRuleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, rule: FleetAdaptationRule) -> FleetAdaptationRule:
        self.session.add(rule)
        await self.session.flush()
        return rule

    async def get_by_id(
        self, rule_id: UUID, fleet_id: UUID | None = None
    ) -> FleetAdaptationRule | None:
        query = select(FleetAdaptationRule).where(FleetAdaptationRule.id == rule_id)
        if fleet_id is not None:
            query = query.where(FleetAdaptationRule.fleet_id == fleet_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_active_by_priority(self, fleet_id: UUID) -> list[FleetAdaptationRule]:
        result = await self.session.execute(
            select(FleetAdaptationRule)
            .where(
                FleetAdaptationRule.fleet_id == fleet_id,
                FleetAdaptationRule.is_active.is_(True),
            )
            .order_by(FleetAdaptationRule.priority.desc(), FleetAdaptationRule.created_at.asc())
        )
        return list(result.scalars().all())

    async def list_by_fleet(self, fleet_id: UUID) -> list[FleetAdaptationRule]:
        result = await self.session.execute(
            select(FleetAdaptationRule)
            .where(FleetAdaptationRule.fleet_id == fleet_id)
            .order_by(FleetAdaptationRule.priority.desc(), FleetAdaptationRule.created_at.asc())
        )
        return list(result.scalars().all())

    async def update(self, rule: FleetAdaptationRule) -> FleetAdaptationRule:
        await self.session.flush()
        return rule

    async def deactivate(self, rule: FleetAdaptationRule) -> FleetAdaptationRule:
        rule.is_active = False
        await self.session.flush()
        return rule

    async def list_fleet_ids_with_active_rules(self) -> list[UUID]:
        result = await self.session.execute(
            select(FleetAdaptationRule.fleet_id)
            .where(FleetAdaptationRule.is_active.is_(True))
            .distinct()
        )
        return list(result.scalars().all())


class FleetAdaptationLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, log: FleetAdaptationLog) -> FleetAdaptationLog:
        self.session.add(log)
        await self.session.flush()
        return log

    async def list_by_fleet(
        self,
        fleet_id: UUID,
        *,
        is_reverted: bool | None = None,
    ) -> list[FleetAdaptationLog]:
        query = select(FleetAdaptationLog).where(FleetAdaptationLog.fleet_id == fleet_id)
        if is_reverted is not None:
            query = query.where(FleetAdaptationLog.is_reverted.is_(is_reverted))
        result = await self.session.execute(
            query.order_by(
                FleetAdaptationLog.triggered_at.desc(), FleetAdaptationLog.created_at.desc()
            )
        )
        return list(result.scalars().all())

    async def get_by_id(self, log_id: UUID) -> FleetAdaptationLog | None:
        result = await self.session.execute(
            select(FleetAdaptationLog).where(FleetAdaptationLog.id == log_id)
        )
        return result.scalar_one_or_none()

    async def mark_reverted(self, log: FleetAdaptationLog) -> FleetAdaptationLog:
        log.is_reverted = True
        log.reverted_at = datetime.now(log.triggered_at.tzinfo)
        await self.session.flush()
        return log


class CrossFleetTransferRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, request: CrossFleetTransferRequest) -> CrossFleetTransferRequest:
        self.session.add(request)
        await self.session.flush()
        return request

    async def get_by_id(self, transfer_id: UUID) -> CrossFleetTransferRequest | None:
        result = await self.session.execute(
            select(CrossFleetTransferRequest).where(CrossFleetTransferRequest.id == transfer_id)
        )
        return result.scalar_one_or_none()

    async def update_status(self, request: CrossFleetTransferRequest) -> CrossFleetTransferRequest:
        await self.session.flush()
        return request

    async def list_for_fleet(
        self,
        fleet_id: UUID,
        *,
        role: Literal["source", "target"] | None = None,
        status: TransferRequestStatus | None = None,
    ) -> list[CrossFleetTransferRequest]:
        query = select(CrossFleetTransferRequest)
        if role == "source":
            query = query.where(CrossFleetTransferRequest.source_fleet_id == fleet_id)
        elif role == "target":
            query = query.where(CrossFleetTransferRequest.target_fleet_id == fleet_id)
        else:
            query = query.where(
                or_(
                    CrossFleetTransferRequest.source_fleet_id == fleet_id,
                    CrossFleetTransferRequest.target_fleet_id == fleet_id,
                )
            )
        if status is not None:
            query = query.where(CrossFleetTransferRequest.status == status)
        result = await self.session.execute(
            query.order_by(CrossFleetTransferRequest.created_at.desc())
        )
        return list(result.scalars().all())


class FleetPersonalityProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_current(self, fleet_id: UUID) -> FleetPersonalityProfile | None:
        result = await self.session.execute(
            select(FleetPersonalityProfile).where(
                FleetPersonalityProfile.fleet_id == fleet_id,
                FleetPersonalityProfile.is_current.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def create_version(self, profile: FleetPersonalityProfile) -> FleetPersonalityProfile:
        current = await self.get_current(profile.fleet_id)
        if current is not None:
            current.is_current = False
        self.session.add(profile)
        await self.session.flush()
        return profile

    async def list_history(self, fleet_id: UUID) -> list[FleetPersonalityProfile]:
        result = await self.session.execute(
            select(FleetPersonalityProfile)
            .where(FleetPersonalityProfile.fleet_id == fleet_id)
            .order_by(
                FleetPersonalityProfile.version.desc(), FleetPersonalityProfile.created_at.desc()
            )
        )
        return list(result.scalars().all())
