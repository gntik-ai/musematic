from __future__ import annotations

from platform.common.tagging.tag_service import TagService
from uuid import uuid4

import pytest
from tests.integration.common.tagging.support import InMemoryTaggingRepository, ResolverStub

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_cross_entity_tag_search_groups_only_visible_entities() -> None:
    repo = InMemoryTaggingRepository()
    visible_workspace = uuid4()
    visible_agent = uuid4()
    hidden_agent = uuid4()
    hidden_fleet = uuid4()
    visible_certification = uuid4()

    for entity_type, entity_id in (
        ("workspace", visible_workspace),
        ("agent", visible_agent),
        ("agent", hidden_agent),
        ("fleet", hidden_fleet),
        ("certification", visible_certification),
    ):
        await repo.insert_tag(entity_type, entity_id, "production", uuid4())

    service = TagService(
        repo,
        visibility_resolver=ResolverStub(
            {
                "workspace": {visible_workspace},
                "agent": {visible_agent},
                "fleet": set(),
                "certification": {visible_certification},
            }
        ),
    )

    full = await service.cross_entity_search(tag="production", requester={"sub": str(uuid4())})
    partial = await service.cross_entity_search(
        tag="production",
        requester={"sub": str(uuid4())},
        entity_types=["agent", "fleet"],
    )
    none = await TagService(
        repo,
        visibility_resolver=ResolverStub({"agent": set(), "fleet": set()}),
    ).cross_entity_search(tag="production", requester={"sub": str(uuid4())})

    assert full.entities == {
        "agent": [visible_agent],
        "certification": [visible_certification],
        "workspace": [visible_workspace],
    }
    assert partial.entities == {"agent": [visible_agent]}
    assert none.entities == {}
