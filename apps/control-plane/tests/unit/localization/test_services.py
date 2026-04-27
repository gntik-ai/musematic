from __future__ import annotations

import json
from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.common.exceptions import AuthorizationError, PlatformError
from platform.localization import dependencies
from platform.localization.events import (
    LocaleFilePublishedPayload,
    LocalizationEventType,
    UserPreferencesUpdatedPayload,
    publish_localization_event,
    register_localization_event_types,
)
from platform.localization.exceptions import (
    DataExportFormatInvalidError,
    InvalidThemeError,
    InvalidTimezoneError,
    LocaleFileNotFoundError,
    LocaleFileVersionConflictError,
    UnsupportedLocaleError,
    WorkspaceNotMemberError,
)
from platform.localization.models import LocaleFile, UserPreferences
from platform.localization.service import LocalizationService
from platform.localization.services.locale_file_service import LocaleFileService
from platform.localization.services.locale_resolver import LocaleResolver
from platform.localization.services.preferences_service import PreferencesService
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

NOW = datetime(2026, 4, 27, 12, 0, tzinfo=UTC)


def _preferences(user_id: UUID, **overrides: Any) -> UserPreferences:
    values = {
        "id": uuid4(),
        "user_id": user_id,
        "default_workspace_id": None,
        "theme": "system",
        "language": "en",
        "timezone": "UTC",
        "notification_preferences": {},
        "data_export_format": "json",
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return UserPreferences(**values)


def _locale_file(locale_code: str = "en", version: int = 1, **overrides: Any) -> LocaleFile:
    values = {
        "id": uuid4(),
        "locale_code": locale_code,
        "version": version,
        "translations": {"common": {"hello": "Hello"}},
        "published_at": NOW,
        "published_by": uuid4(),
        "vendor_source_ref": "vendor://file",
        "created_at": NOW,
    }
    values.update(overrides)
    return LocaleFile(**values)


class _PreferencesRepository:
    def __init__(self) -> None:
        self.rows: dict[UUID, UserPreferences] = {}
        self.clear_rows: list[UserPreferences] = []
        self.raise_on_get = False

    async def get_user_preferences(self, user_id: UUID) -> UserPreferences | None:
        if self.raise_on_get:
            raise PlatformError("STORE_DOWN", "store down")
        return self.rows.get(user_id)

    async def upsert_user_preferences(self, user_id: UUID, **fields: Any) -> UserPreferences:
        current = self.rows.get(user_id) or _preferences(user_id)
        values = {
            "id": current.id,
            "user_id": user_id,
            "default_workspace_id": current.default_workspace_id,
            "theme": current.theme,
            "language": current.language,
            "timezone": current.timezone,
            "notification_preferences": dict(current.notification_preferences or {}),
            "data_export_format": current.data_export_format,
            "created_at": current.created_at,
            "updated_at": NOW,
        }
        values.update(fields)
        self.rows[user_id] = UserPreferences(**values)
        return self.rows[user_id]

    async def clear_default_workspace(self, workspace_id: UUID) -> list[UserPreferences]:
        del workspace_id
        return self.clear_rows


class _LocaleFileRepository:
    def __init__(self) -> None:
        self.latest: dict[str, LocaleFile] = {}
        self.rows: list[LocaleFile] = []
        self.unpublished_publish = False

    async def get_latest_locale_file(self, locale_code: str) -> LocaleFile | None:
        return self.latest.get(locale_code)

    async def list_locale_files(self) -> list[LocaleFile]:
        return self.rows

    async def insert_locale_file_version(
        self,
        *,
        locale_code: str,
        translations: dict[str, Any],
        published_by: UUID | None,
        vendor_source_ref: str | None,
    ) -> LocaleFile:
        row = _locale_file(
            locale_code,
            max((item.version for item in self.rows if item.locale_code == locale_code), default=0)
            + 1,
            translations=translations,
            published_at=None if self.unpublished_publish else NOW,
            published_by=published_by,
            vendor_source_ref=vendor_source_ref,
        )
        self.latest[locale_code] = row
        self.rows.append(row)
        return row


class _AuditChain:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def append(self, actor_id: UUID, domain: str, encoded: bytes) -> None:
        self.entries.append(
            {
                "actor_id": actor_id,
                "domain": domain,
                "payload": json.loads(encoded.decode("utf-8")),
            }
        )


class _Producer:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def publish(self, **kwargs: Any) -> None:
        self.events.append(kwargs)


class _Workspaces:
    def __init__(self, *, allowed: bool = True) -> None:
        self.allowed = allowed
        self.calls: list[tuple[UUID, UUID]] = []

    async def get_workspace(self, workspace_id: UUID, user_id: UUID) -> object:
        self.calls.append((workspace_id, user_id))
        if not self.allowed:
            raise PlatformError("WORKSPACE_NOT_FOUND", "missing workspace")
        return object()


@pytest.mark.asyncio
async def test_preferences_service_defaults_updates_audits_and_events() -> None:
    user_id = uuid4()
    workspace_id = uuid4()
    repository = _PreferencesRepository()
    audit = _AuditChain()
    producer = _Producer()
    service = PreferencesService(
        repository,
        audit_chain=audit,
        producer=producer,
        workspaces_service=_Workspaces(),
    )

    default_response = await service.get_for_user(user_id)
    assert default_response.is_persisted is False
    assert default_response.language == "en"

    updated = await service.upsert(
        user_id,
        {"sub": str(user_id)},
        correlation_ctx=CorrelationContext(correlation_id=uuid4()),
        theme="dark",
        language="es",
        timezone="UTC",
        default_workspace_id=workspace_id,
        notification_preferences={"email": False},
        data_export_format="csv",
    )
    unchanged = await service.upsert(user_id, {"user_id": str(user_id)}, theme="dark")

    assert updated.is_persisted is True
    assert updated.default_workspace_id == workspace_id
    assert updated.notification_preferences == {"email": False}
    assert unchanged.theme == "dark"
    assert len(audit.entries) == 1
    assert audit.entries[0]["domain"] == "localization"
    assert audit.entries[0]["payload"]["action"] == "localization.user_preferences.updated"
    assert set(audit.entries[0]["payload"]["changed_fields"]) == {
        "theme",
        "language",
        "default_workspace_id",
        "notification_preferences",
        "data_export_format",
    }
    assert producer.events[0]["event_type"] == LocalizationEventType.user_preferences_updated
    assert producer.events[0]["payload"]["user_id"] == str(user_id)
    assert await service.get_user_language(user_id) == "es"

    repository.clear_rows = [_preferences(user_id, default_workspace_id=workspace_id)]
    cleared = await service.clear_default_workspace(workspace_id)
    assert cleared[0].user_id == user_id
    assert audit.entries[-1]["payload"]["action"] == (
        "localization.user_preferences.default_workspace_cleared"
    )


@pytest.mark.asyncio
async def test_preferences_service_validates_requester_and_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    service = PreferencesService(
        _PreferencesRepository(),
        workspaces_service=_Workspaces(allowed=False),
    )
    monkeypatch.setattr(
        "platform.localization.services.preferences_service._iana_timezones",
        lambda: frozenset({"UTC"}),
    )

    with pytest.raises(AuthorizationError):
        await service.upsert(user_id, {"sub": str(uuid4())}, theme="dark")
    with pytest.raises(InvalidThemeError):
        await service.upsert(user_id, {"sub": str(user_id)}, theme="sepia")
    with pytest.raises(UnsupportedLocaleError):
        await service.upsert(user_id, {"sub": str(user_id)}, language="it")
    with pytest.raises(InvalidTimezoneError):
        await service.upsert(user_id, {"sub": str(user_id)}, timezone="Moon/Base")
    with pytest.raises(DataExportFormatInvalidError):
        await service.upsert(user_id, {"sub": str(user_id)}, data_export_format="xlsx")
    with pytest.raises(WorkspaceNotMemberError):
        await service.upsert(user_id, {"sub": str(user_id)}, default_workspace_id=uuid4())


@pytest.mark.asyncio
async def test_preferences_service_language_fallbacks_and_object_requester() -> None:
    user_id = uuid4()
    repository = _PreferencesRepository()
    service = PreferencesService(repository)

    assert await service.get_user_language(user_id) == "en"

    repository.rows[user_id] = _preferences(user_id, language="unsupported")
    assert await service.get_user_language(user_id) == "en"

    repository.raise_on_get = True
    assert await service.get_user_language(user_id) == "en"
    repository.raise_on_get = False

    requester = SimpleNamespace(id=user_id)
    response = await service.upsert(requester.id, requester, timezone="UTC")
    assert response.user_id == user_id


@pytest.mark.asyncio
async def test_locale_file_service_publish_list_cache_and_events() -> None:
    repository = _LocaleFileRepository()
    audit = _AuditChain()
    producer = _Producer()
    service = LocaleFileService(repository, audit_chain=audit, producer=producer, lru_size=1)
    user_id = uuid4()

    published = await service.publish(
        locale_code="en",
        translations={"common": {"hello": "Hello", "nested": {"bye": "Bye"}}},
        requester={"user_id": str(user_id)},
        vendor_source_ref="vendor://en",
        correlation_ctx=CorrelationContext(correlation_id=uuid4()),
    )
    first_latest = await service.get_latest("en")
    repository.latest["en"] = _locale_file("en", published.version, translations={"changed": True})
    second_latest = await service.get_latest("en")

    repository.latest["es"] = _locale_file("es", 1)
    await service.get_latest("es")
    third_latest = await service.get_latest("en")

    listed = await service.list_available()
    service._invalidate_locale("en")

    assert published.locale_code == "en"
    assert first_latest is second_latest
    assert third_latest.translations == {"changed": True}
    assert ("en", published.version) not in service._cache
    assert listed[0].locale_code == "en"
    assert audit.entries[0]["payload"]["namespace_count"] == 1
    assert audit.entries[0]["payload"]["key_count"] == 2
    assert producer.events[0]["event_type"] == LocalizationEventType.locale_file_published
    assert producer.events[0]["key"] == "en"


@pytest.mark.asyncio
async def test_locale_file_service_errors_and_unpublished_publish() -> None:
    repository = _LocaleFileRepository()
    producer = _Producer()
    service = LocaleFileService(repository, producer=producer)
    user_id = uuid4()

    with pytest.raises(UnsupportedLocaleError):
        await service.get_latest("pt-BR")
    with pytest.raises(LocaleFileNotFoundError):
        await service.get_latest("en")

    repository.unpublished_publish = True
    response = await service.publish(
        locale_code="fr",
        translations={"common": {"hello": "Bonjour"}},
        requester=SimpleNamespace(id=user_id),
        vendor_source_ref=None,
    )

    assert response.published_by == user_id
    assert response.published_at is None
    assert producer.events == []
    assert LocaleFileVersionConflictError("fr").status_code == 409


@pytest.mark.asyncio
async def test_localization_service_delegates_to_child_services() -> None:
    user_id = uuid4()
    preferences_repository = _PreferencesRepository()
    locale_repository = _LocaleFileRepository()
    english_file = _locale_file("en", 1)
    locale_repository.latest["en"] = english_file
    locale_repository.rows = [english_file]
    preferences = PreferencesService(preferences_repository)
    locale_files = LocaleFileService(locale_repository)
    service = LocalizationService(preferences, locale_files, LocaleResolver())

    assert (await service.get_preferences(user_id)).user_id == user_id
    assert (
        await service.update_preferences(user_id, {"sub": str(user_id)}, theme="dark")
    ).theme
    assert await service.get_user_language(user_id) == "en"
    assert (await service.get_latest_locale_file("en")).locale_code == "en"
    assert len(await service.list_locale_files()) == 1
    assert (
        await service.publish_locale_file(
            locale_code="de",
            translations={"common": {"hello": "Hallo"}},
            requester={"sub": str(user_id)},
            vendor_source_ref=None,
        )
    ).locale_code == "de"
    resolved = await service.resolve_locale(
        url_hint=None,
        user_preference=None,
        accept_language="ja;q=0.9",
    )
    assert resolved.locale == "ja"

    preferences_repository.clear_rows = [_preferences(user_id)]
    await service.handle_workspace_archived(uuid4())


@pytest.mark.asyncio
async def test_localization_dependencies_build_and_resolve(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = PlatformSettings()
    producer = _Producer()
    audit = _AuditChain()
    session = object()
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=settings, clients={"kafka": producer}))
    )
    monkeypatch.setattr(dependencies, "build_audit_chain_service", lambda *args: audit)

    assert dependencies._get_settings(request) is settings
    assert dependencies._get_producer(request) is producer
    assert dependencies.build_preferences_service(
        session,
        settings,
        producer,
        audit,
        None,
    ).audit_chain is audit
    assert dependencies.build_locale_file_service(session, settings, producer, audit).producer is (
        producer
    )
    assert dependencies.build_locale_resolver(settings).supported_locales
    assert dependencies.build_localization_service(
        session=session,
        settings=settings,
        producer=producer,
        audit_chain=audit,
        workspaces_service=None,
    ).preferences.audit_chain is audit
    assert (
        await dependencies.get_preferences_service(
            request,
            session=session,
            workspaces_service=None,
        )
    ).producer is producer
    assert (await dependencies.get_locale_file_service(request, session=session)).audit_chain is (
        audit
    )
    assert (await dependencies.get_locale_resolver(request)).supported_locales
    assert (
        await dependencies.get_localization_service(
            request,
            session=session,
            workspaces_service=None,
        )
    ).locale_files.producer is producer


