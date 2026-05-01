from __future__ import annotations

from datetime import datetime
from platform.common.models.base import Base
from platform.common.models.mixins import TimestampMixin, UUIDMixin
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


class Tenant(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint(
            "slug ~ '^[a-z][a-z0-9-]{0,30}[a-z0-9]$'",
            name="ck_tenants_slug_format",
        ),
        CheckConstraint("kind IN ('default','enterprise')", name="ck_tenants_kind"),
        CheckConstraint(
            "data_isolation_mode IN ('pool','silo')",
            name="ck_tenants_data_isolation_mode",
        ),
        CheckConstraint(
            "status IN ('active','suspended','pending_deletion')",
            name="ck_tenants_status",
        ),
        Index(
            "tenants_one_default",
            "kind",
            unique=True,
            postgresql_where=text("kind = 'default'"),
        ),
        Index("tenants_kind_status_idx", "kind", "status"),
        Index(
            "tenants_scheduled_deletion_at_idx",
            "scheduled_deletion_at",
            postgresql_where=text("status = 'pending_deletion'"),
        ),
    )

    slug: Mapped[str] = mapped_column(String(length=32), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(length=16), nullable=False)
    subdomain: Mapped[str] = mapped_column(String(length=64), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(length=128), nullable=False)
    region: Mapped[str] = mapped_column(String(length=32), nullable=False)
    data_isolation_mode: Mapped[str] = mapped_column(
        String(length=8),
        nullable=False,
        default="pool",
        server_default="pool",
    )
    branding_config_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    subscription_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(length=24),
        nullable=False,
        default="active",
        server_default="active",
    )
    scheduled_deletion_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_by_super_admin_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    dpa_signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dpa_version: Mapped[str | None] = mapped_column(String(length=32), nullable=True)
    dpa_artifact_uri: Mapped[str | None] = mapped_column(String(length=512), nullable=True)
    dpa_artifact_sha256: Mapped[str | None] = mapped_column(String(length=64), nullable=True)
    contract_metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    feature_flags_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
