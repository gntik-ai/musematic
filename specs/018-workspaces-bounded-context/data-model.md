# Data Model: Workspaces Bounded Context

**Feature**: 018-workspaces-bounded-context  
**Date**: 2026-04-11  
**Phase**: 1 — Design

---

## Enums

```python
# models.py

class WorkspaceStatus(str, Enum):
    active = "active"
    archived = "archived"
    deleted = "deleted"

class WorkspaceRole(str, Enum):
    owner = "owner"
    admin = "admin"
    member = "member"
    viewer = "viewer"

class GoalStatus(str, Enum):
    open = "open"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"
```

---

## SQLAlchemy Models

### Workspace

```python
# Table: workspaces_workspaces
class Workspace(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, AuditMixin):
    __tablename__ = "workspaces_workspaces"

    name: Mapped[str]                               # max 100 chars
    description: Mapped[str | None]                  # optional, max 500 chars
    status: Mapped[WorkspaceStatus]                  # active | archived | deleted
    owner_id: Mapped[uuid.UUID]                      # FK to accounts_users.id (logical, not enforced)
    is_default: Mapped[bool]                         # True for auto-provisioned workspaces
    
    # Relationships
    memberships: Mapped[list["Membership"]] = relationship(back_populates="workspace")
    goals: Mapped[list["WorkspaceGoal"]] = relationship(back_populates="workspace")
    settings: Mapped["WorkspaceSettings | None"] = relationship(back_populates="workspace", uselist=False)
    visibility_grant: Mapped["WorkspaceVisibilityGrant | None"] = relationship(back_populates="workspace", uselist=False)

    # Indexes
    __table_args__ = (
        Index("ix_workspaces_owner_id", "owner_id"),
        Index("ix_workspaces_owner_name_status", "owner_id", "name", "status", unique=True,
              postgresql_where=text("status != 'deleted'")),
    )
```

### Membership

```python
# Table: workspaces_memberships
class Membership(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "workspaces_memberships"

    workspace_id: Mapped[uuid.UUID]                  # FK to workspaces_workspaces.id
    user_id: Mapped[uuid.UUID]                       # FK to accounts_users.id (logical)
    role: Mapped[WorkspaceRole]                      # owner | admin | member | viewer

    # Relationships
    workspace: Mapped["Workspace"] = relationship(back_populates="memberships")

    # Indexes
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_user"),
        Index("ix_memberships_user_id", "user_id"),
    )
```

### WorkspaceGoal

```python
# Table: workspaces_goals
class WorkspaceGoal(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "workspaces_goals"

    workspace_id: Mapped[uuid.UUID]                  # FK to workspaces_workspaces.id
    title: Mapped[str]                               # max 200 chars
    description: Mapped[str | None]                  # optional, max 2000 chars
    status: Mapped[GoalStatus]                       # open | in_progress | completed | cancelled
    gid: Mapped[uuid.UUID]                           # Goal ID — unique, first-class correlation dimension
    created_by: Mapped[uuid.UUID]                    # user_id who created the goal

    # Relationships
    workspace: Mapped["Workspace"] = relationship(back_populates="goals")

    # Indexes
    __table_args__ = (
        UniqueConstraint("gid", name="uq_goal_gid"),
        Index("ix_goals_workspace_id", "workspace_id"),
        Index("ix_goals_workspace_status", "workspace_id", "status"),
    )
```

### WorkspaceSettings

```python
# Table: workspaces_settings
class WorkspaceSettings(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "workspaces_settings"

    workspace_id: Mapped[uuid.UUID]                  # FK to workspaces_workspaces.id, unique
    subscribed_agents: Mapped[list[str]]             # ARRAY(Text) — agent FQN patterns
    subscribed_fleets: Mapped[list[uuid.UUID]]       # ARRAY(UUID) — fleet IDs
    subscribed_policies: Mapped[list[uuid.UUID]]     # ARRAY(UUID) — policy IDs
    subscribed_connectors: Mapped[list[uuid.UUID]]   # ARRAY(UUID) — connector IDs

    # Relationships
    workspace: Mapped["Workspace"] = relationship(back_populates="settings")

    __table_args__ = (
        UniqueConstraint("workspace_id", name="uq_settings_workspace"),
    )
```

### WorkspaceVisibilityGrant

```python
# Table: workspaces_visibility_grants
class WorkspaceVisibilityGrant(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "workspaces_visibility_grants"

    workspace_id: Mapped[uuid.UUID]                  # FK to workspaces_workspaces.id, unique
    visibility_agents: Mapped[list[str]]             # ARRAY(Text) — agent FQN patterns
    visibility_tools: Mapped[list[str]]              # ARRAY(Text) — tool FQN patterns

    # Relationships
    workspace: Mapped["Workspace"] = relationship(back_populates="visibility_grant")

    __table_args__ = (
        UniqueConstraint("workspace_id", name="uq_visibility_workspace"),
    )
```

---

## Goal Status State Machine

```python
# state_machine.py

VALID_GOAL_TRANSITIONS: dict[GoalStatus, set[GoalStatus]] = {
    GoalStatus.open: {GoalStatus.in_progress, GoalStatus.cancelled},
    GoalStatus.in_progress: {GoalStatus.completed, GoalStatus.cancelled},
    GoalStatus.completed: set(),       # terminal
    GoalStatus.cancelled: set(),       # terminal
}

def validate_goal_transition(current: GoalStatus, target: GoalStatus) -> None:
    """Raises InvalidTransitionError if the transition is not allowed."""
    if target not in VALID_GOAL_TRANSITIONS.get(current, set()):
        raise InvalidTransitionError(f"Cannot transition goal from {current} to {target}")
```

