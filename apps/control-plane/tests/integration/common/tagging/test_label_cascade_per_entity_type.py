from __future__ import annotations

from platform.common.tagging.constants import ENTITY_TYPES
from platform.common.tagging.label_service import LabelService
from uuid import uuid4

import pytest
from tests.integration.common.tagging.support import InMemoryTaggingRepository

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize("entity_type", ENTITY_TYPES)
async def test_label_cascade_removes_rows_for_each_entity_type(entity_type: str) -> None:
    repo = InMemoryTaggingRepository()
    service = LabelService(repo)
    entity_id = uuid4()
    other_id = uuid4()

    for key in ("env", "tier", "team", "lifecycle", "owner"):
        await repo.upsert_label(entity_type, entity_id, key, "value", uuid4())
    await repo.upsert_label(entity_type, other_id, "env", "production", uuid4())

    await service.cascade_on_entity_deletion(entity_type, entity_id)

    assert await repo.count_labels_for_entity(entity_type, entity_id) == 0
    assert await repo.count_labels_for_entity(entity_type, other_id) == 1
    assert repo.cascades == [(entity_type, entity_id)]
