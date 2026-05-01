from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from platform.simulation.models import (
    BehavioralPrediction,
    DigitalTwin,
    SimulationComparisonReport,
    SimulationIsolationPolicy,
    SimulationRun,
    SimulationScenario,
)
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Select, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

STATUS_CACHE_TTL_SECONDS = 24 * 60 * 60


class SimulationRepository:
    def __init__(self, session: AsyncSession, redis: Any | None = None) -> None:
        self.session = session
        self.redis = redis

    async def create_run(self, run: SimulationRun) -> SimulationRun:
        self.session.add(run)
        await self.session.flush()
        return run

    async def create_scenario(self, scenario: SimulationScenario) -> SimulationScenario:
        self.session.add(scenario)
        await self.session.flush()
        return scenario

    async def get_scenario(
        self,
        scenario_id: UUID,
        workspace_id: UUID,
    ) -> SimulationScenario | None:
        result = await self.session.execute(
            select(SimulationScenario).where(
                SimulationScenario.id == scenario_id,
                SimulationScenario.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_scenarios(
        self,
        workspace_id: UUID,
        *,
        include_archived: bool = False,
        limit: int = 20,
        cursor: str | None = None,
    ) -> tuple[list[SimulationScenario], str | None]:
        query = select(SimulationScenario).where(SimulationScenario.workspace_id == workspace_id)
        if not include_archived:
            query = query.where(SimulationScenario.archived_at.is_(None))
        query = _apply_uuid_cursor(query, SimulationScenario.id, cursor)
        query = query.order_by(
            SimulationScenario.updated_at.desc(),
            SimulationScenario.id.desc(),
        ).limit(limit + 1)
        return _items_with_cursor(list((await self.session.execute(query)).scalars().all()), limit)

    async def update_scenario(
        self,
        scenario_id: UUID,
        workspace_id: UUID,
        values: dict[str, Any],
    ) -> SimulationScenario | None:
        if values:
            await self.session.execute(
                update(SimulationScenario)
                .where(
                    SimulationScenario.id == scenario_id,
                    SimulationScenario.workspace_id == workspace_id,
                )
                .values(**values)
            )
            await self.session.flush()
        return await self.get_scenario(scenario_id, workspace_id)

    async def archive_scenario(
        self,
        scenario_id: UUID,
        workspace_id: UUID,
    ) -> SimulationScenario | None:
        return await self.update_scenario(
            scenario_id,
            workspace_id,
            {"archived_at": datetime.now(UTC)},
        )

    async def list_runs_for_scenario(
        self,
        scenario_id: UUID,
        workspace_id: UUID,
        *,
        limit: int = 20,
    ) -> list[SimulationRun]:
        result = await self.session.execute(
            select(SimulationRun)
            .where(
                SimulationRun.scenario_id == scenario_id,
                SimulationRun.workspace_id == workspace_id,
            )
            .order_by(SimulationRun.created_at.desc(), SimulationRun.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_run(self, run_id: UUID, workspace_id: UUID) -> SimulationRun | None:
        result = await self.session.execute(
            select(SimulationRun).where(
                SimulationRun.id == run_id,
                SimulationRun.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_runs(
        self,
        workspace_id: UUID,
        *,
        status: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> tuple[list[SimulationRun], str | None]:
        query = select(SimulationRun).where(SimulationRun.workspace_id == workspace_id)
        if status is not None:
            query = query.where(SimulationRun.status == status)
        query = _apply_uuid_cursor(query, SimulationRun.id, cursor)
        query = query.order_by(SimulationRun.created_at.desc(), SimulationRun.id.desc()).limit(
            limit + 1
        )
        return _items_with_cursor(list((await self.session.execute(query)).scalars().all()), limit)

    async def update_run_status(
        self,
        run_id: UUID,
        workspace_id: UUID,
        status: str,
        *,
        results: dict[str, Any] | None = None,
    ) -> SimulationRun | None:
        values: dict[str, Any] = {"status": status}
        if status == "running":
            values["started_at"] = datetime.now(UTC)
        if status in {"completed", "cancelled", "failed", "timeout"}:
            values["completed_at"] = datetime.now(UTC)
        if results is not None:
            values["results"] = results
        await self.session.execute(
            update(SimulationRun)
            .where(SimulationRun.id == run_id, SimulationRun.workspace_id == workspace_id)
            .values(**values)
        )
        await self.session.flush()
        return await self.get_run(run_id, workspace_id)

    async def set_run_isolation_bundle(
        self,
        run_id: UUID,
        workspace_id: UUID,
        bundle_fingerprint: str | None,
    ) -> SimulationRun | None:
        await self.session.execute(
            update(SimulationRun)
            .where(SimulationRun.id == run_id, SimulationRun.workspace_id == workspace_id)
            .values(isolation_bundle_fingerprint=bundle_fingerprint)
        )
        await self.session.flush()
        return await self.get_run(run_id, workspace_id)

    async def create_twin(self, twin: DigitalTwin) -> DigitalTwin:
        self.session.add(twin)
        await self.session.flush()
        return twin

    async def get_twin(self, twin_id: UUID, workspace_id: UUID) -> DigitalTwin | None:
        result = await self.session.execute(
            select(DigitalTwin).where(
                DigitalTwin.id == twin_id,
                DigitalTwin.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_twins(
        self,
        workspace_id: UUID,
        *,
        agent_fqn: str | None = None,
        is_active: bool | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> tuple[list[DigitalTwin], str | None]:
        query = select(DigitalTwin).where(DigitalTwin.workspace_id == workspace_id)
        if agent_fqn is not None:
            query = query.where(DigitalTwin.source_agent_fqn == agent_fqn)
        if is_active is not None:
            query = query.where(DigitalTwin.is_active == is_active)
        query = _apply_uuid_cursor(query, DigitalTwin.id, cursor)
        query = query.order_by(DigitalTwin.created_at.desc(), DigitalTwin.id.desc()).limit(
            limit + 1
        )
        return _items_with_cursor(list((await self.session.execute(query)).scalars().all()), limit)

    async def list_twin_versions(self, twin: DigitalTwin) -> list[DigitalTwin]:
        root_id = twin.parent_twin_id or twin.id
        result = await self.session.execute(
            select(DigitalTwin)
            .where(
                DigitalTwin.workspace_id == twin.workspace_id,
                (DigitalTwin.id == root_id) | (DigitalTwin.parent_twin_id == root_id),
            )
            .order_by(DigitalTwin.version.asc(), DigitalTwin.created_at.asc())
        )
        return list(result.scalars().all())

    async def update_twin_active(
        self,
        twin_id: UUID,
        workspace_id: UUID,
        is_active: bool,
    ) -> None:
        await self.session.execute(
            update(DigitalTwin)
            .where(DigitalTwin.id == twin_id, DigitalTwin.workspace_id == workspace_id)
            .values(is_active=is_active)
        )
        await self.session.flush()

    async def create_isolation_policy(
        self,
        policy: SimulationIsolationPolicy,
    ) -> SimulationIsolationPolicy:
        self.session.add(policy)
        await self.session.flush()
        return policy

    async def get_isolation_policy(
        self,
        policy_id: UUID,
        workspace_id: UUID,
    ) -> SimulationIsolationPolicy | None:
        result = await self.session.execute(
            select(SimulationIsolationPolicy).where(
                SimulationIsolationPolicy.id == policy_id,
                SimulationIsolationPolicy.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_isolation_policies(self, workspace_id: UUID) -> list[SimulationIsolationPolicy]:
        result = await self.session.execute(
            select(SimulationIsolationPolicy)
            .where(SimulationIsolationPolicy.workspace_id == workspace_id)
            .order_by(SimulationIsolationPolicy.is_default.desc(), SimulationIsolationPolicy.name)
        )
        return list(result.scalars().all())

    async def create_prediction(self, prediction: BehavioralPrediction) -> BehavioralPrediction:
        self.session.add(prediction)
        await self.session.flush()
        return prediction

    async def get_prediction(
        self,
        prediction_id: UUID,
        workspace_id: UUID | None = None,
    ) -> BehavioralPrediction | None:
        query = select(BehavioralPrediction).where(BehavioralPrediction.id == prediction_id)
        if workspace_id is not None:
            query = query.join(DigitalTwin).where(DigitalTwin.workspace_id == workspace_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_pending_predictions(self, limit: int = 50) -> list[BehavioralPrediction]:
        result = await self.session.execute(
            select(BehavioralPrediction)
            .where(BehavioralPrediction.status == "pending")
            .order_by(BehavioralPrediction.created_at.asc(), BehavioralPrediction.id.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update_prediction(
        self,
        prediction_id: UUID,
        **values: Any,
    ) -> BehavioralPrediction | None:
        await self.session.execute(
            update(BehavioralPrediction)
            .where(BehavioralPrediction.id == prediction_id)
            .values(**values)
        )
        await self.session.flush()
        return await self.get_prediction(prediction_id)

    async def create_comparison_report(
        self,
        report: SimulationComparisonReport,
    ) -> SimulationComparisonReport:
        self.session.add(report)
        await self.session.flush()
        return report

    async def get_comparison_report(
        self,
        report_id: UUID,
        workspace_id: UUID,
    ) -> SimulationComparisonReport | None:
        result = await self.session.execute(
            select(SimulationComparisonReport)
            .join(SimulationRun, SimulationComparisonReport.primary_run_id == SimulationRun.id)
            .where(
                SimulationComparisonReport.id == report_id,
                SimulationRun.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def update_comparison_report(
        self,
        report_id: UUID,
        **values: Any,
    ) -> SimulationComparisonReport | None:
        await self.session.execute(
            update(SimulationComparisonReport)
            .where(SimulationComparisonReport.id == report_id)
            .values(**values)
        )
        await self.session.flush()
        result = await self.session.execute(
            select(SimulationComparisonReport).where(SimulationComparisonReport.id == report_id)
        )
        return result.scalar_one_or_none()

    async def set_status_cache(self, run_id: UUID, status_dict: dict[str, Any]) -> None:
        if self.redis is None:
            return
        payload = {
            **status_dict,
            "last_updated": status_dict.get("last_updated")
            or datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
        value = json.dumps(payload, default=str).encode("utf-8")
        set_method = getattr(self.redis, "set", None)
        if set_method is None:
            return
        try:
            await set_method(_status_cache_key(run_id), value, ttl=STATUS_CACHE_TTL_SECONDS)
        except TypeError:
            await set_method(_status_cache_key(run_id), value, ex=STATUS_CACHE_TTL_SECONDS)

    async def get_status_cache(self, run_id: UUID) -> dict[str, Any] | None:
        if self.redis is None:
            return None
        get_method = getattr(self.redis, "get", None)
        if get_method is None:
            return None
        raw = await get_method(_status_cache_key(run_id))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return cast(dict[str, Any], json.loads(str(raw)))


def _status_cache_key(run_id: UUID) -> str:
    return f"sim:status:{run_id}"


def _apply_uuid_cursor(
    query: Select[Any],
    column: InstrumentedAttribute[UUID],
    cursor: str | None,
) -> Select[Any]:
    if not cursor:
        return query
    try:
        return query.where(column < UUID(cursor))
    except ValueError:
        return query


def _items_with_cursor(items: Sequence[Any], limit: int) -> tuple[list[Any], str | None]:
    page = list(items[:limit])
    next_cursor = None
    if len(items) > limit and page:
        next_cursor = str(page[-1].id)
    return page, next_cursor
