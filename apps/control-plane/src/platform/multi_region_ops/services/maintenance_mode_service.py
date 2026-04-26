from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from platform.audit.service import AuditChainService
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.incident_response.schemas import IncidentSeverity, IncidentSignal
from platform.incident_response.trigger_interface import IncidentTriggerInterface
from platform.multi_region_ops.constants import REDIS_KEY_ACTIVE_WINDOW
from platform.multi_region_ops.events import (
    MaintenanceModeDisabledPayload,
    MaintenanceModeEnabledPayload,
    MultiRegionOpsEventType,
    publish_multi_region_ops_event,
)
from platform.multi_region_ops.exceptions import (
    MaintenanceDisableFailedError,
    MaintenanceWindowInPastError,
    MaintenanceWindowNotFoundError,
    MaintenanceWindowOverlapError,
)
from platform.multi_region_ops.models import MaintenanceWindow
from platform.multi_region_ops.repository import MultiRegionOpsRepository
from platform.multi_region_ops.schemas import (
    MaintenanceWindowCreateRequest,
    MaintenanceWindowUpdateRequest,
)
from typing import Any, Literal
from uuid import UUID, uuid4


class MaintenanceModeService:
    def __init__(
        self,
        *,
        repository: MultiRegionOpsRepository,
        settings: PlatformSettings,
        redis_client: AsyncRedisClient | None = None,
        producer: EventProducer | None = None,
        incident_trigger: IncidentTriggerInterface | None = None,
        audit_chain_service: AuditChainService | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.redis_client = redis_client
        self.producer = producer
        self.incident_trigger = incident_trigger
        self.audit_chain_service = audit_chain_service

    async def schedule(
        self,
        payload: MaintenanceWindowCreateRequest,
        *,
        by_user_id: UUID | None = None,
    ) -> MaintenanceWindow:
        now = datetime.now(UTC)
        if _aware(payload.starts_at) < now:
            raise MaintenanceWindowInPastError()
        overlap = await self.repository.find_overlapping_windows(
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
        )
        if overlap:
            raise MaintenanceWindowOverlapError(overlap[0].id)
        window = await self.repository.insert_window(
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
            reason=payload.reason,
            blocks_writes=payload.blocks_writes,
            announcement_text=payload.announcement_text,
            scheduled_by=by_user_id,
        )
        await self._audit(
            "multi_region_ops.maintenance_window.scheduled",
            {
                "window_id": str(window.id),
                "actor_id": str(by_user_id) if by_user_id else None,
            },
        )
        return window

    async def update(
        self,
        window_id: UUID,
        payload: MaintenanceWindowUpdateRequest,
        *,
        by_user_id: UUID | None = None,
    ) -> MaintenanceWindow:
        window = await self.repository.get_window(window_id)
        if window is None:
            raise MaintenanceWindowNotFoundError(window_id)
        if window.status != "scheduled":
            raise ValueError("Only scheduled maintenance windows can be modified")
        starts_at = payload.starts_at or window.starts_at
        ends_at = payload.ends_at or window.ends_at
        if _aware(starts_at) < datetime.now(UTC):
            raise MaintenanceWindowInPastError()
        overlap = await self.repository.find_overlapping_windows(
            starts_at=starts_at,
            ends_at=ends_at,
            exclude_id=window_id,
        )
        if overlap:
            raise MaintenanceWindowOverlapError(overlap[0].id)
        updated = await self.repository.update_window(
            window_id,
            **payload.model_dump(exclude_unset=True),
        )
        if updated is None:
            raise MaintenanceWindowNotFoundError(window_id)
        await self._audit(
            "multi_region_ops.maintenance_window.updated",
            {"window_id": str(window_id), "actor_id": str(by_user_id) if by_user_id else None},
        )
        return updated

    async def enable(
        self,
        window_id: UUID,
        *,
        by_user_id: UUID | None = None,
    ) -> MaintenanceWindow:
        window = await self.repository.get_window(window_id)
        if window is None:
            raise MaintenanceWindowNotFoundError(window_id)
        enabled_at = datetime.now(UTC)
        window = await self.repository.update_window_status(
            window_id,
            status="active",
            enabled_at=enabled_at,
            disable_failure_reason=None,
        )
        if window is None:
            raise MaintenanceWindowNotFoundError(window_id)
        await self._prime_active_cache(window)
        correlation_ctx = CorrelationContext(correlation_id=uuid4())
        await publish_multi_region_ops_event(
            self.producer,
            MultiRegionOpsEventType.maintenance_mode_enabled,
            MaintenanceModeEnabledPayload(
                window_id=window.id,
                starts_at=window.starts_at,
                ends_at=window.ends_at,
                reason=window.reason,
                announcement_text=window.announcement_text,
            ),
            correlation_ctx,
        )
        await self._audit(
            "multi_region_ops.maintenance_window.enabled",
            {"window_id": str(window.id), "actor_id": str(by_user_id) if by_user_id else None},
        )
        return window

    async def disable(
        self,
        window_id: UUID,
        *,
        by_user_id: UUID | None = None,
        disable_kind: Literal["manual", "scheduled", "failed"] = "manual",
    ) -> MaintenanceWindow:
        window = await self.repository.get_window(window_id)
        if window is None:
            raise MaintenanceWindowNotFoundError(window_id)
        disabled_at = datetime.now(UTC)
        try:
            await self._clear_active_cache()
        except Exception as exc:
            reason = str(exc)
            await self.repository.update_window_status(
                window_id,
                status="active",
                disable_failure_reason=reason,
            )
            await self._fire_disable_failed_incident(window, reason)
            raise MaintenanceDisableFailedError(reason) from exc
        window = await self.repository.update_window_status(
            window_id,
            status="completed",
            disabled_at=disabled_at,
            disable_failure_reason=None,
        )
        if window is None:
            raise MaintenanceWindowNotFoundError(window_id)
        correlation_ctx = CorrelationContext(correlation_id=uuid4())
        await publish_multi_region_ops_event(
            self.producer,
            MultiRegionOpsEventType.maintenance_mode_disabled,
            MaintenanceModeDisabledPayload(
                window_id=window.id,
                disabled_at=disabled_at,
                disable_kind=disable_kind,
            ),
            correlation_ctx,
        )
        await self._audit(
            "multi_region_ops.maintenance_window.disabled",
            {
                "window_id": str(window.id),
                "disable_kind": disable_kind,
                "actor_id": str(by_user_id) if by_user_id else None,
            },
        )
        return window

    async def cancel(self, window_id: UUID, *, by_user_id: UUID | None = None) -> MaintenanceWindow:
        window = await self.repository.get_window(window_id)
        if window is None:
            raise MaintenanceWindowNotFoundError(window_id)
        if window.status != "scheduled":
            raise ValueError("Only scheduled maintenance windows can be cancelled")
        window = await self.repository.update_window_status(window_id, status="cancelled")
        if window is None:
            raise MaintenanceWindowNotFoundError(window_id)
        await self._audit(
            "multi_region_ops.maintenance_window.cancelled",
            {"window_id": str(window.id), "actor_id": str(by_user_id) if by_user_id else None},
        )
        return window

    async def get_active_window(self) -> MaintenanceWindow | None:
        cached = await self._read_active_cache()
        if cached is not None:
            return cached
        window = await self.repository.get_active_window()
        if window is not None:
            await self._prime_active_cache(window)
        return window

    async def list_windows(
        self,
        *,
        status: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[MaintenanceWindow]:
        return await self.repository.list_windows(status=status, since=since, until=until)

    def status_banner(self, window: MaintenanceWindow | None) -> dict[str, Any] | None:
        if window is None:
            return None
        return {
            "producer": "multi_region_ops",
            "message": (
                f"Maintenance in progress until {window.ends_at.isoformat()}: "
                f"{window.announcement_text or window.reason or 'Planned maintenance'}"
            ),
            "window_id": str(window.id),
            "starts_at": window.starts_at.isoformat(),
            "ends_at": window.ends_at.isoformat(),
        }

    async def _prime_active_cache(self, window: MaintenanceWindow) -> None:
        if self.redis_client is None:
            return
        ttl_seconds = max(
            1,
            int((_aware(window.ends_at) - datetime.now(UTC)).total_seconds()) + 60,
        )
        payload = {
            "id": str(window.id),
            "starts_at": window.starts_at.isoformat(),
            "ends_at": window.ends_at.isoformat(),
            "reason": window.reason,
            "blocks_writes": window.blocks_writes,
            "announcement_text": window.announcement_text,
            "status": window.status,
            "scheduled_by": str(window.scheduled_by) if window.scheduled_by else None,
            "enabled_at": window.enabled_at.isoformat() if window.enabled_at else None,
            "disabled_at": window.disabled_at.isoformat() if window.disabled_at else None,
            "disable_failure_reason": window.disable_failure_reason,
            "created_at": window.created_at.isoformat(),
            "updated_at": window.updated_at.isoformat(),
        }
        await self.redis_client.set(
            REDIS_KEY_ACTIVE_WINDOW,
            json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            ttl=ttl_seconds,
        )

    async def _read_active_cache(self) -> MaintenanceWindow | None:
        if self.redis_client is None:
            return None
        raw = await self.redis_client.get(REDIS_KEY_ACTIVE_WINDOW)
        if raw is None:
            return None
        data = json.loads(raw.decode("utf-8"))
        return _window_from_cache(data)

    async def _clear_active_cache(self) -> None:
        if self.redis_client is not None:
            await self.redis_client.delete(REDIS_KEY_ACTIVE_WINDOW)

    async def _fire_disable_failed_incident(self, window: MaintenanceWindow, reason: str) -> None:
        if self.incident_trigger is None:
            return
        await self.incident_trigger.fire(
            IncidentSignal(
                condition_fingerprint=f"maintenance:disable:{window.id}",
                severity=IncidentSeverity.high,
                alert_rule_class="maintenance_disable_failed",
                title="Maintenance disable failed",
                description=reason,
                runbook_scenario="region_failover",
                correlation_context=CorrelationContext(correlation_id=uuid4()),
            )
        )

    async def _audit(self, event_source: str, payload: dict[str, Any]) -> None:
        if self.audit_chain_service is None:
            return
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        await self.audit_chain_service.append(uuid4(), event_source, canonical)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _window_from_cache(data: dict[str, Any]) -> MaintenanceWindow:
    def _dt(key: str) -> datetime | None:
        raw = data.get(key)
        return datetime.fromisoformat(raw) if isinstance(raw, str) and raw else None

    window = MaintenanceWindow(
        starts_at=_dt("starts_at") or datetime.now(UTC),
        ends_at=_dt("ends_at") or datetime.now(UTC) + timedelta(minutes=1),
        reason=data.get("reason"),
        blocks_writes=bool(data.get("blocks_writes", True)),
        announcement_text=data.get("announcement_text"),
        status=str(data.get("status") or "active"),
        disable_failure_reason=data.get("disable_failure_reason"),
        created_at=_dt("created_at") or datetime.now(UTC),
        updated_at=_dt("updated_at") or datetime.now(UTC),
    )
    if data.get("id"):
        window.id = UUID(str(data["id"]))
    if data.get("scheduled_by"):
        window.scheduled_by = UUID(str(data["scheduled_by"]))
    window.enabled_at = _dt("enabled_at")
    window.disabled_at = _dt("disabled_at")
    return window