---

## Pydantic Schemas

### Workspace Schemas

```python
# schemas.py

class CreateWorkspaceRequest(BaseModel):
    name: str                                        # min 1, max 100
    description: str | None = None                   # max 500

class UpdateWorkspaceRequest(BaseModel):
    name: str | None = None                          # min 1, max 100
    description: str | None = None                   # max 500

class WorkspaceResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    status: WorkspaceStatus
    owner_id: uuid.UUID
    is_default: bool
    created_at: datetime
    updated_at: datetime

class WorkspaceListResponse(BaseModel):
    items: list[WorkspaceResponse]
    total: int
    page: int
    page_size: int
```

### Membership Schemas

```python
class AddMemberRequest(BaseModel):
    user_id: uuid.UUID
    role: WorkspaceRole                              # default: member

class ChangeMemberRoleRequest(BaseModel):
    role: WorkspaceRole

class MembershipResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    role: WorkspaceRole
    created_at: datetime

class MemberListResponse(BaseModel):
    items: list[MembershipResponse]
    total: int
```

### Goal Schemas

```python
class CreateGoalRequest(BaseModel):
    title: str                                       # min 1, max 200
    description: str | None = None                   # max 2000

class UpdateGoalStatusRequest(BaseModel):
    status: GoalStatus

class GoalResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    gid: uuid.UUID                                   # Goal ID — first-class correlation
    title: str
    description: str | None
    status: GoalStatus
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

class GoalListResponse(BaseModel):
    items: list[GoalResponse]
    total: int
```

### Visibility Grant Schemas

```python
class SetVisibilityGrantRequest(BaseModel):
    visibility_agents: list[str]                     # FQN patterns
    visibility_tools: list[str]                      # FQN patterns

class VisibilityGrantResponse(BaseModel):
    workspace_id: uuid.UUID
    visibility_agents: list[str]
    visibility_tools: list[str]
    updated_at: datetime
```

### Settings Schemas

```python
class UpdateSettingsRequest(BaseModel):
    subscribed_agents: list[str] | None = None       # FQN patterns
    subscribed_fleets: list[uuid.UUID] | None = None
    subscribed_policies: list[uuid.UUID] | None = None
    subscribed_connectors: list[uuid.UUID] | None = None

class SettingsResponse(BaseModel):
    workspace_id: uuid.UUID
    subscribed_agents: list[str]
    subscribed_fleets: list[uuid.UUID]
    subscribed_policies: list[uuid.UUID]
    subscribed_connectors: list[uuid.UUID]
    updated_at: datetime
```

---

## Kafka Event Types

Published to `workspaces.events` topic (key: `workspace_id`):

| Event Type | Trigger | Payload (beyond envelope) |
|-----------|---------|---------------------------|
| `workspaces.workspace.created` | Workspace created | workspace_id, name, owner_id, is_default |
| `workspaces.workspace.updated` | Workspace name/desc changed | workspace_id, changed_fields |
| `workspaces.workspace.archived` | Workspace archived | workspace_id, archived_by |
| `workspaces.workspace.restored` | Workspace restored | workspace_id, restored_by |
| `workspaces.workspace.deleted` | Workspace permanently deleted | workspace_id, deleted_by |
| `workspaces.membership.added` | Member added | workspace_id, user_id, role |
| `workspaces.membership.role_changed` | Member role changed | workspace_id, user_id, old_role, new_role |
| `workspaces.membership.removed` | Member removed | workspace_id, user_id |
| `workspaces.goal.created` | Goal created | workspace_id, gid, title, created_by |
| `workspaces.goal.status_changed` | Goal status changed | workspace_id, gid, old_status, new_status |
| `workspaces.visibility_grant.updated` | Visibility grant set/removed | workspace_id, visibility_agents, visibility_tools |

---

## Consumed Events

| Source Topic | Event Type | Action |
|-------------|-----------|--------|
| `accounts.events` | `accounts.user.activated` | Create default workspace for user (idempotent) |

---

## Role Permission Matrix

| Operation | Owner | Admin | Member | Viewer |
|-----------|-------|-------|--------|--------|
| Update workspace | ✓ | ✓ | ✗ | ✗ |
| Archive workspace | ✓ | ✗ | ✗ | ✗ |
| Restore workspace | ✓ | ✗ | ✗ | ✗ |
| Delete workspace | ✓ | ✗ | ✗ | ✗ |
| Add member | ✓ | ✓ | ✗ | ✗ |
| Remove member | ✓ | ✓ | ✗ | ✗ |
| Change member role | ✓ | ✓* | ✗ | ✗ |
| List members | ✓ | ✓ | ✓ | ✓ |
| Create goal | ✓ | ✓ | ✓ | ✗ |
| Update goal status | ✓ | ✓ | ✓ | ✗ |
| List goals | ✓ | ✓ | ✓ | ✓ |
| Set visibility grant | ✓ | ✓ | ✗ | ✗ |
| View settings | ✓ | ✓ | ✓ | ✓ |
| Update settings | ✓ | ✓ | ✗ | ✗ |

*Admin can change roles but cannot promote to owner or demote an owner.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WORKSPACES_DEFAULT_NAME_TEMPLATE` | `{display_name}'s Workspace` | Template for default workspace name |
| `WORKSPACES_DEFAULT_LIMIT` | `0` | Default max_workspaces for new users (0=unlimited) |
