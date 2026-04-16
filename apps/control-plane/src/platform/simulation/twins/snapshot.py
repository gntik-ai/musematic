from __future__ import annotations

from copy import deepcopy
from platform.common.config import PlatformSettings
from platform.simulation.events import SimulationEventPublisher
from platform.simulation.exceptions import (
    SimulationInfrastructureUnavailableError,
    SimulationNotFoundError,
)
from platform.simulation.models import DigitalTwin
from platform.simulation.repository import SimulationRepository
from typing import Any
from uuid import UUID


class TwinSnapshotService:
    def __init__(
        self,
        *,
        repository: SimulationRepository,
        registry_service: Any | None,
        clickhouse_client: Any | None,
        publisher: SimulationEventPublisher,
        settings: PlatformSettings,
    ) -> None:
        self.repository = repository
        self.registry_service = registry_service
        self.clickhouse_client = clickhouse_client
        self.publisher = publisher
        self.settings = settings

    async def create_twin(
        self,
        *,
        agent_fqn: str,
        workspace_id: UUID,
        revision_id: UUID | None = None,
    ) -> DigitalTwin:
        profile = await self._get_agent_profile(agent_fqn, workspace_id)
        if profile is None:
            raise SimulationNotFoundError("Agent", agent_fqn)
        selected_revision_id = revision_id or _uuid_or_none(_field(profile, "latest_revision_id"))
        revision = (
            await self._get_agent_revision(agent_fqn, selected_revision_id)
            if selected_revision_id is not None
            else None
        )
        config_snapshot = _config_snapshot(profile, revision)
        history_summary = await self._behavioral_history_summary(agent_fqn, workspace_id)
        if str(_field(profile, "status", "")).lower() == "archived":
            history_summary.setdefault("warning_flags", []).append("agent_archived")
        twin = await self.repository.create_twin(
            DigitalTwin(
                workspace_id=workspace_id,
                source_agent_fqn=agent_fqn,
                source_revision_id=selected_revision_id,
                version=1,
                parent_twin_id=None,
                config_snapshot=config_snapshot,
                behavioral_history_summary=history_summary,
                modifications=[],
                is_active=True,
            )
        )
        await self.publisher.twin_created(twin.id, workspace_id, agent_fqn)
        return twin

    async def modify_twin(
        self,
        *,
        twin_id: UUID,
        workspace_id: UUID,
        modifications: list[dict[str, Any]],
    ) -> DigitalTwin:
        current = await self.repository.get_twin(twin_id, workspace_id)
        if current is None:
            raise SimulationNotFoundError("Digital twin", twin_id)
        await self.repository.update_twin_active(current.id, workspace_id, False)
        snapshot = deepcopy(current.config_snapshot)
        for modification in modifications:
            _apply_modification(snapshot, str(modification["field"]), modification.get("value"))
        new_twin = await self.repository.create_twin(
            DigitalTwin(
                workspace_id=workspace_id,
                source_agent_fqn=current.source_agent_fqn,
                source_revision_id=current.source_revision_id,
                version=current.version + 1,
                parent_twin_id=current.parent_twin_id or current.id,
                config_snapshot=snapshot,
                behavioral_history_summary=dict(current.behavioral_history_summary),
                modifications=[*list(current.modifications or []), *modifications],
                is_active=True,
            )
        )
        await self.publisher.twin_modified(new_twin.id, workspace_id, current.id, new_twin.version)
        return new_twin

    async def _get_agent_profile(self, agent_fqn: str, workspace_id: UUID) -> Any | None:
        if self.registry_service is None:
            raise SimulationInfrastructureUnavailableError("registry", "service is not configured")
        if hasattr(self.registry_service, "get_agent_profile"):
            return await self.registry_service.get_agent_profile(agent_fqn, workspace_id)
        if hasattr(self.registry_service, "get_agent_by_fqn"):
            return await self.registry_service.get_agent_by_fqn(agent_fqn, workspace_id)
        if hasattr(self.registry_service, "resolve_fqn"):
            return await self.registry_service.resolve_fqn(fqn=agent_fqn, workspace_id=workspace_id)
        raise SimulationInfrastructureUnavailableError("registry", "agent lookup is not available")

    async def _get_agent_revision(self, agent_fqn: str, revision_id: UUID) -> Any | None:
        if self.registry_service is None or not hasattr(
            self.registry_service,
            "get_agent_revision",
        ):
            return None
        try:
            return await self.registry_service.get_agent_revision(revision_id)
        except TypeError:
            return await self.registry_service.get_agent_revision(agent_fqn, revision_id)

    async def _behavioral_history_summary(
        self,
        agent_fqn: str,
        workspace_id: UUID,
    ) -> dict[str, Any]:
        days = self.settings.simulation.behavioral_history_days
        rows: list[dict[str, Any]] = []
        if self.clickhouse_client is not None:
            query = """
                SELECT date, avg_quality_score, avg_response_time_ms, avg_error_rate,
                       execution_count
                FROM execution_metrics_daily
                WHERE workspace_id = {workspace_id:String}
                  AND agent_fqn = {agent_fqn:String}
                  AND date >= today() - {days:UInt16}
                ORDER BY date ASC
            """
            try:
                rows = await self.clickhouse_client.execute_query(
                    query,
                    {"workspace_id": str(workspace_id), "agent_fqn": agent_fqn, "days": days},
                )
            except Exception:
                rows = []
        return _summarize_history(rows, days)


