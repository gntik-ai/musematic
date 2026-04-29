from __future__ import annotations

import json
from datetime import UTC, datetime
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.localization.dependencies import (
    get_locale_file_service,
    get_locale_resolver,
    get_localization_service,
    get_preferences_service,
)
from platform.localization.exceptions import LocaleFileVersionConflictError
from platform.localization.router import router as localization_router
from platform.localization.service import LocalizationService
from platform.localization.services.locale_file_service import LocaleFileService
from platform.localization.services.locale_resolver import LocaleResolver
from platform.localization.services.preferences_service import PreferencesService
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI

NOW = datetime(2026, 4, 29, 12, 0, tzinfo=UTC)
Row = SimpleNamespace


class PreferencesRepository:
    def __init__(self) -> None:
        self.rows: dict[UUID, Row] = {}

    async def get_user_preferences(self, user_id: UUID) -> Row | None:
        return self.rows.get(user_id)

    async def upsert_user_preferences(self, user_id: UUID, **fields: Any) -> Row:
        current = self.rows.get(user_id)
        values = {
            "id": getattr(current, "id", uuid4()),
            "user_id": user_id,
            "default_workspace_id": getattr(current, "default_workspace_id", None),
            "theme": getattr(current, "theme", "system"),
            "language": getattr(current, "language", "en"),
            "timezone": getattr(current, "timezone", "UTC"),
            "notification_preferences": getattr(current, "notification_preferences", {}),
            "data_export_format": getattr(current, "data_export_format", "json"),
            "created_at": getattr(current, "created_at", NOW),
            "updated_at": NOW,
        }
        values.update(fields)
        self.rows[user_id] = Row(**values)
        return self.rows[user_id]

    async def clear_default_workspace(self, workspace_id: UUID) -> list[Row]:
        cleared: list[Row] = []
        for row in self.rows.values():
            if row.default_workspace_id == workspace_id:
                row.default_workspace_id = None
                cleared.append(row)
        return cleared


class LocaleFileRepository:
    def __init__(self) -> None:
        self.rows: list[Row] = []
        self.raise_conflict = False

    async def get_latest_locale_file(self, locale_code: str) -> Row | None:
        rows = [row for row in self.rows if row.locale_code == locale_code and row.published_at]
        return max(rows, key=lambda row: row.version, default=None)

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


class AuditChain:
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


class Workspaces:
    def __init__(self, *, allowed: bool = True) -> None:
        self.allowed = allowed

    async def get_workspace(self, workspace_id: UUID, user_id: UUID) -> object:
        del user_id
        if not self.allowed:
            raise PlatformError("WORKSPACE_NOT_FOUND", "Workspace not found.")
        return Row(id=workspace_id)


def build_preferences_service(
    repository: PreferencesRepository,
    *,
    audit_chain: AuditChain | None = None,
    workspaces: Workspaces | None = None,
) -> PreferencesService:
    return PreferencesService(
        repository,  # type: ignore[arg-type]
        audit_chain=audit_chain,  # type: ignore[arg-type]
        workspaces_service=workspaces,
    )


def build_locale_file_service(repository: LocaleFileRepository) -> LocaleFileService:
    return LocaleFileService(repository)  # type: ignore[arg-type]


def build_app(
    *,
    current_user: dict[str, Any],
    preferences_service: PreferencesService | None = None,
    locale_file_service: LocaleFileService | None = None,
    localization_service: LocalizationService | None = None,
    locale_resolver: LocaleResolver | None = None,
) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.include_router(localization_router)
    app.dependency_overrides[get_current_user] = lambda: current_user
    if preferences_service is not None:
        app.dependency_overrides[get_preferences_service] = lambda: preferences_service
    if locale_file_service is not None:
        app.dependency_overrides[get_locale_file_service] = lambda: locale_file_service
    if localization_service is not None:
        app.dependency_overrides[get_localization_service] = lambda: localization_service
    if locale_resolver is not None:
        app.dependency_overrides[get_locale_resolver] = lambda: locale_resolver
    return app
