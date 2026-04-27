from __future__ import annotations

from platform.common.logging import clear_context, set_context_from_request

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class CorrelationLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        tokens = set_context_from_request(request)
        try:
            return await call_next(request)
        finally:
            clear_context(tokens)
