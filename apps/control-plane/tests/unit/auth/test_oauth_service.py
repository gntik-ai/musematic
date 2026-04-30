from __future__ import annotations

from datetime import UTC, datetime
from platform.auth.exceptions import (
    InactiveUserError,
    OAuthLinkConflictError,
    OAuthProviderDisabledError,
    OAuthProviderNotFoundError,
    OAuthRestrictionError,
    OAuthStateExpiredError,
    OAuthStateInvalidError,
    OAuthUnlinkLastMethodError,
)
from platform.auth.schemas import OAuthProviderType
from platform.auth.services.oauth_service import OAuthUserIdentity
from platform.common.exceptions import ValidationError
from platform.common.secret_provider import CredentialPolicyDeniedError, CredentialUnavailableError
from types import SimpleNamespace
from uuid import uuid4

import pytest
from tests.auth_oauth_support import (
    AuthRepositoryStub,
    GitHubProviderStub,
    GoogleProviderStub,
    OAuthRepositoryStub,
    OAuthSecretProviderStub,
    build_oauth_service_fixture,
    build_provider,
    extract_query_param,
)


@pytest.mark.asyncio
async def test_list_public_admin_links_and_audit_serializers(auth_settings) -> None:
    provider = build_provider(provider_type="google")
    repo_auth = AuthRepositoryStub()
    service, repository, auth_repository, *_ = build_oauth_service_fixture(
        auth_settings,
        provider=provider,
        auth_repository=repo_auth,
    )
    repository.providers = {
        "google": provider,
        "github": build_provider(provider_type="github", enabled=False),
    }
    link = await repository.create_link(
        user_id=uuid4(),
        provider_id=provider.id,
        external_id="external-1",
        external_email="alex@example.com",
        external_name="Alex",
        external_avatar_url=None,
        external_groups=[],
        last_login_at=datetime.now(UTC),
    )
    link.provider = provider
    await repository.create_audit_entry(
        provider_type="google",
        provider_id=provider.id,
        user_id=link.user_id,
        external_id="external-1",
        action="sign_in_succeeded",
        outcome="success",
        failure_reason=None,
        source_ip="127.0.0.1",
        user_agent="pytest",
        actor_id=link.user_id,
        changed_fields=None,
    )

    public_response = await service.list_public_providers()
    admin_response = await service.list_admin_providers()
    links_response = await service.list_links(link.user_id)
    audit_response = await service.list_audit_entries(limit=10)

    assert [item.provider_type.value for item in public_response.providers] == ["google"]
    assert len(admin_response.providers) == 2
    assert links_response.items[0].display_name == provider.display_name
    assert audit_response.items[0].action == "sign_in_succeeded"
    assert auth_repository is repo_auth


@pytest.mark.asyncio
async def test_get_authorization_url_stores_state_and_pkce_payload(auth_settings) -> None:
    service, _, _, _, redis_client, _, _ = build_oauth_service_fixture(auth_settings)

    response = await service.get_authorization_url("google", link_for_user_id=uuid4())

    state = extract_query_param(response.redirect_url, "state")
    nonce = service._verify_state(state)
    stored = await redis_client.get(service._state_key(nonce))

    assert stored is not None
    decoded = __import__("json").loads(stored.decode("utf-8"))
    assert decoded["provider_type"] == "google"
    assert decoded["code_verifier"]
    assert extract_query_param(response.redirect_url, "code_challenge")


@pytest.mark.asyncio
async def test_handle_callback_auto_provisions_google_user_and_creates_session(
    auth_settings,
) -> None:
    provider = build_provider(
        provider_type="google", group_role_mapping={"admins": "platform_admin"}
    )
    google = GoogleProviderStub(
        identity={
            "sub": "google-sub",
            "email": "alex@example.com",
            "name": "Alex Example",
            "picture": "https://images.example.com/alex.png",
            "aud": provider.client_id,
            "email_verified": "true",
        },
        groups=["admins"],
    )
    service, repository, auth_repository, accounts_repository, _, producer, auth_service = (
        build_oauth_service_fixture(
            auth_settings,
            provider=provider,
            google_provider=google,
        )
    )
    authorization = await service.get_authorization_url("google")
    state = extract_query_param(authorization.redirect_url, "state")

    result = await service.handle_callback(
        provider_type="google",
        code="oauth-code",
        raw_state=state,
        source_ip="127.0.0.1",
        user_agent="pytest",
    )

    user_id = accounts_repository.created_users[0].id
    auth_repository.roles_by_user[user_id] = [SimpleNamespace(role="platform_admin")]

    assert result["token_pair"].access_token == "access-token"
    assert result["user"]["email"] == "alex@example.com"
    assert repository.audit_entries[0]["action"] == "user_provisioned"
    assert repository.audit_entries[-1]["action"] == "sign_in_succeeded"
    assert auth_service.session_calls
    assert {event["event_type"] for event in producer.events} == {
        "auth.oauth.user_provisioned",
        "auth.oauth.sign_in_succeeded",
    }


