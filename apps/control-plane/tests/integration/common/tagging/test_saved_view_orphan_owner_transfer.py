from __future__ import annotations

from platform.common.tagging.saved_view_service import SavedViewService
from uuid import UUID, uuid4

import pytest
from tests.integration.common.tagging.support import (
    InMemoryTaggingRepository,
    RecordingAudit,
    requester,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_saved_view_orphan_owner_transfers_to_workspace_superadmin(
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = InMemoryTaggingRepository()
    audit = RecordingAudit()
    workspace_id = uuid4()
    former_owner_id = uuid4()
    member_id = uuid4()
    superadmin_id = uuid4()
    active_members = {former_owner_id, member_id, superadmin_id}

    async def is_member(checked_workspace_id: UUID, current_user: object) -> bool:
        assert checked_workspace_id == workspace_id
        return UUID(str(current_user["sub"])) in active_members  # type: ignore[index]

    async def superadmin_provider(checked_workspace_id: UUID) -> UUID:
        assert checked_workspace_id == workspace_id
        return superadmin_id

    service = SavedViewService(
        repo,
        audit_chain=audit,
        workspace_membership_check=is_member,
        workspace_superadmin_provider=superadmin_provider,
    )
    view = await service.create(
        requester=requester(former_owner_id),
        workspace_id=workspace_id,
        name="Shared prod agents",
        entity_type="agent",
        filters={"label.env": "production"},
        shared=True,
    )

    active_members.remove(former_owner_id)
    await service.resolve_orphan_owner(workspace_id, former_owner_id=former_owner_id)

    transferred = await service.get(view.id, requester(member_id))
    captured = capsys.readouterr()

    assert transferred.owner_id == superadmin_id
    assert transferred.is_orphan_transferred is True
    assert transferred.id in {item.id for item in await service.list_for_user(
        requester(member_id),
        "agent",
        workspace_id,
    )}
    assert "tagging.saved_view.orphan_transferred" in captured.out
    assert audit.entries[-1]["payload"]["action"] == "tagging.saved_view.orphan_transferred"
