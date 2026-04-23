from __future__ import annotations

from datetime import UTC, datetime
from platform.auth.models import OAuthAuditEntry, OAuthLink, OAuthProvider
from platform.auth.repository_oauth import OAuthRepository
from types import SimpleNamespace
from uuid import uuid4

import pytest


class ResultStub:
    def __init__(self, *, one=None, values=None, scalar=None) -> None:
        self._one = one
        self._values = list(values or [])
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._one

    def one(self):
        return self._one

    def scalar(self):
        return self._scalar

    def scalars(self):
        return self

    def all(self):
        return list(self._values)


class SessionStub:
    def __init__(self, responses=None, get_responses=None) -> None:
        self.responses = list(responses or [])
        self.get_responses = list(get_responses or [])
        self.added: list[object] = []
        self.deleted: list[object] = []
        self.flush_calls = 0

    async def execute(self, statement):
        del statement
        return self.responses.pop(0) if self.responses else ResultStub()

    async def get(self, model, key, **kwargs):
        del model, key, kwargs
        return self.get_responses.pop(0) if self.get_responses else None

    def add(self, item) -> None:
        self.added.append(item)

    async def delete(self, item) -> None:
        self.deleted.append(item)

    async def flush(self) -> None:
        self.flush_calls += 1


@pytest.mark.asyncio
async def test_repository_upserts_provider_and_writes_link_and_audit_records() -> None:
    provider_id = uuid4()
    created_provider = OAuthProvider(
        id=provider_id,
        provider_type="google",
        display_name="Google",
        enabled=True,
        client_id="client",
        client_secret_ref="plain:secret",
        redirect_uri="https://app.example.com/callback",
        scopes=["openid", "email"],
        domain_restrictions=["example.com"],
        org_restrictions=[],
        group_role_mapping={"admins": "platform_admin"},
        default_role="viewer",
        require_mfa=True,
    )
    existing = OAuthProvider(
        id=uuid4(),
        provider_type="google",
        display_name="Google Workspace",
        enabled=False,
        client_id="client-2",
        client_secret_ref="plain:secret-2",
        redirect_uri="https://app.example.com/callback",
        scopes=["openid"],
        domain_restrictions=[],
        org_restrictions=[],
        group_role_mapping={},
        default_role="viewer",
        require_mfa=False,
    )
    user_id = uuid4()
    link_id = uuid4()
    inserted_link = OAuthLink(
        id=link_id,
        user_id=user_id,
        provider_id=provider_id,
        external_id="external-1",
        external_email="alex@example.com",
        external_name="Alex",
        external_avatar_url="https://images.example.com/alex.png",
        external_groups=["admins"],
        last_login_at=datetime.now(UTC),
    )
    session = SessionStub(
        responses=[
            ResultStub(one=SimpleNamespace(id=provider_id, created=True)),
            ResultStub(one=SimpleNamespace(id=existing.id, created=False)),
            ResultStub(one=link_id),
        ],
        get_responses=[created_provider, existing, inserted_link],
    )
    repository = OAuthRepository(session)

    created, created_flag = await repository.upsert_provider(
        "google",
        display_name="Google",
        enabled=True,
        client_id="client",
        client_secret_ref="plain:secret",
        redirect_uri="https://app.example.com/callback",
        scopes=["openid", "email"],
        domain_restrictions=["example.com"],
        org_restrictions=[],
        group_role_mapping={"admins": "platform_admin"},
        default_role="viewer",
        require_mfa=True,
    )
    updated, updated_flag = await repository.upsert_provider(
        "google",
        display_name="Google Workspace",
        enabled=False,
        client_id="client-2",
        client_secret_ref="plain:secret-2",
        redirect_uri="https://app.example.com/callback",
        scopes=["openid"],
        domain_restrictions=[],
        org_restrictions=[],
        group_role_mapping={},
        default_role="viewer",
        require_mfa=False,
    )
    link = await repository.create_link(
        user_id=user_id,
        provider_id=provider_id,
        external_id="external-1",
        external_email="alex@example.com",
        external_name="Alex",
        external_avatar_url="https://images.example.com/alex.png",
        external_groups=["admins"],
        last_login_at=datetime.now(UTC),
    )
    touched = await repository.update_link(
        link,
        external_email="alex.updated@example.com",
        external_name="Alex Updated",
        external_avatar_url=None,
        external_groups=["reviewers"],
        last_login_at=datetime.now(UTC),
    )
    audit = await repository.create_audit_entry(
        provider_type="google",
        provider_id=provider_id,
        user_id=user_id,
        external_id="external-1",
        action="sign_in_succeeded",
        outcome="success",
        failure_reason=None,
        source_ip="127.0.0.1",
        user_agent="pytest",
        actor_id=user_id,
        changed_fields={"enabled": True},
    )
    await repository.delete_link(link)

    assert created_flag is True
    assert isinstance(created, OAuthProvider)
    assert updated_flag is False
    assert updated.display_name == "Google Workspace"
    assert isinstance(link, OAuthLink)
    assert touched.external_email == "alex.updated@example.com"
    assert isinstance(audit, OAuthAuditEntry)
    assert session.deleted == [link]
    assert session.flush_calls == 3


