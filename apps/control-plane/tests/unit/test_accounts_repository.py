from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.accounts.models import (
    ApprovalRequest,
    EmailVerification,
    Invitation,
    InvitationStatus,
    SignupSource,
    User,
    UserStatus,
)
from platform.accounts.repository import AccountsRepository
from platform.common.models.user import User as PlatformUser
from uuid import UUID, uuid4

import pytest

from tests.auth_support import FakeAsyncRedisClient


class FakeScalars:
    def __init__(self, values) -> None:
        self._values = list(values)

    def all(self):
        return list(self._values)

    def first(self):
        return self._values[0] if self._values else None


class FakeResult:
    def __init__(self, *, scalar_value=None, values=None, rows=None) -> None:
        self._scalar_value = scalar_value
        self._values = list(values or [])
        self._rows = list(rows or [])

    def scalar_one_or_none(self):
        return self._scalar_value

    def scalars(self):
        return FakeScalars(self._values)

    def all(self):
        return list(self._rows)


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.flush_count = 0
        self.execute_results: list[FakeResult] = []
        self.scalar_results: list[object] = []
        self.get_results: dict[tuple[object, object], object] = {}

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flush_count += 1

    async def execute(self, statement):
        del statement
        return self.execute_results.pop(0)

    async def scalar(self, statement):
        del statement
        return self.scalar_results.pop(0)

    async def get(self, model, key):
        return self.get_results.get((model, key))


@pytest.mark.asyncio
async def test_create_user_creates_accounts_and_platform_users() -> None:
    session = FakeSession()
    repository = AccountsRepository(session)

    user = await repository.create_user(
        email="USER@Example.COM",
        display_name="Jane Smith",
        status=UserStatus.pending_verification,
        signup_source=SignupSource.self_registration,
    )

    account_user, platform_user = session.added
    assert user is account_user
    assert account_user.email == "user@example.com"
    assert platform_user.email == "user@example.com"
    assert platform_user.id == account_user.id
    assert platform_user.status == UserStatus.pending_verification.value


@pytest.mark.asyncio
async def test_lookup_helpers_return_scalar_results() -> None:
    session = FakeSession()
    repository = AccountsRepository(session)
    user = User(
        id=uuid4(),
        email="user@example.com",
        display_name="Jane Smith",
        status=UserStatus.active,
        signup_source=SignupSource.self_registration,
    )
    session.execute_results = [
        FakeResult(scalar_value=user),
        FakeResult(scalar_value=user),
        FakeResult(scalar_value=user),
    ]

    assert await repository.get_user_by_email("USER@Example.COM") is user
    assert await repository.get_user_by_id(user.id) is user
    assert await repository.get_user_for_update(user.id) is user


@pytest.mark.asyncio
async def test_update_user_status_updates_both_user_tables() -> None:
    session = FakeSession()
    repository = AccountsRepository(session)
    user_id = uuid4()
    account_user = User(
        id=user_id,
        email="user@example.com",
        display_name="Jane Smith",
        status=UserStatus.active,
        signup_source=SignupSource.self_registration,
    )
    platform_user = PlatformUser(
        id=user_id,
        email="user@example.com",
        display_name="Jane Smith",
        status="active",
    )
    deleted_at = datetime.now(UTC)
    session.execute_results = [
        FakeResult(scalar_value=account_user),
        FakeResult(scalar_value=platform_user),
    ]

    updated = await repository.update_user_status(
        user_id,
        UserStatus.archived,
        archived_at=deleted_at,
        deleted_at=deleted_at,
    )

    assert updated is account_user
    assert account_user.status == UserStatus.archived
    assert account_user.archived_at == deleted_at
    assert platform_user.status == UserStatus.archived.value
    assert platform_user.deleted_at == deleted_at


@pytest.mark.asyncio
async def test_verification_methods_create_lookup_and_consume_tokens() -> None:
    session = FakeSession()
    repository = AccountsRepository(session)
    verification = EmailVerification(
        id=uuid4(),
        user_id=uuid4(),
        token_hash="token-hash",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        consumed=False,
    )
    session.execute_results = [FakeResult(scalar_value=verification)]
    session.get_results[(EmailVerification, verification.id)] = verification

    created = await repository.create_email_verification(
        verification.user_id,
        verification.token_hash,
        verification.expires_at,
    )
    fetched = await repository.get_active_verification_by_token_hash("token-hash")
    await repository.consume_verification(verification.id)

    assert created.user_id == verification.user_id
    assert fetched is verification
    assert verification.consumed is True


