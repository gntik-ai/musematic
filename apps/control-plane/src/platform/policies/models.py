from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import AuditMixin, TimestampMixin, UUIDMixin
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class PolicyScopeType(StrEnum):
    global_scope = "global"
    deployment = "deployment"
    workspace = "workspace"
    agent = "agent"
    execution = "execution"


class PolicyStatus(StrEnum):
    active = "active"
    archived = "archived"


class AttachmentTargetType(StrEnum):
    global_scope = "global"
    deployment = "deployment"
    workspace = "workspace"
    agent_revision = "agent_revision"
    fleet = "fleet"
    execution = "execution"


class EnforcementComponent(StrEnum):
    tool_gateway = "tool_gateway"
    memory_write_gate = "memory_write_gate"
    sanitizer = "sanitizer"
    visibility_filter = "visibility_filter"


class PolicyPolicy(Base, UUIDMixin, TimestampMixin, AuditMixin):
    __tablename__ = "policy_policies"
    __table_args__ = (
        Index("ix_policy_policies_name", "name"),
        Index("ix_policy_policies_scope_type", "scope_type"),
        Index("ix_policy_policies_status", "status"),
        Index("ix_policy_policies_workspace_id", "workspace_id"),
    )

    name: Mapped[str] = mapped_column(String(length=255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    scope_type: Mapped[PolicyScopeType] = mapped_column(
        SAEnum(PolicyScopeType, name="policy_scope_type"),
        nullable=False,
    )
    status: Mapped[PolicyStatus] = mapped_column(
        SAEnum(PolicyStatus, name="policy_status"),
        nullable=False,
        default=PolicyStatus.active,
    )
    workspace_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    current_version_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("policy_versions.id", ondelete="SET NULL"),
        nullable=True,
    )

    versions: Mapped[list[PolicyVersion]] = relationship(
        "platform.policies.models.PolicyVersion",
        foreign_keys="platform.policies.models.PolicyVersion.policy_id",
        back_populates="policy",
        order_by="platform.policies.models.PolicyVersion.version_number.asc()",
    )
    current_version: Mapped[PolicyVersion | None] = relationship(
        "platform.policies.models.PolicyVersion",
        foreign_keys=[current_version_id],
        post_update=True,
    )
    attachments: Mapped[list[PolicyAttachment]] = relationship(
        "platform.policies.models.PolicyAttachment",
        back_populates="policy",
        cascade="all, delete-orphan",
    )


class PolicyVersion(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "policy_versions"
    __table_args__ = (
        Index("ix_policy_versions_policy_id", "policy_id"),
        Index("uq_policy_versions_policy_version", "policy_id", "version_number", unique=True),
    )

    policy_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("policy_policies.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer(), nullable=False)
    rules: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False), nullable=False, default=dict
    )
    change_summary: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    policy: Mapped[PolicyPolicy] = relationship(
        "platform.policies.models.PolicyPolicy",
        foreign_keys=[policy_id],
        back_populates="versions",
    )
    attachments: Mapped[list[PolicyAttachment]] = relationship(
        "platform.policies.models.PolicyAttachment",
        back_populates="policy_version",
    )


class PolicyAttachment(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "policy_attachments"
    __table_args__ = (
        Index("ix_policy_attachments_policy_id", "policy_id"),
        Index("ix_policy_attachments_target_type", "target_type"),
        Index("ix_policy_attachments_is_active", "is_active"),
        Index("ix_policy_attachments_target_lookup", "target_type", "target_id", "is_active"),
    )

    policy_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("policy_policies.id", ondelete="CASCADE"),
        nullable=False,
    )
    policy_version_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("policy_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_type: Mapped[AttachmentTargetType] = mapped_column(
        SAEnum(AttachmentTargetType, name="policy_attachment_target_type"),
        nullable=False,
    )
    target_id: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    created_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    policy: Mapped[PolicyPolicy] = relationship(
        "platform.policies.models.PolicyPolicy",
        back_populates="attachments",
    )
    policy_version: Mapped[PolicyVersion] = relationship(
        "platform.policies.models.PolicyVersion",
        back_populates="attachments",
    )


class PolicyBlockedActionRecord(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "policy_blocked_action_records"
    __table_args__ = (
        Index("ix_policy_blocked_action_records_agent_id", "agent_id"),
        Index("ix_policy_blocked_action_records_component", "enforcement_component"),
        Index("ix_policy_blocked_action_records_execution_id", "execution_id"),
        Index("ix_policy_blocked_action_records_workspace_id", "workspace_id"),
    )

    agent_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    agent_fqn: Mapped[str] = mapped_column(String(length=512), nullable=False)
    enforcement_component: Mapped[EnforcementComponent] = mapped_column(
        SAEnum(EnforcementComponent, name="policy_enforcement_component"),
        nullable=False,
    )
    action_type: Mapped[str] = mapped_column(String(length=64), nullable=False)
    target: Mapped[str] = mapped_column(String(length=512), nullable=False)
    block_reason: Mapped[str] = mapped_column(String(length=255), nullable=False)
    policy_rule_ref: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    execution_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    workspace_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)


class PolicyBundleCache(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "policy_bundle_cache"
    __table_args__ = (
        Index("ix_policy_bundle_cache_fingerprint", "fingerprint", unique=True),
        Index("ix_policy_bundle_cache_expires_at", "expires_at"),
    )

    fingerprint: Mapped[str] = mapped_column(String(length=64), nullable=False)
    bundle_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False), nullable=False, default=dict
    )
    source_version_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True)), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
