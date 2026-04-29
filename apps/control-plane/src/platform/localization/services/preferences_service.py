from __future__ import annotations

import json
from datetime import UTC, datetime
from functools import lru_cache
from platform.audit.service import AuditChainService
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.exceptions import AuthorizationError, PlatformError
from platform.localization.constants import (
    DATA_EXPORT_FORMATS,
    DEFAULT_LOCALE,
    DEFAULT_THEME,
    LOCALES,
    THEMES,
)
from platform.localization.events import (
    LocalizationEventType,
    UserPreferencesUpdatedPayload,
    publish_localization_event,
)
from platform.localization.exceptions import (
    DataExportFormatInvalidError,
    InvalidThemeError,
    InvalidTimezoneError,
    UnsupportedLocaleError,
    WorkspaceNotMemberError,
)
from platform.localization.models import UserPreferences
from platform.localization.repository import LocalizationRepository
from platform.localization.schemas import DataExportFormat, Theme, UserPreferencesResponse
from typing import Any, cast
from uuid import UUID, uuid4
from zoneinfo import available_timezones


@lru_cache(maxsize=1)
def _iana_timezones() -> frozenset[str]:
    return frozenset(available_timezones())


class PreferencesService:
    def __init__(
        self,
        repository: LocalizationRepository,
        *,
        audit_chain: AuditChainService | None = None,
        producer: EventProducer | None = None,
        workspaces_service: Any | None = None,
    ) -> None:
        self.repository = repository
        self.audit_chain = audit_chain
        self.producer = producer
        self.workspaces_service = workspaces_service

    async def get_for_user(self, user_id: UUID) -> UserPreferencesResponse:
        row = await self.repository.get_user_preferences(user_id)
        if row is None:
            return self._virtual_default(user_id)
        return self._response(row, is_persisted=True)

    async def upsert(
        self,
        user_id: UUID,
        requester: Any,
        *,
        correlation_ctx: CorrelationContext | None = None,
        **fields: Any,
    ) -> UserPreferencesResponse:
        requester_id = self._requester_id(requester)
        if requester_id != user_id:
            raise AuthorizationError(
                "PREFERENCES_FORBIDDEN",
                "User preferences can only be modified by the current user.",
            )
        await self._validate_fields(user_id, fields)
        before = await self.get_for_user(user_id)
        row = await self.repository.upsert_user_preferences(user_id, **fields)
        after = self._response(row, is_persisted=True)
        changed_fields = self._changed_fields(before, after, fields)
        if changed_fields:
            await self._audit(
                "localization.user_preferences.updated",
                user_id=user_id,
                changed_fields=changed_fields,
            )
            payload = UserPreferencesUpdatedPayload(
                user_id=user_id,
                changed_fields=changed_fields,
                updated_at=datetime.now(UTC),
            )
            await publish_localization_event(
                self.producer,
                LocalizationEventType.user_preferences_updated,
                payload,
                correlation_ctx or CorrelationContext(correlation_id=uuid4()),
            )
        return after

    async def get_user_language(self, user_id: UUID) -> str:
        try:
            row = await self.repository.get_user_preferences(user_id)
        except PlatformError:
            return DEFAULT_LOCALE
        if row is None or row.language not in LOCALES:
            return DEFAULT_LOCALE
        return row.language

    async def clear_default_workspace(self, workspace_id: UUID) -> list[UserPreferencesResponse]:
        rows = await self.repository.clear_default_workspace(workspace_id)
        responses = [self._response(row, is_persisted=True) for row in rows]
        for response in responses:
            await self._audit(
                "localization.user_preferences.default_workspace_cleared",
                user_id=response.user_id,
                workspace_id=workspace_id,
            )
        return responses

    async def _validate_fields(self, user_id: UUID, fields: dict[str, Any]) -> None:
        theme = fields.get("theme")
        if theme is not None and theme not in THEMES:
            raise InvalidThemeError(str(theme))
        language = fields.get("language")
        if language is not None and language not in LOCALES:
            raise UnsupportedLocaleError(str(language))
        timezone = fields.get("timezone")
        if timezone is not None and timezone not in _iana_timezones():
            raise InvalidTimezoneError(str(timezone))
        data_export_format = fields.get("data_export_format")
        if data_export_format is not None and data_export_format not in DATA_EXPORT_FORMATS:
            raise DataExportFormatInvalidError(str(data_export_format))
        workspace_id = fields.get("default_workspace_id")
        if workspace_id is not None and self.workspaces_service is not None:
            try:
                await self.workspaces_service.get_workspace(workspace_id, user_id)
            except PlatformError as exc:
                raise WorkspaceNotMemberError(workspace_id) from exc

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
    def _requester_id(requester: Any) -> UUID | None:
        if isinstance(requester, dict):
            raw = requester.get("sub") or requester.get("user_id")
            return UUID(str(raw)) if raw is not None else None
        raw_id = getattr(requester, "id", None)
        return UUID(str(raw_id)) if raw_id is not None else None

    @staticmethod
    def _changed_fields(
        before: UserPreferencesResponse,
        after: UserPreferencesResponse,
        touched_fields: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        changed: dict[str, dict[str, Any]] = {}
        for field in touched_fields:
            old = getattr(before, field)
            new = getattr(after, field)
            if old != new:
                changed[field] = {"old": old, "new": new}
        return changed

    @staticmethod
    def _virtual_default(user_id: UUID) -> UserPreferencesResponse:
        return UserPreferencesResponse(
            id=None,
            user_id=user_id,
            default_workspace_id=None,
            theme=cast(Theme, DEFAULT_THEME),
            language=DEFAULT_LOCALE,
            timezone="UTC",
            notification_preferences={},
            data_export_format="json",
            is_persisted=False,
            created_at=None,
            updated_at=None,
        )

    @staticmethod
    def _response(row: UserPreferences, *, is_persisted: bool) -> UserPreferencesResponse:
        return UserPreferencesResponse(
            id=row.id,
            user_id=row.user_id,
            default_workspace_id=row.default_workspace_id,
            theme=cast(Theme, row.theme),
            language=row.language,
            timezone=row.timezone,
            notification_preferences=dict(row.notification_preferences or {}),
            data_export_format=cast(DataExportFormat, row.data_export_format),
            is_persisted=is_persisted,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
