from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from platform.common import database
from platform.common.config import PlatformSettings
from platform.registry.index_worker import RegistryIndexWorker

import pytest

from tests.registry_support import AsyncOpenSearchStub, SessionStub, build_profile, build_revision


@pytest.mark.asyncio
async def test_registry_index_worker_start_and_stop_are_safe(monkeypatch) -> None:
    worker = RegistryIndexWorker(settings=PlatformSettings(), opensearch=AsyncOpenSearchStub())

    async def _run_once() -> None:
        await asyncio.sleep(0)

    monkeypatch.setattr(worker, "run", _run_once)

    await worker.start()
    first_task = worker._task
    await worker.start()
    await worker.stop()

    assert first_task is not None
    assert worker._task is None


@pytest.mark.asyncio
async def test_retry_index_batch_updates_reindex_state_and_logs_failures(monkeypatch) -> None:
    profile = build_profile(needs_reindex=True)
    revision = build_revision(agent_profile=profile)
    session = SessionStub(get_results={(type(profile), profile.id): profile})
    opensearch = AsyncOpenSearchStub()
    worker = RegistryIndexWorker(settings=PlatformSettings(), opensearch=opensearch)

    class RepoStub:
        def __init__(self, session, opensearch) -> None:
            del session, opensearch

        async def get_agents_needing_reindex(self, limit: int = 100):
            del limit
            return [profile]

        async def get_latest_revision(self, agent_profile_id):
            assert agent_profile_id == profile.id
            return revision

        async def set_needs_reindex(self, agent_profile_id, needs_reindex):
            assert agent_profile_id == profile.id
            profile.needs_reindex = needs_reindex

    @asynccontextmanager
    async def _session_factory():
        yield session

    monkeypatch.setattr(database, "AsyncSessionLocal", _session_factory)
    monkeypatch.setattr("platform.registry.index_worker.RegistryRepository", RepoStub)

    await worker._retry_index_batch()

    assert opensearch.indexed
    assert profile.needs_reindex is False
    assert session.commit_calls == 1

    failing_worker = RegistryIndexWorker(
        settings=PlatformSettings(),
        opensearch=AsyncOpenSearchStub(fail_index=RuntimeError("boom")),
    )
    await failing_worker._retry_index_batch()
    assert session.rollback_calls == 1


@pytest.mark.asyncio
async def test_registry_index_worker_run_handles_timeout_and_stop_event(monkeypatch) -> None:
    worker = RegistryIndexWorker(settings=PlatformSettings(), opensearch=AsyncOpenSearchStub())
    calls: list[str] = []

    async def _retry() -> None:
        calls.append("retry")

    async def _wait_for(awaitable, **kwargs):
        del kwargs
        awaitable.close()
        worker._stop_event.set()
        raise TimeoutError

    monkeypatch.setattr(worker, "_retry_index_batch", _retry)
    monkeypatch.setattr("platform.registry.index_worker.asyncio.wait_for", _wait_for)

    await worker.run()

    assert calls == ["retry"]
