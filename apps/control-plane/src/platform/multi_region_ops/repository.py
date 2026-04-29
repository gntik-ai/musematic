from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from platform.multi_region_ops.models import (
    FailoverPlan,
    FailoverPlanRun,
    MaintenanceWindow,
    RegionConfig,
    ReplicationStatus,
)
from typing import Any
from uuid import UUID

from sqlalchemy import and_, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession


class MultiRegionOpsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert_region(
        self,
        *,
        region_code: str,
        region_role: str,
        endpoint_urls: dict[str, Any],
        rpo_target_minutes: int,
        rto_target_minutes: int,
        enabled: bool,
    ) -> RegionConfig:
        region = RegionConfig(
            region_code=region_code,
            region_role=region_role,
            endpoint_urls=endpoint_urls,
            rpo_target_minutes=rpo_target_minutes,
            rto_target_minutes=rto_target_minutes,
            enabled=enabled,
        )
        self.session.add(region)
        await self.session.flush()
        return region

    async def get_region(self, region_id: UUID) -> RegionConfig | None:
        return await self.session.get(RegionConfig, region_id)

    async def get_region_by_code(self, code: str) -> RegionConfig | None:
        result = await self.session.execute(
            select(RegionConfig).where(RegionConfig.region_code == code).limit(1)
        )
        return result.scalar_one_or_none()

    async def list_regions(self, *, enabled_only: bool = False) -> list[RegionConfig]:
        statement = select(RegionConfig)
        if enabled_only:
            statement = statement.where(RegionConfig.enabled.is_(True))
        result = await self.session.execute(statement.order_by(RegionConfig.region_code.asc()))
        return list(result.scalars().all())

    async def update_region(self, region_id: UUID, **updates: Any) -> RegionConfig | None:
        region = await self.get_region(region_id)
        if region is None:
            return None
        for key, value in updates.items():
            if value is not None:
                setattr(region, key, value)
        await self.session.flush()
        return region

    async def count_active_primaries(self, *, exclude_region_id: UUID | None = None) -> int:
        statement = select(func.count(RegionConfig.id)).where(
            RegionConfig.region_role == "primary",
            RegionConfig.enabled.is_(True),
        )
        if exclude_region_id is not None:
            statement = statement.where(RegionConfig.id != exclude_region_id)
        result = await self.session.execute(statement)
        return int(result.scalar_one() or 0)

    async def delete_region(self, region_id: UUID) -> bool:
        region = await self.get_region(region_id)
        if region is None:
            return False
        await self.session.delete(region)
        await self.session.flush()
        return True

    async def has_dependent_plans(self, region_code: str) -> bool:
        result = await self.session.execute(
            select(func.count(FailoverPlan.id)).where(
                or_(
                    FailoverPlan.from_region == region_code,
                    FailoverPlan.to_region == region_code,
                )
            )
        )
        return int(result.scalar_one() or 0) > 0

    async def insert_replication_status(
        self,
        *,
        source_region: str,
        target_region: str,
        component: str,
        lag_seconds: int | None,
        health: str,
        pause_reason: str | None = None,
        error_detail: str | None = None,
        measured_at: datetime | None = None,
    ) -> ReplicationStatus:
        status = ReplicationStatus(
            source_region=source_region,
            target_region=target_region,
            component=component,
            lag_seconds=lag_seconds,
            health=health,
            pause_reason=pause_reason,
            error_detail=error_detail,
            measured_at=measured_at or datetime.now(UTC),
        )
        self.session.add(status)
        await self.session.flush()
        return status

    async def get_latest_per_tuple(
        self,
        *,
        source: str | None = None,
        target: str | None = None,
        component: str | None = None,
    ) -> list[ReplicationStatus]:
        statement = select(ReplicationStatus)
        if source is not None:
            statement = statement.where(ReplicationStatus.source_region == source)
        if target is not None:
            statement = statement.where(ReplicationStatus.target_region == target)
        if component is not None:
            statement = statement.where(ReplicationStatus.component == component)
        result = await self.session.execute(
            statement.order_by(
                ReplicationStatus.source_region.asc(),
                ReplicationStatus.target_region.asc(),
                ReplicationStatus.component.asc(),
                ReplicationStatus.measured_at.desc(),
                ReplicationStatus.id.desc(),
            )
        )
        latest: dict[tuple[str, str, str], ReplicationStatus] = {}
        for row in result.scalars().all():
            key = (row.source_region, row.target_region, row.component)
            latest.setdefault(key, row)
        return list(latest.values())

    async def list_replication_statuses_overview(self) -> list[ReplicationStatus]:
        return await self.get_latest_per_tuple()

    async def list_replication_statuses_window(
        self,
        *,
        source: str | None,
        target: str | None,
        component: str | None,
        since: datetime | None,
        until: datetime | None,
        limit: int = 500,
    ) -> list[ReplicationStatus]:
        statement = select(ReplicationStatus)
        if source is not None:
            statement = statement.where(ReplicationStatus.source_region == source)
        if target is not None:
            statement = statement.where(ReplicationStatus.target_region == target)
        if component is not None:
            statement = statement.where(ReplicationStatus.component == component)
        if since is not None:
            statement = statement.where(ReplicationStatus.measured_at >= since)
        if until is not None:
            statement = statement.where(ReplicationStatus.measured_at <= until)
        result = await self.session.execute(
            statement.order_by(ReplicationStatus.measured_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def count_consecutive_over_threshold(
        self,
        *,
        source: str,
        target: str,
        component: str,
        threshold_seconds: int,
        n: int,
    ) -> bool:
        result = await self.session.execute(
            select(ReplicationStatus)
            .where(
                ReplicationStatus.source_region == source,
                ReplicationStatus.target_region == target,
                ReplicationStatus.component == component,
            )
            .order_by(ReplicationStatus.measured_at.desc(), ReplicationStatus.id.desc())
            .limit(n)
        )
        rows = list(result.scalars().all())
        if len(rows) < n:
            return False
        return all(
            row.health != "paused"
            and row.lag_seconds is not None
            and row.lag_seconds > threshold_seconds
            for row in rows
        )

    async def count_consecutive_at_or_below_threshold(
        self,
        *,
        source: str,
        target: str,
        component: str,
        threshold_seconds: int,
        n: int,
    ) -> bool:
        result = await self.session.execute(
            select(ReplicationStatus)
            .where(
                ReplicationStatus.source_region == source,
                ReplicationStatus.target_region == target,
                ReplicationStatus.component == component,
            )
            .order_by(ReplicationStatus.measured_at.desc(), ReplicationStatus.id.desc())
            .limit(n)
        )
        rows = list(result.scalars().all())
        if len(rows) < n:
            return False
        return all(
            row.health == "healthy"
            and row.lag_seconds is not None
            and row.lag_seconds <= threshold_seconds
            for row in rows
        )

    async def insert_plan(
        self,
        *,
        name: str,
        from_region: str,
        to_region: str,
        steps: list[dict[str, Any]],
        runbook_url: str | None,
        created_by: UUID | None,
    ) -> FailoverPlan:
        plan = FailoverPlan(
            name=name,
            from_region=from_region,
            to_region=to_region,
            steps=steps,
            runbook_url=runbook_url,
            created_by=created_by,
        )
        self.session.add(plan)
        await self.session.flush()
        return plan

    async def get_plan(self, plan_id: UUID) -> FailoverPlan | None:
        return await self.session.get(FailoverPlan, plan_id)

    async def get_plan_by_name(self, name: str) -> FailoverPlan | None:
        result = await self.session.execute(
            select(FailoverPlan).where(FailoverPlan.name == name).limit(1)
        )
        return result.scalar_one_or_none()

    async def list_plans(
        self,
        *,
        from_region: str | None = None,
        to_region: str | None = None,
    ) -> list[FailoverPlan]:
        statement = select(FailoverPlan)
        if from_region is not None:
            statement = statement.where(FailoverPlan.from_region == from_region)
        if to_region is not None:
            statement = statement.where(FailoverPlan.to_region == to_region)
        result = await self.session.execute(statement.order_by(FailoverPlan.name.asc()))
        return list(result.scalars().all())

    async def update_plan(
        self,
        plan_id: UUID,
        *,
        expected_version: int,
        updates: dict[str, Any],
    ) -> FailoverPlan | None:
        plan = await self.get_plan(plan_id)
        if plan is None or plan.version != expected_version:
            return None
        for key, value in updates.items():
            if value is not None:
                setattr(plan, key, value)
        plan.version += 1
        await self.session.flush()
        return plan

    async def delete_plan(self, plan_id: UUID) -> bool:
        plan = await self.get_plan(plan_id)
        if plan is None:
            return False
        await self.session.delete(plan)
        await self.session.flush()
        return True

    async def has_in_progress_runs(self, plan_id: UUID) -> bool:
        result = await self.session.execute(
            select(func.count(FailoverPlanRun.id)).where(
                FailoverPlanRun.plan_id == plan_id,
                FailoverPlanRun.outcome == "in_progress",
            )
        )
        return int(result.scalar_one() or 0) > 0

    async def insert_plan_run(
        self,
        *,
        plan_id: UUID,
        run_kind: str,
        initiated_by: UUID | None,
        reason: str | None,
        lock_token: str,
    ) -> FailoverPlanRun:
        run = FailoverPlanRun(
            plan_id=plan_id,
            run_kind=run_kind,
            outcome="in_progress",
            step_outcomes=[],
            initiated_by=initiated_by,
            reason=reason,
            lock_token=lock_token,
        )
        self.session.add(run)
        await self.session.flush()
        return run

    async def update_plan_run_outcome(
        self,
        run_id: UUID,
        *,
        outcome: str,
        ended_at: datetime | None = None,
    ) -> FailoverPlanRun | None:
        run = await self.get_plan_run(run_id)
        if run is None:
            return None
        run.outcome = outcome
        if ended_at is not None:
            run.ended_at = ended_at
        await self.session.flush()
        return run

    async def append_plan_run_step_outcome(
        self,
        run_id: UUID,
        step_outcome: dict[str, Any],
    ) -> FailoverPlanRun | None:
        run = await self.get_plan_run(run_id)
        if run is None:
            return None
        run.step_outcomes = [*list(run.step_outcomes or []), step_outcome]
        await self.session.flush()
        return run

    async def get_plan_run(self, run_id: UUID) -> FailoverPlanRun | None:
        return await self.session.get(FailoverPlanRun, run_id)

    async def list_plan_runs(self, plan_id: UUID, *, limit: int = 100) -> list[FailoverPlanRun]:
        result = await self.session.execute(
            select(FailoverPlanRun)
            .where(FailoverPlanRun.plan_id == plan_id)
            .order_by(FailoverPlanRun.started_at.desc(), FailoverPlanRun.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_latest_in_progress_run(
        self,
        *,
        from_region: str,
        to_region: str,
    ) -> FailoverPlanRun | None:
        result = await self.session.execute(
            select(FailoverPlanRun)
            .join(FailoverPlan, FailoverPlan.id == FailoverPlanRun.plan_id)
            .where(
                FailoverPlan.from_region == from_region,
                FailoverPlan.to_region == to_region,
                FailoverPlanRun.outcome == "in_progress",
            )
            .order_by(FailoverPlanRun.started_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def mark_plan_tested(self, plan_id: UUID, ts: datetime) -> None:
        await self.session.execute(
            update(FailoverPlan).where(FailoverPlan.id == plan_id).values(tested_at=ts)
        )
        await self.session.flush()

    async def mark_plan_executed(self, plan_id: UUID, ts: datetime) -> None:
        await self.session.execute(
            update(FailoverPlan).where(FailoverPlan.id == plan_id).values(last_executed_at=ts)
        )
        await self.session.flush()

    async def insert_window(
        self,
        *,
        starts_at: datetime,
        ends_at: datetime,
        reason: str | None,
        blocks_writes: bool,
        announcement_text: str | None,
        scheduled_by: UUID | None,
    ) -> MaintenanceWindow:
        window = MaintenanceWindow(
            starts_at=starts_at,
            ends_at=ends_at,
            reason=reason,
            blocks_writes=blocks_writes,
            announcement_text=announcement_text,
            status="scheduled",
            scheduled_by=scheduled_by,
        )
        self.session.add(window)
        await self.session.flush()
        await self.session.refresh(window)
        return window

    async def get_window(self, window_id: UUID) -> MaintenanceWindow | None:
        return await self.session.get(MaintenanceWindow, window_id)

    async def get_active_window(self) -> MaintenanceWindow | None:
        result = await self.session.execute(
            select(MaintenanceWindow)
            .where(MaintenanceWindow.status == "active")
            .order_by(MaintenanceWindow.enabled_at.desc().nullslast())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_windows(
        self,
        *,
        status: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 500,
    ) -> list[MaintenanceWindow]:
        statement = select(MaintenanceWindow)
        if status is not None:
            statement = statement.where(MaintenanceWindow.status == status)
        if since is not None:
            statement = statement.where(MaintenanceWindow.ends_at >= since)
        if until is not None:
            statement = statement.where(MaintenanceWindow.starts_at <= until)
        result = await self.session.execute(
            statement.order_by(
                desc(MaintenanceWindow.starts_at), MaintenanceWindow.id.desc()
            ).limit(limit)
        )
        return list(result.scalars().all())

    async def update_window_status(
        self,
        window_id: UUID,
        *,
        status: str,
        **fields: Any,
    ) -> MaintenanceWindow | None:
        window = await self.get_window(window_id)
        if window is None:
            return None
        window.status = status
        for key, value in fields.items():
            setattr(window, key, value)
        await self.session.flush()
        await self.session.refresh(window)
        return window

    async def update_window(
        self,
        window_id: UUID,
        **fields: Any,
    ) -> MaintenanceWindow | None:
        window = await self.get_window(window_id)
        if window is None:
            return None
        for key, value in fields.items():
            if value is not None:
                setattr(window, key, value)
        await self.session.flush()
        await self.session.refresh(window)
        return window

    async def find_overlapping_windows(
        self,
        *,
        starts_at: datetime,
        ends_at: datetime,
        exclude_id: UUID | None = None,
        statuses: Sequence[str] = ("scheduled", "active"),
    ) -> list[MaintenanceWindow]:
        statement = select(MaintenanceWindow).where(
            MaintenanceWindow.status.in_(tuple(statuses)),
            and_(MaintenanceWindow.starts_at < ends_at, MaintenanceWindow.ends_at > starts_at),
        )
        if exclude_id is not None:
            statement = statement.where(MaintenanceWindow.id != exclude_id)
        result = await self.session.execute(statement.order_by(MaintenanceWindow.starts_at.asc()))
        return list(result.scalars().all())
