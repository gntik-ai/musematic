from __future__ import annotations

from datetime import UTC, datetime
from platform.localization.exceptions import LocaleFileVersionConflictError
from platform.localization.services.locale_file_service import LocaleFileService
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

NOW = datetime(2026, 4, 29, 12, 0, tzinfo=UTC)
Row = SimpleNamespace


class _Repository:
    def __init__(self) -> None:
        self.rows: list[Row] = []
        self.raise_conflict = False

    async def get_latest_locale_file(self, locale_code: str) -> Row | None:
        matching = [row for row in self.rows if row.locale_code == locale_code]
        return max(matching, key=lambda row: row.version, default=None)

    async def list_locale_files(self) -> list[Row]:
        return self.rows

    async def insert_locale_file_version(
        self,
        *,
        locale_code: str,
        translations: dict[str, Any],
        published_by: UUID | None,
        vendor_source_ref: str | None,
    ) -> Row:
        if self.raise_conflict:
            raise LocaleFileVersionConflictError(locale_code)
        version = max(
            (row.version for row in self.rows if row.locale_code == locale_code),
            default=0,
        ) + 1
        row = Row(
            id=uuid4(),
            locale_code=locale_code,
            version=version,
            translations=translations,
            published_at=NOW,
            published_by=published_by,
            vendor_source_ref=vendor_source_ref,
            created_at=NOW,
        )
        self.rows.append(row)
        return row


@pytest.mark.asyncio
async def test_locale_file_service_versions_and_caches_by_locale_version() -> None:
    repository = _Repository()
    service = LocaleFileService(repository, lru_size=2)
    requester = {"user_id": str(uuid4())}

    first = await service.publish(
        locale_code="en",
        translations={"common": {"hello": "Hello"}},
        requester=requester,
        vendor_source_ref="vendor://en/1",
    )
    cached_first = await service.get_latest("en")
    repository.rows.append(
        Row(
            id=uuid4(),
            locale_code="en",
            version=first.version,
            translations={"common": {"hello": "Changed behind cache"}},
            published_at=NOW,
            published_by=first.published_by,
            vendor_source_ref="vendor://en/1-copy",
            created_at=NOW,
        )
    )
    still_cached = await service.get_latest("en")
    second = await service.publish(
        locale_code="en",
        translations={"common": {"hello": "Hello v2"}},
        requester=requester,
        vendor_source_ref="vendor://en/2",
    )

    assert first.version == 1
    assert second.version == 2
    assert cached_first is still_cached
    assert (await service.get_latest("en")).translations == {"common": {"hello": "Hello v2"}}


@pytest.mark.asyncio
async def test_locale_file_service_lru_size_is_capped_and_conflicts_surface() -> None:
    repository = _Repository()
    service = LocaleFileService(repository, lru_size=1)
    requester = {"sub": str(uuid4())}

    await service.publish(
        locale_code="en",
        translations={"common": {"hello": "Hello"}},
        requester=requester,
        vendor_source_ref=None,
    )
    await service.publish(
        locale_code="es",
        translations={"common": {"hello": "Hola"}},
        requester=requester,
        vendor_source_ref=None,
    )
    await service.get_latest("en")
    await service.get_latest("es")

    assert list(service._cache) == [("es", 1)]

    repository.raise_conflict = True
    with pytest.raises(LocaleFileVersionConflictError):
        await service.publish(
            locale_code="es",
            translations={"common": {"hello": "Hola otra vez"}},
            requester=requester,
            vendor_source_ref=None,
        )