@pytest.mark.asyncio
async def test_handle_callback_returns_mfa_challenge_when_required(auth_settings) -> None:
    provider = build_provider(provider_type="google", require_mfa=True)
    google = GoogleProviderStub(groups=[])
    user_id = uuid4()
    auth_repository = AuthRepositoryStub(
        users_by_id={
            user_id: SimpleNamespace(
                id=user_id,
                email="alex@example.com",
                display_name="Alex Example",
                status="active",
            )
        },
        roles_by_user={user_id: [SimpleNamespace(role="viewer")]},
        enrollments_by_user={user_id: SimpleNamespace(status="active")},
    )
    repository = OAuthRepositoryStub(
        providers={provider.provider_type: provider},
    )
    existing_link = await repository.create_link(
        user_id=user_id,
        provider_id=provider.id,
        external_id="google-subject",
        external_email="alex@example.com",
        external_name="Alex Example",
        external_avatar_url=None,
        external_groups=[],
        last_login_at=None,
    )
    existing_link.provider = provider
    service, _, _, _, _, _, auth_service = build_oauth_service_fixture(
        auth_settings,
        provider=provider,
        google_provider=google,
        repository=repository,
        auth_repository=auth_repository,
    )
    state = extract_query_param(
        (await service.get_authorization_url("google")).redirect_url, "state"
    )

    result = await service.handle_callback(
        provider_type="google",
        code="oauth-code",
        raw_state=state,
        source_ip="127.0.0.1",
        user_agent="pytest",
    )

    assert result["mfa_required"] is True
    assert result["session_token"] == "oauth-mfa-token"
    assert auth_service.challenge_calls


@pytest.mark.asyncio
async def test_handle_callback_links_existing_user_and_returns_link_payload(auth_settings) -> None:
    provider = build_provider(provider_type="google")
    service, repository, _, _, _, producer, _ = build_oauth_service_fixture(
        auth_settings, provider=provider
    )
    user_id = uuid4()
    state = extract_query_param(
        (await service.get_authorization_url("google", link_for_user_id=user_id)).redirect_url,
        "state",
    )

    result = await service.handle_callback(
        provider_type="google",
        code="oauth-code",
        raw_state=state,
        source_ip="127.0.0.1",
        user_agent="pytest",
    )

    assert result["linked"] is True
    assert result["link"].provider_type == OAuthProviderType.GOOGLE
    assert repository.audit_entries[-1]["action"] == "account_linked"
    assert producer.events[-1]["event_type"] == "auth.oauth.account_linked"


@pytest.mark.asyncio
async def test_handle_callback_audits_state_and_provider_failures(auth_settings) -> None:
    provider = build_provider(provider_type="google")
    service, repository, _, _, _, _, _ = build_oauth_service_fixture(
        auth_settings, provider=provider
    )
    state = extract_query_param(
        (await service.get_authorization_url("google")).redirect_url, "state"
    )
    provider.enabled = False

    with pytest.raises(OAuthProviderDisabledError):
        await service.handle_callback(
            provider_type="google",
            code="oauth-code",
            raw_state=state,
            source_ip="127.0.0.1",
            user_agent="pytest",
        )

    assert repository.audit_entries[-1]["failure_reason"] == "OAUTH_PROVIDER_DISABLED"

    service2, repository2, *_ = build_oauth_service_fixture(
        auth_settings, provider=build_provider(provider_type="google")
    )
    with pytest.raises(OAuthStateInvalidError):
        await service2.handle_callback(
            provider_type="google",
            code="oauth-code",
            raw_state="tampered.state",
            source_ip="127.0.0.1",
            user_agent="pytest",
        )

    assert repository2.audit_entries[-1]["failure_reason"] == "OAUTH_STATE_INVALID"


