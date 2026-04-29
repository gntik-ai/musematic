from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from .support import PreferencesRepository, build_app, build_preferences_service

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_theme_preference_persists_to_cookie_and_preferences_row() -> None:
    user_id = uuid4()
    repository = PreferencesRepository()
    service = build_preferences_service(repository)
    app = build_app(
        current_user={"sub": str(user_id), "roles": ["workspace_member"]},
        preferences_service=service,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        updated = await client.patch(
            "/api/v1/me/preferences",
            json={"theme": "high_contrast"},
        )
        reloaded = await client.get(
            "/api/v1/me/preferences",
            cookies={"musematic-theme": "high_contrast"},
        )

    assert updated.status_code == 200
    assert updated.json()["theme"] == "high_contrast"
    assert updated.cookies.get("musematic-theme") == "high_contrast"
    assert repository.rows[user_id].theme == "high_contrast"
    assert reloaded.status_code == 200
    assert reloaded.json()["theme"] == "high_contrast"
