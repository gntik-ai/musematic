from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.memory.consolidation_worker import ConsolidationWorker, SessionMemoryCleaner
from platform.memory.embedding_worker import EmbeddingWorker
from platform.memory.models import EmbeddingJobStatus, RetentionPolicy
from uuid import uuid4

import pytest

from tests.integration.memory_flow_support import build_memory_flow_stack
from tests.memory_support import (
    build_embedding_job,
    build_memory_entry,
    install_qdrant_models_stub,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_memory_consolidation_workers_process_embedding_promotion_and_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_qdrant_models_stub(monkeypatch)
    stack = build_memory_flow_stack()
    workspace_id = uuid4()

    async def _fake_embedding(*, api_url: str, model: str, content: str) -> list[float]:
        del api_url, model
        return [0.1, 0.2, float(len(content))]

    monkeypatch.setattr("platform.memory.embedding_worker.request_embedding", _fake_embedding)
    monkeypatch.setattr("platform.memory.write_gate.request_embedding", _fake_embedding)

    entry = build_memory_entry(workspace_id=workspace_id, content="Cluster memory one")
    stack.repo.memory_entries[entry.id] = entry
    job = build_embedding_job(memory_entry_id=entry.id)
    stack.repo.embedding_jobs[job.id] = job

    await EmbeddingWorker(
        repository=stack.repo,
        qdrant=stack.qdrant,
        settings=stack.service.settings,
    ).run()

    for content in ("Cluster memory one", "Cluster memory one!", "Cluster memory one?"):
        seeded = build_memory_entry(workspace_id=workspace_id, content=content)
        stack.repo.memory_entries[seeded.id] = seeded

    await ConsolidationWorker(
        repository=stack.repo,
        write_gate=stack.write_gate,
        settings=stack.service.settings,
        producer=stack.producer,
    ).run()

    expired = build_memory_entry(
        workspace_id=workspace_id,
        retention_policy=RetentionPolicy.session_only,
        ttl_expires_at=datetime.now(UTC) - timedelta(seconds=1),
        qdrant_point_id=uuid4(),
    )
    stack.repo.memory_entries[expired.id] = expired
    await SessionMemoryCleaner(repository=stack.repo, qdrant=stack.qdrant).run()

    assert stack.repo.embedding_jobs[job.id].status is EmbeddingJobStatus.completed
    assert any(
        item.provenance_consolidated_by is not None
        for item in stack.repo.memory_entries.values()
    )
    assert any(
        event["event_type"] == "memory.consolidation.completed"
        for event in stack.producer.events
    )
    assert expired.deleted_at is not None
