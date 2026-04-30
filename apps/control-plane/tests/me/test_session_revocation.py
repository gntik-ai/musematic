from __future__ import annotations

from platform.auth.schemas import ServiceAccountCreateResponse
from platform.auth.service import AuthService
from platform.common.config import AuthSettings
from uuid import uuid4

import pytest

from tests.unit.test_me_service_router import (
    AuthRepositoryForSelfService,
    SessionStoreForAuth,
)


@pytest.mark.asyncio
async def test_session_listing_sanitizes_and_revocation_preserves_current_session() -> None:
    user_id = uuid4()
    current_session_id = uuid4()
    other_session_id = uuid4()
    service = AuthService(
        repository=AuthRepositoryForSelfService(user_id),
        redis_client=object(),
        settings=AuthSettings(jwt_secret_key="test-secret", jwt_algorithm="HS256"),
        producer=None,
    )
    session_store = SessionStoreForAuth(current_session_id, other_session_id)
    service.session_store = session_store

    sessions = await service.list_user_sessions(user_id, current_session_id)

    assert sessions[0]["is_current"] is True
    assert sessions[1]["is_current"] is False
    assert all("refresh_jti" not in item for item in sessions)

    with pytest.raises(ValueError, match="cannot revoke current session"):
        await service.revoke_session_by_id(user_id, current_session_id, current_session_id)

    revoked = await service.revoke_other_sessions(user_id, current_session_id)
    assert revoked == 1
    assert session_store.deleted == [other_session_id]


def test_service_account_response_type_import_keeps_task_contract_visible() -> None:
    response = ServiceAccountCreateResponse(
        service_account_id=uuid4(),
        name="cli",
        api_key="msk_test",
        role="service_account",
    )
    assert response.api_key.startswith("msk_")
