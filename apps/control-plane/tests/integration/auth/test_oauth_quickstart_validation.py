from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from platform.auth.models import OAuthAuditEntry, OAuthLink, OAuthProvider, UserCredential, UserRole
from platform.auth.password import hash_password
from platform.common.models.user import User as PlatformUser
from platform.main import create_app
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from tests.accounts_support import build_test_clients, issue_access_token
from tests.auth_oauth_support import (
    GitHubProviderStub,
    GoogleProviderStub,
    decode_fragment_payload,
    extract_query_param,
)
from tests.auth_support import RecordingProducer, role_claim


def _redis_url(redis_client) -> str:
    return redis_client._url or "redis://localhost:6379"


def _build_settings(auth_settings, *, database_url: str, redis_client, **auth_updates):
    return auth_settings.model_copy(
        update={
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


async def _create_local_auth_method(
    session_factory: async_sessionmaker,
    *,
    user_id: UUID,
    email: str,
    password: str,
    role: str = "viewer",
) -> None:
    async with session_factory() as session:
        session.add(
            UserCredential(
                user_id=user_id,
                email=email.lower(),
                password_hash=hash_password(password),
                is_active=True,
            )
        )
        session.add(UserRole(user_id=user_id, role=role, workspace_id=None))
        await session.commit()


async def _create_link(
    session_factory: async_sessionmaker,
    *,
    user_id: UUID,
    provider_id: UUID,
    external_id: str,
    email: str,
) -> OAuthLink:
    now = datetime.now(UTC)
    async with session_factory() as session:
        link = OAuthLink(
            user_id=user_id,
            provider_id=provider_id,
            external_id=external_id,
            external_email=email.lower(),
            external_name="Existing User",
            external_avatar_url=None,
            external_groups=[],
            linked_at=now,
            last_login_at=now,
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
    monkeypatch.setattr("platform.auth.dependencies_oauth.GoogleOAuthProvider", lambda: google)
    monkeypatch.setattr("platform.auth.dependencies_oauth.GitHubOAuthProvider", lambda: github)
    return google, github


def _auth_headers(settings, user_id: UUID, role: str = "viewer") -> dict[str, str]:
    token = issue_access_token(settings, user_id, [role_claim(role)])
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_quickstart_account_linking_and_unlink_flow(
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
                "sub": "google-linked-subject",
                "email": "linked@example.com",
                "name": "Linked User",
                "picture": "https://images.example.com/linked.png",
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
    await _insert_provider(session_factory, provider_type="google")
    user = await _create_platform_user(
        session_factory,
        email="linked@example.com",
        display_name="Linked User",
    )
    await _create_local_auth_method(
        session_factory,
        user_id=user.id,
        email="linked@example.com",
        password="SecureP@ss123",
    )
    app = create_app(settings=settings)
    headers = _auth_headers(settings, user.id)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            link_begin = await client.post("/api/v1/auth/oauth/google/link", headers=headers)
            link_state = extract_query_param(link_begin.json()["redirect_url"], "state")
            link_callback = await client.get(
                f"/api/v1/auth/oauth/google/callback?code=google-link&state={link_state}",
                headers={"Origin": "https://app.example.com", "User-Agent": "link-ui"},
            )

            authorize = await client.get("/api/v1/auth/oauth/google/authorize")
            sign_in_state = extract_query_param(authorize.json()["redirect_url"], "state")
            sign_in = await client.get(
                f"/api/v1/auth/oauth/google/callback?code=google-login&state={sign_in_state}",
                headers={"Origin": "https://app.example.com", "User-Agent": "signin-ui"},
            )

            unlink = await client.delete("/api/v1/auth/oauth/google/link", headers=headers)
            local_login = await client.post(
                "/api/v1/auth/login",
                json={"email": "linked@example.com", "password": "SecureP@ss123"},
            )
            post_unlink_authorize = await client.get("/api/v1/auth/oauth/google/authorize")
            post_unlink_state = extract_query_param(
                post_unlink_authorize.json()["redirect_url"], "state"
            )
            post_unlink_sign_in = await client.get(
                "/api/v1/auth/oauth/google/callback"
                f"?code=google-after-unlink&state={post_unlink_state}",
                headers={"Origin": "https://app.example.com", "User-Agent": "revisit-ui"},
            )

    sign_in_payload = decode_fragment_payload(sign_in.headers["location"])
    assert link_begin.status_code == 200
    assert link_callback.status_code == 302
    assert link_callback.headers["location"] == "https://app.example.com/profile?message=oauth_linked"
    assert sign_in.status_code == 302
    assert sign_in_payload["user"]["id"] == str(user.id)
    assert unlink.status_code == 204
    assert local_login.status_code == 200
    assert post_unlink_sign_in.status_code == 302
    assert post_unlink_sign_in.headers["location"] == (
        "https://app.example.com/login?error=oauth_link_conflict"
    )

    async with session_factory() as session:
        user_count = await session.scalar(
            select(func.count())
            .select_from(PlatformUser)
            .where(PlatformUser.email == "linked@example.com")
        )
        link_count = await session.scalar(select(func.count()).select_from(OAuthLink))
        actions = (
            (
                await session.execute(
                    select(OAuthAuditEntry.action).order_by(OAuthAuditEntry.created_at.asc())
                )
            )
            .scalars()
            .all()
        )

    assert int(user_count or 0) == 1
    assert int(link_count or 0) == 0
    assert "account_linked" in actions
    assert "account_unlinked" in actions
    assert "sign_in_succeeded" in actions


@pytest.mark.integration
@pytest.mark.asyncio
async def test_quickstart_google_domain_restriction_rejection(
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
                "sub": "google-domain-reject",
                "email": "user@othercompany.com",
                "name": "Other Company",
                "picture": "https://images.example.com/other.png",
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
    await _insert_provider(
        session_factory,
        provider_type="google",
        domain_restrictions=["company.com"],
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
                headers={"Origin": "https://app.example.com", "User-Agent": "domain-ui"},
            )

    assert callback.status_code == 302
    assert callback.headers["location"] == "https://app.example.com/login?error=domain_not_allowed"

    async with session_factory() as session:
        user_count = await session.scalar(
            select(func.count())
            .select_from(PlatformUser)
            .where(PlatformUser.email == "user@othercompany.com")
        )
        link_count = await session.scalar(select(func.count()).select_from(OAuthLink))
        latest_audit = await session.scalar(
            select(OAuthAuditEntry).order_by(OAuthAuditEntry.created_at.desc())
        )

    assert int(user_count or 0) == 0
    assert int(link_count or 0) == 0
    assert latest_audit is not None
    assert latest_audit.action == "sign_in_failed"
    assert latest_audit.failure_reason == "DOMAIN_NOT_ALLOWED"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_quickstart_google_group_role_mapping_is_applied(
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
                "sub": "google-engineer",
                "email": "engineer@company.com",
                "name": "Engineer User",
                "picture": "https://images.example.com/engineer.png",
                "aud": "google-client",
                "email_verified": "true",
            },
            groups=["engineering", "security"],
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
    await _insert_provider(
        session_factory,
        provider_type="google",
        default_role="viewer",
        group_role_mapping={"engineering": "workspace_admin"},
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
                headers={"Origin": "https://app.example.com", "User-Agent": "groups-ui"},
            )

    payload = decode_fragment_payload(callback.headers["location"])
    user_id = UUID(payload["user"]["id"])

    async with session_factory() as session:
        role = await session.scalar(select(UserRole).where(UserRole.user_id == user_id))
        link = await session.scalar(
            select(OAuthLink).where(OAuthLink.external_id == "google-engineer")
        )

    assert callback.status_code == 302
    assert role is not None
    assert role.role == "workspace_admin"
    assert link is not None
    assert link.external_groups == ["engineering", "security"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_quickstart_github_org_restriction_rejection(
    monkeypatch: pytest.MonkeyPatch,
    auth_settings,
    session_factory: async_sessionmaker,
    redis_client,
    migrated_database_url: str,
) -> None:
    producer = RecordingProducer()
    _patch_provider_factories(
        monkeypatch,
        github_provider=GitHubProviderStub(
            user_payload={
                "id": 555,
                "login": "outsider",
                "name": "Outsider",
                "avatar_url": "https://images.example.com/outsider.png",
            },
            email="outsider@example.com",
            memberships={"my-org": False},
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
    await _insert_provider(
        session_factory,
        provider_type="github",
        org_restrictions=["my-org"],
    )
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
                headers={"Origin": "https://app.example.com", "User-Agent": "org-ui"},
            )

    assert callback.status_code == 302
    assert callback.headers["location"] == "https://app.example.com/login?error=org_not_allowed"

    async with session_factory() as session:
        user_count = await session.scalar(
            select(func.count())
            .select_from(PlatformUser)
            .where(PlatformUser.email == "outsider@example.com")
        )
        latest_audit = await session.scalar(
            select(OAuthAuditEntry).order_by(OAuthAuditEntry.created_at.desc())
        )

    assert int(user_count or 0) == 0
    assert latest_audit is not None
    assert latest_audit.failure_reason == "ORG_NOT_ALLOWED"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_quickstart_last_auth_method_unlink_rejected(
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
    provider = await _insert_provider(session_factory, provider_type="google")
    user = await _create_platform_user(
        session_factory,
        email="oauth-only@example.com",
        display_name="OAuth Only",
    )
    await _create_link(
        session_factory,
        user_id=user.id,
        provider_id=provider.id,
        external_id="oauth-only-subject",
        email="oauth-only@example.com",
    )
    app = create_app(settings=settings)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.delete(
                "/api/v1/auth/oauth/google/link",
                headers=_auth_headers(settings, user.id),
            )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "OAUTH_LAST_AUTH_METHOD"

    async with session_factory() as session:
        link_count = await session.scalar(select(func.count()).select_from(OAuthLink))

    assert int(link_count or 0) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_quickstart_admin_provider_roundtrip_and_redaction(
    monkeypatch: pytest.MonkeyPatch,
    auth_settings,
    session_factory: async_sessionmaker,
    redis_client,
    migrated_database_url: str,
) -> None:
    producer = RecordingProducer()
    secret_value = "ACTUAL_RESOLVED_SECRET_VALUE_DO_NOT_LEAK"
    monkeypatch.setenv("OAUTH_SECRET_VAULT_OAUTH_GOOGLE_CLIENT_SECRET", secret_value)
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
    app = create_app(settings=settings)
    admin_headers = _auth_headers(settings, uuid4(), role="platform_admin")
    create_payload = {
        "display_name": "Sign in with Google",
        "enabled": False,
        "client_id": "test-client-id",
        "client_secret_ref": "vault:oauth/google/client-secret",
        "redirect_uri": "https://platform.example.com/api/v1/auth/oauth/google/callback",
        "scopes": ["openid", "email", "profile"],
        "domain_restrictions": [],
        "org_restrictions": [],
        "group_role_mapping": {},
        "default_role": "member",
        "require_mfa": False,
    }
    enable_payload = {**create_payload, "enabled": True}

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            created = await client.put(
                "/api/v1/admin/oauth/providers/google",
                headers=admin_headers,
                json=create_payload,
            )
            admin_list = await client.get(
                "/api/v1/admin/oauth/providers",
                headers=admin_headers,
            )
            audit_list = await client.get(
                "/api/v1/admin/oauth/audit?limit=10",
                headers=admin_headers,
            )
            public_before = await client.get("/api/v1/auth/oauth/providers")
            enabled = await client.put(
                "/api/v1/admin/oauth/providers/google",
                headers=admin_headers,
                json=enable_payload,
            )
            public_after = await client.get("/api/v1/auth/oauth/providers")

    assert created.status_code == 201
    assert enabled.status_code == 200
    assert public_before.json() == {"providers": []}
    assert public_after.json() == {
        "providers": [{"provider_type": "google", "display_name": "Sign in with Google"}]
    }
    assert secret_value not in admin_list.text
    assert secret_value not in audit_list.text

    audit_payload = audit_list.json()["items"]
    assert audit_payload
    assert audit_payload[0]["action"] == "provider_configured"
    assert (
        audit_payload[0]["changed_fields"]["client_secret_ref"]
        == "vault:oauth/google/client-secret"
    )

    async with session_factory() as session:
        provider = await session.scalar(
            select(OAuthProvider).where(OAuthProvider.provider_type == "google")
        )

    assert provider is not None
    assert provider.enabled is True
    assert provider.client_secret_ref == "vault:oauth/google/client-secret"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_quickstart_audit_entries_do_not_contain_token_values(
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
                "sub": "google-audit-subject",
                "email": "audit@example.com",
                "name": "Audit User",
                "picture": "https://images.example.com/audit.png",
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
    await _insert_provider(session_factory, provider_type="google")
    app = create_app(settings=settings)
    token_pattern = re.compile(r"[A-Za-z0-9\-_]{64,}")

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            authorize = await client.get("/api/v1/auth/oauth/google/authorize")
            state = extract_query_param(authorize.json()["redirect_url"], "state")
            callback = await client.get(
                f"/api/v1/auth/oauth/google/callback?code=audit-code&state={state}",
                headers={"Origin": "https://app.example.com", "User-Agent": "audit-ui"},
            )

    assert callback.status_code == 302

    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(OAuthAuditEntry).order_by(OAuthAuditEntry.created_at.asc())
                )
            )
            .scalars()
            .all()
        )

    assert rows
    for row in rows:
        text = json.dumps(
            {
                "provider_type": row.provider_type,
                "external_id": row.external_id,
                "action": row.action,
                "outcome": row.outcome,
                "failure_reason": row.failure_reason,
                "source_ip": row.source_ip,
                "user_agent": row.user_agent,
                "changed_fields": row.changed_fields,
            },
            sort_keys=True,
        )
        assert not token_pattern.search(text), text
        for secret_like in ("google-access-token", "google-id-token", "audit-code"):
            assert secret_like not in text
