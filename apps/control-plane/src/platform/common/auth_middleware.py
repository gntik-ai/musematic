from __future__ import annotations

from platform.auth.dependencies import resolve_api_key_identity
from platform.common.config import settings as default_settings

import jwt
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

EXEMPT_PATHS: set[str] = {
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/api/v1/auth/mfa/verify",
}


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


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        api_key = request.headers.get("X-API-Key", "").strip()
        if api_key:
            identity = await resolve_api_key_identity(request, api_key)
            if identity is None:
                return _unauthorized_response("INVALID_API_KEY", "Invalid API key")
            request.state.user = identity
            return await call_next(request)

        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return _unauthorized_response("UNAUTHORIZED", "Missing authentication")

        token = header.removeprefix("Bearer ").strip()
        settings = getattr(request.app.state, "settings", default_settings)
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

        request.state.user = payload
        return await call_next(request)
