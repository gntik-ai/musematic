from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from platform.auth.exceptions import (
    IBORConnectorNotFoundError,
    IBORCredentialResolutionError,
    IBORSyncInProgressError,
)
from platform.auth.ibor_sync import IBORSyncService
from platform.auth.models import IBORSourceType, IBORSyncMode, IBORSyncRunStatus, UserRole
from platform.registry.models import LifecycleStatus
from types import SimpleNamespace
from typing import ClassVar
from uuid import uuid4

import httpx
import pytest
from tests.auth_ibor_support import InMemoryAccountsRepository, InMemoryIBORRepository
from tests.auth_support import FakeAsyncRedisClient, RecordingProducer


async def _create_connector(
    repository: InMemoryIBORRepository,
    *,
    source_type: IBORSourceType = IBORSourceType.oidc,
    sync_mode: IBORSyncMode = IBORSyncMode.pull,
    credential_ref: str = "helper-creds",
):
    return await repository.create_connector(
        name=f"{source_type.value}-{sync_mode.value}",
        source_type=source_type,
        sync_mode=sync_mode,
        cadence_seconds=300,
        credential_ref=credential_ref,
        role_mapping_policy=[
            {"directory_group": "Platform-Admins", "platform_role": "platform_admin"}
        ],
        enabled=True,
        created_by=uuid4(),
    )


def _service(
    repository: InMemoryIBORRepository,
    *,
    credential_resolver=None,
    redis_client: FakeAsyncRedisClient | None = None,
    session_factory=None,
) -> IBORSyncService:
    return IBORSyncService(
        repository=repository,
        accounts_repository=InMemoryAccountsRepository(),
        redis_client=redis_client or FakeAsyncRedisClient(),
        settings=SimpleNamespace(),
        producer=RecordingProducer(),
        session_factory=session_factory,
        credential_resolver=credential_resolver,
    )


class _HTTPXResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class _HTTPXClient:
    calls: ClassVar[list[tuple[str, str, dict[str, str], object]]] = []
    get_payload: ClassVar[dict[str, list[dict[str, object]]]] = {
        "items": [{"email": "api@corp.com", "groups": ["Platform-Admins"]}]
    }

    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb

    async def get(self, url: str, headers: dict[str, str]):
        type(self).calls.append(("GET", url, dict(headers), None))
        return _HTTPXResponse(type(self).get_payload)

    async def post(self, url: str, json: dict[str, object], headers: dict[str, str]):
        type(self).calls.append(("POST", url, dict(headers), dict(json)))
        return _HTTPXResponse({"status": "ok"})


@pytest.mark.asyncio
async def test_trigger_sync_background_paths_and_continue_sync_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = InMemoryIBORRepository()
    connector = await _create_connector(repository, credential_ref='{"users": []}')
    service = _service(repository)

    triggered = await service.trigger_sync(connector.id, triggered_by=uuid4())
    await asyncio.gather(*tuple(service._background_tasks))

    assert triggered.status is IBORSyncRunStatus.running
    assert repository.sync_runs[triggered.run_id].status is IBORSyncRunStatus.succeeded

    session_branch_service = _service(repository, session_factory=object())
    called: dict[str, object] = {}

    async def _fake_run_background(connector_id, run_id, *, triggered_by, lock_token):
        called.update(
            {
                "connector_id": connector_id,
                "run_id": run_id,
                "triggered_by": triggered_by,
                "lock_token": lock_token,
            }
        )

    monkeypatch.setattr(session_branch_service, "_run_background", _fake_run_background)
    triggered_session = await session_branch_service.trigger_sync(
        connector.id, triggered_by=uuid4()
    )
    await asyncio.gather(*tuple(session_branch_service._background_tasks))

    assert called["connector_id"] == connector.id
    assert called["run_id"] == triggered_session.run_id

    failed_run = await repository.create_sync_run(
        connector_id=connector.id,
        mode=IBORSyncMode.pull,
        status=IBORSyncRunStatus.running,
        triggered_by=None,
    )

    async def _explode(_connector):
        raise RuntimeError("boom")

    monkeypatch.setattr(service, "_run_pull", _explode)
    failed = await service._continue_sync(
        connector.id,
        failed_run.id,
        triggered_by=None,
        lock_token="token",
    )

    with pytest.raises(IBORConnectorNotFoundError):
        await service._continue_sync(connector.id, uuid4(), triggered_by=None, lock_token="token")

    assert failed.status is IBORSyncRunStatus.failed
    assert failed.counts["errors"] == 1
    assert failed.error_details[0]["error"] == "boom"


