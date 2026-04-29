from __future__ import annotations

from platform.common.tagging.constants import MAX_TAGS_PER_ENTITY
from platform.common.tagging.exceptions import TagAttachLimitExceededError
from platform.common.tagging.tag_service import TagService
from uuid import uuid4

import pytest
from tests.integration.common.tagging.support import InMemoryTaggingRepository, requester

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_tag_attach_rejects_the_fifty_first_tag() -> None:
    repo = InMemoryTaggingRepository()
    service = TagService(repo)
    actor_id = uuid4()
    entity_id = uuid4()

    for index in range(MAX_TAGS_PER_ENTITY):
        await service.attach(
            entity_type="agent",
            entity_id=entity_id,
            tag=f"tag-{index}",
            requester=requester(actor_id),
        )

    with pytest.raises(TagAttachLimitExceededError) as exc_info:
        await service.attach(
            entity_type="agent",
            entity_id=entity_id,
            tag="tag-over-limit",
            requester=requester(actor_id),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.details == {"limit": MAX_TAGS_PER_ENTITY}
