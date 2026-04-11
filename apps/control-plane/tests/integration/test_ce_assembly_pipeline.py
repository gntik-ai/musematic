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
    ConnectorsServiceStub,
    EventProducerStub,
    ExecutionServiceStub,
    InteractionsServiceStub,
    MemoryContextRepository,
    MemoryServiceStub,
    PoliciesServiceStub,
    RegistryLookupStub,
    WorkspaceRepoStub,
    WorkspacesServiceStub,
    build_profile_create,
)
from tests.registry_support import ObjectStorageStub


def _build_pipeline_service(workspace_id, goal_id):
    repository = MemoryContextRepository()
    clickhouse = ClickHouseClientStub()
    storage = ObjectStorageStub()
    producer = EventProducerStub()
    workspaces = WorkspacesServiceStub(
        workspace_ids=[workspace_id],
        repo=WorkspaceRepoStub(
            workspace=SimpleNamespace(
                id=workspace_id,
                name="Finance Ops",
                description="Payment and exception handling",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
            goal=SimpleNamespace(
                gid=goal_id,
                title="Reduce chargeback handling latency",
                description="Prefer deterministic context",
                status="open",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
        ),
    )
    service = ContextEngineeringService(
        repository=repository,
        adapters=build_default_adapters(
            registry_service=RegistryLookupStub(
                agent=SimpleNamespace(
                    purpose="Resolve payment exceptions",
                    approach="Use deterministic context assembly",
                    role_types=["executor"],
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            ),
            execution_service=ExecutionServiceStub(
                workflow_state={"id": "wf-1", "content": "Current workflow step is verification"},
                tool_outputs=[
                    {"id": "tool-1", "content": "Tool output confirms retryable failure"}
                ],
                reasoning_traces=[{"id": "reason-1", "content": "Reasoning trace prefers retry"}],
            ),
            interactions_service=InteractionsServiceStub(
                history=[{"id": "conv-1", "content": "Customer reported a failed payment"}]
            ),
            memory_service=MemoryServiceStub(
                items=[{"id": "mem-1", "content": "Previous retry succeeded", "score": 0.9}]
            ),
            connectors_service=ConnectorsServiceStub(
                payloads=[{"id": "conn-1", "content": "Connector payload: PSP timeout"}]
            ),
            workspaces_service=workspaces,
        ),
        quality_scorer=QualityScorer(),
        compactor=ContextCompactor(),
        privacy_filter=PrivacyFilter(
            policies_service=PoliciesServiceStub(
                policies=[
                    {
                        "policy_id": "policy-1",
                        "allowed_agent_fqns": ["finance:agent"],
                        "allowed_classifications": ["public", "internal"],
                    }
                ]
            )
        ),
        object_storage=storage,
        clickhouse_client=clickhouse,  # type: ignore[arg-type]
        settings=PlatformSettings(),
        event_producer=producer,
        workspaces_service=workspaces,
    )
    return service, repository, clickhouse, storage, producer


@pytest.mark.asyncio
async def test_context_engineering_full_assembly_pipeline() -> None:
    workspace_id = uuid4()
    goal_id = uuid4()
    actor_id = uuid4()
    service, repository, clickhouse, storage, producer = _build_pipeline_service(
        workspace_id, goal_id
    )
    payload = build_profile_create(
        source_config=[
            {
                "source_type": item.value,
                "priority": 100 - index * 5,
                "enabled": True,
                "max_elements": 5,
            }
            for index, item in enumerate(ContextSourceType)
        ],
        budget_config={"max_tokens_step": 512, "max_sources": 9},
    )
    profile = await service.create_profile(workspace_id, payload, actor_id)
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
        goal_id=goal_id,
        task_brief="resolve payment exception quickly",
    )

    record = next(iter(repository.records.values()))
    assert bundle.elements
    assert bundle.quality_score > 0
    assert record.bundle_storage_key is not None
    assert any(
        item["event_type"] == "context_engineering.assembly.completed"
        for item in producer.published
    )
    assert clickhouse.insert_calls
    assert storage.objects
    assert any("goal:" in provenance["origin"] for provenance in record.provenance_chain)
