from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Theme = Literal["light", "dark", "system", "high_contrast"]
DataExportFormat = Literal["json", "csv", "ndjson"]
LocaleResolveSource = Literal["url", "preference", "browser", "default"]


class UserPreferencesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = None
    user_id: UUID
    default_workspace_id: UUID | None = None
    theme: Theme
    language: str
    timezone: str
    notification_preferences: dict[str, Any] = Field(default_factory=dict)
    data_export_format: DataExportFormat
    is_persisted: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


class UserPreferencesUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    theme: Theme | None = None
    language: str | None = None
    timezone: str | None = None
    default_workspace_id: UUID | None = None
    notification_preferences: dict[str, Any] | None = None
    data_export_format: DataExportFormat | None = None


class LocaleFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    locale_code: str
    version: int
    translations: dict[str, Any]
    published_at: datetime | None
    published_by: UUID | None = None
    vendor_source_ref: str | None = None
    created_at: datetime


class LocaleFileListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    locale_code: str
    version: int
    published_at: datetime | None
    published_by: UUID | None = None
    vendor_source_ref: str | None = None
    created_at: datetime


class LocaleFilePublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    locale_code: str
    translations: dict[str, Any]
    vendor_source_ref: str | None = Field(default=None, max_length=256)


class LocaleResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url_hint: str | None = None
    accept_language: str | None = None
    user_preference: str | None = None


class LocaleResolveResponse(BaseModel):
    locale: str
    source: LocaleResolveSource


class DriftCheckNamespaceRow(BaseModel):
    namespace: str
    locale_code: str
    english_published_at: datetime | None
    localized_published_at: datetime | None
    days_drift: float | None
    in_grace: bool
    over_threshold: bool


class DriftCheckResponse(BaseModel):
    threshold_days: int
    rows: list[DriftCheckNamespaceRow]

