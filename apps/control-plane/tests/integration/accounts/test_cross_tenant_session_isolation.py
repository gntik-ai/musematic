from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

CONTROL_PLANE = Path(__file__).resolve().parents[3]


def _read(relative: str) -> str:
    return (CONTROL_PLANE / relative).read_text(encoding="utf-8")


def test_auth_middleware_rejects_tokens_bound_to_a_different_resolved_tenant() -> None:
    middleware = _read("src/platform/common/auth_middleware.py")

    assert "request_tenant = getattr(request.state, \"tenant\", None)" in middleware
    assert 'token_tenant_id = payload.get("tenant_id")' in middleware
    assert "str(token_tenant_id) != str(request_tenant.id)" in middleware
    assert '_unauthorized_response("tenant_mismatch"' in middleware


def test_oauth_session_cookie_is_scoped_to_the_resolved_tenant_subdomain() -> None:
    router = _read("src/platform/auth/router_oauth.py")

    assert "response.set_cookie(" in router
    assert "domain=_tenant_cookie_domain(request)" in router
    assert "return f\"{tenant.subdomain}." in router
