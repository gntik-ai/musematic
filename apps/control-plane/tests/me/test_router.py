from __future__ import annotations

from inspect import signature
from platform.me.router import create_service_account, list_service_accounts, router
from platform.me.schemas import UserServiceAccountCreateRequest
from uuid import uuid4

import pytest

from tests.unit.test_me_service_router import RouterServiceStub


def test_me_router_handlers_do_not_accept_user_id_parameters() -> None:
    for route in router.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            continue
        assert "user_id" not in signature(endpoint).parameters


@pytest.mark.asyncio
async def test_service_account_router_uses_authenticated_principal() -> None:
    user_id = uuid4()
    session_id = uuid4()
    service = RouterServiceStub(user_id, session_id)
    current_user = {"sub": str(user_id), "session_id": str(session_id)}

    listed = await list_service_accounts(current_user=current_user, me_service=service)
    created = await create_service_account(
        UserServiceAccountCreateRequest(name="cli", scopes=["agents:read"], mfa_token="123456"),
        current_user=current_user,
        me_service=service,
    )

    assert listed.items == []
    assert created.api_key == "msk_test"
    assert "list_service_accounts" in service.calls
    assert "create_service_account" in service.calls
