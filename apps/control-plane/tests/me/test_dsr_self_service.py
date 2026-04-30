from __future__ import annotations

from platform.common.exceptions import NotFoundError
from platform.me.schemas import UserDSRSubmitRequest
from platform.me.service import MeService
from platform.privacy_compliance.models import DSRRequestType
from uuid import uuid4

import pytest
from pydantic import ValidationError

from tests.unit.test_me_service_router import (
    AuditStub,
    AuthStub,
    ConsentStub,
    DSRStub,
    NotificationsStub,
    _dsr,
)


@pytest.mark.asyncio
async def test_dsr_submission_auto_fills_subject_and_hides_unowned_records() -> None:
    user_id = uuid4()
    dsr = DSRStub(user_id)
    service = MeService(
        auth_service=AuthStub(user_id, uuid4(), uuid4()),
        consent_service=ConsentStub(user_id),
        dsr_service=dsr,
        notifications_service=NotificationsStub(user_id),
        audit_service=AuditStub(user_id),
    )

    submitted = await service.submit_dsr(
        user_id,
        UserDSRSubmitRequest(request_type=DSRRequestType.access),
    )
    assert submitted.subject_user_id == user_id
    assert dsr.created_payloads[0].subject_user_id == user_id

    dsr.get_response = _dsr(uuid4())
    with pytest.raises(NotFoundError):
        await service.get_dsr(user_id, dsr.get_response.id)


def test_erasure_dsr_requires_typed_confirmation() -> None:
    with pytest.raises(ValidationError):
        UserDSRSubmitRequest(request_type=DSRRequestType.erasure)
    assert (
        UserDSRSubmitRequest(
            request_type=DSRRequestType.erasure,
            confirm_text="DELETE",
        ).confirm_text
        == "DELETE"
    )
