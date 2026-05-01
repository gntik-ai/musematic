from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.auth.exceptions import InvalidRefreshTokenError
from platform.auth.tokens import create_access_token, create_token_pair, decode_token
from platform.common.tenant_context import TenantContext
from uuid import uuid4

import jwt
import pytest


def test_create_token_pair_and_decode_refresh(auth_settings) -> None:
    user_id = uuid4()
    session_id = uuid4()
    roles = [{"role": "viewer", "workspace_id": None}]

    access_token, refresh_token = create_token_pair(
        user_id=user_id,
        email="user@example.com",
        session_id=session_id,
        roles=roles,
        settings=auth_settings.auth,
    )

    access_claims = jwt.decode(
        access_token,
        auth_settings.auth.verification_key,
        algorithms=[auth_settings.auth.jwt_algorithm],
    )
    refresh_claims = decode_token(refresh_token, auth_settings.auth)

    assert access_claims["sub"] == str(user_id)
    assert access_claims["email"] == "user@example.com"
    assert access_claims["roles"] == roles
    assert access_claims["session_id"] == str(session_id)
    assert access_claims["type"] == "access"
    assert refresh_claims["sub"] == str(user_id)
    assert refresh_claims["session_id"] == str(session_id)
    assert refresh_claims["type"] == "refresh"


def test_create_access_token_includes_identity_context(auth_settings) -> None:
    token = create_access_token(
        user_id=uuid4(),
        email="agent@example.com",
        session_id=uuid4(),
        roles=[{"role": "agent", "workspace_id": None}],
        settings=auth_settings.auth,
        identity_type="agent",
        agent_purpose="retrieval",
    )

    claims = jwt.decode(
        token,
        auth_settings.auth.verification_key,
        algorithms=[auth_settings.auth.jwt_algorithm],
    )

    assert claims["identity_type"] == "agent"
    assert claims["agent_purpose"] == "retrieval"


def test_create_access_token_includes_tenant_claims(auth_settings) -> None:
    tenant_id = uuid4()
    token = create_access_token(
        user_id=uuid4(),
        email="tenant-user@example.com",
        session_id=uuid4(),
        roles=[{"role": "member", "workspace_id": None}],
        settings=auth_settings.auth,
        tenant=TenantContext(
            id=tenant_id,
            slug="acme",
            subdomain="acme",
            kind="enterprise",
            status="active",
            region="eu-central",
        ),
    )

    claims = jwt.decode(
        token,
        auth_settings.auth.verification_key,
        algorithms=[auth_settings.auth.jwt_algorithm],
    )

    assert claims["tenant_id"] == str(tenant_id)
    assert claims["tenant_slug"] == "acme"
    assert claims["tenant_kind"] == "enterprise"


def test_decode_token_rejects_invalid_and_expired_tokens(auth_settings) -> None:
    expired_refresh = jwt.encode(
        {
            "sub": str(uuid4()),
            "session_id": str(uuid4()),
            "jti": str(uuid4()),
            "type": "refresh",
            "iat": int(datetime.now(UTC).timestamp()),
            "exp": int((datetime.now(UTC) - timedelta(seconds=30)).timestamp()),
        },
        auth_settings.auth.signing_key,
        algorithm=auth_settings.auth.jwt_algorithm,
    )

    with pytest.raises(InvalidRefreshTokenError):
        decode_token("not-a-token", auth_settings.auth)

    with pytest.raises(InvalidRefreshTokenError):
        decode_token(expired_refresh, auth_settings.auth)


def test_token_helpers_require_signing_and_verification_keys() -> None:
    from platform.common.config import AuthSettings

    empty_settings = AuthSettings()

    with pytest.raises(InvalidRefreshTokenError, match="JWT signing key is not configured"):
        create_access_token(
            user_id=uuid4(),
            email="user@example.com",
            session_id=uuid4(),
            roles=[],
            settings=empty_settings,
        )

    with pytest.raises(InvalidRefreshTokenError, match="JWT verification key is not configured"):
        decode_token("token", empty_settings)


def test_decode_token_rejects_non_mapping_payload(monkeypatch, auth_settings) -> None:
    monkeypatch.setattr("platform.auth.tokens.jwt.decode", lambda *args, **kwargs: "not-a-dict")

    with pytest.raises(InvalidRefreshTokenError):
        decode_token("token", auth_settings.auth)
