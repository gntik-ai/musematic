from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from platform.common.models.base import Base
from platform.common.models.mixins import TenantScopedMixin, UUIDMixin
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


class ModelCatalogEntry(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "model_catalog_entries"
    __table_args__ = (
        UniqueConstraint("provider", "model_id", name="uq_model_catalog_provider_model"),
        CheckConstraint("context_window > 0", name="ck_model_catalog_context_window"),
        CheckConstraint(
            "input_cost_per_1k_tokens >= 0",
            name="ck_model_catalog_input_cost_nonnegative",
        ),
        CheckConstraint(
            "output_cost_per_1k_tokens >= 0",
            name="ck_model_catalog_output_cost_nonnegative",
        ),
        CheckConstraint(
            "quality_tier IN ('tier1', 'tier2', 'tier3')",
            name="ck_model_catalog_quality_tier",
        ),
        CheckConstraint(
            "status IN ('approved', 'deprecated', 'blocked')",
            name="ck_model_catalog_status",
        ),
        CheckConstraint(
            "approval_expires_at > approved_at",
            name="ck_model_catalog_approval_expiry",
        ),
        Index("ix_model_catalog_status_expires", "status", "approval_expires_at"),
    )

    provider: Mapped[str] = mapped_column(String(length=64), nullable=False)
    model_id: Mapped[str] = mapped_column(String(length=256), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(length=256), nullable=True)
    approved_use_cases: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    prohibited_use_cases: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    context_window: Mapped[int] = mapped_column(Integer, nullable=False)
    input_cost_per_1k_tokens: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    output_cost_per_1k_tokens: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    quality_tier: Mapped[str] = mapped_column(String(length=16), nullable=False)
    approved_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    approval_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(length=32), nullable=False, default="approved")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ModelCard(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "model_cards"

    catalog_entry_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("model_catalog_entries.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    capabilities: Mapped[str | None] = mapped_column(Text, nullable=True)
    training_cutoff: Mapped[date | None] = mapped_column(Date, nullable=True)
    known_limitations: Mapped[str | None] = mapped_column(Text, nullable=True)
    safety_evaluations: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    bias_assessments: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    card_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ModelFallbackPolicy(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "model_fallback_policies"
    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('global', 'workspace', 'agent')",
            name="ck_model_fallback_scope_type",
        ),
        CheckConstraint(
            "(scope_type = 'global' AND scope_id IS NULL) OR "
            "(scope_type != 'global' AND scope_id IS NOT NULL)",
            name="ck_model_fallback_scope_id",
        ),
        CheckConstraint("retry_count > 0 AND retry_count <= 10", name="ck_model_fallback_retry"),
        CheckConstraint(
            "backoff_strategy IN ('fixed', 'linear', 'exponential')",
            name="ck_model_fallback_backoff",
        ),
        CheckConstraint(
            "acceptable_quality_degradation IN ('tier_equal', 'tier_plus_one', 'tier_plus_two')",
            name="ck_model_fallback_quality_degradation",
        ),
        CheckConstraint(
            "recovery_window_seconds >= 30",
            name="ck_model_fallback_recovery_window",
        ),
        Index("ix_fallback_scope", "scope_type", "scope_id"),
        Index("ix_fallback_primary", "primary_model_id"),
    )

    name: Mapped[str] = mapped_column(String(length=128), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(length=16), nullable=False)
    scope_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    primary_model_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("model_catalog_entries.id"),
        nullable=False,
    )
    fallback_chain: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    backoff_strategy: Mapped[str] = mapped_column(
        String(length=32), nullable=False, default="exponential"
    )
    acceptable_quality_degradation: Mapped[str] = mapped_column(
        String(length=16), nullable=False, default="tier_plus_one"
    )
    recovery_window_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ModelProviderCredential(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "model_provider_credentials"
    __table_args__ = (
        UniqueConstraint("workspace_id", "provider", name="uq_model_provider_workspace_provider"),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(length=64), nullable=False)
    vault_ref: Mapped[str] = mapped_column(String(length=256), nullable=False)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rotation_schedule_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("secret_rotation_schedules.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class InjectionDefensePattern(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "injection_defense_patterns"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_injection_pattern_severity",
        ),
        CheckConstraint(
            "layer IN ('input_sanitizer', 'output_validator')",
            name="ck_injection_pattern_layer",
        ),
        CheckConstraint(
            "action IN ('strip', 'quote_as_data', 'reject', 'redact', 'block')",
            name="ck_injection_pattern_action",
        ),
        Index("ix_injection_patterns_layer", "layer", "workspace_id", "severity"),
    )

    pattern_name: Mapped[str] = mapped_column(String(length=128), nullable=False)
    pattern_regex: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(length=16), nullable=False)
    layer: Mapped[str] = mapped_column(String(length=32), nullable=False)
    action: Mapped[str] = mapped_column(String(length=32), nullable=False)
    seeded: Mapped[bool] = mapped_column(nullable=False, default=False)
    workspace_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("workspaces_workspaces.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
