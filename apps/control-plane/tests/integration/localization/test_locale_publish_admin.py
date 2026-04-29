from __future__ import annotations

from platform.localization.service import LocalizationService
from platform.localization.services.locale_resolver import LocaleResolver
from uuid import uuid4

import httpx
import pytest

from .support import (
    LocaleFileRepository,
    PreferencesRepository,
    build_app,
    build_locale_file_service,
    build_preferences_service,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_admin_locale_publish_requires_superadmin_and_writes_version() -> None:
    user_id = uuid4()
    locale_repository = LocaleFileRepository()
    localization_service = LocalizationService(
        build_preferences_service(PreferencesRepository()),
        build_locale_file_service(locale_repository),
        LocaleResolver(),
    )
    app = build_app(
        current_user={"sub": str(user_id), "roles": ["superadmin"]},
        localization_service=localization_service,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        published = await client.post(
            "/api/v1/admin/locales",
            json={
                "locale_code": "es",
                "translations": {"common": {"hello": "Hola"}},
                "vendor_source_ref": "vendor://es/1",
            },
        )

    assert published.status_code == 201
    assert published.json()["locale_code"] == "es"
    assert published.json()["version"] == 1
    assert published.json()["published_by"] == str(user_id)


@pytest.mark.asyncio
async def test_admin_locale_publish_forbidden_and_conflict_surfaces() -> None:
    user_id = uuid4()
    locale_repository = LocaleFileRepository()
    localization_service = LocalizationService(
        build_preferences_service(PreferencesRepository()),
        build_locale_file_service(locale_repository),
        LocaleResolver(),
    )
    app = build_app(
        current_user={"sub": str(user_id), "roles": ["viewer"]},
        localization_service=localization_service,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        forbidden = await client.post(
            "/api/v1/admin/locales",
            json={"locale_code": "es", "translations": {}},
        )

    locale_repository.raise_conflict = True
    app = build_app(
        current_user={"sub": str(user_id), "roles": ["superadmin"]},
        localization_service=localization_service,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        conflict = await client.post(
            "/api/v1/admin/locales",
            json={"locale_code": "es", "translations": {}},
        )

    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "SUPERADMIN_REQUIRED"
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "LOCALE_FILE_VERSION_CONFLICT"
