from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from platform.auth.models import OAuthAuditEntry, OAuthLink, OAuthProvider
from platform.common.models.user import User as PlatformUser
from platform.main import create_app
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from tests.accounts_support import build_test_clients
from tests.auth_oauth_support import (
    GitHubProviderStub,
    GoogleProviderStub,
    decode_fragment_payload,
    extract_query_param,
)
from tests.auth_support import RecordingProducer


def _redis_url(redis_client) -> str:
    return redis_client._url or "redis://localhost:6379"


def _build_settings(auth_settings, *, database_url: str, redis_client, **auth_updates):
    return auth_settings.model_copy(
        update={
            "PLATFORM_DOMAIN": "testserver",
            "db": auth_settings.db.model_copy(update={"dsn": database_url}),
            "redis": auth_settings.redis.model_copy(
                update={"url": _redis_url(redis_client), "test_mode": "standalone"}
            ),
            "auth": auth_settings.auth.model_copy(update=auth_updates),
        }
    )


async def _insert_provider(
    session_factory: async_sessionmaker,
    *,
    provider_type: str,
    enabled: bool = True,
    default_role: str = "viewer",
    require_mfa: bool = False,
    domain_restrictions: list[str] | None = None,
    org_restrictions: list[str] | None = None,
    group_role_mapping: dict[str, str] | None = None,
) -> OAuthProvider:
    scopes = (
        ["openid", "email", "profile"] if provider_type == "google" else ["read:user", "user:email"]
    )
    async with session_factory() as session:
        provider = OAuthProvider(
            provider_type=provider_type,
            display_name="Google" if provider_type == "google" else "GitHub",
            enabled=enabled,
            client_id=f"{provider_type}-client",
            client_secret_ref=f"plain:{provider_type}-secret",
            redirect_uri=f"https://app.example.com/oauth/{provider_type}/callback",
            scopes=scopes,
            domain_restrictions=list(domain_restrictions or []),
            org_restrictions=list(org_restrictions or []),
            group_role_mapping=dict(group_role_mapping or {}),
            default_role=default_role,
            require_mfa=require_mfa,
        )
        session.add(provider)
        await session.commit()
        await session.refresh(provider)
        return provider