@pytest.mark.asyncio
async def test_handle_callback_rejects_duplicate_email_and_github_org_restrictions(
    auth_settings,
) -> None:
    provider = build_provider(provider_type="google")
    auth_repository = AuthRepositoryStub(
        users_by_email={
            "alex@example.com": SimpleNamespace(
                id=uuid4(),
                email="alex@example.com",
                display_name="Alex",
                status="active",
            )
        }
    )
    service, repository, _, _, _, _, _ = build_oauth_service_fixture(
        auth_settings,
        provider=provider,
        auth_repository=auth_repository,
    )
    state = extract_query_param(
        (await service.get_authorization_url("google")).redirect_url, "state"
    )

    with pytest.raises(OAuthLinkConflictError):
        await service.handle_callback(
            provider_type="google",
            code="oauth-code",
            raw_state=state,
            source_ip="127.0.0.1",
            user_agent="pytest",
        )

    assert repository.audit_entries[-1]["failure_reason"] == "OAUTH_LINK_CONFLICT"

    github_provider = build_provider(provider_type="github", org_restrictions=["musematic"])
    github_client = GitHubProviderStub(memberships={"musematic": False})
    service2, repository2, *_ = build_oauth_service_fixture(
        auth_settings,
        provider=github_provider,
        github_provider=github_client,
    )
    state2 = extract_query_param(
        (await service2.get_authorization_url("github")).redirect_url, "state"
    )

    with pytest.raises(OAuthRestrictionError):
        await service2.handle_callback(
            provider_type="github",
            code="oauth-code",
            raw_state=state2,
            source_ip="127.0.0.1",
            user_agent="pytest",
        )

    assert repository2.audit_entries[-1]["failure_reason"] == "ORG_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_unlink_account_enforces_last_auth_method_and_deletes_link(auth_settings) -> None:
    provider = build_provider(provider_type="google")
    user_id = uuid4()
    repository = OAuthRepositoryStub(
        providers={provider.provider_type: provider},
        auth_method_count=1,
    )
    link = await repository.create_link(
        user_id=user_id,
        provider_id=provider.id,
        external_id="google-subject",
        external_email="alex@example.com",
        external_name="Alex Example",
        external_avatar_url=None,
        external_groups=[],
        last_login_at=None,
    )
    link.provider = provider
    repository.links_by_user_provider[(user_id, provider.id)] = link
    service, _, _, _, _, producer, _ = build_oauth_service_fixture(
        auth_settings,
        provider=provider,
        repository=repository,
    )

    with pytest.raises(OAuthUnlinkLastMethodError):
        await service.unlink_account(user_id, "google")

    repository.auth_method_count = 2
    await service.unlink_account(user_id, "google")

    assert repository.deleted_links == [link]
    assert repository.audit_entries[-1]["action"] == "account_unlinked"
    assert producer.events[-1]["event_type"] == "auth.oauth.account_unlinked"

@pytest.mark.asyncio
async def test_upsert_provider_records_changed_fields_and_event(auth_settings) -> None:
    provider = build_provider(provider_type="google", enabled=False)
    actor_id = uuid4()
    auth_repository = AuthRepositoryStub(
        users_by_id={actor_id: SimpleNamespace(id=actor_id, email="admin@example.com")}
    )
    service, repository, _, _, _, producer, _ = build_oauth_service_fixture(
        auth_settings,
        provider=provider,
        auth_repository=auth_repository,
    )

    response, created = await service.upsert_provider(
        provider_type="google",
        actor_id=actor_id,
        display_name="Google Workspace",
        enabled=True,
        client_id="google-client-updated",
        client_secret_ref="plain:new-secret",
        redirect_uri="https://app.example.com/oauth/google/callback",
        scopes=["openid", "email"],
        domain_restrictions=["example.com"],
        org_restrictions=[],
        group_role_mapping={"admins": "platform_admin"},
        default_role="workspace_member",
        require_mfa=True,
    )

    assert created is False
    assert response.display_name == "Google Workspace"
    assert response.default_role == "workspace_member"
    assert response.last_edited_by == actor_id
    assert repository.audit_entries[-1]["action"] == "provider_configured"
    assert repository.audit_entries[-1]["actor_id"] == actor_id
    assert repository.audit_entries[-1]["changed_fields"]["enabled"] == {
        "before": False,
        "after": True,
    }
    client_secret_diff = repository.audit_entries[-1]["changed_fields"]["client_secret_ref"]
    assert client_secret_diff == {
        "before": "plain:<redacted>",
        "after": "plain:<redacted>",
    }
    assert "google-secret" not in str(repository.audit_entries[-1]["changed_fields"])
    assert "new-secret" not in str(repository.audit_entries[-1]["changed_fields"])
    assert producer.events[-1]["event_type"] == "auth.oauth.provider_configured"

    with pytest.raises(ValidationError, match="cannot be blank"):
        await service.upsert_provider(
            provider_type="google",
            actor_id=actor_id,
            display_name="Google Workspace",
            enabled=True,
            client_id="google-client",
            client_secret_ref="plain:secret",
            redirect_uri="https://app.example.com/oauth/google/callback",
            scopes=["openid"],
            domain_restrictions=[],
            org_restrictions=[],
            group_role_mapping={"admins": "   "},
            default_role="viewer",
            require_mfa=False,
        )

    with pytest.raises(ValidationError, match="Unknown OAuth role mapping role"):
        await service.upsert_provider(
            provider_type="google",
            actor_id=actor_id,
            display_name="Google Workspace",
            enabled=True,
            client_id="google-client",
            client_secret_ref="plain:secret",
            redirect_uri="https://app.example.com/oauth/google/callback",
            scopes=["openid"],
            domain_restrictions=[],
            org_restrictions=[],
            group_role_mapping={"admins": "unknown_role"},
            default_role="viewer",
            require_mfa=False,
        )