@pytest.mark.asyncio
async def test_repository_query_helpers_return_scalar_and_collection_results() -> None:
    provider = SimpleNamespace(provider_type="google")
    link = SimpleNamespace(user_id=uuid4(), provider=provider, linked_at=datetime.now(UTC))
    audit = SimpleNamespace(action="sign_in_succeeded", created_at=datetime.now(UTC))
    session = SessionStub(
        responses=[
            ResultStub(one=provider),
            ResultStub(values=[provider]),
            ResultStub(one=link),
            ResultStub(one=link),
            ResultStub(values=[link]),
            ResultStub(scalar=1),
            ResultStub(scalar=2),
            ResultStub(values=[audit]),
        ]
    )
    repository = OAuthRepository(session)

    loaded_provider = await repository.get_provider_by_type("google")
    providers = await repository.get_all_providers()
    loaded_external = await repository.get_link_by_external(uuid4(), "external-1")
    loaded_user_link = await repository.get_link_for_user_provider(uuid4(), uuid4())
    links = await repository.get_links_for_user(uuid4())
    auth_methods = await repository.count_auth_methods(uuid4())
    audits = await repository.list_audit_entries(limit=10)

    assert loaded_provider is provider
    assert providers == [provider]
    assert loaded_external is link
    assert loaded_user_link is link
    assert links == [link]
    assert auth_methods == 3
    assert audits == [audit]

@pytest.mark.asyncio
async def test_create_link_reuses_concurrent_insert_and_rejects_wrong_user() -> None:
    user_id = uuid4()
    provider_id = uuid4()
    existing = OAuthLink(
        id=uuid4(),
        user_id=user_id,
        provider_id=provider_id,
        external_id="external-1",
        external_email="old@example.com",
        external_name="Old",
        external_avatar_url=None,
        external_groups=[],
        last_login_at=None,
    )
    session = SessionStub(responses=[ResultStub(one=None), ResultStub(one=existing)])
    repository = OAuthRepository(session)

    link = await repository.create_link(
        user_id=user_id,
        provider_id=provider_id,
        external_id="external-1",
        external_email="new@example.com",
        external_name="New",
        external_avatar_url="https://images.example.com/new.png",
        external_groups=["admins"],
        last_login_at=datetime.now(UTC),
    )

    assert link is existing
    assert link.external_email == "new@example.com"
    assert link.external_groups == ["admins"]
    assert session.flush_calls == 1

    conflicting = OAuthLink(
        id=uuid4(),
        user_id=uuid4(),
        provider_id=provider_id,
        external_id="external-1",
        external_email="new@example.com",
        external_name="New",
        external_avatar_url=None,
        external_groups=[],
        last_login_at=None,
    )
    conflict_session = SessionStub(
        responses=[ResultStub(one=None), ResultStub(one=conflicting)]
    )
    conflict_repository = OAuthRepository(conflict_session)

    with pytest.raises(ValueError, match="already belongs to a different user"):
        await conflict_repository.create_link(
            user_id=user_id,
            provider_id=provider_id,
            external_id="external-1",
            external_email="new@example.com",
            external_name="New",
            external_avatar_url=None,
            external_groups=[],
        )


@pytest.mark.asyncio
async def test_list_audit_entries_applies_all_optional_filters() -> None:
    audit = SimpleNamespace(action="sign_in_failed", created_at=datetime.now(UTC))
    session = SessionStub(responses=[ResultStub(values=[audit])])
    repository = OAuthRepository(session)
    now = datetime.now(UTC)

    audits = await repository.list_audit_entries(
        provider_type="google",
        user_id=uuid4(),
        outcome="failure",
        start_time=now,
        end_time=now,
        limit=5,
    )

    assert audits == [audit]

