from __future__ import annotations

from datetime import UTC, datetime
from email.utils import format_datetime
from platform.common.api_versioning.registry import DeprecationMarker, get_marker

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Match


class ApiVersioningMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        marker = self._resolve_marker(request)
        now = datetime.now(UTC)
        if marker is not None and now >= marker.sunset:
            response: Response = JSONResponse(
                status_code=410,
                content={
                    "error": "endpoint_sunset",
                    "successor": marker.successor_path,
                    "sunset_date": marker.sunset.isoformat(),
                },
            )
            self._decorate(response, marker)
            return response

        response = await call_next(request)
        if marker is not None:
            self._decorate(response, marker)
        return response

    @staticmethod
    def _resolve_marker(request: Request) -> DeprecationMarker | None:
        router = getattr(request.app, "router", None)
        if router is None:
            return None
        for route in router.routes:
            match, _child_scope = route.matches(request.scope)
            if match is Match.FULL:
                return get_marker(getattr(route, "unique_id", None))
        return None

    @staticmethod
    def _decorate(response: Response, marker: DeprecationMarker) -> None:
        response.headers["Deprecation"] = "true"
        response.headers["Sunset"] = format_datetime(marker.sunset.astimezone(UTC), usegmt=True)
        if marker.successor_path:
            response.headers["Link"] = f'<{marker.successor_path}>; rel="successor-version"'
