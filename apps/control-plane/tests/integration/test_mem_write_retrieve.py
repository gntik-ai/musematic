from __future__ import annotations

from platform.memory.models import MemoryScope, RetentionPolicy
from platform.memory.schemas import MemoryWriteRequest, RetrievalQuery
from uuid import uuid4

import pytest

from tests.integration.memory_flow_support import build_memory_flow_stack
from tests.memory_support import install_qdrant_models_stub

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_memory_write_retrieve_flow_round_trips_scoped_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_qdrant_models_stub(monkeypatch)
    stack = build_memory_flow_stack()
    workspace_id = uuid4()

    async def _fake_embedding(*, api_url: str, model: str, content: str) -> list[float]:
        del api_url, model
        return [0.1, 0.2, float(len(content))]

    monkeypatch.setattr("platform.memory.write_gate.request_embedding", _fake_embedding)
    monkeypatch.setattr("platform.memory.retrieval_coordinator.request_embedding", _fake_embedding)

    written = await stack.service.write_memory(
        MemoryWriteRequest(
            content="ACME prefers payment terms NET-30.",
            scope=MemoryScope.per_agent,
            namespace="finance",
            source_authority=0.9,
            retention_policy=RetentionPolicy.permanent,
            tags=["customer"],
        ),
        "finance:writer",
        workspace_id,
    )
    stack.qdrant.search_results = [
        {
            "id": str(written.memory_entry_id),
            "score": 0.95,
            "payload": {"memory_entry_id": str(written.memory_entry_id)},
        }
    ]
    listed, total = await stack.service.list_memory_entries(
        workspace_id,
        "finance:writer",
        None,
        1,
        20,
    )
    retrieved = await stack.service.retrieve(
        RetrievalQuery(query_text="payment terms", include_contradictions=False),
        "finance:writer",
        workspace_id,
    )

    assert written.contradiction_detected is False
    assert total == 1
    assert listed[0].id == written.memory_entry_id
    assert retrieved.results[0].memory_entry_id == written.memory_entry_id
    assert {"vector", "keyword"}.issubset(retrieved.results[0].sources_contributed)