async def _create_platform_user(
    session_factory: async_sessionmaker,
    *,
    email: str,
    display_name: str,
    status: str = "active",
    user_id: UUID | None = None,
) -> PlatformUser:
    async with session_factory() as session:
        user = PlatformUser(
            id=user_id or uuid4(),
            email=email.lower(),
            display_name=display_name,
            status=status,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _create_link(
    session_factory: async_sessionmaker,
    *,
    user_id: UUID,
    provider_id: UUID,
    external_id: str,
    email: str,
    linked_at: datetime,
    last_login_at: datetime,
) -> OAuthLink:
    async with session_factory() as session:
        link = OAuthLink(
            user_id=user_id,
            provider_id=provider_id,
            external_id=external_id,
            external_email=email.lower(),
            external_name="Existing User",
            external_avatar_url=None,
            external_groups=[],
            linked_at=linked_at,
            last_login_at=last_login_at,
        )
        session.add(link)
        await session.commit()
        await session.refresh(link)
        return link


def _patch_provider_factories(
    monkeypatch: pytest.MonkeyPatch,
    *,
    google_provider: GoogleProviderStub | None = None,
    github_provider: GitHubProviderStub | None = None,
) -> tuple[GoogleProviderStub, GitHubProviderStub]:
    google = google_provider or GoogleProviderStub()
    github = github_provider or GitHubProviderStub()
    monkeypatch.setattr("platform.auth.dependencies_oauth.GoogleOAuthProvider", lambda **_: google)
    monkeypatch.setattr("platform.auth.dependencies_oauth.GitHubOAuthProvider", lambda **_: github)
    return google, github


@pytest.mark.integration
@pytest.mark.asyncio
async def test_google_new_user_provision_flow(
    monkeypatch: pytest.MonkeyPatch,
    auth_settings,
    session_factory: async_sessionmaker,
    redis_client,
    migrated_database_url: str,
) -> None:
    producer = RecordingProducer()
    google_provider, _ = _patch_provider_factories(
        monkeypatch,
        google_provider=GoogleProviderStub(
            identity={
                "sub": "google-subject-new-user",
                "email": "testuser@gmail.com",
                "name": "Test User",
                "picture": "https://images.example.com/testuser.png",
                "aud": "google-client",
                "email_verified": "true",
            }
        ),
    )
    monkeypatch.setattr(
        "platform.main._build_clients",
        lambda resolved: build_test_clients(redis_client, producer),
    )
    settings = _build_settings(
        auth_settings,
        database_url=migrated_database_url,
        redis_client=redis_client,
        oauth_state_secret="oauth-state-secret",
    )
    await _insert_provider(session_factory, provider_type="google", default_role="viewer")
    app = create_app(settings=settings)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            authorize = await client.get("/api/v1/auth/oauth/google/authorize")
            state = extract_query_param(authorize.json()["redirect_url"], "state")
            callback = await client.get(
                f"/api/v1/auth/oauth/google/callback?code=google-code&state={state}",
                headers={"Origin": "https://app.example.com", "User-Agent": "pytest-google/1.0"},
            )

    payload = decode_fragment_payload(callback.headers["location"])
    assert authorize.status_code == 200
    assert callback.status_code == 302
    assert callback.headers["location"].startswith(
        "https://app.example.com/auth/oauth/google/callback#oauth_session="
    )
    assert "session=" in callback.headers.get("set-cookie", "")
    assert payload["user"]["email"] == "testuser@gmail.com"
    assert google_provider.exchanged_codes[-1]["code"] == "google-code"

    async with session_factory() as session:
        user = await session.scalar(
            select(PlatformUser).where(PlatformUser.email == "testuser@gmail.com")
        )
        link = await session.scalar(
            select(OAuthLink).where(OAuthLink.external_id == "google-subject-new-user")
        )
        audit_entries = (
            (
                await session.execute(
                    select(OAuthAuditEntry).order_by(OAuthAuditEntry.created_at.asc())
                )
            )
            .scalars()
            .all()
        )

    assert user is not None
    assert link is not None
    assert link.user_id == user.id
    assert [entry.action for entry in audit_entries] == ["user_provisioned", "sign_in_succeeded"]
    serialized_audit = json.dumps(
        [
            {
                "action": entry.action,
                "failure_reason": entry.failure_reason,
                "changed_fields": entry.changed_fields or {},
            }
            for entry in audit_entries
        ]
    )
    for secret_like in ("google-access-token", "google-id-token", "google-code"):
        assert secret_like not in serialized_audit
    event_types = [event["event_type"] for event in producer.events]
    assert "auth.oauth.user_provisioned" in event_types
    assert event_types[-1] == "auth.oauth.sign_in_succeeded"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_github_new_user_provision_flow(
    monkeypatch: pytest.MonkeyPatch,
    auth_settings,
    session_factory: async_sessionmaker,
    redis_client,
    migrated_database_url: str,
) -> None:
    producer = RecordingProducer()
    _, github_provider = _patch_provider_factories(
        monkeypatch,
        github_provider=GitHubProviderStub(
            user_payload={
                "id": 9876,
                "login": "octocat",
                "name": "Octo Cat",
                "avatar_url": "https://images.example.com/octocat.png",
            },
            email="githubuser@example.com",
        ),
    )
    monkeypatch.setattr(
        "platform.main._build_clients",
        lambda resolved: build_test_clients(redis_client, producer),
    )
    settings = _build_settings(
        auth_settings,
        database_url=migrated_database_url,
        redis_client=redis_client,
        oauth_state_secret="oauth-state-secret",
    )
    await _insert_provider(session_factory, provider_type="github")
    app = create_app(settings=settings)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            authorize = await client.get("/api/v1/auth/oauth/github/authorize")
            state = extract_query_param(authorize.json()["redirect_url"], "state")
            callback = await client.get(
                f"/api/v1/auth/oauth/github/callback?code=github-code&state={state}",
                headers={"Origin": "https://app.example.com", "User-Agent": "pytest-github/1.0"},
            )

    payload = decode_fragment_payload(callback.headers["location"])
    assert authorize.status_code == 200
    assert callback.status_code == 302
    assert payload["user"]["email"] == "githubuser@example.com"

    async with session_factory() as session:
        user = await session.scalar(
            select(PlatformUser).where(PlatformUser.email == "githubuser@example.com")
        )
        link = await session.scalar(select(OAuthLink).where(OAuthLink.external_id == "9876"))

    assert user is not None
    assert link is not None
    assert link.user_id == user.id
    assert github_provider.auth_urls


@pytest.mark.integration
@pytest.mark.asyncio
async def test_returning_user_sign_in_updates_existing_link(
    monkeypatch: pytest.MonkeyPatch,
    auth_settings,
    session_factory: async_sessionmaker,
    redis_client,
    migrated_database_url: str,
) -> None:
    producer = RecordingProducer()
    _patch_provider_factories(
        monkeypatch,
        google_provider=GoogleProviderStub(
            identity={
                "sub": "google-returning-sub",
                "email": "existing@example.com",
                "name": "Existing User",
                "picture": "https://images.example.com/existing.png",
                "aud": "google-client",
                "email_verified": "true",
            }
        ),
    )
    monkeypatch.setattr(
        "platform.main._build_clients",
        lambda resolved: build_test_clients(redis_client, producer),
    )
    settings = _build_settings(
        auth_settings,
        database_url=migrated_database_url,
        redis_client=redis_client,
        oauth_state_secret="oauth-state-secret",
    )
    provider = await _insert_provider(session_factory, provider_type="google")
    user = await _create_platform_user(
        session_factory,
        email="existing@example.com",
        display_name="Existing User",
    )
    previous_login = datetime.now(UTC) - timedelta(days=1)
    await _create_link(
        session_factory,
        user_id=user.id,
        provider_id=provider.id,
        external_id="google-returning-sub",
        email="existing@example.com",
        linked_at=previous_login,
        last_login_at=previous_login,
    )
    app = create_app(settings=settings)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            authorize = await client.get("/api/v1/auth/oauth/google/authorize")
            state = extract_query_param(authorize.json()["redirect_url"], "state")
            callback = await client.get(
                f"/api/v1/auth/oauth/google/callback?code=google-code&state={state}",
                headers={"Origin": "https://app.example.com", "User-Agent": "pytest-returning/1.0"},
            )

    payload = decode_fragment_payload(callback.headers["location"])
    assert callback.status_code == 302
    assert payload["user"]["id"] == str(user.id)

    async with session_factory() as session:
        count_users = await session.scalar(
            select(func.count())
            .select_from(PlatformUser)
            .where(PlatformUser.email == "existing@example.com")
        )
        refreshed_link = await session.scalar(
            select(OAuthLink).where(OAuthLink.external_id == "google-returning-sub")
        )

    assert int(count_users or 0) == 1
    assert refreshed_link is not None
    assert refreshed_link.last_login_at is not None
    assert refreshed_link.last_login_at > previous_login
    event_types = [event["event_type"] for event in producer.events]
    assert "auth.user.authenticated" in event_types
    assert event_types[-1] == "auth.oauth.sign_in_succeeded"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_callback_rejects_expired_or_tampered_state(
    monkeypatch: pytest.MonkeyPatch,
    auth_settings,
    session_factory: async_sessionmaker,
    redis_client,
    migrated_database_url: str,
) -> None:
    producer = RecordingProducer()
    _patch_provider_factories(monkeypatch)
    monkeypatch.setattr(
        "platform.main._build_clients",
        lambda resolved: build_test_clients(redis_client, producer),
    )
    settings = _build_settings(
        auth_settings,
        database_url=migrated_database_url,
        redis_client=redis_client,
        oauth_state_secret="oauth-state-secret",
    )
    await _insert_provider(session_factory, provider_type="google")
    app = create_app(settings=settings)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            authorize = await client.get("/api/v1/auth/oauth/google/authorize")
            state = extract_query_param(authorize.json()["redirect_url"], "state")
            nonce, signature = state.split(".", 1)
            await redis_client.delete(f"oauth:state:{nonce}")
            expired = await client.get(
                f"/api/v1/auth/oauth/google/callback?code=google-code&state={state}",
                headers={"Origin": "https://app.example.com"},
            )
            tampered = await client.get(
                f"/api/v1/auth/oauth/google/callback?code=google-code&state={nonce}.{signature[:-1]}x",
                headers={"Origin": "https://app.example.com"},
            )

    assert expired.status_code == 302
    assert expired.headers["location"] == (
        "https://app.example.com/auth/oauth/google/callback?error=oauth_state_expired"
    )
    assert tampered.status_code == 302
    assert tampered.headers["location"] == (
        "https://app.example.com/auth/oauth/google/callback?error=oauth_state_invalid"
    )

    async with session_factory() as session:
        failures = (
            (
                await session.execute(
                    select(OAuthAuditEntry).where(OAuthAuditEntry.action == "sign_in_failed")
                )
            )
            .scalars()
            .all()
        )

    assert {entry.failure_reason for entry in failures} == {
        "OAUTH_STATE_EXPIRED",
        "OAUTH_STATE_INVALID",
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_callback_rejects_provider_disabled_mid_flow_and_duplicate_email(
    monkeypatch: pytest.MonkeyPatch,
    auth_settings,
    session_factory: async_sessionmaker,
    redis_client,
    migrated_database_url: str,
) -> None:
    producer = RecordingProducer()
    _patch_provider_factories(
        monkeypatch,
        google_provider=GoogleProviderStub(
            identity={
                "sub": "google-duplicate-sub",
                "email": "duplicate@example.com",
                "name": "Duplicate User",
                "picture": "https://images.example.com/duplicate.png",
                "aud": "google-client",
                "email_verified": "true",
            }
        ),
    )
    monkeypatch.setattr(
        "platform.main._build_clients",
        lambda resolved: build_test_clients(redis_client, producer),
    )
    settings = _build_settings(
        auth_settings,
        database_url=migrated_database_url,
        redis_client=redis_client,
        oauth_state_secret="oauth-state-secret",
    )
    provider = await _insert_provider(session_factory, provider_type="google")
    await _create_platform_user(
        session_factory,
        email="duplicate@example.com",
        display_name="Duplicate User",
    )
    app = create_app(settings=settings)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            authorize = await client.get("/api/v1/auth/oauth/google/authorize")
            state = extract_query_param(authorize.json()["redirect_url"], "state")
            nonce = state.split(".", 1)[0]
            async with session_factory() as session:
                live_provider = await session.scalar(
                    select(OAuthProvider).where(OAuthProvider.id == provider.id)
                )
                assert live_provider is not None
                live_provider.enabled = False
                await session.commit()
            disabled = await client.get(
                f"/api/v1/auth/oauth/google/callback?code=google-code&state={state}",
                headers={"Origin": "https://app.example.com"},
            )
            remaining_state = await redis_client.get(f"oauth:state:{nonce}")

    assert disabled.status_code == 302
    assert (
        disabled.headers["location"]
        == "https://app.example.com/auth/oauth/google/callback?error=oauth_provider_disabled"
    )
    assert remaining_state is None

    async with session_factory() as session:
        live_provider = await session.scalar(
            select(OAuthProvider).where(OAuthProvider.id == provider.id)
        )
        assert live_provider is not None
        live_provider.enabled = True
        await session.commit()

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            authorize = await client.get("/api/v1/auth/oauth/google/authorize")
            state = extract_query_param(authorize.json()["redirect_url"], "state")
            conflict = await client.get(
                f"/api/v1/auth/oauth/google/callback?code=google-code&state={state}",
                headers={"Origin": "https://app.example.com"},
            )

    assert conflict.status_code == 302
    assert conflict.headers["location"] == (
        "https://app.example.com/auth/oauth/google/callback?error=oauth_link_conflict"
    )

    async with session_factory() as session:
        link_count = await session.scalar(select(func.count()).select_from(OAuthLink))
        failure_reasons = (
            (
                await session.execute(
                    select(OAuthAuditEntry.failure_reason).where(
                        OAuthAuditEntry.action == "sign_in_failed"
                    )
                )
            )
            .scalars()
            .all()
        )

    assert int(link_count or 0) == 0
    assert "OAUTH_PROVIDER_DISABLED" in set(failure_reasons)
    assert "OAUTH_LINK_CONFLICT" in set(failure_reasons)
