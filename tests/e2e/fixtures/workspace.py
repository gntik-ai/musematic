from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest


@pytest.fixture(scope="function")
async def workspace(http_client) -> AsyncIterator[dict]:
    workspace_name = f"test-{uuid4().hex[:8]}"
    response = await http_client.post(
        "/api/v1/workspaces",
        json={"name": workspace_name, "display_name": workspace_name},
    )
    assert response.status_code in {200, 201}, response.text
    payload = response.json()
    try:
        yield payload
    finally:
        workspace_id = payload.get("id", workspace_name)
        await http_client.delete(f"/api/v1/workspaces/{workspace_id}")
