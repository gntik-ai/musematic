from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, Callable

from platform.common.clients.opensearch import AsyncOpenSearchClient
from platform.common.config import Settings, settings as default_settings

FastAPIApp: Any = None
try:  # pragma: no cover - FastAPI is not installed in this sandbox.
    from fastapi import FastAPI as _FastAPIApp
except Exception:  # pragma: no cover - optional integration surface
    pass
else:  # pragma: no cover - optional integration surface
    FastAPIApp = _FastAPIApp


def build_lifespan(settings: Settings | None = None) -> Callable[[Any], Any]:
    resolved = settings or default_settings

    @asynccontextmanager
    async def lifespan(app: Any) -> AsyncIterator[None]:
        client = AsyncOpenSearchClient.from_settings(resolved)
        app.state.opensearch_client = client
        try:
            yield
        finally:
            await client.close()

    return lifespan


def create_app(settings: Settings | None = None) -> Any:
    if FastAPIApp is None:
        app = SimpleNamespace()
        app.state = SimpleNamespace()
        return app
    return FastAPIApp(lifespan=build_lifespan(settings))
