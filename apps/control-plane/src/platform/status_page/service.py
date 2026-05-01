"""Status page service for FR-675-FR-682.

See specs/095-public-status-banner-workbench-uis/plan.md for the implementation plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from platform.incident_response.models import Incident
from platform.multi_region_ops.models import MaintenanceWindow
from platform.status_page.models import PlatformStatusSnapshot
from platform.status_page.repository import StatusPageRepository
from platform.status_page.schemas import (
    ComponentDetail,
    ComponentHistoryPoint,
    ComponentStatus,
    MaintenanceWindowSummary,
    MyIncidentSummary,
    MyMaintenanceWindowSummary,
    MyPlatformStatus,
    OverallState,
    PlatformStatusSnapshotPayload,
    PlatformStatusSnapshotRead,
    PublicIncident,
    PublicIncidentsResponse,
    SourceKind,
    UptimeSummary,
    snapshot_read_from_payload,
)
from typing import Any

CURRENT_SNAPSHOT_KEY = "status:snapshot:current"
LAST_GOOD_SNAPSHOT_KEY = "status:fallback:lastgood"

DEFAULT_COMPONENTS: tuple[tuple[str, str], ...] = (
    ("control-plane-api", "Control Plane API"),
    ("web-app", "Authenticated Web App"),
    ("reasoning-engine", "Reasoning Engine"),
    ("workflow-engine", "Workflow Engine"),
)


@dataclass(frozen=True)
class SnapshotWithSource:
    snapshot: PlatformStatusSnapshotRead
    source: str

    @property
    def age_seconds(self) -> int:
        generated_at = self.snapshot.generated_at
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=UTC)
        return max(0, int((datetime.now(UTC) - generated_at).total_seconds()))


class StatusPageService:
    def __init__(
        self,
        *,
        repository: StatusPageRepository,
        redis_client: Any | None = None,
    ) -> None:
        self.repository = repository
        self.redis_client = redis_client

    async def compose_current_snapshot(
        self,
        *,
        component_health: list[dict[str, Any]] | None = None,
        source_kind: SourceKind = SourceKind.poll,
    ) -> PlatformStatusSnapshotRead:
        generated_at = datetime.now(UTC)
        active_incidents = [
            self._incident_to_public(incident)
            for incident in await self.repository.list_active_incidents()
        ]
        recently_resolved = [
            self._incident_to_public(incident)
            for incident in await self.repository.list_recent_resolved_incidents(days=7)
        ]
        scheduled = [
            self._maintenance_to_summary(window)
            for window in await self.repository.list_scheduled_maintenance(days=30)
        ]
        active_maintenance_windows = await self.repository.list_active_maintenance()
        active_maintenance = (
            self._maintenance_to_summary(active_maintenance_windows[0])
            if active_maintenance_windows
            else None
        )
        uptime = self._normalise_uptime(await self.repository.get_uptime_30d())
        components = self._normalise_components(
            component_health,
            generated_at=generated_at,
            uptime=uptime,
        )
        overall_state = self._aggregate_overall_state(
            components=components,
            active_incidents=active_incidents,
            active_maintenance=active_maintenance,
        )
        payload = PlatformStatusSnapshotPayload(
            overall_state=overall_state,
            components=components,
            active_incidents=active_incidents,
            scheduled_maintenance=scheduled,
            active_maintenance=active_maintenance,
            recently_resolved_incidents=recently_resolved,
            uptime_30d=uptime,
        )
        row = await self.repository.insert_snapshot(
            generated_at=generated_at,
            overall_state=overall_state.value,
            payload=payload.model_dump(mode="json"),
            source_kind=source_kind.value,
        )
        snapshot = self._snapshot_from_row(row)
        await self._cache_snapshot(snapshot)
        return snapshot

    async def get_public_snapshot(self) -> SnapshotWithSource:
        cached = await self._get_cached_snapshot(CURRENT_SNAPSHOT_KEY)
        if cached is not None:
            return SnapshotWithSource(cached, "redis")

        row = await self.repository.get_current_snapshot()
        if row is not None:
            snapshot = self._snapshot_from_row(row)
            await self._cache_snapshot(snapshot, current_only=True)
            return SnapshotWithSource(snapshot, "postgres")

        snapshot = await self.compose_current_snapshot(source_kind=SourceKind.fallback)
        return SnapshotWithSource(snapshot, "fallback")

    async def get_component_detail(self, component_id: str, *, days: int = 30) -> ComponentDetail:
        current = await self.get_public_snapshot()
        component = next(
            (item for item in current.snapshot.components if item.id == component_id),
            None,
        )
        if component is None:
            raise KeyError(component_id)
        history = [
            ComponentHistoryPoint.model_validate(point)
            for point in await self.repository.get_component_history(component_id, days=days)
        ]
        return ComponentDetail(**component.model_dump(), history_30d=history)

    async def list_public_incidents(
        self,
        *,
        status: str | None = None,
    ) -> PublicIncidentsResponse:
        if status == "active":
            incidents = [
                self._incident_to_public(incident)
                for incident in await self.repository.list_active_incidents()
            ]
        elif status == "resolved":
            incidents = [
                self._incident_to_public(incident)
                for incident in await self.repository.list_recent_resolved_incidents(days=7)
            ]
        else:
            snapshot = (await self.get_public_snapshot()).snapshot
            incidents = snapshot.active_incidents + snapshot.recently_resolved_incidents
        return PublicIncidentsResponse(incidents=incidents)

    async def get_my_platform_status(self, current_user: dict[str, Any]) -> MyPlatformStatus:
        del current_user
        snapshot = (await self.get_public_snapshot()).snapshot
        active_maintenance = None
        if snapshot.active_maintenance is not None:
            active_maintenance = MyMaintenanceWindowSummary(
                **snapshot.active_maintenance.model_dump(),
                affects_my_features=[],
            )

        return MyPlatformStatus(
            overall_state=snapshot.overall_state,
            active_maintenance=active_maintenance,
            active_incidents=[
                MyIncidentSummary(**incident.model_dump(), affects_my_features=[])
                for incident in snapshot.active_incidents
            ],
        )

    def _snapshot_from_row(self, row: PlatformStatusSnapshot) -> PlatformStatusSnapshotRead:
        return snapshot_read_from_payload(
            generated_at=row.generated_at,
            payload=row.payload,
            source_kind=row.source_kind,
            snapshot_id=str(row.id),
        )

    def _normalise_components(
        self,
        component_health: list[dict[str, Any]] | None,
        *,
        generated_at: datetime,
        uptime: dict[str, UptimeSummary],
    ) -> list[ComponentStatus]:
        raw_components = component_health
        if raw_components is None:
            raw_components = [
                {
                    "id": component_id,
                    "name": name,
                    "state": OverallState.operational.value,
                    "last_check_at": generated_at,
                    "uptime_30d_pct": uptime.get(
                        component_id,
                        UptimeSummary(pct=100, incidents=0),
                    ).pct,
                }
                for component_id, name in DEFAULT_COMPONENTS
            ]

        components: list[ComponentStatus] = []
        for item in raw_components:
            component_id = str(item.get("id", "")).strip()
            if not component_id:
                continue
            state = self._normalise_state(str(item.get("state", OverallState.operational.value)))
            components.append(
                ComponentStatus(
                    id=component_id,
                    name=str(item.get("name") or component_id.replace("-", " ").title()),
                    state=state,
                    last_check_at=item.get("last_check_at") or generated_at,
                    uptime_30d_pct=item.get("uptime_30d_pct")
                    or uptime.get(component_id, UptimeSummary(pct=100, incidents=0)).pct,
                )
            )
        return components

    def _normalise_uptime(self, raw: dict[str, Any]) -> dict[str, UptimeSummary]:
        uptime: dict[str, UptimeSummary] = {}
        for component_id, value in raw.items():
            if isinstance(value, UptimeSummary):
                uptime[str(component_id)] = value
            elif isinstance(value, dict):
                uptime[str(component_id)] = UptimeSummary.model_validate(value)
        for component_id, _name in DEFAULT_COMPONENTS:
            uptime.setdefault(component_id, UptimeSummary(pct=100, incidents=0))
        return uptime

    def _aggregate_overall_state(
        self,
        *,
        components: list[ComponentStatus],
        active_incidents: list[PublicIncident],
        active_maintenance: MaintenanceWindowSummary | None,
    ) -> OverallState:
        if active_maintenance is not None:
            return OverallState.maintenance
        if not components:
            return OverallState.degraded if active_incidents else OverallState.operational
        outage_states = {OverallState.partial_outage, OverallState.full_outage}
        if all(component.state in outage_states for component in components):
            return OverallState.full_outage
        if any(component.state in outage_states for component in components):
            return OverallState.partial_outage
        if any(component.state == OverallState.degraded for component in components):
            return OverallState.degraded
        if any(
            incident.severity.value in {"high", "critical", "warning"}
            for incident in active_incidents
        ):
            return OverallState.degraded
        return OverallState.operational

    def _normalise_state(self, state: str) -> OverallState:
        if state in {"outage", "down", "unavailable"}:
            return OverallState.partial_outage
        try:
            return OverallState(state)
        except ValueError:
            return OverallState.degraded

    def _incident_to_public(self, incident: Incident) -> PublicIncident:
        last_update_at = incident.resolved_at or incident.triggered_at
        last_update_summary = (
            "Incident resolved." if incident.resolved_at is not None else incident.description
        )
        return PublicIncident(
            id=str(incident.id),
            title=incident.title,
            severity=incident.severity,
            started_at=incident.triggered_at,
            resolved_at=incident.resolved_at,
            components_affected=self._incident_components(incident),
            last_update_at=last_update_at,
            last_update_summary=last_update_summary,
            updates=[{"at": last_update_at, "text": last_update_summary}],
        )

    def _incident_components(self, incident: Incident) -> list[str]:
        candidates = [
            incident.alert_rule_class,
            incident.runbook_scenario or "",
            incident.condition_fingerprint,
            incident.title,
        ]
        lowered = " ".join(candidates).lower()
        components: list[str] = []
        if "control" in lowered or "api" in lowered:
            components.append("control-plane-api")
        if "reasoning" in lowered:
            components.append("reasoning-engine")
        if "workflow" in lowered or "execution" in lowered:
            components.append("workflow-engine")
        return components

    def _maintenance_to_summary(self, window: MaintenanceWindow) -> MaintenanceWindowSummary:
        return MaintenanceWindowSummary(
            window_id=str(window.id),
            title=window.announcement_text or window.reason or "Scheduled maintenance",
            starts_at=window.starts_at,
            ends_at=window.ends_at,
            blocks_writes=window.blocks_writes,
            components_affected=[],
        )

    async def _get_cached_snapshot(self, key: str) -> PlatformStatusSnapshotRead | None:
        if self.redis_client is None:
            return None
        getter = getattr(self.redis_client, "get", None)
        if not callable(getter):
            return None
        value = await getter(key)
        if value is None:
            return None
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        return PlatformStatusSnapshotRead.model_validate_json(str(value))

    async def _cache_snapshot(
        self,
        snapshot: PlatformStatusSnapshotRead,
        *,
        current_only: bool = False,
    ) -> None:
        if self.redis_client is None:
            return
        body = snapshot.model_dump_json().encode("utf-8")
        await self._redis_set(CURRENT_SNAPSHOT_KEY, body, ttl=90)
        if not current_only:
            await self._redis_set(LAST_GOOD_SNAPSHOT_KEY, body, ttl=24 * 60 * 60)

    async def _redis_set(self, key: str, value: bytes, *, ttl: int) -> None:
        setter = getattr(self.redis_client, "set", None)
        if not callable(setter):
            return
        try:
            await setter(key, value, ttl=ttl)
        except TypeError:
            await setter(key, value, ex=ttl)
