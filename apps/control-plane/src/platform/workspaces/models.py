from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import (
    AuditMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
    WorkspaceScopedMixin,
)
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class WorkspaceStatus(StrEnum):
    active = "active"
    archived = "archived"
    deleted = "deleted"


class WorkspaceRole(StrEnum):
    owner = "owner"
    admin = "admin"
    member = "member"
    viewer = "viewer"


class GoalStatus(StrEnum):
    open = "open"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class WorkspaceGoalState(StrEnum):
    ready = "ready"
    working = "working"
    complete = "complete"


class Workspace(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, AuditMixin):
    __tablename__ = "workspaces_workspaces"
    __table_args__ = (
        Index("ix_workspaces_workspaces_owner_id", "owner_id"),
        Index(
            "ix_workspaces_workspaces_owner_name_status",
            "owner_id",
            "name",
            "status",
            unique=True,
            postgresql_where=text("status != 'deleted'"),
        ),
    )

    name: Mapped[str] = mapped_column(String(length=100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(length=500), nullable=True)
    status: Mapped[WorkspaceStatus] = mapped_column(
        SAEnum(WorkspaceStatus, name="workspaces_workspace_status"),
        nullable=False,
        default=WorkspaceStatus.active,
    )
    owner_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    memberships: Mapped[list[Membership]] = relationship(
        "platform.workspaces.models.Membership",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    goals: Mapped[list[WorkspaceGoal]] = relationship(
        "platform.workspaces.models.WorkspaceGoal",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    agent_decision_configs: Mapped[list[WorkspaceAgentDecisionConfig]] = relationship(
        "platform.workspaces.models.WorkspaceAgentDecisionConfig",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    settings: Mapped[WorkspaceSettings | None] = relationship(
        "platform.workspaces.models.WorkspaceSettings",
        back_populates="workspace",
        uselist=False,
        cascade="all, delete-orphan",
    )
    visibility_grant: Mapped[WorkspaceVisibilityGrant | None] = relationship(
        "platform.workspaces.models.WorkspaceVisibilityGrant",
        back_populates="workspace",
        uselist=False,
        cascade="all, delete-orphan",
    )


class Membership(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "workspaces_memberships"
    __table_args__ = (
        Index("ix_workspaces_memberships_user_id", "user_id"),
        Index("uq_workspaces_memberships_workspace_user", "workspace_id", "user_id", unique=True),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    role: Mapped[WorkspaceRole] = mapped_column(
        SAEnum(WorkspaceRole, name="workspaces_workspace_role"),
        nullable=False,
        default=WorkspaceRole.member,
    )

    workspace: Mapped[Workspace] = relationship(
        "platform.workspaces.models.Workspace",
        back_populates="memberships",
    )


class WorkspaceGoal(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "workspaces_goals"
    __table_args__ = (
        Index("uq_workspaces_goals_gid", "gid", unique=True),
        Index("ix_workspaces_goals_workspace_id", "workspace_id"),
        Index("ix_workspaces_goals_workspace_status", "workspace_id", "status"),
        Index("ix_workspaces_goals_state", "state"),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(length=200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[GoalStatus] = mapped_column(
        SAEnum(GoalStatus, name="workspaces_goal_status"),
        nullable=False,
        default=GoalStatus.open,
    )
    state: Mapped[WorkspaceGoalState] = mapped_column(
        SAEnum(WorkspaceGoalState, name="workspacegoalstate"),
        nullable=False,
        default=WorkspaceGoalState.ready,
        server_default="ready",
    )
    auto_complete_timeout_seconds: Mapped[int | None] = mapped_column(
        Integer(), nullable=True, default=None
    )
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    gid: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, default=uuid4)
    created_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    workspace: Mapped[Workspace] = relationship(
        "platform.workspaces.models.Workspace",
        back_populates="goals",
    )


class WorkspaceAgentDecisionConfig(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "workspaces_agent_decision_configs"
    __table_args__ = (
        UniqueConstraint("workspace_id", "agent_fqn", name="uq_wksp_agent_decision_cfg"),
        Index("ix_wksp_agent_decision_cfg_workspace", "workspace_id"),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_fqn: Mapped[str] = mapped_column(Text(), nullable=False)
    response_decision_strategy: Mapped[str] = mapped_column(
        String(64), nullable=False, default="llm_relevance", server_default="llm_relevance"
    )
    response_decision_config: Mapped[dict[str, object]] = mapped_column(
        JSONB(), nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    subscribed_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))

    workspace: Mapped[Workspace] = relationship(
        "platform.workspaces.models.Workspace",
        back_populates="agent_decision_configs",
    )


class WorkspaceSettings(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "workspaces_settings"
    __table_args__ = (Index("uq_workspaces_settings_workspace", "workspace_id", unique=True),)

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    subscribed_agents: Mapped[list[str]] = mapped_column(
        ARRAY(Text()),
        nullable=False,
        default=list,
    )
    subscribed_fleets: Mapped[list[UUID]] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True)),
        nullable=False,
        default=list,
    )
    subscribed_policies: Mapped[list[UUID]] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True)),
        nullable=False,
        default=list,
    )
    subscribed_connectors: Mapped[list[UUID]] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True)),
        nullable=False,
        default=list,
    )

    workspace: Mapped[Workspace] = relationship(
        "platform.workspaces.models.Workspace",
        back_populates="settings",
    )


class WorkspaceVisibilityGrant(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "workspaces_visibility_grants"
    __table_args__ = (
        Index("uq_workspaces_visibility_grants_workspace", "workspace_id", unique=True),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    visibility_agents: Mapped[list[str]] = mapped_column(
        ARRAY(Text()),
        nullable=False,
        default=list,
    )
    visibility_tools: Mapped[list[str]] = mapped_column(
        ARRAY(Text()),
        nullable=False,
        default=list,
    )

    workspace: Mapped[Workspace] = relationship(
        "platform.workspaces.models.Workspace",
        back_populates="visibility_grant",
    )


class WorkspaceGovernanceChain(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "workspace_governance_chains"
    __table_args__ = (
        Index("ix_workspace_governance_chains_workspace_id", "workspace_id"),
        Index(
            "uq_workspace_governance_chains_version",
            "workspace_id",
            "version",
            unique=True,
        ),
        Index(
            "uq_workspace_governance_chains_current",
            "workspace_id",
            unique=True,
            postgresql_where=text("is_current = true"),
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    observer_fqns: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    judge_fqns: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    enforcer_fqns: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    policy_binding_ids: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    verdict_to_action_mapping: Mapped[dict[str, str]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
