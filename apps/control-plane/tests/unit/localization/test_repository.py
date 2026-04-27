from __future__ import annotations

from datetime import UTC, datetime
from platform.localization.exceptions import LocaleFileVersionConflictError
from platform.localization.models import LocaleFile, UserPreferences
from platform.localization.repository import LocalizationRepository
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError


NOW = datetime(2026, 4, 27, 12, 0, tzinfo=UTC)


class _Result:
    def __init__(
        self,
        *,
        scalar: object | None = None,
        rows: list[object] | None = None,
    ) -> None:
        self._scalar = scalar
        self._rows = rows or []

    def scalar_one_or_none(self) -> object | None:
        return self._scalar

    def scalar_one(self) -> object:
        assert self._scalar is not None
        return self._scalar

    def scalars(self) -> "_Result":
        return self

    def all(self) -> list[object]:
        return self._rows


class _Session:
    def __init__(self, *results: _Result, flush_error: Exception | None = None) -> None:
        self.results = list(results)
        self.flush_error = flush_error
        self.executed: list[object] = []
        self.added: list[object] = []
        self.refreshed: list[object] = []

    async def execute(self, statement: object) -> _Result:
        self.executed.append(statement)
        return self.results.pop(0)

    def add(self, row: object) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        if self.flush_error is not None:
            raise self.flush_error

    async def refresh(self, row: object) -> None:
        self.refreshed.append(row)


def _preferences(**overrides: object) -> UserPreferences:
    values = {
        "id": uuid4(),
        "user_id": uuid4(),
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


def _locale_file(**overrides: object) -> LocaleFile:
    values = {
        "id": uuid4(),
        "locale_code": "en",
        "version": 1,
        "translations": {"common": {"hello": "Hello"}},
        "published_at": NOW,
        "published_by": uuid4(),
        "vendor_source_ref": "vendor://file",
        "created_at": NOW,
    }
    values.update(overrides)
    return LocaleFile(**values)


@pytest.mark.asyncio
async def test_repository_reads_and_upserts_preferences() -> None:
    user_id = uuid4()
    preferences = _preferences(user_id=user_id, language="es")
    upserted = _preferences(user_id=user_id, language="fr")
    repository = LocalizationRepository(_Session(_Result(scalar=preferences), _Result(scalar=upserted)))

    assert await repository.get_user_preferences(user_id) == preferences
    assert await repository.upsert_user_preferences(user_id, language="fr") == upserted


@pytest.mark.asyncio
async def test_repository_clears_default_workspace_and_lists_locale_files() -> None:
    workspace_id = uuid4()
    cleared = [_preferences(default_workspace_id=workspace_id)]
    rows = [_locale_file(locale_code="fr", version=2), _locale_file(locale_code="en", version=1)]
    repository = LocalizationRepository(
        _Session(_Result(rows=cleared), _Result(scalar=rows[0]), _Result(rows=rows), _Result(rows=rows))
    )

    assert await repository.clear_default_workspace(workspace_id) == cleared
    assert await repository.get_latest_locale_file("fr") == rows[0]
    assert await repository.list_locale_files() == rows
    assert await repository.list_locale_files("fr") == rows


@pytest.mark.asyncio
async def test_repository_inserts_next_locale_file_version() -> None:
    latest = SimpleNamespace(version=2)
    session = _Session(_Result(scalar=latest))
    repository = LocalizationRepository(session)

    row = await repository.insert_locale_file_version(
        locale_code="fr",
        translations={"common": {"hello": "Bonjour"}},
        published_by=uuid4(),
        vendor_source_ref="vendor://fr",
    )

    assert row.version == 3
    assert row.published_at is not None
    assert session.added == [row]
    assert session.refreshed == [row]


@pytest.mark.asyncio
async def test_repository_insert_locale_file_version_starts_at_one_and_wraps_conflict() -> None:
    repository = LocalizationRepository(_Session(_Result()))

    row = await repository.insert_locale_file_version(
        locale_code="fr",
        translations={"common": {"hello": "Bonjour"}},
        published_by=None,
        vendor_source_ref=None,
    )

    assert row.version == 1

    conflict = IntegrityError("insert", {}, Exception("duplicate"))
    with pytest.raises(LocaleFileVersionConflictError):
        await LocalizationRepository(_Session(_Result(), flush_error=conflict)).insert_locale_file_version(
            locale_code="fr",
            translations={},
            published_by=None,
            vendor_source_ref=None,
        )


@pytest.mark.asyncio
async def test_repository_collects_latest_namespace_timestamps_per_locale() -> None:
    newer = _locale_file(
        locale_code="fr",
        version=2,
        translations={"common": {}, "admin": {}},
        published_at=NOW,
    )
    older = _locale_file(
        locale_code="fr",
        version=1,
        translations={"common": {}, "billing": {}},
        published_at=datetime(2026, 4, 26, 12, 0, tzinfo=UTC),
    )
    unpublished = _locale_file(locale_code="es", published_at=None)
    repository = LocalizationRepository(_Session(_Result(rows=[newer, older, unpublished])))

    timestamps = await repository.get_namespace_publish_timestamps_per_locale()

    assert timestamps["fr"]["common"] == newer.published_at
    assert timestamps["fr"]["admin"] == newer.published_at
    assert timestamps["fr"]["billing"] == older.published_at
    assert "es" not in timestamps
