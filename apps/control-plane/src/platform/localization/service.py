from __future__ import annotations

from platform.common.events.envelope import CorrelationContext
from platform.localization.schemas import (
    LocaleFileListItem,
    LocaleFileResponse,
    LocaleResolveResponse,
    UserPreferencesResponse,
)
from platform.localization.services.locale_file_service import LocaleFileService
from platform.localization.services.locale_resolver import LocaleResolver
from platform.localization.services.preferences_service import PreferencesService
from typing import Any
from uuid import UUID


class LocalizationService:
    def __init__(
        self,
        preferences: PreferencesService,
        locale_files: LocaleFileService,
        locale_resolver: LocaleResolver,
    ) -> None:
        self.preferences = preferences
        self.locale_files = locale_files
        self.locale_resolver = locale_resolver

    async def get_preferences(self, user_id: UUID) -> UserPreferencesResponse:
        return await self.preferences.get_for_user(user_id)

    async def update_preferences(
        self,
        user_id: UUID,
        requester: Any,
        *,
        correlation_ctx: CorrelationContext | None = None,
        **fields: Any,
    ) -> UserPreferencesResponse:
        return await self.preferences.upsert(
            user_id,
            requester,
            correlation_ctx=correlation_ctx,
            **fields,
        )

    async def get_user_language(self, user_id: UUID) -> str:
        return await self.preferences.get_user_language(user_id)

    async def get_latest_locale_file(self, locale_code: str) -> LocaleFileResponse:
        return await self.locale_files.get_latest(locale_code)

    async def list_locale_files(self) -> list[LocaleFileListItem]:
        return await self.locale_files.list_available()

    async def publish_locale_file(
        self,
        *,
        locale_code: str,
        translations: dict[str, Any],
        requester: Any,
        vendor_source_ref: str | None,
        correlation_ctx: CorrelationContext | None = None,
    ) -> LocaleFileResponse:
        return await self.locale_files.publish(
            locale_code=locale_code,
            translations=translations,
            requester=requester,
            vendor_source_ref=vendor_source_ref,
            correlation_ctx=correlation_ctx,
        )

    async def resolve_locale(
        self,
        *,
        url_hint: str | None,
        user_preference: str | None,
        accept_language: str | None,
    ) -> LocaleResolveResponse:
        locale, source = await self.locale_resolver.resolve(
            url_hint=url_hint,
            user_preference=user_preference,
            accept_language=accept_language,
        )
        return LocaleResolveResponse(locale=locale, source=source)

    async def handle_workspace_archived(self, workspace_id: UUID) -> None:
        await self.preferences.clear_default_workspace(workspace_id)

