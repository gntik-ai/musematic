from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.auth.models import (
    AuthAttempt,
    IBORConnector,
    IBORSourceType,
    IBORSyncMode,
    IBORSyncRun,
    IBORSyncRunStatus,
    MfaEnrollment,
    PasswordResetToken,
    ServiceAccountCredential,
    UserCredential,
    UserRole,
)
from platform.auth.repository import AuthRepository
from types import SimpleNamespace
from uuid import uuid4

import pytest


class ResultStub:
    def __init__(
        self,
        *,
        scalar_one_or_none=None,
        values=None,
        first=None,
        rowcount=0,
    ) -> None:
        self._scalar_one_or_none = scalar_one_or_none
        self._values = list(values or [])
        self._first = first
        self.rowcount = rowcount

    def scalar_one_or_none(self):
        return self._scalar_one_or_none

    def scalars(self):
        return self

    def all(self):
        return list(self._values)

    def first(self):
        if self._first is not None:
            return self._first
        return self._values[0] if self._values else None


class SessionStub:
    def __init__(self, responses=None) -> None:
        self.responses = list(responses or [])
        self.added: list[object] = []
        self.executed: list[object] = []
        self.flush_calls = 0

    async def execute(self, statement):
        self.executed.append(statement)
        if not self.responses:
            return ResultStub()
        return self.responses.pop(0)

    def add(self, item) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        self.flush_calls += 1


@pytest.mark.asyncio
async def test_repository_create_methods_add_entities_and_flush() -> None:
    session = SessionStub()
    repository = AuthRepository(session)
    user_id = uuid4()
    service_account_id = uuid4()

    credential = await repository.create_credential(user_id, "user@example.com", "hash-1")
    role = await repository.assign_user_role(user_id, "viewer", None)
    await repository.record_auth_attempt(
        user_id,
        "user@example.com",
        "127.0.0.1",
        "pytest",
        "success",
    )
    enrollment = await repository.create_mfa_enrollment(
        user_id,
        "encrypted",
        ["hash-a"],
        datetime.now(UTC) + timedelta(minutes=10),
    )
    service_account = await repository.create_service_account_credential(
        service_account_id,
        "ci-bot",
        "hash-2",
        "service_account",
        None,
    )

    assert isinstance(credential, UserCredential)
    assert credential.email == "user@example.com"
    assert isinstance(role, UserRole)
    assert isinstance(session.added[2], AuthAttempt)
    assert isinstance(enrollment, MfaEnrollment)
    assert isinstance(service_account, ServiceAccountCredential)
    assert session.flush_calls == 5


@pytest.mark.asyncio
async def test_repository_query_methods_return_scalar_and_collection_results() -> None:
    credential = SimpleNamespace(email="user@example.com")
    roles = [SimpleNamespace(role="viewer"), SimpleNamespace(role="auditor")]
    permissions = [SimpleNamespace(role="viewer", action="read")]
    all_permissions = [*permissions, SimpleNamespace(role="creator", action="write")]
    enrollment = SimpleNamespace(status="pending")
    service_account = SimpleNamespace(service_account_id=uuid4(), status="active")
    session = SessionStub(
        responses=[
            ResultStub(scalar_one_or_none=credential),
            ResultStub(values=roles),
            ResultStub(values=permissions),
            ResultStub(values=all_permissions),
            ResultStub(values=[enrollment]),
            ResultStub(values=[service_account]),
            ResultStub(scalar_one_or_none=service_account),
        ]
    )
    repository = AuthRepository(session)

    loaded_credential = await repository.get_credential_by_email("USER@EXAMPLE.COM")
    loaded_roles = await repository.get_user_roles(uuid4(), None)
    loaded_permissions = await repository.get_role_permissions("viewer")
    loaded_all_permissions = await repository.get_all_role_permissions()
    loaded_enrollment = await repository.get_mfa_enrollment(uuid4())
    loaded_service_accounts = await repository.get_active_service_accounts()
    loaded_service_account = await repository.get_service_account_by_id(uuid4())

    assert loaded_credential is credential
    assert loaded_roles == roles
    assert loaded_permissions == permissions
    assert loaded_all_permissions == all_permissions
    assert loaded_enrollment is enrollment
    assert loaded_service_accounts == [service_account]
    assert loaded_service_account is service_account


