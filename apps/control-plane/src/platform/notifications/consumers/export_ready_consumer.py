"""Notifications consumer for ``data_lifecycle.export.completed`` events.

T038 (UPD-051): when ExportJobWorker finalizes a workspace or tenant export
it publishes ``data_lifecycle.export.completed`` on ``data_lifecycle.events``.
This consumer dispatches an ``export_ready`` notification to the user who
requested the job (resolved by joining ``data_export_jobs.requested_by_user_id``).

The consumer is intentionally tolerant: any unexpected payload shape or a
missing requesting user is logged and skipped rather than crashing the
notifications worker — export-job completion is observable from the
data-lifecycle Grafana dashboard regardless.
"""

from __future__ import annotations

from platform.common import database
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.events.consumer import EventConsumerManager
from platform.common.events.envelope import EventEnvelope
from platform.common.events.producer import EventProducer
from platform.common.logging import get_logger
from platform.data_lifecycle.events import KAFKA_TOPIC, DataLifecycleEventType
from platform.data_lifecycle.repository import DataLifecycleRepository
from platform.notifications.dependencies import build_notifications_service
from platform.workspaces.dependencies import build_workspaces_service
from typing import Any
from uuid import UUID

LOGGER = get_logger(__name__)


class ExportReadyConsumer:
    def __init__(
        self,
        *,
        settings: PlatformSettings,
        redis_client: AsyncRedisClient,
        producer: EventProducer | None,
    ) -> None:
        self.settings = settings
        self.redis_client = redis_client
        self.producer = producer

    def register(self, manager: EventConsumerManager) -> None:
        manager.subscribe(
            KAFKA_TOPIC,
            f"{self.settings.KAFKA_CONSUMER_GROUP_ID}.notifications-export-ready",
            self.handle_event,
        )

    async def handle_event(self, envelope: EventEnvelope) -> None:
        if envelope.event_type != DataLifecycleEventType.export_completed.value:
            return
        payload: dict[str, Any] = envelope.payload or {}
        try:
            job_id = UUID(str(payload["job_id"]))
        except (KeyError, ValueError, TypeError):
            LOGGER.warning(
                "data_lifecycle.export_completed payload missing job_id",
                extra={"payload_keys": sorted(payload.keys())},
            )
            return

        async with database.AsyncSessionLocal() as session:
            repo = DataLifecycleRepository(session)
            job = await repo.get_export_job(job_id)
            if job is None:
                LOGGER.info(
                    "data_lifecycle.export_completed for unknown job",
                    extra={"job_id": str(job_id)},
                )
                return
            user_id = job.requested_by_user_id
            if user_id is None:
                LOGGER.info(
                    "data_lifecycle.export_completed has no requester; skipping",
                    extra={"job_id": str(job_id)},
                )
                return

            workspaces_service = build_workspaces_service(
                session=session,
                settings=self.settings,
                producer=self.producer,
                accounts_service=None,
            )
            service = build_notifications_service(
                session=session,
                settings=self.settings,
                redis_client=self.redis_client,
                producer=self.producer,
                workspaces_service=workspaces_service,
            )
            try:
                await service.process_export_ready(
                    user_id=UUID(str(user_id)),
                    job_id=job_id,
                    output_size_bytes=int(job.output_size_bytes or 0),
                    expires_at=job.output_expires_at,
                )
                await session.commit()
            except Exception:  # pragma: no cover - defensive
                await session.rollback()
                LOGGER.exception(
                    "Failed to dispatch export-ready notification",
                    extra={"job_id": str(job_id)},
                )