@pytest.mark.asyncio
async def test_sync_helpers_cover_credentials_adapters_and_lock_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = InMemoryIBORRepository()
    redis_client = FakeAsyncRedisClient()
    connector = await _create_connector(repository, credential_ref=json.dumps({"token": "inline"}))
    service = _service(repository, redis_client=redis_client)

    inline = await service._resolve_credential(connector)
    monkeypatch.setenv(service._credential_env_key("env-creds"), json.dumps({"token": "env"}))
    env_connector = await _create_connector(repository, credential_ref="env-creds")
    env_value = await service._resolve_credential(env_connector)

    connector.credential_ref = "missing-creds"
    with pytest.raises(IBORCredentialResolutionError):
        await service._resolve_credential(connector)

    headers = service._credential_headers({"headers": {"X-Test": "1"}, "token": "secret"})
    normalized_payload = service._normalize_directory_payload(
        {"Resources": [{"userName": "alice@corp.com", "groups": [{"value": "Admins"}]}]}
    )
    normalized_users = service._normalize_directory_users(
        [
            "bob@corp.com",
            {"mail": "carol@corp.com", "memberOf": ["Ops"]},
            object(),
        ]
    )
    normalized_groups = service._normalize_groups(["Direct", {"display": "Mapped"}, object()])

    first_lock = await service._acquire_lock(connector.id, 30)
    second_lock = await service._acquire_lock(connector.id, 30)
    await service._release_lock(connector.id, first_lock.token or "")
    third_lock = await service._acquire_lock(connector.id, 30)

    monkeypatch.setattr(httpx, "AsyncClient", _HTTPXClient)
    _HTTPXClient.calls.clear()

    oidc_connector = await _create_connector(
        repository, source_type=IBORSourceType.oidc, credential_ref="oidc"
    )
    scim_connector = await _create_connector(
        repository, source_type=IBORSourceType.scim, credential_ref="scim"
    )
    ldap_connector = await _create_connector(
        repository, source_type=IBORSourceType.ldap, credential_ref="ldap"
    )
    push_connector = await _create_connector(
        repository,
        source_type=IBORSourceType.scim,
        sync_mode=IBORSyncMode.push,
        credential_ref="push",
    )

    ldap_module = SimpleNamespace(
        ALL=object(),
        Server=lambda host, get_info=None: SimpleNamespace(host=host, get_info=get_info),
    )

    class _Connection:
        def __init__(self, server, user, password, auto_bind):
            self.server = server
            self.user = user
            self.password = password
            self.auto_bind = auto_bind
            self.entries = [
                SimpleNamespace(
                    entry_attributes_as_dict={
                        "mail": "ldap@corp.com",
                        "displayName": "LDAP User",
                        "memberOf": ["Platform-Admins"],
                    }
                )
            ]

        def search(self, base_dn, search_filter, attributes):
            self.base_dn = base_dn
            self.search_filter = search_filter
            self.attributes = attributes

    ldap_module.Connection = _Connection
    monkeypatch.setitem(sys.modules, "ldap3", ldap_module)

    helper_service = _service(
        repository,
        credential_resolver=lambda ref: {
            "oidc": {"users_url": "https://oidc.example.test/users", "token": "oidc-token"},
            "scim": {"scim_endpoint": "https://scim.example.test", "token": "scim-token"},
            "push": {"scim_endpoint": "https://push.example.test", "token": "push-token"},
            "ldap": {
                "server": "ldaps://ldap.example.test",
                "bind_dn": "cn=reader",
                "password": "secret",
                "base_dn": "dc=example,dc=test",
                "search_filter": "(objectClass=person)",
                "attributes": ["mail", "displayName", "memberOf"],
            },
        }[ref],
    )
    repository.db.agents = [
        SimpleNamespace(
            id=uuid4(),
            fqn="finance:sync-agent",
            display_name="Sync Agent",
            status=SimpleNamespace(__str__=lambda self: "published"),
        )
    ]
    repository.db.agents[0].status = type("Status", (), {"__str__": lambda self: "published"})()
    repository.db.agents[0].status = __import__(
        "platform.registry.models", fromlist=["LifecycleStatus"]
    ).LifecycleStatus.published

    oidc_users = await helper_service._pull_oidc(oidc_connector)
    scim_users = await helper_service._pull_scim(scim_connector)
    ldap_users = await helper_service._pull_ldap(ldap_connector)
    push_counts, push_errors = await helper_service._push_scim(push_connector)

    assert inline == {"token": "inline"}
    assert env_value == {"token": "env"}
    assert headers["Authorization"] == "Bearer secret"
    assert headers["X-Test"] == "1"
    assert normalized_payload[0]["email"] == "alice@corp.com"
    assert normalized_users[0]["display_name"] == "bob"
    assert normalized_users[1]["email"] == "carol@corp.com"
    assert normalized_groups == {"Direct", "Mapped"}
    assert first_lock.success is True
    assert first_lock.token is not None
    assert second_lock.success is False
    assert third_lock.success is True
    assert oidc_users[0]["email"] == "api@corp.com"
    assert scim_users[0]["groups"] == ["Platform-Admins"]
    assert ldap_users[0]["email"] == "ldap@corp.com"
    assert push_counts["users_updated"] == 1
    assert push_errors == []
    assert any(call[0] == "GET" and call[1].endswith("/Users") for call in _HTTPXClient.calls)
    assert any(call[0] == "POST" and call[1].endswith("/Users") for call in _HTTPXClient.calls)


