from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

import platform.tenants.platform_router as platform_router
from platform.common.config import PlatformSettings
from platform.tenants.platform_router import (
    ForceCascadeDeletionRequest,
    force_cascade_deletion,
    require_platform_staff,
)


def _request(service: object | None = None) -> SimpleNamespace:
    state = SimpleNamespace(settings=PlatformSettings(), clients={}, tenant_service=service)
    return SimpleNamespace(app=SimpleNamespace(state=state))


@pytest.mark.asyncio
async def test_require_platform_staff_allows_only_platform_staff_role() -> None:
    assert await require_platform_staff({"roles": [{"role": "platform_staff"}]})
    with pytest.raises(HTTPException) as exc:
        await require_platform_staff({"roles": [{"role": "operator"}]})
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_force_cascade_deletion_requires_incident_mode() -> None:
    with pytest.raises(HTTPException) as exc:
        await force_cascade_deletion(
            str(uuid4()),
            ForceCascadeDeletionRequest(two_pa_token=str(uuid4()), incident_mode=False),
            _request(),  # type: ignore[arg-type]
            current_user={"sub": str(uuid4()), "roles": [{"role": "platform_staff"}]},
            session=object(),  # type: ignore[arg-type]
        )

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_force_cascade_deletion_consumes_two_pa_and_returns_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()
    actor_id = uuid4()
    calls: list[tuple[str, object]] = []

    class ServiceStub:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def _get_mutable_tenant(self, value):
            calls.append(("get", value))
            return SimpleNamespace(id=value)

        async def _consume_deletion_two_pa(self, actor, tenant, token):
            calls.append(("consume", (actor, tenant, token)))

        async def complete_deletion(self, value):
            calls.append(("complete", value))
            return {"users": 3}

    monkeypatch.setattr(platform_router, "_service", lambda request, session: ServiceStub())

    response = await force_cascade_deletion(
        str(tenant_id),
        ForceCascadeDeletionRequest(two_pa_token=str(uuid4()), incident_mode=True),
        _request(),  # type: ignore[arg-type]
        current_user={"sub": str(actor_id), "roles": [{"role": "platform_staff"}]},
        session=object(),  # type: ignore[arg-type]
    )

    assert response.tenant_id == str(tenant_id)
    assert response.row_count_digest == {"users": 3}
    assert calls[0] == ("get", tenant_id)
    assert calls[-1] == ("complete", tenant_id)


def test_platform_router_settings_fallback() -> None:
    assert platform_router._settings(_request()).profile == "api"  # type: ignore[arg-type]
    assert platform_router._settings(SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))).profile