@pytest.mark.asyncio
async def test_repository_update_methods_issue_execute_calls() -> None:
    session = SessionStub()
    repository = AuthRepository(session)
    await repository.update_password_hash(uuid4(), "new-hash")
    await repository.revoke_user_role(uuid4())
    await repository.activate_mfa_enrollment(uuid4())
    await repository.consume_recovery_code(uuid4(), 0, ["hash-b"])
    await repository.update_service_account_key_hash(uuid4(), "new-key", "active")
    await repository.revoke_service_account(uuid4())

    assert len(session.executed) == 6


@pytest.mark.asyncio
async def test_repository_platform_user_and_ibor_create_update_methods() -> None:
    session = SessionStub()
    repository = AuthRepository(session)
    user_id = uuid4()
    connector_id = uuid4()

    platform_user = await repository.create_platform_user(
        user_id,
        "USER@EXAMPLE.COM",
        "Platform User",
    )
    reset_token = await repository.create_password_reset_token(
        user_id,
        "raw-token",
        datetime.now(UTC) + timedelta(minutes=5),
    )
    connector = await repository.create_connector(
        name="corp-oidc",
        source_type=IBORSourceType.oidc,
        sync_mode=IBORSyncMode.pull,
        cadence_seconds=600,
        credential_ref="secret/ibor/oidc",
        role_mapping_policy=[{"directory_group": "Admins", "platform_role": "platform_admin"}],
        enabled=True,
        created_by=user_id,
    )
    run = await repository.create_sync_run(
        connector_id=connector_id,
        mode=IBORSyncMode.pull,
        status=IBORSyncRunStatus.running,
        counts={"errors": 0},
        error_details=[],
        triggered_by=user_id,
    )

    updated_connector = await repository.update_connector(connector, cadence_seconds=1200)
    disabled_connector = await repository.soft_delete_connector(connector)
    updated_run = await repository.update_sync_run(
        run,
        status=IBORSyncRunStatus.succeeded,
        counts={"users_created": 1},
        error_details=[],
        finished_at=datetime.now(UTC),
    )
    await repository.touch_connector_run(
        connector,
        status=IBORSyncRunStatus.succeeded.value,
        last_run_at=datetime.now(UTC),
    )

    assert platform_user.email == "user@example.com"
    assert isinstance(reset_token, PasswordResetToken)
    assert isinstance(connector, IBORConnector)
    assert isinstance(run, IBORSyncRun)
    assert updated_connector.cadence_seconds == 1200
    assert disabled_connector.enabled is False
    assert updated_run.status is IBORSyncRunStatus.succeeded
    assert connector.last_run_status == IBORSyncRunStatus.succeeded.value
    assert session.flush_calls == 8


