from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from platform.common import database
from platform.common.config import settings as default_settings
from platform.multi_region_ops.constants import REDIS_KEY_ACTIVE_WINDOW
from platform.multi_region_ops.models import MaintenanceWindow
from platform.multi_region_ops.repository import MultiRegionOpsRepository
from platform.multi_region_ops.services.maintenance_mode_service import _window_from_cache
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

LOGGER = logging.getLogger(__name__)
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class MaintenanceGateMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        settings = getattr(request.app.state, "settings", default_settings)
        if not getattr(settings, "feature_maintenance_mode", False):
            return await call_next(request)
        if request.method not in MUTATING_METHODS:
            return await call_next(request)
        try:
            window = await self._active_window(request)
        except Exception:
            LOGGER.critical("maintenance_gate_truth_unavailable", exc_info=True)
            return await call_next(request)
        if window is None or not window.blocks_writes:
            return await call_next(request)
        retry_after = max(1, int((_aware(window.ends_at) - datetime.now(UTC)).total_seconds()))
        return JSONResponse(
            status_code=503,
            content={
                "error": "maintenance_in_progress",
                "reason": window.reason,
                "ends_at": window.ends_at.isoformat(),
                "announcement": window.announcement_text,
            },
            headers={"Retry-After": str(retry_after)},
        )

    async def _active_window(self, request: Request) -> MaintenanceWindow | None:
        redis_client = getattr(request.app.state, "clients", {}).get("redis")
        if redis_client is not None:
            try:
                raw = await redis_client.get(REDIS_KEY_ACTIVE_WINDOW)
            except Exception:
                raw = None
            if raw is not None:
                try:
                    return _window_from_cache(json.loads(raw.decode("utf-8")))
                except Exception:
                    LOGGER.warning("maintenance_gate_cache_decode_failed", exc_info=True)
        async with database.AsyncSessionLocal() as session:
            repository = MultiRegionOpsRepository(session)
            window = await repository.get_active_window()
            if window is not None and redis_client is not None:
                await self._prime_cache(redis_client, window)
            return window

    async def _prime_cache(self, redis_client: Any, window: MaintenanceWindow) -> None:
        ttl_seconds = max(1, int((_aware(window.ends_at) - datetime.now(UTC)).total_seconds()) + 60)
        payload = {
            "id": str(window.id),
            "starts_at": window.starts_at.isoformat(),
            "ends_at": window.ends_at.isoformat(),
            "reason": window.reason,
            "blocks_writes": window.blocks_writes,
            "announcement_text": window.announcement_text,
            "status": window.status,
            "scheduled_by": str(window.scheduled_by) if window.scheduled_by else None,
            "enabled_at": window.enabled_at.isoformat() if window.enabled_at else None,
            "disabled_at": window.disabled_at.isoformat() if window.disabled_at else None,
            "disable_failure_reason": window.disable_failure_reason,
            "created_at": window.created_at.isoformat(),
            "updated_at": window.updated_at.isoformat(),
        }
        set_method = redis_client.set
        await set_method(
            REDIS_KEY_ACTIVE_WINDOW,
            json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            ttl=ttl_seconds,
        )


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
