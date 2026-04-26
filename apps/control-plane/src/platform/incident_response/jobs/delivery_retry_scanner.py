from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from platform.audit.dependencies import build_audit_chain_service
from platform.common import database
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.events.producer import EventProducer
from platform.incident_response.dependencies import (
    build_incident_service,
    build_runbook_service,
)
from platform.incident_response.repository import IncidentResponseRepository
from platform.incident_response.services.providers.opsgenie import OpsGenieClient
from platform.incident_response.services.providers.pagerduty import PagerDutyClient
from platform.incident_response.services.providers.victorops import VictorOpsClient
from platform.security_compliance.providers.rotatable_secret_provider import RotatableSecretProvider
from typing import Any, cast

LOGGER = logging.getLogger(__name__)


async def run_delivery_retry_scan(app: Any) -> int:
    started = time.perf_counter()
    settings = cast(PlatformSettings, app.state.settings)
    async with database.AsyncSessionLocal() as session:
        secret_provider = RotatableSecretProvider(
            settings=settings,
            redis_client=cast(AsyncRedisClient | None, app.state.clients.get("redis")),
        )
        provider_clients = {
            "pagerduty": PagerDutyClient(
                secret_provider=secret_provider,
                timeout_seconds=settings.incident_response.external_alert_request_timeout_seconds,
            ),
            "opsgenie": OpsGenieClient(
                secret_provider=secret_provider,
                timeout_seconds=settings.incident_response.external_alert_request_timeout_seconds,
            ),
            "victorops": VictorOpsClient(
                secret_provider=secret_provider,
                timeout_seconds=settings.incident_response.external_alert_request_timeout_seconds,
            ),
        }
        audit_chain = build_audit_chain_service(
            session=session,
            settings=settings,
            producer=cast(EventProducer | None, app.state.clients.get("kafka")),
        )
        runbook_service = build_runbook_service(
            session=session,
            settings=settings,
            audit_chain_service=audit_chain,
        )
        service = build_incident_service(
            session=session,
            settings=settings,
            redis_client=cast(AsyncRedisClient | None, app.state.clients.get("redis")),
            producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            provider_clients=provider_clients,
            runbook_service=runbook_service,
            audit_chain_service=audit_chain,
        )
        repository = IncidentResponseRepository(session)
        pending = await repository.list_pending_retries(datetime.now(UTC))
        semaphore = asyncio.Semaphore(16)

        async def _dispatch(alert: Any) -> None:
            async with semaphore:
                if alert.attempt_count >= settings.incident_response.delivery_retry_max_attempts:
                    await repository.update_external_alert_status(
                        alert.id,
                        status="failed",
                        error=alert.last_error or "retry attempts exhausted",
                        next_retry_at=None,
                    )
                    LOGGER.error(
                        "incident_response_delivery_retry_exhausted",
                        extra={"external_alert_id": str(alert.id)},
                    )
                    return
                await service._dispatch_external_alert(alert.id)

        await asyncio.gather(*(_dispatch(alert) for alert in pending))
        await session.commit()
    LOGGER.info(
        "incident_response_delivery_retry_scan_completed",
        extra={
            "count": len(pending),
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        },
    )
    return len(pending)


def build_delivery_retry_scheduler(app: Any) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio",
            fromlist=["AsyncIOScheduler"],
        )
    except Exception:
        return None
    settings = cast(PlatformSettings, app.state.settings)
    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")

    async def _run() -> None:
        await run_delivery_retry_scan(app)

    scheduler.add_job(
        _run,
        "interval",
        seconds=settings.incident_response.delivery_retry_scan_interval_seconds,
        id="incident-response-delivery-retry",
        replace_existing=True,
    )
    return scheduler
