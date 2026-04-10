from __future__ import annotations

from typing import Any, cast

from platform.common.clients.opensearch import AsyncOpenSearchClient


def get_opensearch_client(request: Any) -> AsyncOpenSearchClient:
    return cast(AsyncOpenSearchClient, request.app.state.opensearch_client)