class _CommitRollbackSession:
    def __init__(self) -> None:
        self.commit_calls = 0
        self.rollback_calls = 0

    async def commit(self) -> None:
        self.commit_calls += 1

    async def rollback(self) -> None:
        self.rollback_calls += 1


class _SessionFactory:
    def __init__(self, session: _CommitRollbackSession) -> None:
        self.session = session

    def __call__(self):
        session = self.session

        class _ContextManager:
            async def __aenter__(self):
                return session

            async def __aexit__(self, exc_type, exc, tb) -> None:
                del exc_type, exc, tb

        return _ContextManager()


class _ExplicitLockRedisClient(FakeAsyncRedisClient):
    def __init__(self, *, success: bool = True, token: str | None = 'lock-token') -> None:
        super().__init__()
        self.success = success
        self.token = token
        self.acquire_calls: list[tuple[str, str, int]] = []
        self.release_calls: list[tuple[str, str, str]] = []

    async def acquire_lock(self, scope: str, key: str, ttl_seconds: int):
        self.acquire_calls.append((scope, key, ttl_seconds))
        return SimpleNamespace(success=self.success, token=self.token)

    async def release_lock(self, scope: str, key: str, token: str) -> None:
        self.release_calls.append((scope, key, token))


class _SyncCollector:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def post_user(self, payload: dict[str, object]) -> None:
        self.calls.append(dict(payload))


class _BrokenCollector:
    def post_user(self, payload: dict[str, object]) -> None:
        del payload
        raise RuntimeError('collector boom')


@pytest.mark.asyncio
async def test_run_background_commits_and_rolls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = InMemoryIBORRepository()
    connector = await _create_connector(repository, credential_ref='{"users": []}')
    run = await repository.create_sync_run(
        connector_id=connector.id,
        mode=IBORSyncMode.pull,
        status=IBORSyncRunStatus.running,
        triggered_by=None,
    )
    session = _CommitRollbackSession()
    service = _service(repository, session_factory=_SessionFactory(session))

    async def _succeed(self, connector_id, run_id, *, triggered_by, lock_token):
        del self, connector_id, run_id, triggered_by, lock_token
        return SimpleNamespace(status=IBORSyncRunStatus.succeeded)

    monkeypatch.setattr(IBORSyncService, '_continue_sync', _succeed)
    await service._run_background(connector.id, run.id, triggered_by=None, lock_token='token')

    assert session.commit_calls == 1
    assert session.rollback_calls == 0

    async def _fail(self, connector_id, run_id, *, triggered_by, lock_token):
        del self, connector_id, run_id, triggered_by, lock_token
        raise RuntimeError('session boom')

    monkeypatch.setattr(IBORSyncService, '_continue_sync', _fail)
    with pytest.raises(RuntimeError, match='session boom'):
        await service._run_background(connector.id, run.id, triggered_by=None, lock_token='token')

    assert session.rollback_calls == 1


