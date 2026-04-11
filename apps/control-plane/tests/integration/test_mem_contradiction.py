from __future__ import annotations

from platform.memory.models import MemoryScope, RetentionPolicy
from platform.memory.schemas import ConflictResolution, MemoryWriteRequest
from uuid import uuid4

import pytest

from tests.integration.memory_flow_support import build_memory_flow_stack
from tests.memory_support import install_qdrant_models_stub

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_memory_contradiction_flow_creates_and_resolves_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_qdrant_models_stub(monkeypatch)
    stack = build_memory_flow_stack()
    workspace_id = uuid4()

    async def _fake_embedding(*, api_url: str, model: str, content: str) -> list[float]:
        del api_url, model, content
        return [0.1, 0.2, 0.3]

    monkeypatch.setattr("platform.memory.write_gate.request_embedding", _fake_embedding)

    first = await stack.service.write_memory(
        MemoryWriteRequest(
            content="ACME prefers invoice terms NET-30.",
            scope=MemoryScope.per_agent,
            namespace="finance",
            retention_policy=RetentionPolicy.permanent,
            tags=["customer"],
        ),
        "finance:writer",
        workspace_id,
    )
    stack.qdrant.search_results = [
        {
            "id": str(first.memory_entry_id),
            "score": 0.99,
            "payload": {"memory_entry_id": str(first.memory_entry_id)},
        }
    ]
    second = await stack.service.write_memory(
        MemoryWriteRequest(
            content="ACME rejects invoice terms and requires prepaid wire transfers.",
            scope=MemoryScope.per_agent,
            namespace="finance",
            retention_policy=RetentionPolicy.permanent,
            tags=["customer"],
        ),
        "finance:writer",
        workspace_id,
    )
    conflicts, total = await stack.service.list_conflicts(workspace_id, None, 1, 20)
    resolved = await stack.service.resolve_conflict(
        second.conflict_id,
        ConflictResolution(action="dismiss", resolution_notes="accepted override"),
        str(uuid4()),
        workspace_id,
    )

    assert second.contradiction_detected is True
    assert second.conflict_id is not None
    assert total == 1
    assert conflicts[0].id == second.conflict_id
    assert resolved.status.value == "dismissed"
