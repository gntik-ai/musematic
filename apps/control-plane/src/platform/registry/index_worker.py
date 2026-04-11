from __future__ import annotations

import asyncio
import logging
from platform.common import database
from platform.common.clients.opensearch import AsyncOpenSearchClient
from platform.common.config import PlatformSettings
from platform.registry.repository import RegistryRepository
from platform.registry.service import build_search_document

LOGGER = logging.getLogger(__name__)


class RegistryIndexWorker:
    def __init__(
        self,
        *,
        settings: PlatformSettings,
        opensearch: AsyncOpenSearchClient,
    ) -> None:
        self.settings = settings
        self.opensearch = opensearch
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def run(self) -> None:
        poll_interval = self.settings.registry.reindex_poll_interval_seconds
        while not self._stop_event.is_set():
            try:
                await self._retry_index_batch()
            except Exception as exc:  # pragma: no cover - defensive logging
                LOGGER.warning("Registry index worker iteration failed: %s", exc)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=poll_interval)
            except TimeoutError:
                continue

    async def _retry_index_batch(self) -> None:
        async with database.AsyncSessionLocal() as session:
            repository = RegistryRepository(session, self.opensearch)
            profiles = await repository.get_agents_needing_reindex(limit=100)
            for profile in profiles:
                try:
                    revision = await repository.get_latest_revision(profile.id)
                    await self.opensearch.index_document(
                        self.settings.registry.search_index,
                        build_search_document(profile, revision),
                        document_id=str(profile.id),
                        refresh=False,
                    )
                    await repository.set_needs_reindex(profile.id, False)
                    await session.commit()
                except Exception as exc:
                    await session.rollback()
                    LOGGER.warning("Failed to re-index registry agent %s: %s", profile.id, exc)
