from __future__ import annotations

from platform.privacy_compliance.events import PrivacyEventPublisher
from platform.privacy_compliance.exceptions import ConsentRequired
from platform.privacy_compliance.models import ConsentType, PrivacyConsentRecord
from platform.privacy_compliance.services.consent_service import ConsentService
from uuid import uuid4

import pytest


class Repo:
    def __init__(self) -> None:
        self.records = {}

    async def current_consent_state(self, user_id):
        return {item: self.records.get(item.value) for item in ConsentType}

    async def upsert_consent(self, *, user_id, consent_type, granted, workspace_id=None):
        record = PrivacyConsentRecord(
            id=uuid4(),
            user_id=user_id,
            consent_type=consent_type,
            granted=granted,
            workspace_id=workspace_id,
        )
        self.records[consent_type] = record
        return record

    async def revoke_consent(self, *, user_id, consent_type):
        record = self.records[consent_type]
        record.granted = False
        return record

    async def get_consent_records(self, user_id):
        del user_id
        return list(self.records.values())


@pytest.mark.asyncio
async def test_require_or_prompt_blocks_missing_consents_then_allows_complete_state() -> None:
    service = ConsentService(repository=Repo(), event_publisher=PrivacyEventPublisher(None))
    user_id = uuid4()
    workspace_id = uuid4()

    with pytest.raises(ConsentRequired):
        await service.require_or_prompt(user_id, workspace_id)

    await service.record_consents(
        user_id,
        dict.fromkeys(ConsentType, True),
        workspace_id,
    )
    await service.require_or_prompt(user_id, workspace_id)

