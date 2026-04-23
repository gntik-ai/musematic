from __future__ import annotations

from platform.context_engineering.correlation_scheduler import CorrelationRecomputerTask
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest


class _CorrelationServiceStub:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, str, int]] = []

    async def compute_for_agent(self, workspace_id: UUID, agent_fqn: str, *, window_days: int):
        self.calls.append((workspace_id, agent_fqn, window_days))
        return [SimpleNamespace(id=uuid4())]


class _RegistryStub:
    def __init__(self, items) -> None:
        self.items = list(items)

    async def list_active_agents(self, workspace_id: UUID | None):
        del workspace_id
        return list(self.items)


@pytest.mark.asyncio
async def test_correlation_recomputer_returns_empty_without_registry_support() -> None:
    task = CorrelationRecomputerTask(
        correlation_service=_CorrelationServiceStub(),  # type: ignore[arg-type]
        registry_service=object(),
        default_window_days=30,
    )

    assert await task.run() == []


@pytest.mark.asyncio
async def test_correlation_recomputer_runs_for_active_agents() -> None:
    workspace_id = uuid4()
    service = _CorrelationServiceStub()
    task = CorrelationRecomputerTask(
        correlation_service=service,  # type: ignore[arg-type]
        registry_service=_RegistryStub(
            [{"agent_fqn": "finance:agent", "workspace_id": str(workspace_id)}]
        ),
        default_window_days=30,
    )

    items = await task.run()

    assert items == [{"agent_fqn": "finance:agent", "workspace_id": workspace_id, "count": 1}]
    assert service.calls == [(workspace_id, "finance:agent", 30)]


@pytest.mark.asyncio
async def test_correlation_recomputer_enqueues_single_agent_override() -> None:
    workspace_id = uuid4()
    service = _CorrelationServiceStub()
    task = CorrelationRecomputerTask(
        correlation_service=service,  # type: ignore[arg-type]
        registry_service=_RegistryStub([]),
        default_window_days=30,
    )

    items = await task.enqueue_recompute(
        workspace_id,
        agent_fqn="finance:agent",
        window_days=14,
    )

    assert items == [{"agent_fqn": "finance:agent", "workspace_id": workspace_id, "count": 1}]
    assert service.calls == [(workspace_id, "finance:agent", 14)]



@pytest.mark.asyncio
async def test_correlation_recomputer_enqueues_workspace_scan_when_agent_is_omitted() -> None:
    workspace_id = uuid4()
    service = _CorrelationServiceStub()
    task = CorrelationRecomputerTask(
        correlation_service=service,  # type: ignore[arg-type]
        registry_service=_RegistryStub(
            [{"agent_fqn": "finance:agent", "workspace_id": str(workspace_id)}]
        ),
        default_window_days=30,
    )

    items = await task.enqueue_recompute(workspace_id)

    assert items == [{"agent_fqn": "finance:agent", "workspace_id": workspace_id, "count": 1}]
    assert service.calls == [(workspace_id, "finance:agent", 30)]
