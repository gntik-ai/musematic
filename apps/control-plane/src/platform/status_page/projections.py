"""Status page projections for FR-675-FR-682.

See specs/095-public-status-banner-workbench-uis/plan.md for the implementation plan.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from importlib import import_module
from platform.common import database
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.events.consumer import EventConsumerManager
from platform.common.events.envelope import EventEnvelope
from platform.common.logging import get_logger
from platform.status_page.repository import StatusPageRepository
from platform.status_page.schemas import SourceKind
from platform.status_page.service import StatusPageService
from typing import Any

import httpx

LOGGER = get_logger(__name__)

STATUS_EVENT_TOPICS = (
    "multi_region_ops.events",
    "incident_response.events",
    "platform.status.derived",
)
STATUS_RECOMPOSE_EVENT_PREFIXES = (
    "maintenance.",
    "multi_region_ops.maintenance.",
    "incident.",
    "incident_response.",
    "platform.status.",
)
DEFAULT_HEALTH_TARGETS: Mapping[str, str] = {
    "control-plane-api": "http://localhost:8000",
}


class StatusPageProjectionConsumer:
    def __init__(
        self,
        *,
        settings: PlatformSettings,
        redis_client: AsyncRedisClient | None = None,
    ) -> None:
        self.settings = settings
        self.redis_client = redis_client

    def register(self, manager: EventConsumerManager) -> None:
        for topic in STATUS_EVENT_TOPICS:
            manager.subscribe(
                topic,
                f"{self.settings.kafka.consumer_group}.status-page-projections",
                self.handle_event,
            )

    async def handle_event(self, envelope: EventEnvelope) -> None:
        if not _should_recompose(envelope):
            return
        async with database.AsyncSessionLocal() as session:
            service = StatusPageService(
                repository=StatusPageRepository(session),
                redis_client=self.redis_client,
            )
            try:
                await service.compose_current_snapshot(source_kind=SourceKind.kafka)
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Failed to recompose platform status snapshot from event")


async def poll_component_health(
    targets: Mapping[str, str] | None = None,
    *,
    timeout_seconds: float = 2.0,
) -> list[dict[str, Any]]:
    resolved_targets = targets or _health_targets_from_env() or DEFAULT_HEALTH_TARGETS
    now = datetime.now(UTC)
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        results = await _poll_all_targets(client, resolved_targets, now=now)
    return results


async def compose_polled_snapshot(
    service: StatusPageService,
    *,
    targets: Mapping[str, str] | None = None,
) -> None:
    component_health = await poll_component_health(targets)
    await service.compose_current_snapshot(
        component_health=component_health,
        source_kind=SourceKind.poll,
    )


async def compute_30d_uptime_rollup(service: StatusPageService) -> None:
    snapshot = await service.get_public_snapshot()
    uptime = {
        component.id: {
            "pct": component.uptime_30d_pct if component.uptime_30d_pct is not None else 100,
            "incidents": snapshot.snapshot.uptime_30d.get(component.id, {}).incidents
            if component.id in snapshot.snapshot.uptime_30d
            else 0,
        }
        for component in snapshot.snapshot.components
    }
    component_health = [
        {
            "id": component.id,
            "name": component.name,
            "state": component.state.value,
            "last_check_at": component.last_check_at,
            "uptime_30d_pct": uptime[component.id]["pct"],
        }
        for component in snapshot.snapshot.components
    ]
    await service.compose_current_snapshot(
        component_health=component_health,
        source_kind=SourceKind.poll,
    )


def build_status_page_scheduler(service: StatusPageService) -> Any:
    scheduler_module = import_module("apscheduler.schedulers.asyncio")
    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        compose_polled_snapshot,
        "interval",
        seconds=60,
        id="status-page-snapshot-poll",
        kwargs={"service": service},
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        compute_30d_uptime_rollup,
        "cron",
        hour=0,
        minute=5,
        id="status-page-uptime-rollup",
        kwargs={"service": service},
        max_instances=1,
        coalesce=True,
    )
    return scheduler


async def _poll_all_targets(
    client: httpx.AsyncClient,
    targets: Mapping[str, str],
    *,
    now: datetime,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for component_id, base_url in targets.items():
        state = "operational"
        name = component_id.replace("-", " ").title()
        for path in ("/healthz", "/readyz"):
            try:
                response = await client.get(f"{base_url.rstrip('/')}{path}")
                if response.status_code >= 500:
                    state = "partial_outage"
                    break
                if response.status_code >= 400:
                    state = "degraded"
            except httpx.HTTPError:
                state = "partial_outage"
                break
        results.append(
            {
                "id": component_id,
                "name": name,
                "state": state,
                "last_check_at": now,
                "uptime_30d_pct": 100.0 if state == "operational" else 99.0,
            }
        )
    return results


def _health_targets_from_env() -> Mapping[str, str] | None:
    raw = os.environ.get("STATUS_PAGE_HEALTH_TARGETS")
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        LOGGER.warning("Ignoring invalid STATUS_PAGE_HEALTH_TARGETS JSON")
        return None
    if not isinstance(parsed, dict):
        return None
    return {str(key): str(value) for key, value in parsed.items()}


def _should_recompose(envelope: EventEnvelope) -> bool:
    event_type = envelope.event_type
    return any(event_type.startswith(prefix) for prefix in STATUS_RECOMPOSE_EVENT_PREFIXES)
