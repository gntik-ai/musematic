from __future__ import annotations

from platform.agentops.proficiency.scheduler import ProficiencyRecomputerTask
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from tests.agentops_support import build_proficiency_assessment


class _RepositoryStub:
    def __init__(self, latest=None) -> None:
        self.latest = latest

    async def get_latest_proficiency_assessment(self, agent_fqn: str, workspace_id: UUID):
        del agent_fqn, workspace_id
        return self.latest


class _ProficiencyServiceStub:
    def __init__(self, latest=None) -> None:
        self.repository = _RepositoryStub(latest)
        self.calls: list[tuple[str, UUID, str]] = []

    async def compute_for_agent(self, agent_fqn: str, workspace_id: UUID, *, trigger: str):
        self.calls.append((agent_fqn, workspace_id, trigger))
        return SimpleNamespace(level="competent")


class _RegistryStub:
    def __init__(self, items) -> None:
        self.items = list(items)

    async def list_active_agents(self, workspace_id: UUID | None):
        del workspace_id
        return list(self.items)


class _GovernancePublisherStub:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def record(self, event_type: str, agent_fqn: str, workspace_id: UUID, payload, **kwargs):
        self.events.append(
            {
                "event_type": event_type,
                "agent_fqn": agent_fqn,
                "workspace_id": workspace_id,
                "payload": payload,
                **kwargs,
            }
        )


@pytest.mark.asyncio
async def test_proficiency_recomputer_returns_empty_without_registry_support() -> None:
    task = ProficiencyRecomputerTask(
        proficiency_service=_ProficiencyServiceStub(),  # type: ignore[arg-type]
        registry_service=object(),
        governance_publisher=None,
    )

    assert await task.run() == []


@pytest.mark.asyncio
async def test_proficiency_recomputer_computes_all_agents_and_emits_previous_level() -> None:
    workspace_id = uuid4()
    latest = build_proficiency_assessment(workspace_id=workspace_id, level="advanced")
    service = _ProficiencyServiceStub(latest)
    publisher = _GovernancePublisherStub()
    task = ProficiencyRecomputerTask(
        proficiency_service=service,  # type: ignore[arg-type]
        registry_service=_RegistryStub(
            [{"agent_fqn": "finance:agent", "workspace_id": str(workspace_id)}]
        ),
        governance_publisher=publisher,  # type: ignore[arg-type]
    )

    items = await task.run()

    assert items == [
        {"agent_fqn": "finance:agent", "workspace_id": workspace_id, "level": "competent"}
    ]
    assert service.calls == [("finance:agent", workspace_id, "scheduled")]
    assert publisher.events[0]["payload"] == {
        "level": "competent",
        "previous_level": "advanced",
    }