@pytest.mark.asyncio
async def test_sync_helper_branches_cover_explicit_locks_and_missing_endpoints() -> None:
    repository = InMemoryIBORRepository()
    connector = await _create_connector(repository, credential_ref='async-creds')
    lock_client = _ExplicitLockRedisClient()

    async def _resolver(reference: str) -> dict[str, object]:
        mapping = {
            'async-creds': {'token': 'async-token'},
            'missing-oidc': {},
            'missing-scim': {},
            'ldap-inline': {'users': [{'email': 'ldap-inline@corp.com'}]},
        }
        return mapping[reference]

    service = IBORSyncService(
        repository=repository,
        accounts_repository=None,
        redis_client=lock_client,
        settings=SimpleNamespace(),
        producer=RecordingProducer(),
        credential_resolver=_resolver,
    )

    resolved = await service._resolve_credential(connector)
    existing_id = uuid4()
    await repository.create_platform_user(existing_id, 'known@corp.com', 'Known')
    existing_user = await service._ensure_user('known@corp.com', 'Known')
    created_user = await service._ensure_user('new@corp.com', 'New User')
    headers = service._credential_headers(
        {'headers': {'Authorization': 'Basic abc'}, 'token': 'ignored'}
    )
    payload_from_list = service._normalize_directory_payload([{'mail': 'list@corp.com'}])
    empty_payload = service._normalize_directory_payload({'ignored': True})
    non_list_groups = service._normalize_groups('admins')
    unmapped_groups = service._normalize_groups([{'unknown': 'value'}])

    lock = await service._acquire_lock(connector.id, 30)
    await service._release_lock(connector.id, lock.token or '')

    failing_service = IBORSyncService(
        repository=repository,
        accounts_repository=None,
        redis_client=_ExplicitLockRedisClient(success=False, token=None),
        settings=SimpleNamespace(),
        producer=RecordingProducer(),
        credential_resolver=_resolver,
    )

    with pytest.raises(IBORSyncInProgressError):
        await failing_service.trigger_sync(connector.id, triggered_by=None)

    oidc_connector = await _create_connector(
        repository, source_type=IBORSourceType.oidc, credential_ref='missing-oidc'
    )
    scim_connector = await _create_connector(
        repository, source_type=IBORSourceType.scim, credential_ref='missing-scim'
    )
    ldap_connector = await _create_connector(
        repository, source_type=IBORSourceType.ldap, credential_ref='ldap-inline'
    )

    with pytest.raises(IBORCredentialResolutionError):
        await service._pull_oidc(oidc_connector)
    with pytest.raises(IBORCredentialResolutionError):
        await service._pull_scim(scim_connector)
    ldap_users = await service._pull_ldap(ldap_connector)

    with pytest.raises(IBORConnectorNotFoundError):
        await service._get_connector_or_raise(uuid4())

    assert resolved == {'token': 'async-token'}
    assert existing_user == (existing_id, 0, 0)
    assert created_user[1:] == (1, 0)
    assert repository.platform_users_by_email['new@corp.com'].id == created_user[0]
    assert headers['Authorization'] == 'Basic abc'
    assert payload_from_list[0]['email'] == 'list@corp.com'
    assert empty_payload == []
    assert non_list_groups == set()
    assert unmapped_groups == set()
    assert lock.success is True
    assert lock_client.acquire_calls == [('ibor:sync', str(connector.id), 30)]
    assert lock_client.release_calls == [('ibor:sync', str(connector.id), 'lock-token')]
    assert ldap_users[0]['email'] == 'ldap-inline@corp.com'


@pytest.mark.asyncio
async def test_pull_and_push_helper_paths_cover_revocation_and_error_handling() -> None:
    repository = InMemoryIBORRepository()
    pull_connector = await _create_connector(repository, credential_ref='{"users": []}')
    sourced_role = UserRole(
        user_id=uuid4(),
        role='platform_admin',
        workspace_id=None,
        source_connector_id=pull_connector.id,
    )
    sourced_role.id = uuid4()
    sourced_role.created_at = datetime.now(UTC)
    sourced_role.updated_at = sourced_role.created_at
    repository.user_roles.append(sourced_role)
    pull_service = _service(repository, credential_resolver=lambda _ref: {'users': []})

    pull_counts, pull_errors = await pull_service._run_pull(pull_connector)

    assert pull_counts['roles_revoked'] == 1
    assert pull_errors == []
    assert repository.user_roles == []

    push_connector = await _create_connector(
        repository,
        source_type=IBORSourceType.scim,
        sync_mode=IBORSyncMode.push,
        credential_ref='push-sync',
    )
    repository.db.agents = [
        SimpleNamespace(
            id=uuid4(),
            fqn='finance:sync-agent',
            display_name='Sync Agent',
            status=LifecycleStatus.published,
        )
    ]

    sync_collector = _SyncCollector()
    sync_service = _service(
        repository,
        credential_resolver=lambda _ref: {'collector': sync_collector},
    )
    sync_counts, sync_errors = await sync_service._push_scim(push_connector)

    missing_endpoint_service = _service(repository, credential_resolver=lambda _ref: {})
    missing_counts, missing_errors = await missing_endpoint_service._push_scim(push_connector)

    broken_service = _service(
        repository,
        credential_resolver=lambda _ref: {'collector': _BrokenCollector()},
    )
    broken_counts, broken_errors = await broken_service._push_scim(push_connector)

    assert sync_counts['users_updated'] == 1
    assert sync_errors == []
    assert sync_collector.calls[0]['userName'] == 'finance:sync-agent'
    assert missing_counts['errors'] == 1
    assert missing_errors[0]['agent_fqn'] == 'finance:sync-agent'
    assert broken_counts['errors'] == 1
    assert broken_errors[0]['error'] == 'collector boom'