@pytest.mark.asyncio
async def test_upsert_provider_omits_missing_actor_from_last_edited_fk(auth_settings) -> None:
    provider = build_provider(provider_type="google", enabled=False)
    service, repository, _, _, _, _, _ = build_oauth_service_fixture(
        auth_settings,
        provider=provider,
        auth_repository=AuthRepositoryStub(),
    )
    actor_id = uuid4()

    response, _ = await service.upsert_provider(
        provider_type="google",
        actor_id=actor_id,
        display_name="Google Workspace",
        enabled=True,
        client_id="google-client",
        client_secret_ref="plain:secret",
        redirect_uri="https://app.example.com/oauth/google/callback",
        scopes=["openid"],
        domain_restrictions=[],
        org_restrictions=[],
        group_role_mapping={},
        default_role="viewer",
        require_mfa=False,
    )

    assert response.last_edited_by is None
    assert repository.upsert_calls[-1]["last_edited_by"] is None
    assert repository.audit_entries[-1]["actor_id"] == actor_id


@pytest.mark.asyncio
async def test_link_callback_conflict_records_failed_link_audit(auth_settings) -> None:
    provider = build_provider(provider_type="google")
    service, repository, _, _, _, _, _ = build_oauth_service_fixture(
        auth_settings,
        provider=provider,
    )
    target_user_id = uuid4()
    existing_link = await repository.create_link(
        user_id=uuid4(),
        provider_id=provider.id,
        external_id="google-subject",
        external_email="alex@example.com",
        external_name="Alex Example",
        external_avatar_url=None,
        external_groups=[],
        last_login_at=None,
    )
    existing_link.provider = provider
    state = extract_query_param(
        (
            await service.get_authorization_url(
                "google",
                link_for_user_id=target_user_id,
            )
        ).redirect_url,
        "state",
    )

    with pytest.raises(OAuthLinkConflictError):
        await service.handle_callback(
            provider_type="google",
            code="oauth-code",
            raw_state=state,
            source_ip="127.0.0.1",
            user_agent="pytest",
        )

    assert repository.audit_entries[-1]["action"] == "account_linked"
    assert repository.audit_entries[-1]["outcome"] == "failure"
    assert repository.audit_entries[-1]["failure_reason"] == "OAUTH_LINK_CONFLICT"


