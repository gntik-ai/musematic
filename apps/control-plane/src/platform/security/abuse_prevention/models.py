"""SQLAlchemy models for the abuse-prevention bounded context (UPD-050).

Mirrors migration 109 — six tables. Note: NONE of these models extend
``TenantScopedMixin`` because all UPD-050 surfaces apply to the default
tenant only (an Enterprise tenant cannot publish to public marketplace,
nor does it have an abuse-prevention surface — see spec Out of Scope).
The ``account_suspensions`` row carries an explicit ``tenant_id`` for
audit-chain partitioning per UPD-046 R7, but the data itself is not
tenant-scoped via RLS.
"""

from __future__ import annotations

from datetime import datetime
from platform.common.models.base import Base
from platform.common.models.mixins import UUIDMixin
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


class AbusePreventionSetting(Base):
    """Key/value store of abuse-prevention thresholds and toggles.

    The 12 seed rows are inserted by migration 109; the admin surface
    (T032 / T037 / T060) mutates them via the settings service.
    """

    __tablename__ = "abuse_prevention_settings"

    setting_key: Mapped[str] = mapped_column(String(length=64), primary_key=True)
    setting_value_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class DisposableEmailDomain(Base):
    """Curated disposable-email domain registry.

    Synced weekly from the upstream `disposable-email-domains` GitHub
    project per research R3. Domains stop being blocked after the
    7-day soak window once `pending_removal_at` is in the past.
    """

    __tablename__ = "disposable_email_domains"

    domain: Mapped[str] = mapped_column(String(length=253), primary_key=True)
    source: Mapped[str] = mapped_column(String(length=64), nullable=False)
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    pending_removal_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class DisposableEmailOverride(Base):
    """Super-admin override that exempts a domain from the disposable check."""

    __tablename__ = "disposable_email_overrides"

    domain: Mapped[str] = mapped_column(String(length=253), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text(), nullable=True)


class TrustedSourceAllowlistEntry(Base, UUIDMixin):
    """IP or ASN that bypasses velocity rules (FR-027).

    `kind` is constrained to `ip` or `asn` by a CHECK constraint
    declared in the migration.
    """

    __tablename__ = "trusted_source_allowlist"

    kind: Mapped[str] = mapped_column(String(length=8), nullable=False)
    value: Mapped[str] = mapped_column(String(length=64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text(), nullable=True)


class SignupVelocityCounter(Base):
    """Durable snapshot of a Redis-tracked velocity counter.

    Composite primary key `(counter_key, counter_window_start)` so the
    same counter key can have multiple historical windows recorded.
    """

    __tablename__ = "signup_velocity_counters"
    __table_args__ = (
        Index("svc_window_idx", "counter_window_start"),
    )

    counter_key: Mapped[str] = mapped_column(
        String(length=128), primary_key=True
    )
    counter_window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    counter_value: Mapped[int] = mapped_column(
        Integer(), nullable=False, server_default="0"
    )


class AccountSuspension(Base, UUIDMixin):
    """Durable record of a suspension event.

    Active suspension is `lifted_at IS NULL`; the partial index
    `as_user_active_idx` covers the login-path point lookup. Reason and
    suspended_by columns each have CHECK constraints declared in the
    migration.
    """

    __tablename__ = "account_suspensions"
    __table_args__ = (
        Index(
            "as_user_active_idx",
            "user_id",
            postgresql_where=text("lifted_at IS NULL"),
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(length=64), nullable=False)
    evidence_json: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    suspended_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    suspended_by: Mapped[str] = mapped_column(
        String(length=32), nullable=False, server_default=text("'system'")
    )
    suspended_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    lifted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lifted_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    lift_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
