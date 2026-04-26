from __future__ import annotations

import asyncio
import logging
import time
from platform.common import database
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.events.producer import EventProducer
from platform.cost_governance.clickhouse_repository import ClickHouseCostRepository
from platform.cost_governance.dependencies import build_cost_governance_service
from platform.cost_governance.exceptions import InsufficientHistoryError
from platform.cost_governance.repository import CostGovernanceRepository
from typing import Any, cast
from uuid import UUID

LOGGER = logging.getLogger(__name__)


async def run_anomaly_evaluation(app: Any) -> None:
    started = time.perf_counter()
    async with database.AsyncSessionLocal() as session:
        workspace_ids = await CostGovernanceRepository(session).list_workspace_ids_with_costs()
    semaphore = asyncio.Semaphore(8)

    async def _detect(workspace_id: UUID) -> None:
        async with semaphore:
            async with database.AsyncSessionLocal() as session:
                service = build_cost_governance_service(
                    session=session,
                    settings=cast(PlatformSettings, app.state.settings),
                    producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                    redis_client=cast(AsyncRedisClient | None, app.state.clients.get("redis")),
                    clickhouse_repository=cast(
                        ClickHouseCostRepository | None,
                        getattr(app.state, "cost_clickhouse_repository", None),
                    ),
                )
                try:
                    await service.anomaly_service.detect(workspace_id)
                    await session.commit()
                except InsufficientHistoryError:
                    await session.rollback()
                except Exception:
                    await session.rollback()
                    LOGGER.exception(
                        "Cost anomaly evaluation failed",
                        extra={"workspace_id": str(workspace_id)},
                    )

    await asyncio.gather(*(_detect(workspace_id) for workspace_id in workspace_ids))
    LOGGER.info(
        "Cost anomaly evaluation completed",
        extra={
            "workspace_count": len(workspace_ids),
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        },
    )


def build_anomaly_scheduler(app: Any) -> Any | None:
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
        await run_anomaly_evaluation(app)

    scheduler.add_job(
        _run,
        "interval",
        seconds=settings.cost_governance.anomaly_evaluation_interval_seconds,
        id="cost-governance-anomaly-evaluation",
        replace_existing=True,
    )
    return scheduler
