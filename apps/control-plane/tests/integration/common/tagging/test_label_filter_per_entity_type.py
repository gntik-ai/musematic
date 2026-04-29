from __future__ import annotations

from platform.common.tagging.constants import ENTITY_TYPES
from platform.common.tagging.label_service import LabelService
from uuid import uuid4

import pytest
from tests.integration.common.tagging.support import InMemoryTaggingRepository

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize("entity_type", ENTITY_TYPES)
async def test_label_filters_are_and_conjunctive_per_entity_type(entity_type: str) -> None:
    repo = InMemoryTaggingRepository()
    service = LabelService(repo)
    first = uuid4()
    second = uuid4()
    missing_tier = uuid4()
    wrong_env = uuid4()

    await repo.upsert_label(entity_type, first, "env", "production", uuid4())
    await repo.upsert_label(entity_type, first, "tier", "critical", uuid4())
    await repo.upsert_label(entity_type, second, "env", "production", uuid4())
    await repo.upsert_label(entity_type, second, "tier", "critical", uuid4())
    await repo.upsert_label(entity_type, missing_tier, "env", "production", uuid4())
    await repo.upsert_label(entity_type, wrong_env, "env", "staging", uuid4())
    await repo.upsert_label(entity_type, wrong_env, "tier", "critical", uuid4())

    result = await service.filter_query(
        entity_type,
        {"env": "production", "tier": "critical"},
        {first, second, missing_tier, wrong_env},
        limit=10,
    )

    assert result == sorted([first, second], key=str)
