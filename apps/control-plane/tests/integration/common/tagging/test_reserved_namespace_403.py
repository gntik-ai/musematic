from __future__ import annotations

from platform.common.tagging.label_service import LabelService
from uuid import uuid4

import httpx
import pytest
from tests.integration.common.tagging.support import (
    InMemoryTaggingRepository,
    build_router_app,
    requester,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_reserved_namespace_requires_superadmin_or_admin_reserved_endpoint() -> None:
    repo = InMemoryTaggingRepository()
    entity_id = uuid4()
    non_superadmin = requester(uuid4(), roles=["workspace_member"])
    app = build_router_app(
        current_user=non_superadmin,
        label_service=LabelService(repo),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        forbidden = await client.post(
            f"/api/v1/labels/agent/{entity_id}",
            json={"key": "system.managed", "value": "true"},
        )
        ordinary = await client.post(
            f"/api/v1/labels/agent/{entity_id}",
            json={"key": "env", "value": "production"},
        )

    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "RESERVED_LABEL_NAMESPACE"
    assert ordinary.status_code == 200

    superadmin_app = build_router_app(
        current_user=requester(uuid4(), roles=["superadmin"]),
        label_service=LabelService(repo),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=superadmin_app),
        base_url="http://testserver",
    ) as client:
        allowed = await client.post(
            f"/api/v1/admin/labels/reserved/agent/{entity_id}",
            json={"key": "system.managed", "value": "true"},
        )

    assert allowed.status_code == 200
    assert allowed.json()["is_reserved"] is True
