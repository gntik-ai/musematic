from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.common.exceptions import NotFoundError
from platform.context_engineering.compactor import ContextCompactor
from platform.context_engineering.privacy_filter import PrivacyFilter
from platform.context_engineering.quality_scorer import QualityScorer
from platform.context_engineering.service import ContextEngineeringService
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


def _service() -> ContextEngineeringService:
    return ContextEngineeringService(
        repository=SimpleNamespace(session=SimpleNamespace()),
        adapters={},
        quality_scorer=QualityScorer(),
        compactor=ContextCompactor(),
        privacy_filter=PrivacyFilter(policies_service=None),
        object_storage=SimpleNamespace(),
        clickhouse_client=SimpleNamespace(),
        settings=PlatformSettings(),
        event_producer=None,
        workspaces_service=None,
        registry_service=None,
    )


@pytest.mark.asyncio
async def test_correlation_orchestration_methods_delegate_and_handle_not_found(monkeypatch) -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service = _service()
    latest_response = SimpleNamespace(total=1, items=[SimpleNamespace(dimension="retrieval")])
    fleet_response = SimpleNamespace(total=1)
    correlation_service = SimpleNamespace(
        get_latest=AsyncMock(return_value=latest_response),
        query_fleet=AsyncMock(return_value=fleet_response),
    )
    recomputer = SimpleNamespace(
        enqueue_recompute=AsyncMock(return_value=[{"count": 1}]),
        run=AsyncMock(return_value=[{"count": 1}]),
    )
    monkeypatch.setattr(service, "_correlation_service", lambda: correlation_service)
    monkeypatch.setattr(service, "_correlation_recomputer", lambda: recomputer)

    latest = await service.get_latest_correlation(
        workspace_id,
        actor_id,
        agent_fqn="finance:agent",
        window_days=30,
        classification="strong_positive",
    )
    fleet = await service.query_fleet_correlations(
        workspace_id,
        actor_id,
        classification="strong_negative",
    )
    enqueued = await service.enqueue_correlation_recompute(
        workspace_id,
        actor_id,
        agent_fqn="finance:agent",
        window_days=14,
    )
    ran = await service.run_correlation_recompute(workspace_id=workspace_id)

    assert latest is latest_response
    assert fleet is fleet_response
    assert enqueued == {"enqueued": True, "estimated_completion_seconds": 30}
    assert ran == [{"count": 1}]

    correlation_service.get_latest = AsyncMock(return_value=SimpleNamespace(total=0, items=[]))
    with pytest.raises(NotFoundError):
        await service.get_latest_correlation(
            workspace_id,
            actor_id,
            agent_fqn="finance:agent",
        )
