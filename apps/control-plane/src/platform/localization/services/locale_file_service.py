from __future__ import annotations

import json
from collections import OrderedDict
from platform.audit.service import AuditChainService
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.localization.constants import LOCALE_LRU_SIZE, LOCALES
from platform.localization.events import (
    LocaleFilePublishedPayload,
    LocalizationEventType,
    publish_localization_event,
)
from platform.localization.exceptions import LocaleFileNotFoundError, UnsupportedLocaleError
from platform.localization.models import LocaleFile
from platform.localization.repository import LocalizationRepository
from platform.localization.schemas import LocaleFileListItem, LocaleFileResponse
from typing import Any
from uuid import UUID, uuid4


class LocaleFileService:
    def __init__(
        self,
        repository: LocalizationRepository,
        *,
        audit_chain: AuditChainService | None = None,
        producer: EventProducer | None = None,
        lru_size: int = LOCALE_LRU_SIZE,
    ) -> None:
        self.repository = repository
        self.audit_chain = audit_chain
        self.producer = producer
        self.lru_size = lru_size
        self._cache: OrderedDict[tuple[str, int], LocaleFileResponse] = OrderedDict()

    async def get_latest(self, locale_code: str) -> LocaleFileResponse:
        self._validate_locale(locale_code)
        row = await self.repository.get_latest_locale_file(locale_code)
        if row is None:
            raise LocaleFileNotFoundError(locale_code)
        key = (row.locale_code, row.version)
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached
        response = self._response(row)
        self._cache[key] = response
        self._cache.move_to_end(key)
        while len(self._cache) > self.lru_size:
            self._cache.popitem(last=False)
        return response

    async def list_available(self) -> list[LocaleFileListItem]:
        rows = await self.repository.list_locale_files()
        return [self._list_item(row) for row in rows]

    async def publish(
        self,
        *,
        locale_code: str,
        translations: dict[str, Any],
        requester: Any,
        vendor_source_ref: str | None,
        correlation_ctx: CorrelationContext | None = None,
    ) -> LocaleFileResponse:
        self._validate_locale(locale_code)
        published_by = self._requester_id(requester)
        row = await self.repository.insert_locale_file_version(
            locale_code=locale_code,
            translations=translations,
            published_by=published_by,
            vendor_source_ref=vendor_source_ref,
        )
        self._invalidate_locale(locale_code)
        response = self._response(row)
        namespace_count = len(translations)
        key_count = self._count_keys(translations)
        await self._audit(
            "localization.locale_file.published",
            locale_code=locale_code,
            version=row.version,
            published_by=published_by,
            vendor_source_ref=vendor_source_ref,
            namespace_count=namespace_count,
            key_count=key_count,
        )
        if row.published_at is not None:
            await publish_localization_event(
                self.producer,
                LocalizationEventType.locale_file_published,
                LocaleFilePublishedPayload(
                    locale_code=locale_code,
                    version=row.version,
                    published_by=published_by,
                    vendor_source_ref=vendor_source_ref,
                    namespace_count=namespace_count,
                    key_count=key_count,
                    published_at=row.published_at,
                ),
                correlation_ctx or CorrelationContext(correlation_id=uuid4()),
            )
        return response

    def _invalidate_locale(self, locale_code: str) -> None:
        for key in list(self._cache):
            if key[0] == locale_code:
                del self._cache[key]

    async def _audit(self, action: str, **payload: Any) -> None:
        if self.audit_chain is None:
            return
        canonical = {"action": action, **payload}
        encoded = json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        await self.audit_chain.append(uuid4(), "localization", encoded)

    @staticmethod
    def _validate_locale(locale_code: str) -> None:
        if locale_code not in LOCALES:
            raise UnsupportedLocaleError(locale_code)

    @staticmethod
    def _requester_id(requester: Any) -> UUID | None:
        if isinstance(requester, dict):
            raw = requester.get("sub") or requester.get("user_id")
            return UUID(str(raw)) if raw is not None else None
        raw_id = getattr(requester, "id", None)
        return UUID(str(raw_id)) if raw_id is not None else None

    @classmethod
    def _count_keys(cls, translations: dict[str, Any]) -> int:
        total = 0
        for value in translations.values():
            if isinstance(value, dict):
                total += cls._count_keys(value)
            else:
                total += 1
        return total

    @staticmethod
    def _response(row: LocaleFile) -> LocaleFileResponse:
        return LocaleFileResponse(
            id=row.id,
            locale_code=row.locale_code,
            version=row.version,
            translations=dict(row.translations or {}),
            published_at=row.published_at,
            published_by=row.published_by,
            vendor_source_ref=row.vendor_source_ref,
            created_at=row.created_at,
        )

    @staticmethod
    def _list_item(row: LocaleFile) -> LocaleFileListItem:
        return LocaleFileListItem(
            id=row.id,
            locale_code=row.locale_code,
            version=row.version,
            published_at=row.published_at,
            published_by=row.published_by,
            vendor_source_ref=row.vendor_source_ref,
            created_at=row.created_at,
        )

