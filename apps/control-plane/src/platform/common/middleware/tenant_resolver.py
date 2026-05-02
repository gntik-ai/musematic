from __future__ import annotations

import asyncio
import random
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.tenant_context import current_tenant
from platform.tenants.resolver import TenantResolver
from typing import Any

from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request

OPAQUE_404_BODY = b'{"detail":"Not Found"}'
OPAQUE_404_HEADERS = {
    "content-type": "application/json",
    "content-length": str(len(OPAQUE_404_BODY)),
}
__all__ = [
    "OPAQUE_404_BODY",
    "OPAQUE_404_HEADERS",
    "TENANT_RESOLVER_BYPASS_PATHS",
    "TenantResolverMiddleware",
    "_build_opaque_404_response",
]
TENANT_RESOLVER_BYPASS_PATHS: frozenset[str] = frozenset(
    {"/health", "/healthz", "/api/v1/healthz"}
)


class TenantResolverMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: Any,
        *,
        settings: PlatformSettings,
        session_factory: async_sessionmaker[AsyncSession],
        redis_client: AsyncRedisClient | None = None,
        resolver: TenantResolver | None = None,
    ) -> None:
        super().__init__(app)
        self.settings = settings
        self.resolver = resolver or TenantResolver(
            settings=settings,
            session_factory=session_factory,
            redis_client=redis_client,
        )

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in TENANT_RESOLVER_BYPASS_PATHS:
            return await call_next(request)

        tenant = await self.resolver.resolve(request.headers.get("host", ""))
        if tenant is None:
            await _apply_timing_floor(self.settings)
            return _build_opaque_404_response()
        if tenant.status == "pending_deletion" and not _is_platform_staff_request(request):
            await _apply_timing_floor(self.settings)
            return _build_opaque_404_response()

        token = current_tenant.set(tenant)
        request.state.tenant = tenant
        try:
            return await call_next(request)
        finally:
            current_tenant.reset(token)


def _build_opaque_404_response() -> Response:
    return Response(
        content=OPAQUE_404_BODY,
        status_code=404,
        media_type=None,
        headers=OPAQUE_404_HEADERS,
    )


async def _apply_timing_floor(settings: PlatformSettings) -> None:
    if settings.PLATFORM_TENANT_ENFORCEMENT_LEVEL == "lenient":
        await asyncio.sleep(random.uniform(0, 0.001))
        return
    await asyncio.sleep(0)


def _is_platform_staff_request(request: Request) -> bool:
    return request.url.path.startswith("/api/v1/platform/")
