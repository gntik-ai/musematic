from __future__ import annotations

from platform.two_person_approval.dependencies import get_two_person_approval_service
from platform.two_person_approval.service import TwoPersonApprovalService
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_get_two_person_approval_service_uses_request_redis_client() -> None:
    redis_client = object()
    session = object()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                clients={"redis": redis_client},
            )
        )
    )

    service = await get_two_person_approval_service(request, session)

    assert isinstance(service, TwoPersonApprovalService)
    assert service.session is session
    assert service.redis_client is redis_client
