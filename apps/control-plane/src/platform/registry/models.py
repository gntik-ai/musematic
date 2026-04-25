from __future__ import annotations

from datetime import datetime
from enum import IntEnum, StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import SoftDeleteMixin, TimestampMixin, UUIDMixin
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class LifecycleStatus(StrEnum):
    draft = "draft"
    validated = "validated"
    published = "published"
    disabled = "disabled"
    deprecated = "deprecated"
    archived = "archived"
    decommissioned = "decommissioned"


class AgentRoleType(StrEnum):
    executor = "executor"
    planner = "planner"
    orchestrator = "orchestrator"
    observer = "observer"
    judge = "judge"
    enforcer = "enforcer"
    custom = "custom"


class MaturityLevel(IntEnum):
    unverified = 0
    basic_compliance = 1
    tested = 2
    certified = 3


class AssessmentMethod(StrEnum):
    manifest_declared = "manifest_declared"
    system_assessed = "system_assessed"


class EmbeddingStatus(StrEnum):
    pending = "pending"
    complete = "complete"
    failed = "failed"


class AgentNamespace(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "registry_namespaces"
    __table_args__ = (
        Index(
            "uq_registry_ns_workspace_name",
            "workspace_id",
            "name",
            unique=True,
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(length=63), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    profiles: Mapped[list[AgentProfile]] = relationship(
        "platform.registry.models.AgentProfile",
        back_populates="namespace",
        cascade="all, delete-orphan",
    )


class AgentProfile(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "registry_agent_profiles"
    __table_args__ = (
        Index(
            "uq_registry_profile_ns_local_active",
            "namespace_id",
            "local_name",
            unique=True,
            postgresql_where=text("status != 'decommissioned'"),
        ),
        Index(
            "uq_registry_profile_fqn_active",
            "fqn",
            unique=True,
            postgresql_where=text("status != 'decommissioned'"),
        ),
        Index("ix_registry_profile_workspace_status", "workspace_id", "status"),
        Index("ix_registry_profile_fqn", "fqn"),
        Index("ix_registry_profile_needs_reindex", "needs_reindex"),
        Index("ix_registry_profile_mcp_server_refs", "mcp_server_refs", postgresql_using="gin"),
    )

    workspace_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    namespace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("registry_namespaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    local_name: Mapped[str] = mapped_column(String(length=63), nullable=False)
    fqn: Mapped[str] = mapped_column(String(length=127), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    purpose: Mapped[str] = mapped_column(Text(), nullable=False)
    approach: Mapped[str | None] = mapped_column(Text(), nullable=True)
    role_types: Mapped[list[str]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=list,
    )
    custom_role_description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    visibility_agents: Mapped[list[str]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=list,
    )
    visibility_tools: Mapped[list[str]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=list,
    )
    tags: Mapped[list[str]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=list,
    )
    mcp_server_refs: Mapped[list[str]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    data_categories: Mapped[list[str]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    status: Mapped[LifecycleStatus] = mapped_column(
        SAEnum(LifecycleStatus, name="registry_lifecycle_status"),
        nullable=False,
        default=LifecycleStatus.draft,
    )
    maturity_level: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    embedding_status: Mapped[EmbeddingStatus] = mapped_column(
        SAEnum(EmbeddingStatus, name="registry_embedding_status"),
        nullable=False,
        default=EmbeddingStatus.pending,
    )
    needs_reindex: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    created_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    decommissioned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decommission_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    decommissioned_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    namespace: Mapped[AgentNamespace] = relationship(
        "platform.registry.models.AgentNamespace",
        back_populates="profiles",
    )
    revisions: Mapped[list[AgentRevision]] = relationship(
        "platform.registry.models.AgentRevision",
        back_populates="agent_profile",
        cascade="all, delete-orphan",
        order_by="AgentRevision.created_at.asc()",
    )
    maturity_records: Mapped[list[AgentMaturityRecord]] = relationship(
        "platform.registry.models.AgentMaturityRecord",
        back_populates="agent_profile",
        cascade="all, delete-orphan",
    )
    lifecycle_audit_entries: Mapped[list[LifecycleAuditEntry]] = relationship(
        "platform.registry.models.LifecycleAuditEntry",
        back_populates="agent_profile",
        cascade="all, delete-orphan",
    )


class AgentRevision(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "registry_agent_revisions"
    __table_args__ = (
        Index("ix_registry_revision_profile_id", "agent_profile_id"),
        Index(
            "uq_registry_revision_profile_version",
            "agent_profile_id",
            "version",
            unique=True,
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    agent_profile_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("registry_agent_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[str] = mapped_column(String(length=32), nullable=False)
    sha256_digest: Mapped[str] = mapped_column(String(length=64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(length=512), nullable=False)
    manifest_snapshot: Mapped[dict[str, object]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
    )
    uploaded_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    agent_profile: Mapped[AgentProfile] = relationship(
        "platform.registry.models.AgentProfile",
        back_populates="revisions",
    )


class AgentMaturityRecord(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "registry_maturity_records"

    workspace_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    agent_profile_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("registry_agent_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    previous_level: Mapped[int] = mapped_column(Integer(), nullable=False)
    new_level: Mapped[int] = mapped_column(Integer(), nullable=False)
    assessment_method: Mapped[AssessmentMethod] = mapped_column(
        SAEnum(AssessmentMethod, name="registry_assessment_method"),
        nullable=False,
    )
    reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    actor_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    agent_profile: Mapped[AgentProfile] = relationship(
        "platform.registry.models.AgentProfile",
        back_populates="maturity_records",
    )


class LifecycleAuditEntry(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "registry_lifecycle_audit"
    __table_args__ = (Index("ix_registry_lifecycle_audit_profile", "agent_profile_id"),)

    workspace_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    agent_profile_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("registry_agent_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    previous_status: Mapped[LifecycleStatus] = mapped_column(
        SAEnum(LifecycleStatus, name="registry_lifecycle_status"),
        nullable=False,
    )
    new_status: Mapped[LifecycleStatus] = mapped_column(
        SAEnum(LifecycleStatus, name="registry_lifecycle_status"),
        nullable=False,
    )
    actor_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text(), nullable=True)

    agent_profile: Mapped[AgentProfile] = relationship(
        "platform.registry.models.AgentProfile",
        back_populates="lifecycle_audit_entries",
    )
