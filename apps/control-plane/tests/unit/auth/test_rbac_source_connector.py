from __future__ import annotations

from platform.accounts.models import SignupSource, UserStatus
from platform.auth.ibor_sync import IBORSyncService
from platform.auth.models import IBORSourceType, IBORSyncMode
from uuid import uuid4

import pytest
from tests.auth_ibor_support import InMemoryAccountsRepository, InMemoryIBORRepository
from tests.auth_support import FakeAsyncRedisClient, RecordingProducer


@pytest.mark.asyncio
async def test_manual_roles_are_preserved_while_connector_roles_are_revoked() -> None:
    repository = InMemoryIBORRepository()
    accounts = InMemoryAccountsRepository()
    connector = await repository.create_connector(
        name="oidc-source",
        source_type=IBORSourceType.oidc,
        sync_mode=IBORSyncMode.pull,
        cadence_seconds=3600,
        credential_ref="oidc-source-creds",
        role_mapping_policy=[
            {"directory_group": "Platform-Admins", "platform_role": "platform_admin"}
        ],
        enabled=True,
        created_by=uuid4(),
    )
    bob = await accounts.create_user(
        email="bob@corp.com",
        display_name="Bob",
        status=UserStatus.active,
        signup_source=SignupSource.self_registration,
    )
    await repository.assign_user_role(
        bob.id,
        "platform_admin",
        None,
        source_connector_id=None,
    )
    users = [
        {
            "email": "alice@corp.com",
            "display_name": "Alice",
            "groups": ["Platform-Admins"],
        }
    ]
    service = IBORSyncService(
        repository=repository,
        accounts_repository=accounts,
        redis_client=FakeAsyncRedisClient(),
        settings=type("Settings", (), {})(),
        producer=RecordingProducer(),
        credential_resolver=lambda _ref: {"users": users},
    )

    await service.run_sync(connector.id, triggered_by=uuid4())
    alice = await accounts.get_user_by_email("alice@corp.com")
    alice_roles = await repository.list_user_roles(user_id=alice.id)
    assert {(role.role, role.source_connector_id) for role in alice_roles} == {
        ("platform_admin", connector.id)
    }

    users[:] = []
    await service.run_sync(connector.id, triggered_by=uuid4())

    bob_roles = await repository.list_user_roles(user_id=bob.id)
    alice_roles_after = await repository.list_user_roles(user_id=alice.id)
    assert {(role.role, role.source_connector_id) for role in bob_roles} == {
        ("platform_admin", None)
    }
    assert alice_roles_after == []
