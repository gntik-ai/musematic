from __future__ import annotations

from platform.auth.models import OAuthProvider
from platform.main import create_app

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from tests.accounts_support import build_test_clients
from tests.auth_oauth_support import GoogleProviderStub, extract_query_param
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


async def _insert_google_provider(session_factory: async_sessionmaker) -> None:
    async with session_factory() as session:
        session.add(
            OAuthProvider(
                provider_type="google",
                display_name="Google",
                enabled=True,
                client_id="google-client",
                client_secret_ref="plain:google-secret",
                redirect_uri="https://app.example.com/oauth/google/callback",
                scopes=["openid", "email", "profile"],
                domain_restrictions=[],
                org_restrictions=[],
                group_role_mapping={},
                default_role="viewer",
                require_mfa=False,
            )
        )
        await session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_callback_rate_limit_429_with_retry_after(
    monkeypatch: pytest.MonkeyPatch,
    auth_settings,
    session_factory: async_sessionmaker,
    redis_client,
    migrated_database_url: str,
) -> None:
    producer = RecordingProducer()
    google_provider = GoogleProviderStub()
    monkeypatch.setattr(
        "platform.auth.dependencies_oauth.GoogleOAuthProvider",
        lambda **_: google_provider,
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
        oauth_rate_limit_max=0,
        oauth_rate_limit_window=60,
    )
    await _insert_google_provider(session_factory)
    app = create_app(settings=settings)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            authorize = await client.get("/api/v1/auth/oauth/google/authorize")
            state = extract_query_param(authorize.json()["redirect_url"], "state")
            response = await client.get(
                f"/api/v1/auth/oauth/google/callback?code=google-code&state={state}"
            )

    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) >= 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rate_limit_does_not_consume_state(
    monkeypatch: pytest.MonkeyPatch,
    auth_settings,
    session_factory: async_sessionmaker,
    redis_client,
    migrated_database_url: str,
) -> None:
    producer = RecordingProducer()
    google_provider = GoogleProviderStub()
    monkeypatch.setattr(
        "platform.auth.dependencies_oauth.GoogleOAuthProvider",
        lambda **_: google_provider,
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
        oauth_rate_limit_max=0,
        oauth_rate_limit_window=60,
    )
    await _insert_google_provider(session_factory)
    app = create_app(settings=settings)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            authorize = await client.get("/api/v1/auth/oauth/google/authorize")
            state = extract_query_param(authorize.json()["redirect_url"], "state")
            nonce = state.split(".", 1)[0]
            response = await client.get(
                f"/api/v1/auth/oauth/google/callback?code=google-code&state={state}"
            )
            raw_state = await redis_client.get(f"oauth:state:{nonce}")

    assert response.status_code == 429
    assert raw_state is not None
