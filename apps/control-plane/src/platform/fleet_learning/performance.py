from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from platform.fleet_learning.models import FleetPerformanceProfile
from platform.fleet_learning.repository import FleetPerformanceProfileRepository
from platform.fleet_learning.schemas import (
    FleetPerformanceProfileQuery,
    FleetPerformanceProfileResponse,
)
from typing import Any
from uuid import UUID


class FleetPerformanceProfileService:
    def __init__(
        self,
        *,
        repository: FleetPerformanceProfileRepository,
        clickhouse: Any,
        fleet_service: Any,
    ) -> None:
        self.repository = repository
        self.clickhouse = clickhouse
        self.fleet_service = fleet_service

    async def compute_profile(
        self,
        fleet_id: UUID,
        workspace_id: UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> FleetPerformanceProfileResponse:
        members = await self.fleet_service.get_fleet_members(fleet_id, workspace_id)
        member_fqns = [member.agent_fqn for member in members]
        rows: list[dict[str, Any]] = []
        if member_fqns:
            rows = await self.clickhouse.execute_query(
                """
                SELECT
                    agent_fqn,
                    avg(completion_time_ms) AS avg_completion_time_ms,
                    count() AS execution_count,
                    countIf(status = 'success') / greatest(count(), 1) AS success_rate,
                    sum(cost_usd) / greatest(count(), 1) AS cost_per_task,
                    avg(quality_score) AS quality_score
                FROM execution_metrics
                WHERE agent_fqn IN {member_fqns:Array(String)}
                  AND completed_at BETWEEN {period_start:DateTime64} AND {period_end:DateTime64}
                GROUP BY agent_fqn
                """,
                {
                    "member_fqns": member_fqns,
                    "period_start": period_start,
                    "period_end": period_end,
                },
            )
        member_metrics: dict[str, dict[str, float]] = {}
        avg_times: list[float] = []
        total_executions = 0
        total_cost_per_task = 0.0
        total_success_rate = 0.0
        total_quality = 0.0
        for row in rows:
            avg_ms = float(row.get("avg_completion_time_ms") or 0.0)
            success_rate = float(row.get("success_rate") or 0.0)
            cost_per_task = float(row.get("cost_per_task") or 0.0)
            quality_score = float(row.get("quality_score") or 0.0)
            execution_count = int(row.get("execution_count") or 0)
            agent_fqn = str(row["agent_fqn"])
            member_metrics[agent_fqn] = {
                "avg_completion_time_ms": avg_ms,
                "success_rate": success_rate,
                "cost_per_task": cost_per_task,
                "quality_score": quality_score,
            }
            avg_times.append(avg_ms)
            total_executions += execution_count
            total_cost_per_task += cost_per_task
            total_success_rate += success_rate
            total_quality += quality_score
        count = len(member_metrics)
        avg_completion_time_ms = sum(avg_times) / count if count else 0.0
        success_rate = total_success_rate / count if count else 0.0
        cost_per_task = total_cost_per_task / count if count else 0.0
        avg_quality_score = total_quality / count if count else 0.0
        hours = max((period_end - period_start).total_seconds() / 3600.0, 1e-9)
        throughput_per_hour = total_executions / hours
        stddev = (
            math.sqrt(sum((value - avg_completion_time_ms) ** 2 for value in avg_times) / count)
            if count
            else 0.0
        )
        flagged_member_fqns = [
            agent_fqn
            for agent_fqn, metrics in member_metrics.items()
            if stddev > 0
            and abs(float(metrics["avg_completion_time_ms"]) - avg_completion_time_ms) > 2 * stddev
        ]
        profile = await self.repository.insert(
            FleetPerformanceProfile(
                fleet_id=fleet_id,
                workspace_id=workspace_id,
                period_start=period_start,
                period_end=period_end,
                avg_completion_time_ms=avg_completion_time_ms,
                success_rate=success_rate,
                cost_per_task=cost_per_task,
                avg_quality_score=avg_quality_score,
                throughput_per_hour=throughput_per_hour,
                member_metrics=member_metrics,
                flagged_member_fqns=flagged_member_fqns,
            )
        )
        return FleetPerformanceProfileResponse.model_validate(profile)

    async def compute_all_profiles(
        self,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> list[FleetPerformanceProfileResponse]:
        end = period_end or datetime.now(UTC)
        start = period_start or (end - timedelta(days=1))
        results: list[FleetPerformanceProfileResponse] = []
        for fleet in await self.fleet_service.list_active_fleets():
            results.append(await self.compute_profile(fleet.id, fleet.workspace_id, start, end))
        return results

    async def get_profile(
        self,
        fleet_id: UUID,
        workspace_id: UUID,
        query: FleetPerformanceProfileQuery,
    ) -> FleetPerformanceProfileResponse:
        profile = await self.repository.get_by_range(
            fleet_id,
            start=query.start,
            end=query.end,
        )
        if profile is None:
            raise ValueError(f"No performance profile exists for fleet {fleet_id}")
        if profile.workspace_id != workspace_id:
            raise ValueError(f"Fleet {fleet_id} does not belong to workspace {workspace_id}")
        return FleetPerformanceProfileResponse.model_validate(profile)

    async def get_profile_history(
        self,
        fleet_id: UUID,
        workspace_id: UUID,
    ) -> list[FleetPerformanceProfileResponse]:
        items = await self.repository.list_by_range(fleet_id)
        return [
            FleetPerformanceProfileResponse.model_validate(item)
            for item in items
            if item.workspace_id == workspace_id
        ]
