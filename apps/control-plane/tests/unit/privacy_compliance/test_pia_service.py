from __future__ import annotations

from platform.privacy_compliance.events import PrivacyEventPublisher
from platform.privacy_compliance.exceptions import PIAApprovalError
from platform.privacy_compliance.services.pia_service import PIAService
from uuid import uuid4

import pytest


class Repo:
    def __init__(self) -> None:
        self.item = None
        self.session = self

    async def flush(self) -> None:
        return None

    async def create_pia(self, item):
        item.id = uuid4()
        self.item = item
        return item

    async def get_pia(self, pia_id):
        del pia_id
        return self.item

    async def get_approved_pia(self, subject_type, subject_id):
        if (
            self.item
            and self.item.subject_type == subject_type
            and self.item.subject_id == subject_id
        ):
            return self.item
        return None


@pytest.mark.asyncio
async def test_pia_approval_enforces_two_person_rule() -> None:
    service = PIAService(repository=Repo(), event_publisher=PrivacyEventPublisher(None))
    submitter = uuid4()
    pia = await service.submit_draft(
        subject_type="agent",
        subject_id=uuid4(),
        data_categories=["pii"],
        legal_basis="contractual compliance basis",
        retention_policy=None,
        risks=[],
        mitigations=[],
        submitted_by=submitter,
    )

    with pytest.raises(PIAApprovalError):
        await service.approve(pia.id, submitter)

    approved = await service.approve(pia.id, uuid4())
    assert approved.status == "approved"
