from __future__ import annotations

from platform.common.config import settings as default_settings

import jwt
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

EXEMPT_PATHS: set[str] = {"/health", "/docs", "/openapi.json", "/redoc"}


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

        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return _unauthorized_response("UNAUTHORIZED", "Missing authentication")

        token = header.removeprefix("Bearer ").strip()
        settings = getattr(request.app.state, "settings", default_settings)
        try:
            payload = jwt.decode(
                token,
                settings.auth.jwt_secret_key,
                algorithms=[settings.auth.jwt_algorithm],
            )
        except jwt.ExpiredSignatureError:
            return _unauthorized_response("TOKEN_EXPIRED", "Authentication token expired")
        except jwt.PyJWTError:
            return _unauthorized_response("UNAUTHORIZED", "Invalid authentication token")

        request.state.user = payload
        return await call_next(request)
