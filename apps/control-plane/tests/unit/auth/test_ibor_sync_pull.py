from __future__ import annotations

import asyncio
from platform.auth.exceptions import IBORSyncInProgressError
from platform.auth.ibor_sync import IBORSyncService
from platform.auth.models import IBORSourceType, IBORSyncMode, IBORSyncRunStatus
from uuid import uuid4

import pytest
from tests.auth_ibor_support import InMemoryAccountsRepository, InMemoryIBORRepository
from tests.auth_support import FakeAsyncRedisClient, RecordingProducer


async def _create_connector(
    repository: InMemoryIBORRepository,
    *,
    source_type: IBORSourceType = IBORSourceType.oidc,
):
    return await repository.create_connector(
        name=f"{source_type.value}-connector",
        source_type=source_type,
        sync_mode=IBORSyncMode.pull,
        cadence_seconds=3600,
        credential_ref=f"{source_type.value}-creds",
        role_mapping_policy=[
            {"directory_group": "Platform-Admins", "platform_role": "platform_admin"},
            {"directory_group": "Viewers", "platform_role": "viewer"},
        ],
        enabled=True,
        created_by=uuid4(),
    )


def _service(
    repository: InMemoryIBORRepository,
    *,
    accounts: InMemoryAccountsRepository | None = None,
    redis_client: FakeAsyncRedisClient | None = None,
    credential_resolver=None,
    producer: RecordingProducer | None = None,
) -> IBORSyncService:
    return IBORSyncService(
        repository=repository,
        accounts_repository=accounts,
        redis_client=redis_client or FakeAsyncRedisClient(),
        settings=type("Settings", (), {})(),
        producer=producer or RecordingProducer(),
        credential_resolver=credential_resolver,
    )


@pytest.mark.asyncio
async def test_pull_sync_imports_roles_and_revokes_them_when_membership_disappears() -> None:
    repository = InMemoryIBORRepository()
    accounts = InMemoryAccountsRepository()
    connector = await _create_connector(repository, source_type=IBORSourceType.oidc)
    users = [
        {
            "email": "alice@corp.com",
            "display_name": "Alice",
            "groups": ["Platform-Admins", "Viewers"],
        }
    ]
    service = _service(
        repository,
        accounts=accounts,
        credential_resolver=lambda _ref: {"users": users},
    )

    first = await service.run_sync(connector.id, triggered_by=uuid4())
    alice = await accounts.get_user_by_email("alice@corp.com")
    roles = await repository.list_user_roles(user_id=alice.id)

    assert first.status is IBORSyncRunStatus.succeeded
    assert first.counts["roles_added"] == 1
    assert {(role.role, role.source_connector_id) for role in roles} == {
        ("platform_admin", connector.id)
    }

    users[:] = [{"email": "alice@corp.com", "display_name": "Alice", "groups": []}]
    second = await service.run_sync(connector.id, triggered_by=uuid4())
    roles_after = await repository.list_user_roles(user_id=alice.id)

    assert second.status is IBORSyncRunStatus.succeeded
    assert second.counts["roles_revoked"] == 1
    assert roles_after == []


@pytest.mark.asyncio
@pytest.mark.parametrize("source_type", [IBORSourceType.oidc, IBORSourceType.scim])
async def test_pull_sync_reports_partial_success_and_uses_http_adapters(
    source_type: IBORSourceType,
) -> None:
    repository = InMemoryIBORRepository()
    accounts = InMemoryAccountsRepository()
    connector = await _create_connector(repository, source_type=source_type)
    service = _service(
        repository,
        accounts=accounts,
        credential_resolver=lambda _ref: {
            "users": [
                {
                    "email": "alice@corp.com",
                    "display_name": "Alice",
                    "groups": ["Platform-Admins"],
                },
                {
                    "display_name": "Broken",
                    "groups": ["Platform-Admins"],
                },
            ]
        },
    )

    result = await service.run_sync(connector.id, triggered_by=uuid4())

    assert result.status is IBORSyncRunStatus.partial_success
    assert result.counts["roles_added"] == 1
    assert result.counts["errors"] == 1
    assert result.error_details[0]["email"] == "unknown"


@pytest.mark.asyncio
async def test_trigger_sync_rejects_concurrent_runs() -> None:
    repository = InMemoryIBORRepository()
    connector = await _create_connector(repository, source_type=IBORSourceType.oidc)
    started = asyncio.Event()
    release = asyncio.Event()
    service = _service(
        repository,
        accounts=InMemoryAccountsRepository(),
        redis_client=FakeAsyncRedisClient(),
        credential_resolver=lambda _ref: {"users": []},
    )

    async def _slow_run_pull(_connector):
        started.set()
        await release.wait()
        return service._empty_counts(), []

    service._run_pull = _slow_run_pull  # type: ignore[method-assign]

    first_task = asyncio.create_task(service.run_sync(connector.id, triggered_by=uuid4()))
    await asyncio.wait_for(started.wait(), timeout=1)

    with pytest.raises(IBORSyncInProgressError):
        await service.run_sync(connector.id, triggered_by=uuid4())

    release.set()
    result = await first_task
    assert result.status is IBORSyncRunStatus.succeeded
