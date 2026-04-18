from __future__ import annotations

from contextvars import ContextVar
from uuid import UUID, uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")
goal_id_var: ContextVar[str] = ContextVar("goal_id", default="")


class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        correlation_id = request.headers.get("X-Correlation-ID", "").strip() or str(uuid4())
        goal_id_header = request.headers.get("X-Goal-Id", "").strip()
        correlation_token = correlation_id_var.set(correlation_id)
        goal_token = None
        resolved_goal_id: str | None = None
        if goal_id_header:
            try:
                resolved_goal_id = str(UUID(goal_id_header))
            except ValueError:
                correlation_id_var.reset(correlation_token)
                return JSONResponse(
                    status_code=422,
                    content={"error": "invalid X-Goal-Id header"},
                )
            goal_token = goal_id_var.set(resolved_goal_id)
            request.state.goal_id = resolved_goal_id
        request.state.correlation_id = correlation_id
        try:
            response = await call_next(request)
        finally:
            if goal_token is not None:
                goal_id_var.reset(goal_token)
            correlation_id_var.reset(correlation_token)
        response.headers["X-Correlation-ID"] = correlation_id
        if resolved_goal_id is not None:
            response.headers["X-Goal-Id"] = resolved_goal_id
        response.headers["X-Request-ID"] = str(uuid4())
        return response