@pytest.mark.asyncio
async def test_repository_ibor_query_and_assignment_branches() -> None:
    connector_id = uuid4()
    user_id = uuid4()
    workspace_id = uuid4()
    platform_user = SimpleNamespace(id=user_id, email="user@example.com")
    sourced_role = UserRole(
        user_id=user_id,
        role="viewer",
        workspace_id=workspace_id,
        source_connector_id=connector_id,
    )
    manual_role = UserRole(
        user_id=user_id,
        role="viewer",
        workspace_id=None,
        source_connector_id=None,
    )
    reassigned_role = UserRole(
        user_id=user_id,
        role="editor",
        workspace_id=workspace_id,
        source_connector_id=uuid4(),
    )
    connector = SimpleNamespace(id=connector_id, name="corp-oidc", enabled=True)
    running = SimpleNamespace(id=uuid4(), connector_id=connector_id)
    older = SimpleNamespace(id=uuid4(), started_at=datetime.now(UTC) - timedelta(minutes=2))
    newer = SimpleNamespace(id=uuid4(), started_at=datetime.now(UTC) - timedelta(minutes=1))
    latest = SimpleNamespace(id=uuid4(), started_at=datetime.now(UTC))
    session = SessionStub(
        responses=[
            ResultStub(scalar_one_or_none=platform_user),
            ResultStub(scalar_one_or_none=platform_user),
            ResultStub(scalar_one_or_none=platform_user),
            ResultStub(values=[manual_role]),
            ResultStub(values=[manual_role, sourced_role]),
            ResultStub(values=[sourced_role]),
            ResultStub(scalar_one_or_none=connector),
            ResultStub(values=[connector]),
            ResultStub(values=[connector]),
            ResultStub(scalar_one_or_none=connector),
            ResultStub(first=running),
            ResultStub(scalar_one_or_none=running),
            ResultStub(values=[latest, newer, older]),
            ResultStub(values=[older]),
            ResultStub(values=[sourced_role]),
            ResultStub(scalar_one_or_none=manual_role),
            ResultStub(scalar_one_or_none=reassigned_role),
            ResultStub(scalar_one_or_none=sourced_role),
            ResultStub(scalar_one_or_none=None),
            ResultStub(rowcount=1),
        ]
    )
    repository = AuthRepository(session)

    loaded_user = await repository.get_platform_user(user_id)
    loaded_user_by_email = await repository.get_platform_user_by_email("USER@EXAMPLE.COM")
    roles_by_email = await repository.list_user_roles(user_email="user@example.com")
    filtered_roles = await repository.get_user_roles(user_id, workspace_id)
    roles_by_connector = await repository.get_user_roles_by_source_connector(user_id, connector_id)
    connector_by_name = await repository.get_connector_by_name("corp-oidc")
    listed = await repository.list_connectors()
    enabled = await repository.list_enabled_connectors()
    loaded_connector = await repository.get_connector(connector_id)
    running_run = await repository.get_running_sync_run(connector_id)
    loaded_run = await repository.get_sync_run(running.id)
    page, next_cursor = await repository.list_sync_runs(connector_id, limit=2)
    next_page, final_cursor = await repository.list_sync_runs(
        connector_id, limit=2, cursor=next_cursor
    )
    connector_roles = await repository.list_user_roles_by_connector(connector_id)
    preserved = await repository.assign_user_role(user_id, "viewer", None, connector_id)
    reassigned = await repository.assign_user_role(user_id, "editor", workspace_id, connector_id)
    cleared = await repository.assign_user_role(user_id, "viewer", workspace_id, None)
    created = await repository.assign_user_role(user_id, "admin", workspace_id, connector_id)
    disabled = await repository.disable_mfa_enrollment(user_id)

    assert loaded_user is platform_user
    assert loaded_user_by_email is platform_user
    assert roles_by_email == [manual_role]
    assert filtered_roles == [manual_role, sourced_role]
    assert roles_by_connector == [sourced_role]
    assert connector_by_name is connector
    assert listed == [connector]
    assert enabled == [connector]
    assert loaded_connector is connector
    assert running_run is running
    assert loaded_run is running
    assert page == [latest, newer]
    assert next_cursor == repository._encode_run_cursor(newer.started_at, newer.id)
    assert next_page == [older]
    assert final_cursor is None
    assert connector_roles == [sourced_role]
    assert preserved is manual_role
    assert reassigned.source_connector_id == connector_id
    assert cleared.source_connector_id is None
    assert created.role == "admin"
    assert disabled is True
    assert session.flush_calls == 3


@pytest.mark.asyncio
async def test_repository_list_user_roles_requires_identifier() -> None:
    repository = AuthRepository(SessionStub())

    with pytest.raises(ValueError, match="user_id or user_email is required"):
        await repository.list_user_roles()
