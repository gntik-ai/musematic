from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{0,30}[a-z0-9]$")

TenantKind = Literal["default", "enterprise"]
TenantStatus = Literal["active", "suspended", "pending_deletion"]
DataIsolationMode = Literal["pool", "silo"]


class TenantBranding(BaseModel):
    model_config = ConfigDict(extra="allow")

    logo_url: str | None = None
    accent_color_hex: str | None = None
    display_name_override: str | None = None
    favicon_url: str | None = None
    support_email: EmailStr | None = None

    @field_validator("accent_color_hex")
    @classmethod
    def _validate_accent(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise ValueError("accent_color_hex must be a #RRGGBB value")
        return value


class TenantCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=32)
    display_name: str = Field(min_length=1, max_length=128)
    region: str = Field(min_length=1, max_length=32)
    first_admin_email: EmailStr
    dpa_artifact_id: str = Field(min_length=1)
    dpa_version: str = Field(min_length=1, max_length=32)
    contract_metadata: dict[str, Any] = Field(default_factory=dict)
    branding_config: TenantBranding = Field(default_factory=TenantBranding)

    @field_validator("slug")
    @classmethod
    def _validate_slug(cls, value: str) -> str:
        if not SLUG_RE.fullmatch(value):
            raise ValueError("slug must match ^[a-z][a-z0-9-]{0,30}[a-z0-9]$")
        return value


class TenantUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    region: str | None = Field(default=None, min_length=1, max_length=32)
    branding_config: TenantBranding | None = None
    contract_metadata: dict[str, Any] | None = None
    feature_flags: dict[str, Any] | None = None


class TenantSuspend(BaseModel):
    reason: str = Field(min_length=1, max_length=512)


class TenantScheduleDeletion(BaseModel):
    reason: str = Field(min_length=1, max_length=512)
    two_pa_token: str = Field(min_length=1)


class TenantPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    kind: TenantKind
    subdomain: str
    status: TenantStatus
    region: str
    display_name: str
    branding: TenantBranding = Field(default_factory=TenantBranding)


class TenantAdminView(TenantPublic):
    scheduled_deletion_at: datetime | None = None
    created_at: datetime
    data_isolation_mode: DataIsolationMode = "pool"
    subscription_id: UUID | None = None
    dpa_signed_at: datetime | None = None
    dpa_version: str | None = None
    dpa_artifact_uri: str | None = None
    dpa_artifact_sha256: str | None = None
    contract_metadata: dict[str, Any] = Field(default_factory=dict)
    feature_flags: dict[str, Any] = Field(default_factory=dict)
    member_count: int = 0
    active_workspace_count: int = 0
    subscription_summary: dict[str, Any] | None = None


class TenantPlatformView(TenantAdminView):
    created_by_super_admin_id: UUID | None = None


class TenantListResponse(BaseModel):
    items: list[TenantAdminView]
    next_cursor: str | None = None


class TenantProvisionResponse(BaseModel):
    id: UUID
    slug: str
    subdomain: str
    kind: TenantKind
    status: TenantStatus
    first_admin_invite_sent_to: EmailStr
    dns_records_pending: bool = True
