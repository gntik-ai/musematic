from __future__ import annotations

from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.context_engineering.adapters import build_default_adapters
from platform.context_engineering.compactor import ContextCompactor
from platform.context_engineering.models import ContextSourceType
from platform.context_engineering.privacy_filter import PrivacyFilter
from platform.context_engineering.quality_scorer import QualityScorer
from platform.context_engineering.schemas import ProfileAssignmentCreate
from platform.context_engineering.service import ContextEngineeringService
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.analytics_support import ClickHouseClientStub
from tests.context_engineering_support import (
    EventProducerStub,
    ExecutionServiceStub,
    InteractionsServiceStub,
    MemoryContextRepository,
    PoliciesServiceStub,
    RegistryLookupStub,
    WorkspaceRepoStub,
    WorkspacesServiceStub,
    build_profile_create,
)
from tests.registry_support import ObjectStorageStub


def _service(workspace_id):
    repo = MemoryContextRepository()
    producer = EventProducerStub()
    workspaces = WorkspacesServiceStub(
        workspace_ids=[workspace_id],
        repo=WorkspaceRepoStub(
            workspace=SimpleNamespace(
                id=workspace_id,
                name="Finance",
                description="Finance",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        ),
    )
    service = ContextEngineeringService(
        repository=repo,
        adapters=build_default_adapters(
            registry_service=RegistryLookupStub(
                agent=SimpleNamespace(
                    purpose="Resolve payment exceptions",
                    approach="Keep deterministic instructions",
                    role_types=["executor"],
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            ),
            interactions_service=InteractionsServiceStub(
                history=[
                    {
                        "id": "conv-1",
                        "content": " ".join(["retry"] * 24),
                        "token_count": 24,
                        "timestamp": datetime.now(UTC),
                    }
                ]
            ),
            execution_service=ExecutionServiceStub(
                tool_outputs=[
                    {
                        "id": "tool-1",
                        "content": " ".join(["connector"] * 120),
                        "token_count": 120,
                        "timestamp": datetime.now(UTC),
                    }
                ]
            ),
            workspaces_service=workspaces,
        ),
        quality_scorer=QualityScorer(),
        compactor=ContextCompactor(),
        privacy_filter=PrivacyFilter(policies_service=PoliciesServiceStub()),
        object_storage=ObjectStorageStub(),
        clickhouse_client=ClickHouseClientStub(),  # type: ignore[arg-type]
        settings=PlatformSettings(),
        event_producer=producer,
        workspaces_service=workspaces,
    )
    return service, repo, producer


@pytest.mark.asyncio
async def test_budget_enforcement_compacts_bundle_within_limit() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service, repo, _ = _service(workspace_id)
    profile = await service.create_profile(
        workspace_id,
        build_profile_create(
            source_config=[
                {
                    "source_type": ContextSourceType.system_instructions.value,
                    "priority": 100,
                    "enabled": True,
                    "max_elements": 1,
                },
                {
                    "source_type": ContextSourceType.conversation_history.value,
                    "priority": 80,
                    "enabled": True,
                    "max_elements": 1,
                },
                {
                    "source_type": ContextSourceType.tool_outputs.value,
                    "priority": 40,
                    "enabled": True,
                    "max_elements": 1,
                },
            ],
            budget_config={"max_tokens_step": 80, "max_sources": 3},
        ),
        actor_id,
    )
    await service.assign_profile(
        workspace_id,
        profile.id,
        ProfileAssignmentCreate(
            assignment_level="agent",
            agent_fqn="finance:agent",
        ),
        actor_id,
    )

    bundle = await service.assemble_context(
        execution_id=uuid4(),
        step_id=uuid4(),
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        task_brief="retry payment",
    )

    record = next(iter(repo.records.values()))
    assert bundle.token_count <= 80
    assert record.compaction_applied is True
    assert any(item.source_type.value == "system_instructions" for item in bundle.elements)


@pytest.mark.asyncio
async def test_budget_enforcement_marks_minimum_viable_overflow() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service, repo, producer = _service(workspace_id)
    profile = await service.create_profile(
        workspace_id,
        build_profile_create(budget_config={"max_tokens_step": 1, "max_sources": 2}),
        actor_id,
    )
    await service.assign_profile(
        workspace_id,
        profile.id,
        ProfileAssignmentCreate(
            assignment_level="agent",
            agent_fqn="finance:agent",
        ),
        actor_id,
    )

    bundle = await service.assemble_context(
        execution_id=uuid4(),
        step_id=uuid4(),
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
        task_brief="retry payment",
    )

    record = next(iter(repo.records.values()))
    assert "budget_exceeded_minimum" in bundle.flags
    assert "budget_exceeded_minimum" in record.flags
    assert any(
        item["event_type"] == "context_engineering.budget.exceeded_minimum"
        for item in producer.published
    )
