from __future__ import annotations

from datetime import UTC, datetime
from platform.memory.models import PatternStatus
from platform.memory.schemas import PatternNomination, PatternReview, TrajectoryRecordCreate
from uuid import uuid4

import pytest

from tests.integration.memory_flow_support import build_memory_flow_stack
from tests.memory_support import install_qdrant_models_stub

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_memory_trajectory_patterns_flow_promotes_and_rejects_patterns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_qdrant_models_stub(monkeypatch)
    stack = build_memory_flow_stack()
    workspace_id = uuid4()

    async def _fake_embedding(*, api_url: str, model: str, content: str) -> list[float]:
        del api_url, model, content
        return [0.4, 0.5, 0.6]

    monkeypatch.setattr("platform.memory.write_gate.request_embedding", _fake_embedding)

    trajectory = await stack.service.record_trajectory(
        TrajectoryRecordCreate(
            execution_id=uuid4(),
            agent_fqn="finance:writer",
            actions=[],
            tool_invocations=[],
            reasoning_snapshots=[],
            verdicts=[],
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        ),
        workspace_id,
    )
    pending = await stack.service.nominate_pattern(
        PatternNomination(
            trajectory_record_id=trajectory.id,
            content="Always validate payment terms before invoicing.",
            description="Reusable invoicing safeguard.",
            tags=["finance"],
        ),
        "finance:writer",
        workspace_id,
    )
    approved = await stack.service.review_pattern(
        pending.id,
        PatternReview(approved=True),
        str(uuid4()),
        workspace_id,
    )
    rejected_seed = await stack.service.nominate_pattern(
        PatternNomination(
            trajectory_record_id=trajectory.id,
            content="Discard this draft pattern.",
            description="Should not be promoted.",
            tags=["draft"],
        ),
        "finance:writer",
        workspace_id,
    )
    rejected = await stack.service.review_pattern(
        rejected_seed.id,
        PatternReview(approved=False, rejection_reason="insufficient evidence"),
        str(uuid4()),
        workspace_id,
    )
    approved_patterns, _ = await stack.service.list_patterns(
        workspace_id,
        PatternStatus.approved,
        1,
        20,
    )

    assert approved.memory_entry_id is not None
    assert approved.status is PatternStatus.approved
    assert rejected.status is PatternStatus.rejected
    assert [item.id for item in approved_patterns] == [approved.id]
