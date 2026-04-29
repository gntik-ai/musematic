from __future__ import annotations

from platform.common.tagging.label_service import LabelService
from uuid import uuid4

import pytest
from tests.integration.common.tagging.support import (
    InMemoryTaggingRepository,
    RecordingAudit,
    requester,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_label_upsert_keeps_one_row_and_audits_old_value() -> None:
    repo = InMemoryTaggingRepository()
    audit = RecordingAudit()
    actor_id = uuid4()
    entity_id = uuid4()
    service = LabelService(repo, audit_chain=audit)

    await service.attach(
        entity_type="agent",
        entity_id=entity_id,
        key="env",
        value="staging",
        requester=requester(actor_id),
    )
    updated = await service.attach(
        entity_type="agent",
        entity_id=entity_id,
        key="env",
        value="production",
        requester=requester(actor_id),
    )

    assert updated.value == "production"
    assert await repo.count_labels_for_entity("agent", entity_id) == 1
    assert audit.entries[1]["payload"]["old_value"] == "staging"
    assert audit.entries[1]["payload"]["new_value"] == "production"
