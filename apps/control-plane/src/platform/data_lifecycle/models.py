"""SQLAlchemy models for the data_lifecycle bounded context.

Three tables back this BC:

* :class:`DataExportJob` — async export job ledger (workspace + tenant)
* :class:`DeletionJob`   — two-phase deletion ledger (workspace + tenant)
* :class:`SubProcessor`  — platform-level public sub-processor registry

DataExportJob and DeletionJob are tenant-scoped (RLS enforced via the
``tenant_isolation`` policy installed by migration 111). SubProcessor is
a platform-level table read by the public sub-processors page; it has
NO RLS policy because it must be readable without a tenant context.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import (
    TenantScopedMixin,
    TimestampMixin,
    UUIDMixin,
)
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

if TYPE_CHECKING:  # pragma: no cover - type-only imports
    pass


class ScopeType(StrEnum):
    """Scope of a data-lifecycle job."""

    workspace = "workspace"
    tenant = "tenant"


class ExportStatus(StrEnum):
    """Lifecycle of a data export job."""

    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class DeletionPhase(StrEnum):
    """Phase of a two-phase deletion job."""

    phase_1 = "phase_1"
    phase_2 = "phase_2"
    completed = "completed"
    aborted = "aborted"


class DataExportJob(Base, UUIDMixin, TenantScopedMixin):
    """Async data export job ledger.

    Migrations: created in ``111_data_lifecycle``. RLS enforced via
    ``tenant_isolation`` policy.
    """

    __tablename__ = "data_export_jobs"
    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('workspace','tenant')",
            name="ck_data_export_jobs_scope_type",
        ),
        CheckConstraint(
            "status IN ('pending','processing','completed','failed')",
            name="ck_data_export_jobs_status",
        ),
        Index(
            "data_export_jobs_tenant_status_idx",
            "tenant_id",
            "status",
            text("created_at DESC"),
        ),
        Index(
            "data_export_jobs_scope_idx",
            "scope_type",
            "scope_id",
            text("created_at DESC"),
        ),
        Index(
            "data_export_jobs_active_idx",
            "status",
            postgresql_where=text("status IN ('pending','processing')"),
        ),
    )

    scope_type: Mapped[str] = mapped_column(String(length=16), nullable=False)
    scope_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    requested_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(length=32), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    output_url: Mapped[str | None] = mapped_column(Text(), nullable=True)
    output_size_bytes: Mapped[int | None] = mapped_column(BigInteger(), nullable=True)
    output_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    correlation_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class DeletionJob(Base, UUIDMixin, TenantScopedMixin):
    """Two-phase deletion job ledger.

    Append-only state machine: phase_1 -> phase_2 -> completed, or
    phase_1 -> aborted. The ``uq_deletion_jobs_active_per_scope``
    partial-unique index prevents two concurrent active deletions on
    the same scope.
    """

    __tablename__ = "deletion_jobs"
    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('workspace','tenant')",
            name="ck_deletion_jobs_scope_type",
        ),
        CheckConstraint(
            "phase IN ('phase_1','phase_2','completed','aborted')",
            name="ck_deletion_jobs_phase",
        ),
        CheckConstraint(
            "grace_period_days BETWEEN 1 AND 365",
            name="ck_deletion_jobs_grace_bounds",
        ),
        Index(
            "deletion_jobs_scope_idx",
            "tenant_id",
            "scope_type",
            "scope_id",
            text("created_at DESC"),
        ),
        Index(
            "deletion_jobs_grace_scan_idx",
            "grace_ends_at",
            postgresql_where=text("phase = 'phase_1'"),
        ),
        Index(
            "deletion_jobs_cancel_token_uq",
            "cancel_token_hash",
            unique=True,
        ),
        Index(
            "uq_deletion_jobs_active_per_scope",
            "scope_type",
            "scope_id",
            unique=True,
            postgresql_where=text("phase IN ('phase_1','phase_2')"),
        ),
    )

    scope_type: Mapped[str] = mapped_column(String(length=16), nullable=False)
    scope_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    phase: Mapped[str] = mapped_column(String(length=16), nullable=False)
    requested_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    two_pa_token_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    grace_period_days: Mapped[int] = mapped_column(Integer(), nullable=False)
    grace_ends_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    cancel_token_hash: Mapped[bytes] = mapped_column(LargeBinary(), nullable=False)
    cancel_token_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    cascade_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    cascade_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    tombstone_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    final_export_job_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("data_export_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    abort_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    correlation_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class SubProcessorEmailSubscription(Base, UUIDMixin):
    """Public-page change-notification subscriptions.

    Created via ``POST /api/v1/public/sub-processors/subscribe`` with
    anti-enumeration semantics: every request returns 202 with the same
    body. The server SHA-256-hashes a one-time verification token and
    sends the plaintext via UPD-077 email. The subscriber clicks the
    link to set ``verified_at``; only verified rows receive change
    fanouts.

    Platform-level (no tenant_id) because the public page is a public
    artifact — subscribers don't belong to any tenant.
    """

    __tablename__ = "sub_processor_email_subscriptions"
    __table_args__ = (
        Index(
            "uq_sub_processor_email_subscriptions_token_hash",
            "verification_token_hash",
            unique=True,
        ),
        Index(
            "ix_sub_processor_email_subscriptions_email_active",
            "email",
            postgresql_where=text(
                "verified_at IS NOT NULL AND unsubscribed_at IS NULL"
            ),
        ),
    )

    email: Mapped[str] = mapped_column(String(length=320), nullable=False)
    verification_token_hash: Mapped[bytes] = mapped_column(
        LargeBinary(), nullable=False
    )
    verification_token_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    unsubscribed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class SubProcessor(Base, UUIDMixin, TimestampMixin):
    """Platform-level public sub-processor registry.

    Read by the public ``/legal/sub-processors`` page (independently
    deployed via the ``public-pages`` Helm release per rule 49).
    Writes are admin-only and audited.

    NOT tenant-scoped — the public page must render without a tenant
    context. Access control is enforced at the router layer.
    """

    __tablename__ = "sub_processors"
    __table_args__ = (
        UniqueConstraint("name", name="uq_sub_processors_name"),
        Index(
            "sub_processors_active_category_idx",
            "is_active",
            "category",
        ),
    )

    name: Mapped[str] = mapped_column(String(length=128), nullable=False)
    category: Mapped[str] = mapped_column(String(length=64), nullable=False)
    location: Mapped[str] = mapped_column(String(length=64), nullable=False)
    data_categories: Mapped[list[str]] = mapped_column(
        ARRAY(Text()),
        nullable=False,
        server_default=text("ARRAY[]::text[]"),
    )
    privacy_policy_url: Mapped[str | None] = mapped_column(Text(), nullable=True)
    dpa_url: Mapped[str | None] = mapped_column(Text(), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        server_default=text("true"),
    )
    started_using_at: Mapped[date | None] = mapped_column(Date(), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
