from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.auth.exceptions import InvalidRefreshTokenError
from platform.common.config import AuthSettings
from typing import Any
from uuid import UUID, uuid4

import jwt


def _signing_key(settings: AuthSettings) -> str:
    if settings.jwt_private_key:
        return settings.jwt_private_key
    if settings.jwt_secret_key:
        return settings.jwt_secret_key
    raise InvalidRefreshTokenError("JWT signing key is not configured")


def _verification_key(settings: AuthSettings) -> str:
    if settings.jwt_public_key:
        return settings.jwt_public_key
    if settings.jwt_secret_key:
        return settings.jwt_secret_key
    if settings.jwt_private_key:
        return settings.jwt_private_key
    raise InvalidRefreshTokenError("JWT verification key is not configured")


def _normalize_roles(roles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for role in roles:
        normalized.append(
            {
                "role": str(role["role"]),
                "workspace_id": (
                    str(role["workspace_id"]) if role.get("workspace_id") is not None else None
                ),
            }
        )
    return normalized


def create_access_token(
    user_id: UUID,
    email: str,
    session_id: UUID,
    roles: list[dict[str, Any]],
    settings: AuthSettings,
    *,
    identity_type: str = "user",
    agent_purpose: str | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "roles": _normalize_roles(roles),
        "session_id": str(session_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.access_token_ttl)).timestamp()),
        "type": "access",
        "identity_type": identity_type,
    }
    if agent_purpose is not None:
        payload["agent_purpose"] = agent_purpose
    return jwt.encode(payload, _signing_key(settings), algorithm=settings.jwt_algorithm)


def create_refresh_token(
    user_id: UUID,
    session_id: UUID,
    settings: AuthSettings,
    *,
    refresh_jti: UUID | None = None,
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "session_id": str(session_id),
        "jti": str(refresh_jti or uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.refresh_token_ttl)).timestamp()),
        "type": "refresh",
    }
    return jwt.encode(payload, _signing_key(settings), algorithm=settings.jwt_algorithm)


def create_token_pair(
    user_id: UUID,
    email: str,
    session_id: UUID,
    roles: list[dict[str, Any]],
    settings: AuthSettings,
) -> tuple[str, str]:
    access_token = create_access_token(user_id, email, session_id, roles, settings)
    refresh_token = create_refresh_token(user_id, session_id, settings)
    return access_token, refresh_token


def decode_token(token: str, settings: AuthSettings) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            _verification_key(settings),
            algorithms=[settings.jwt_algorithm],
        )
    except (jwt.ExpiredSignatureError, jwt.DecodeError, jwt.InvalidTokenError) as exc:
        raise InvalidRefreshTokenError() from exc
    if not isinstance(payload, dict):
        raise InvalidRefreshTokenError()
    return payload
