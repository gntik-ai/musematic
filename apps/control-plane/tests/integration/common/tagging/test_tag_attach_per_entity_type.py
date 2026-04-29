from __future__ import annotations

from platform.common.tagging.constants import ENTITY_TYPES
from platform.common.tagging.tag_service import TagService
from uuid import uuid4

import httpx
import pytest
from tests.integration.common.tagging.support import (
    InMemoryTaggingRepository,
    RecordingAudit,
    build_router_app,
    requester,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize("entity_type", ENTITY_TYPES)
async def test_tag_attach_endpoint_is_idempotent_for_each_entity_type(entity_type: str) -> None:
    repo = InMemoryTaggingRepository()
    audit = RecordingAudit()
    actor_id = uuid4()
    entity_id = uuid4()
    app = build_router_app(
        current_user=requester(actor_id),
        tag_service=TagService(repo, audit_chain=audit),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        first = await client.post(
            f"/api/v1/tags/{entity_type}/{entity_id}",
            json={"tag": "production"},
        )
        second = await client.post(
            f"/api/v1/tags/{entity_type}/{entity_id}",
            json={"tag": "production"},
        )
        listed = await client.get(f"/api/v1/tags/{entity_type}/{entity_id}")

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert listed.status_code == 200, listed.text
    assert listed.json()["tags"] == [first.json()]
    assert await repo.count_tags_for_entity(entity_type, entity_id) == 1
    assert [entry["payload"]["action"] for entry in audit.entries] == ["tagging.tag.attached"]
