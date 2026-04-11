from __future__ import annotations

from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.context_engineering.adapters import build_default_adapters
from platform.context_engineering.compactor import ContextCompactor
from platform.context_engineering.models import ContextSourceType
from platform.context_engineering.privacy_filter import PrivacyFilter
from platform.context_engineering.quality_scorer import QualityScorer
from platform.context_engineering.schemas import AbTestCreate
from platform.context_engineering.service import ContextEngineeringService
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.analytics_support import ClickHouseClientStub
from tests.context_engineering_support import (
    EventProducerStub,
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
    return ContextEngineeringService(
        repository=repo,
        adapters=build_default_adapters(
            registry_service=RegistryLookupStub(
                agent=SimpleNamespace(
                    purpose="Do work",
                    approach="Be deterministic",
                    role_types=["executor"],
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            ),
            interactions_service=InteractionsServiceStub(
                history=[{"id": "c1", "content": "payment failed"}]
            ),
            workspaces_service=workspaces,
        ),
        quality_scorer=QualityScorer(),
        compactor=ContextCompactor(),
        privacy_filter=PrivacyFilter(policies_service=PoliciesServiceStub()),
        object_storage=ObjectStorageStub(),
        clickhouse_client=ClickHouseClientStub(),  # type: ignore[arg-type]
        settings=PlatformSettings(),
        event_producer=EventProducerStub(),
        workspaces_service=workspaces,
    ), repo


@pytest.mark.asyncio
async def test_ab_test_metrics_update_and_completion() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service, repo = _service(workspace_id)
    control = await service.create_profile(
        workspace_id,
        build_profile_create(name="control"),
        actor_id,
    )
    variant = await service.create_profile(
        workspace_id,
        build_profile_create(
            name="variant",
            source_config=[
                {
                    "source_type": ContextSourceType.system_instructions.value,
                    "priority": 100,
                    "enabled": True,
                    "max_elements": 1,
                },
                {
                    "source_type": ContextSourceType.conversation_history.value,
                    "priority": 60,
                    "enabled": True,
                    "max_elements": 1,
                },
            ],
        ),
        actor_id,
    )
    await service.create_ab_test(
        workspace_id,
        AbTestCreate(
            name="exp",
            control_profile_id=control.id,
            variant_profile_id=variant.id,
            target_agent_fqn="finance:agent",
        ),
        actor_id,
    )
    for _ in range(40):
        await service.assemble_context(
            execution_id=uuid4(),
            step_id=uuid4(),
            agent_fqn="finance:agent",
            workspace_id=workspace_id,
            task_brief="payment retry",
        )

    ab_test = next(iter(repo.ab_tests.values()))
    assert ab_test.control_assembly_count + ab_test.variant_assembly_count == 40
    assert ab_test.control_assembly_count > 0
    assert ab_test.variant_assembly_count > 0

    ended = await service.end_ab_test(workspace_id, ab_test.id, actor_id)

    assert ended.status.value == "completed"
