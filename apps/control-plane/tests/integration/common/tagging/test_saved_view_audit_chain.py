from __future__ import annotations

from platform.common.tagging.saved_view_service import SavedViewService
from uuid import uuid4

import pytest
from tests.integration.common.tagging.support import (
    InMemoryTaggingRepository,
    RecordingAudit,
    requester,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_saved_view_mutations_emit_audit_chain_entries() -> None:
    repo = InMemoryTaggingRepository()
    audit = RecordingAudit()
    workspace_id = uuid4()
    owner_id = uuid4()
    service = SavedViewService(repo, audit_chain=audit)
    actor = requester(owner_id)

    created = await service.create(
        requester=actor,
        workspace_id=workspace_id,
        name="Prod agents",
        entity_type="agent",
        filters={"label.env": "production"},
        shared=False,
    )
    updated = await service.update(created.id, created.version, actor, name="Production agents")
    shared = await service.share(updated.id, actor)
    unshared = await service.unshare(shared.id, actor)
    await service.delete(unshared.id, actor)

    assert [entry["payload"]["action"] for entry in audit.entries] == [
        "tagging.saved_view.created",
        "tagging.saved_view.updated",
        "tagging.saved_view.shared",
        "tagging.saved_view.unshared",
        "tagging.saved_view.deleted",
    ]