@pytest.mark.asyncio
async def test_resend_count_helpers_use_redis_counter() -> None:
    redis_client = FakeAsyncRedisClient()
    repository = AccountsRepository(FakeSession())
    user_id = uuid4()

    assert await repository.get_resend_count(redis_client, user_id) == 0
    assert await repository.increment_resend_count(redis_client, user_id) == 1
    assert await repository.increment_resend_count(redis_client, user_id) == 2
    assert await repository.get_resend_count(redis_client, user_id) == 2


@pytest.mark.asyncio
async def test_approval_request_methods_create_and_paginate_results() -> None:
    session = FakeSession()
    repository = AccountsRepository(session)
    user = User(
        id=uuid4(),
        email="pending@example.com",
        display_name="Pending User",
        status=UserStatus.pending_approval,
        signup_source=SignupSource.self_registration,
    )
    user.created_at = datetime.now(UTC)
    approval = ApprovalRequest(
        id=uuid4(),
        user_id=user.id,
        requested_at=datetime.now(UTC),
    )
    session.execute_results = [
        FakeResult(scalar_value=approval),
        FakeResult(rows=[(user, approval)]),
    ]
    session.scalar_results = [1]

    created = await repository.create_approval_request(user.id, approval.requested_at)
    fetched = await repository.get_approval_request_for_update(user.id)
    items, total = await repository.get_pending_approvals(page=1, page_size=20)

    assert created.user_id == user.id
    assert fetched is approval
    assert total == 1
    assert items[0].email == user.email


@pytest.mark.asyncio
async def test_invitation_methods_create_transition_and_deserialize() -> None:
    session = FakeSession()
    repository = AccountsRepository(session)
    inviter_id = uuid4()
    invitation = Invitation(
        id=uuid4(),
        inviter_id=inviter_id,
        invitee_email="invitee@example.com",
        token_hash="token-hash",
        roles_json='["viewer"]',
        workspace_ids_json='["00000000-0000-0000-0000-000000000001"]',
        invitee_message="Welcome",
        status=InvitationStatus.pending,
        expires_at=datetime.now(UTC) + timedelta(days=7),
        created_at=datetime.now(UTC),
    )
    session.execute_results = [
        FakeResult(scalar_value=invitation),
        FakeResult(values=[invitation]),
    ]
    session.scalar_results = [1]
    session.get_results[(Invitation, invitation.id)] = invitation

    created = await repository.create_invitation(
        inviter_id=inviter_id,
        invitee_email="INVITEE@Example.COM",
        token_hash="token-hash",
        roles_json='["viewer"]',
        workspace_ids_json='["00000000-0000-0000-0000-000000000001"]',
        message="Welcome",
        expires_at=invitation.expires_at,
    )
    fetched_by_token = await repository.get_invitation_by_token_hash("token-hash")
    await repository.consume_invitation(invitation.id, uuid4())
    consumed_at = invitation.consumed_at
    await repository.revoke_invitation(invitation.id, inviter_id)
    items, total = await repository.list_invitations_by_inviter(
        inviter_id=inviter_id,
        status_filter=InvitationStatus.revoked,
        page=1,
        page_size=20,
    )

    assert created.invitee_email == "invitee@example.com"
    assert fetched_by_token is invitation
    assert invitation.status == InvitationStatus.revoked
    assert consumed_at is not None
    assert total == 1
    assert items == [invitation]
    assert repository.deserialize_roles(invitation) == ["viewer"]
    assert repository.deserialize_workspace_ids(invitation) == [
        UUID("00000000-0000-0000-0000-000000000001")
    ]


@pytest.mark.asyncio
async def test_get_invitation_by_id_uses_session_get() -> None:
    session = FakeSession()
    repository = AccountsRepository(session)
    invitation = Invitation(
        id=uuid4(),
        inviter_id=uuid4(),
        invitee_email="invitee@example.com",
        token_hash="token",
        roles_json="[]",
        workspace_ids_json=None,
        invitee_message=None,
        status=InvitationStatus.pending,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    session.get_results[(Invitation, invitation.id)] = invitation

    assert await repository.get_invitation_by_id(invitation.id) is invitation