@pytest.mark.asyncio
async def test_localization_events_register_and_publish(monkeypatch: pytest.MonkeyPatch) -> None:
    registered: list[tuple[str, object]] = []
    producer = _Producer()
    correlation_id = uuid4()
    monkeypatch.setattr(
        "platform.localization.events.event_registry.register",
        lambda event_type, schema: registered.append((event_type, schema)),
    )

    register_localization_event_types()
    await publish_localization_event(
        None,
        LocalizationEventType.user_preferences_updated,
        UserPreferencesUpdatedPayload(user_id=uuid4(), changed_fields={}, updated_at=NOW),
        CorrelationContext(correlation_id=correlation_id),
    )
    await publish_localization_event(
        producer,
        "custom.event",
        LocaleFilePublishedPayload(
            locale_code="en",
            version=1,
            published_by=None,
            vendor_source_ref=None,
            namespace_count=1,
            key_count=1,
            published_at=NOW,
        ),
        CorrelationContext(correlation_id=correlation_id),
        source="test",
    )

    assert {event_type for event_type, _schema in registered} == {
        LocalizationEventType.user_preferences_updated.value,
        LocalizationEventType.locale_file_published.value,
    }
    assert producer.events == [
        {
            "topic": "localization.events",
            "key": "en",
            "event_type": "custom.event",
            "payload": {
                "locale_code": "en",
                "version": 1,
                "published_by": None,
                "vendor_source_ref": None,
                "namespace_count": 1,
                "key_count": 1,
                "published_at": NOW.isoformat().replace("+00:00", "Z"),
            },
            "correlation_ctx": CorrelationContext(correlation_id=correlation_id),
            "source": "test",
        }
    ]
