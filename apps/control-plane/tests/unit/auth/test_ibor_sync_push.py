from __future__ import annotations

from platform.auth.ibor_sync import IBORSyncService
from platform.auth.models import IBORSourceType, IBORSyncMode, IBORSyncRunStatus
from platform.registry.models import LifecycleStatus
from uuid import uuid4

import pytest
from tests.auth_ibor_support import (
    FakeDB,
    InMemoryAccountsRepository,
    InMemoryIBORRepository,
    SCIMCollector,
)
from tests.auth_support import FakeAsyncRedisClient, RecordingProducer
from tests.registry_support import build_namespace, build_profile


async def _push_connector(repository: InMemoryIBORRepository):
    return await repository.create_connector(
        name="corp-scim",
        source_type=IBORSourceType.scim,
        sync_mode=IBORSyncMode.push,
        cadence_seconds=86400,
        credential_ref="corp-scim-creds",
        role_mapping_policy=[],
        enabled=True,
        created_by=uuid4(),
    )


def _service(repository: InMemoryIBORRepository, collector: SCIMCollector) -> IBORSyncService:
    return IBORSyncService(
        repository=repository,
        accounts_repository=InMemoryAccountsRepository(),
        redis_client=FakeAsyncRedisClient(),
        settings=type("Settings", (), {})(),
        producer=RecordingProducer(),
        credential_resolver=lambda _ref: {"collector": collector},
    )


@pytest.mark.asyncio
async def test_push_sync_exports_only_operational_agents() -> None:
    workspace_id = uuid4()
    namespace = build_namespace(workspace_id=workspace_id, name="finance")
    repository = InMemoryIBORRepository(
        db=FakeDB(
            agents=[
                build_profile(
                    namespace=namespace, local_name="pub", status=LifecycleStatus.published
                ),
                build_profile(
                    namespace=namespace, local_name="disabled", status=LifecycleStatus.disabled
                ),
                build_profile(
                    namespace=namespace, local_name="deprecated", status=LifecycleStatus.deprecated
                ),
                build_profile(
                    namespace=namespace, local_name="draft", status=LifecycleStatus.draft
                ),
            ]
        )
    )
    connector = await _push_connector(repository)
    collector = SCIMCollector()
    service = _service(repository, collector)

    result = await service.run_sync(connector.id, triggered_by=uuid4())

    assert result.status is IBORSyncRunStatus.succeeded
    assert len(collector.calls) == 3
    assert {call["userName"] for call in collector.calls} == {
        "finance:pub",
        "finance:disabled",
        "finance:deprecated",
    }
    assert all(call["active"] is True for call in collector.calls)


@pytest.mark.asyncio
async def test_push_sync_marks_decommissioned_agents_inactive() -> None:
    workspace_id = uuid4()
    namespace = build_namespace(workspace_id=workspace_id, name="finance")
    decommissioned = build_profile(
        namespace=namespace,
        local_name="retired",
        status=LifecycleStatus.decommissioned,
    )
    repository = InMemoryIBORRepository(
        db=FakeDB(
            agents=[
                build_profile(
                    namespace=namespace, local_name="active", status=LifecycleStatus.published
                ),
                decommissioned,
            ]
        )
    )
    connector = await _push_connector(repository)
    collector = SCIMCollector()
    service = _service(repository, collector)

    result = await service.run_sync(connector.id, triggered_by=uuid4())

    retired_call = next(call for call in collector.calls if call["userName"] == decommissioned.fqn)
    assert result.status is IBORSyncRunStatus.succeeded
    assert retired_call["active"] is False