def _summarize_history(rows: list[dict[str, Any]], period_days: int) -> dict[str, Any]:
    quality = _numeric_series(rows, "avg_quality_score")
    response = _numeric_series(rows, "avg_response_time_ms")
    error = _numeric_series(rows, "avg_error_rate")
    return {
        "period_days": period_days,
        "history_days_used": len(rows),
        "avg_quality_score": _avg(quality),
        "avg_response_time_ms": _avg(response),
        "avg_error_rate": _avg(error),
        "execution_count": int(sum(_numeric_series(rows, "execution_count"))),
        "quality_trend": _trend(quality),
        "response_trend": _trend(response, inverse=True),
        "error_trend": _trend(error, inverse=True),
    }


def _numeric_series(rows: list[dict[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = row.get(key)
        if value is None:
            continue
        values.append(float(value))
    return values


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _trend(values: list[float], *, inverse: bool = False) -> str:
    if len(values) < 2 or values[0] == 0:
        return "stable"
    change = (values[-1] - values[0]) / abs(values[0])
    if inverse:
        change = -change
    if change > 0.05:
        return "improving"
    if change < -0.05:
        return "degrading"
    return "stable"


def _config_snapshot(profile: Any, revision: Any | None) -> dict[str, Any]:
    profile_data = _dump(profile)
    revision_data = _dump(revision)
    source = {**profile_data, **revision_data}
    return {
        "model": source.get("model_config") or source.get("model") or {},
        "tools": source.get("tool_selections") or source.get("tools") or [],
        "policies": source.get("policies") or source.get("policy_refs") or [],
        "context_profile": source.get("context_profile") or source.get("context_profile_id") or {},
        "connectors": source.get("connector_suggestions") or source.get("connectors") or [],
        "visibility": source.get("visibility_config") or source.get("visibility") or {},
        "manifest": source.get("manifest_snapshot") or source.get("manifest") or {},
    }


def _apply_modification(snapshot: dict[str, Any], field_path: str, value: Any) -> None:
    target = snapshot
    parts = field_path.split(".")
    for part in parts[:-1]:
        next_value = target.setdefault(part, {})
        if not isinstance(next_value, dict):
            next_value = {}
            target[part] = next_value
        target = next_value
    target[parts[-1]] = value


def _dump(value: Any | None) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        return dict(value.model_dump(mode="json"))
    if hasattr(value, "__dict__"):
        return {key: item for key, item in vars(value).items() if not key.startswith("_")}
    return {}


def _field(value: Any, name: str, default: Any | None = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _uuid_or_none(value: Any) -> UUID | None:
    if value is None:
        return None
    return value if isinstance(value, UUID) else UUID(str(value))
