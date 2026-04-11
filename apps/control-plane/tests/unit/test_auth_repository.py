from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.auth.models import (
    AuthAttempt,
    MfaEnrollment,
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
    ) -> None:
        self._scalar_one_or_none = scalar_one_or_none
        self._values = list(values or [])
        self._first = first

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
