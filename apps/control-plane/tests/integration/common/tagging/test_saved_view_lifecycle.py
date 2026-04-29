from __future__ import annotations

from platform.common.tagging.saved_view_service import SavedViewService
from uuid import UUID, uuid4

import pytest
from tests.integration.common.tagging.support import (
    InMemoryTaggingRepository,
    RecordingAudit,
    requester,
    saved_view_ids,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_saved_view_personal_share_unshare_and_rename_lifecycle() -> None:
    repo = InMemoryTaggingRepository()
    audit = RecordingAudit()
    workspace_id = uuid4()
    owner_id = uuid4()
    member_id = uuid4()
    members = {owner_id, member_id}

    async def is_member(checked_workspace_id: UUID, current_user: object) -> bool:
        assert checked_workspace_id == workspace_id
        return UUID(str(current_user["sub"])) in members  # type: ignore[index]

    service = SavedViewService(
        repo,
        audit_chain=audit,
        workspace_membership_check=is_member,
    )

    created = await service.create(
        requester=requester(owner_id),
        workspace_id=workspace_id,
        name="Prod agents",
        entity_type="agent",
        filters={"label.env": "production"},
        shared=False,
    )
    member_before_share = await service.list_for_user(requester(member_id), "agent", workspace_id)
    shared = await service.share(created.id, requester(owner_id))
    member_after_share = await service.list_for_user(requester(member_id), "agent", workspace_id)
    unshared = await service.unshare(shared.id, requester(owner_id))
    member_after_unshare = await service.list_for_user(requester(member_id), "agent", workspace_id)
    renamed = await service.update(
        unshared.id,
        unshared.version,
        requester(owner_id),
        name="Production agents",
    )

    assert member_before_share == []
    assert saved_view_ids(member_after_share) == {created.id}
    assert member_after_unshare == []
    assert renamed.name == "Production agents"
    assert [entry["payload"]["action"] for entry in audit.entries] == [
        "tagging.saved_view.created",
        "tagging.saved_view.shared",
        "tagging.saved_view.unshared",
        "tagging.saved_view.updated",
    ]
