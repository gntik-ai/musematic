from __future__ import annotations

from platform.me.service import MeService
from platform.privacy_compliance.models import ConsentType
from uuid import uuid4

import pytest

from tests.unit.test_me_service_router import (
    AuditStub,
    AuthStub,
    ConsentStub,
    DSRStub,
    NotificationsStub,
)


@pytest.mark.asyncio
async def test_consent_revoke_returns_state_and_appends_self_service_audit() -> None:
    user_id = uuid4()
    current_session_id = uuid4()
    service = MeService(
        auth_service=AuthStub(user_id, current_session_id, uuid4()),
        consent_service=ConsentStub(user_id),
        dsr_service=DSRStub(user_id),
        notifications_service=NotificationsStub(user_id),
        audit_service=AuditStub(user_id),
    )

    listed = await service.list_consents(user_id)
    revoked = await service.revoke_consent(user_id, ConsentType.data_collection.value)
    history = await service.list_consent_history(user_id)

    assert listed.items[0].granted is True
    assert revoked.granted is False
    assert [item.granted for item in history.items] == [True, False]
