"""ExportJobWorker — Kafka consumer that drives export job execution.

Subscribes to ``data_lifecycle.events`` and dispatches every event of
type ``data_lifecycle.export.requested`` to the appropriate export
service method (workspace today; tenant once US3 lands).

Per-job dispatch is idempotent via the Redis lease acquired inside
``ExportService.run_workspace_export``. Worker rebalances are safe.
"""

from __future__ import annotations

import os
import socket
from platform.common.events.consumer import EventConsumerManager
from platform.common.events.envelope import EventEnvelope
from platform.common.logging import get_logger
from platform.data_lifecycle.events import (
    KAFKA_TOPIC,
    DataLifecycleEventType,
)
from platform.data_lifecycle.models import DataExportJob, ScopeType
from platform.data_lifecycle.repository import DataLifecycleRepository
from platform.data_lifecycle.services.export_service import ExportService
from typing import Any
from uuid import UUID

LOGGER = get_logger(__name__)


class ExportJobWorker:
    """Consumes ``data_lifecycle.export.requested`` and runs the job."""

    def __init__(
        self,
        *,
        consumer_group_id: str,
        session_factory: Any,
        export_service_factory: Any,
    ) -> None:
        """Wire the worker.

        ``session_factory`` is a callable that returns a context manager
        yielding an :class:`AsyncSession`. ``export_service_factory``
        receives that session and returns a configured
        :class:`ExportService`. The two-callable shape lets tests inject
        in-memory fakes.
        """

        self._consumer_group_id = consumer_group_id
        self._session_factory = session_factory
        self._export_service_factory = export_service_factory
        self._worker_id = self._derive_worker_id()

    def register(self, manager: EventConsumerManager) -> None:
        manager.subscribe(
            KAFKA_TOPIC,
            f"{self._consumer_group_id}.data-lifecycle-exports",
            self.handle_event,
        )

    async def handle_event(self, envelope: EventEnvelope) -> None:
        if envelope.event_type != DataLifecycleEventType.export_requested.value:
            return
        payload = envelope.payload or {}
        try:
            job_id = UUID(str(payload["job_id"]))
        except (KeyError, ValueError):
            LOGGER.warning(
                "data_lifecycle.export_worker_invalid_payload",
                event_type=envelope.event_type,
            )
            return
        await self._run(job_id=job_id, correlation_ctx=envelope.correlation_context)

    async def _run(self, *, job_id: UUID, correlation_ctx: Any) -> None:
        async with self._session_factory() as session:
            repo = DataLifecycleRepository(session)
            job: DataExportJob | None = await repo.get_export_job(job_id)
            if job is None:
                LOGGER.warning(
                    "data_lifecycle.export_worker_job_missing",
                    job_id=str(job_id),
                )
                return
            if job.status not in {"pending", "processing"}:
                LOGGER.info(
                    "data_lifecycle.export_worker_skip_finalized",
                    job_id=str(job_id),
                    status=job.status,
                )
                return
            service: ExportService = self._export_service_factory(session=session)
            if job.scope_type == ScopeType.workspace.value:
                await service.run_workspace_export(
                    job=job,
                    worker_id=self._worker_id,
                    correlation_ctx=correlation_ctx,
                )
            elif job.scope_type == ScopeType.tenant.value:
                await service.run_tenant_export(
                    job=job,
                    worker_id=self._worker_id,
                    correlation_ctx=correlation_ctx,
                )
            else:
                LOGGER.info(
                    "data_lifecycle.export_worker_skip_unsupported_scope",
                    job_id=str(job_id),
                    scope_type=job.scope_type,
                )
            await session.commit()

    @staticmethod
    def _derive_worker_id() -> str:
        host = socket.gethostname()
        pid = os.getpid()
        return f"control-plane-{host}-{pid}"