@pytest.mark.asyncio
async def test_handle_callback_rejects_inactive_linked_user(auth_settings) -> None:
    provider = build_provider(provider_type="google")
    user_id = uuid4()
    auth_repository = AuthRepositoryStub(
        users_by_id={
            user_id: SimpleNamespace(
                id=user_id,
                email="alex@example.com",
                display_name="Alex Example",
                status="blocked",
            )
        },
        roles_by_user={user_id: [SimpleNamespace(role="viewer", workspace_id=None)]},
    )
    repository = OAuthRepositoryStub(providers={provider.provider_type: provider})
    existing_link = await repository.create_link(
        user_id=user_id,
        provider_id=provider.id,
        external_id="google-subject",
        external_email="alex@example.com",
        external_name="Alex Example",
        external_avatar_url=None,
        external_groups=[],
        last_login_at=None,
    )
    existing_link.provider = provider
    service, _, _, _, _, _, _ = build_oauth_service_fixture(
        auth_settings,
        provider=provider,
        repository=repository,
        auth_repository=auth_repository,
    )
    state = extract_query_param(
        (await service.get_authorization_url("google")).redirect_url,
        "state",
    )

    with pytest.raises(InactiveUserError):
        await service.handle_callback(
            provider_type="google",
            code="oauth-code",
            raw_state=state,
            source_ip="127.0.0.1",
            user_agent="pytest",
        )

    assert repository.audit_entries[-1]["action"] == "sign_in_failed"
    assert repository.audit_entries[-1]["failure_reason"] == "FORBIDDEN"

@pytest.mark.asyncio
async def test_handle_callback_audits_identity_resolution_failure(auth_settings) -> None:
    class FailingGoogleProvider(GoogleProviderStub):
        async def exchange_code(self, **kwargs):
            del kwargs
            raise RuntimeError("oauth-down")

    provider = build_provider(provider_type="google")
    service, repository, *_ = build_oauth_service_fixture(
        auth_settings,
        provider=provider,
        google_provider=FailingGoogleProvider(),
    )
    state = extract_query_param(
        (await service.get_authorization_url("google")).redirect_url,
        "state",
    )

    with pytest.raises(RuntimeError, match="oauth-down"):
        await service.handle_callback(
            provider_type="google",
            code="oauth-code",
            raw_state=state,
            source_ip="127.0.0.1",
            user_agent="pytest",
        )

    assert repository.audit_entries[-1]["action"] == "sign_in_failed"
    assert repository.audit_entries[-1]["failure_reason"] == "oauth-down"


@pytest.mark.asyncio
async def test_oauth_resolve_secret_supports_plain_inline_refs(auth_settings) -> None:
    class RejectingSecretProvider:
        async def get(self, reference: str) -> str:
            raise AssertionError(f"unexpected secret provider lookup: {reference}")

    service, *_ = build_oauth_service_fixture(
        auth_settings,
        secret_provider=RejectingSecretProvider(),
    )

    assert await service._resolve_secret("plain:mock-google-client-secret") == (
        "mock-google-client-secret"
    )


@pytest.mark.asyncio
async def test_oauth_internal_helpers_cover_error_paths(auth_settings) -> None:
    provider = build_provider(provider_type="google", enabled=False)
    service, _, _, _, redis_client, _, _ = build_oauth_service_fixture(
        auth_settings,
        provider=provider,
        secret_provider=OAuthSecretProviderStub({"vault/google": "resolved-secret"}),
    )

    assert await service._resolve_secret("vault/google") == "resolved-secret"
    assert service._resolve_role(provider, ["unmapped"]) == provider.default_role

    with pytest.raises(OAuthProviderDisabledError):
        await service._require_enabled_provider("google")

    with pytest.raises(OAuthProviderNotFoundError):
        await service._require_provider("missing")

    with pytest.raises(OAuthProviderNotFoundError):
        service._provider_client("unknown")

    with pytest.raises(OAuthStateInvalidError):
        service._verify_state("invalid-state")

    expired_state = service._sign_state("expired")
    with pytest.raises(OAuthStateExpiredError):
        await service._consume_state(expired_state, "google")

    mismatch_state = service._sign_state("mismatch")
    await redis_client.set(
        service._state_key("mismatch"),
        b'{"provider_type":"github","code_verifier":"verifier"}',
        ttl=60,
    )
    with pytest.raises(OAuthStateInvalidError):
        await service._consume_state(mismatch_state, "google")


