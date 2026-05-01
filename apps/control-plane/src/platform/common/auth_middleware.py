from __future__ import annotations

import hashlib
from platform.auth.dependencies import resolve_api_key_identity
from platform.common.config import settings as default_settings
from typing import Any

import jwt
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

EXEMPT_PATHS: frozenset[str] = frozenset(
    {
        "/health",
        "/healthz",
        "/api/v1/healthz",
        "/api/openapi.json",
        "/api/docs",
        "/api/redoc",
        "/openapi.json",
        "/docs",
        "/redoc",
        "/api/v1/accounts/register",
        "/api/v1/accounts/verify-email",
        "/api/v1/accounts/resend-verification",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/mfa/verify",
        "/api/v1/auth/oauth/links",
        "/api/v1/security/audit-chain/public-key",
    }
)
EXEMPT_PREFIXES: frozenset[str] = frozenset({"/api/v1/public/"})

EXTERNAL_A2A_CERT_HEADERS: tuple[str, ...] = (
    "X-Client-Cert-Fingerprint",
    "X-SSL-Client-SHA1",
    "X-Forwarded-Client-Cert",
    "X-Client-Cert",
    "X-SSL-Client-Cert",
    "Ssl-Client-Cert",
    "X-ARR-ClientCert",
)


def _unauthorized_response(code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": {},
            }
        },
    )


def _with_principal_type(identity: dict[str, Any], principal_type: str) -> dict[str, Any]:
    payload = dict(identity)
    payload["principal_type"] = principal_type
    payload.setdefault("identity_type", principal_type)

    if principal_type == "service_account":
        principal_id = payload.get("service_account_id") or payload.get("sub")
        if isinstance(principal_id, str):
            payload.setdefault("principal_id", principal_id)
    elif principal_type == "user":
        principal_id = payload.get("sub")
        if isinstance(principal_id, str):
            payload.setdefault("principal_id", principal_id)

    return payload


def _resolve_external_a2a_identity(request: Request) -> dict[str, str] | None:
    for header_name in EXTERNAL_A2A_CERT_HEADERS:
        header_value = request.headers.get(header_name, "").strip()
        if not header_value:
            continue
        principal_id = hashlib.sha256(header_value.encode("utf-8")).hexdigest()
        return {
            "principal_type": "external_a2a",
            "identity_type": "external_a2a",
            "principal_id": principal_id,
            "auth_mechanism": "mtls",
        }
    return None


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request.state.origin_region = request.headers.get("X-Origin-Region") or "unknown"
        path = request.url.path
        settings = getattr(request.app.state, "settings", default_settings)
        public_invitation_endpoint = path.startswith("/api/v1/accounts/invitations/") and (
            request.method == "GET" or (request.method == "POST" and path.endswith("/accept"))
        )
        public_oauth_endpoint = path == "/api/v1/auth/oauth/providers" or (
            path.startswith("/api/v1/auth/oauth/")
            and request.method == "GET"
            and path.endswith(("/authorize", "/callback"))
        )
        public_a2a_endpoint = path == "/.well-known/agent.json" or path.startswith("/api/v1/a2a/")
        e2e_user_bootstrap_endpoint = (
            path == "/api/v1/_e2e/users"
            and request.method == "POST"
            and bool(getattr(settings, "feature_e2e_mode", False))
        )
        if public_a2a_endpoint:
            external_a2a_identity = _resolve_external_a2a_identity(request)
            if external_a2a_identity is not None:
                request.state.user = external_a2a_identity
        if (
            path in EXEMPT_PATHS
            or any(path.startswith(prefix) for prefix in EXEMPT_PREFIXES)
            or public_invitation_endpoint
            or public_oauth_endpoint
            or public_a2a_endpoint
            or e2e_user_bootstrap_endpoint
        ):
            return await call_next(request)

        api_key = request.headers.get("X-API-Key", "").strip()
        if api_key:
            identity = await resolve_api_key_identity(request, api_key)
            if identity is None:
                return _unauthorized_response("INVALID_API_KEY", "Invalid API key")
            request.state.user = _with_principal_type(identity, "service_account")
            return await call_next(request)

        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return _unauthorized_response("UNAUTHORIZED", "Missing authentication")

        token = header.removeprefix("Bearer ").strip()
        try:
            payload = jwt.decode(
                token,
                settings.auth.verification_key,
                algorithms=[settings.auth.jwt_algorithm],
            )
        except jwt.ExpiredSignatureError:
            return _unauthorized_response("TOKEN_EXPIRED", "Authentication token expired")
        except jwt.PyJWTError:
            return _unauthorized_response("UNAUTHORIZED", "Invalid authentication token")
        if not isinstance(payload, dict) or payload.get("type") not in {None, "access"}:
            return _unauthorized_response("UNAUTHORIZED", "Invalid authentication token")
        request_tenant = getattr(request.state, "tenant", None)
        token_tenant_id = payload.get("tenant_id")
        if (
            request_tenant is not None
            and token_tenant_id is not None
            and str(token_tenant_id) != str(request_tenant.id)
        ):
            return _unauthorized_response("tenant_mismatch", "Token tenant does not match host")
        jti = payload.get("jti")
        if isinstance(jti, str) and jti:
            redis_client = getattr(request.app.state, "clients", {}).get("redis")
            get = getattr(redis_client, "get", None)
            if callable(get):
                revoked = await get(f"jit:revoked:{jti}")
                if revoked is not None:
                    return _unauthorized_response("JIT_REVOKED", "JIT credential revoked")

        if request.state.origin_region == "unknown" and payload.get("region_hint"):
            request.state.origin_region = str(payload["region_hint"])
        request.state.user = _with_principal_type(payload, "user")
        return await call_next(request)
