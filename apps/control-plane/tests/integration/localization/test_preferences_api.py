from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from .support import (
    AuditChain,
    PreferencesRepository,
    Workspaces,
    build_app,
    build_preferences_service,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_preferences_api_defaults_patch_validation_and_membership() -> None:
    user_id = uuid4()
    workspace_id = uuid4()
    repository = PreferencesRepository()
    audit = AuditChain()
    service = build_preferences_service(
        repository,
        audit_chain=audit,
        workspaces=Workspaces(allowed=True),
    )
    app = build_app(
        current_user={"sub": str(user_id), "roles": ["workspace_member"]},
        preferences_service=service,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        default_response = await client.get("/api/v1/me/preferences")
        updated = await client.patch(
            "/api/v1/me/preferences",
            json={
                "language": "es",
                "theme": "dark",
                "timezone": "UTC",
                "default_workspace_id": str(workspace_id),
                "data_export_format": "csv",
            },
        )
        invalid_locale = await client.patch(
            "/api/v1/me/preferences",
            json={"language": "it"},
        )

    assert default_response.status_code == 200
    assert default_response.json()["is_persisted"] is False
    assert updated.status_code == 200
    assert updated.json()["language"] == "es"
    assert updated.cookies.get("musematic-locale") == "es"
    assert updated.cookies.get("musematic-theme") == "dark"
    assert audit.entries[0]["payload"]["action"] == "localization.user_preferences.updated"
    assert invalid_locale.status_code == 422
    assert invalid_locale.json()["error"]["code"] == "UNSUPPORTED_LOCALE"


@pytest.mark.asyncio
async def test_preferences_api_refuses_default_workspace_outside_membership() -> None:
    user_id = uuid4()
    service = build_preferences_service(
        PreferencesRepository(),
        workspaces=Workspaces(allowed=False),
    )
    app = build_app(
        current_user={"sub": str(user_id), "roles": ["workspace_member"]},
        preferences_service=service,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.patch(
            "/api/v1/me/preferences",
            json={"default_workspace_id": str(uuid4())},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "WORKSPACE_NOT_MEMBER"