@pytest.mark.asyncio
async def test_oauth_secret_provider_and_serializer_edge_paths(monkeypatch, auth_settings) -> None:
    class SecretProviderStub:
        def __init__(self) -> None:
            self.put_calls: list[tuple[str, dict[str, str]]] = []
            self.flushed: list[str] = []
            self.raise_policy_denied_versions = False
            self.raise_unavailable_versions = False

        async def get(self, reference: str) -> str:
            assert reference == "vault/github"
            return "provider-secret"

        async def put(self, reference: str, value: dict[str, str]) -> None:
            self.put_calls.append((reference, value))

        async def flush_cache(self, reference: str) -> None:
            self.flushed.append(reference)

        async def list_versions(self, reference: str) -> list[int]:
            assert reference
            if self.raise_policy_denied_versions:
                raise CredentialPolicyDeniedError(reference)
            if self.raise_unavailable_versions:
                raise CredentialUnavailableError(reference)
            return [1, 2]

    provider = build_provider(provider_type="github")
    provider.source = SimpleNamespace(value="env")
    service, _, auth_repository, *_ = build_oauth_service_fixture(auth_settings, provider=provider)
    secret_provider = SecretProviderStub()
    service.secret_provider = secret_provider  # type: ignore[assignment]

    assert await service._resolve_secret("vault/github") == "provider-secret"
    await service._put_secret("vault/github", "rotated")
    await service._flush_secret_cache("vault/github")
    assert await service._list_secret_versions("vault/github") == [1, 2]
    assert secret_provider.put_calls == [("vault/github", {"value": "rotated"})]
    assert secret_provider.flushed == ["vault/github"]
    secret_provider.raise_unavailable_versions = True
    assert await service._list_secret_versions("vault/github") == []
    secret_provider.raise_unavailable_versions = False
    secret_provider.raise_policy_denied_versions = True
    with pytest.raises(CredentialPolicyDeniedError):
        await service._list_secret_versions("vault/github")

    service.secret_provider = None
    with pytest.raises(ValidationError):
        service._require_secret_provider()

    assert service._provider_client("google") is service.google_provider
    assert service._provider_client("github") is service.github_provider
    signed = service._sign_state("nonce")
    assert service._verify_state(signed) == "nonce"
    with pytest.raises(OAuthStateInvalidError):
        service._verify_state(f"{signed}tampered")

    assert service._parse_optional_uuid(None) is None
    user_id = uuid4()
    assert service._parse_optional_uuid(str(user_id)) == user_id

    snapshot = service._provider_snapshot(provider)
    assert snapshot is not None
    assert snapshot["source"] == "env"
    assert service._provider_snapshot(None) is None
    assert service._diff_provider(None, snapshot)["created"] is True
    created_plain_secret_diff = service._diff_provider(
        None,
        {"client_secret_ref": "plain:created-secret"},
    )
    assert created_plain_secret_diff["client_secret_ref"] == "plain:<redacted>"
    assert "created-secret" not in str(created_plain_secret_diff)
    diff = service._diff_provider(
        {"display_name": "Old", "enabled": True},
        {"display_name": "New", "enabled": True},
    )
    assert diff == {"display_name": {"before": "Old", "after": "New"}}

    now = datetime.now(UTC)
    history = service._serialize_history_entry(
        SimpleNamespace(
            created_at=now,
            actor_id=user_id,
            action="provider_updated",
            changed_fields={
                "client_id": {"before": "old", "after": "new"},
                "ignored": "same",
            },
        )
    )
    assert history.before == {"client_id": "old"}
    assert history.after == {"client_id": "new"}

    auth_repository.roles_by_user[user_id] = [SimpleNamespace(role="viewer")]
    auth_repository.enrollments_by_user[user_id] = SimpleNamespace(status="active")
    identity = OAuthUserIdentity(
        external_id="external",
        email="fallback@example.com",
        name="Fallback User",
        locale="en",
        timezone="UTC",
        avatar_url="https://images.example.com/avatar.png",
        groups=[],
    )
    payload = await service._build_user_payload(
        user_id=user_id,
        platform_user=SimpleNamespace(
            email="fallback@example.com",
            display_name=None,
            status="active",
        ),
        identity=identity,
    )
    assert payload["display_name"] == "fallback"
    assert payload["roles"] == ["viewer"]
    assert payload["mfa_enrolled"] is True

    assert service._initial_user_status(
        OAuthUserIdentity(
            external_id="external",
            email="incomplete@example.com",
            name=None,
            locale=None,
            timezone=None,
            avatar_url=None,
            groups=[],
        )
    ).value == "pending_profile_completion"

    admin_approval_settings = auth_settings.model_copy(
        update={
            "accounts": auth_settings.accounts.model_copy(
                update={"signup_mode": "admin_approval"}
            )
        }
    )
    admin_service, *_ = build_oauth_service_fixture(admin_approval_settings, provider=provider)
    assert admin_service._initial_user_status(identity).value == "pending_approval"
    assert service._initial_user_status(identity).value == "active"
