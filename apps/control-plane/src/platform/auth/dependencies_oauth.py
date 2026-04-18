from __future__ import annotations

from platform.accounts.repository import AccountsRepository
from platform.auth.dependencies import (
    _get_producer,
    _get_redis_client,
    _get_settings,
    build_auth_service,
)
from platform.auth.repository import AuthRepository
from platform.auth.repository_oauth import OAuthRepository
from platform.auth.services.oauth_providers.github import GitHubOAuthProvider
from platform.auth.services.oauth_providers.google import GoogleOAuthProvider
from platform.auth.services.oauth_service import OAuthService
from platform.common.clients.redis import AsyncRedisClient
from platform.common.dependencies import get_db
from typing import cast

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession


def build_oauth_service(request: Request, db: AsyncSession) -> OAuthService:
    return OAuthService(
        repository=OAuthRepository(db),
        auth_repository=AuthRepository(db),
        accounts_repository=AccountsRepository(db),
        redis_client=_get_redis_client(request),
        settings=_get_settings(request),
        producer=_get_producer(request),
        auth_service=build_auth_service(request, db),
        google_provider=GoogleOAuthProvider(),
        github_provider=GitHubOAuthProvider(),
    )


async def get_oauth_service(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> OAuthService:
    return build_oauth_service(request, db)


async def rate_limit_callback(request: Request) -> None:
    redis_client = cast(AsyncRedisClient, request.app.state.clients["redis"])
    settings = _get_settings(request)
    client_ip = request.client.host if request.client is not None else "0.0.0.0"
    result = await redis_client.check_rate_limit(
        "oauth-callback",
        client_ip,
        settings.auth.oauth_rate_limit_max,
        settings.auth.oauth_rate_limit_window * 1000,
    )
    if result.allowed:
        return
    retry_after = max(1, (result.retry_after_ms + 999) // 1000)
    raise HTTPException(
        status_code=429,
        detail="Too many OAuth callback attempts",
        headers={"Retry-After": str(retry_after)},
    )
