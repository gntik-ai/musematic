# Data Model: Workspace Goal Management and Agent Response Decision

**Phase 1 output for**: [plan.md](plan.md)
**Date**: 2026-04-18

---

## Overview

This feature makes three additive database changes:

1. **Two new columns + one new column on `workspaces_goals`** (existing table, workspaces BC)
2. **New table `workspaces_agent_decision_configs`** (workspaces BC, one row per workspace × agent FQN)
3. **New table `workspace_goal_decision_rationales`** (interactions BC, one row per agent × message evaluation)

No existing columns or tables are removed or renamed. No existing constraints change.

---

## Migration: 046_workspace_goal_lifecycle_and_decision

**File**: `apps/control-plane/migrations/versions/046_workspace_goal_lifecycle_and_decision.py`
**Revision**: `046_workspace_goal_lifecycle_and_decision`
**Down revision**: `045_oauth_providers_and_links`

```sql
-- 1. New enum type for goal lifecycle state
CREATE TYPE workspacegoalstate AS ENUM ('ready', 'working', 'complete');

-- 2. Extend workspaces_goals (additive)
ALTER TABLE workspaces_goals
  ADD COLUMN state workspacegoalstate NOT NULL DEFAULT 'ready',
  ADD COLUMN auto_complete_timeout_seconds INTEGER NULL,
  ADD COLUMN last_message_at TIMESTAMPTZ NULL;

CREATE INDEX ix_workspaces_goals_state ON workspaces_goals (state);
CREATE INDEX ix_workspaces_goals_auto_complete
  ON workspaces_goals (state, last_message_at)
  WHERE state = 'working' AND auto_complete_timeout_seconds IS NOT NULL;

-- 3. New table: per-workspace, per-agent decision strategy config
CREATE TABLE workspaces_agent_decision_configs (
  id          UUID          NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  created_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  workspace_id UUID         NOT NULL REFERENCES workspaces_workspaces(id) ON DELETE CASCADE,
  agent_fqn   TEXT          NOT NULL,
  response_decision_strategy VARCHAR(64) NOT NULL DEFAULT 'llm_relevance',
  response_decision_config   JSONB       NOT NULL DEFAULT '{}',
  subscribed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX uq_wksp_agent_decision_cfg
  ON workspaces_agent_decision_configs (workspace_id, agent_fqn);
CREATE INDEX ix_wksp_agent_decision_cfg_workspace
  ON workspaces_agent_decision_configs (workspace_id);

-- 4. New table: immutable decision rationale per (agent, message) evaluation
CREATE TABLE workspace_goal_decision_rationales (
  id           UUID         NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  workspace_id UUID         NOT NULL,
  goal_id      UUID         NOT NULL REFERENCES workspaces_goals(id) ON DELETE CASCADE,
  message_id   UUID         NOT NULL REFERENCES workspace_goal_messages(id) ON DELETE CASCADE,
  agent_fqn    TEXT         NOT NULL,
  strategy_name VARCHAR(64) NOT NULL,
  decision     VARCHAR(8)   NOT NULL,   -- 'respond' | 'skip'
  score        FLOAT4       NULL,
  matched_terms TEXT[]       NOT NULL DEFAULT '{}',
  rationale    TEXT         NOT NULL DEFAULT '',
  error        TEXT         NULL
);

CREATE UNIQUE INDEX uq_wgdr_message_agent
  ON workspace_goal_decision_rationales (message_id, agent_fqn);
CREATE INDEX ix_wgdr_goal ON workspace_goal_decision_rationales (goal_id, created_at);
CREATE INDEX ix_wgdr_workspace ON workspace_goal_decision_rationales (workspace_id, agent_fqn);
```

**Rollback**:

```sql
DROP TABLE workspace_goal_decision_rationales;
DROP TABLE workspaces_agent_decision_configs;
ALTER TABLE workspaces_goals
  DROP COLUMN last_message_at,
  DROP COLUMN auto_complete_timeout_seconds,
  DROP COLUMN state;
DROP TYPE workspacegoalstate;
```

---

## SQLAlchemy Models

### Modified: `WorkspaceGoal` in `apps/control-plane/src/platform/workspaces/models.py`

```python
import enum
from sqlalchemy import Enum as SAEnum

class WorkspaceGoalState(enum.Enum):
    ready    = "ready"
    working  = "working"
    complete = "complete"

# Additions to WorkspaceGoal class (existing columns unchanged):
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
    TZDateTime(), nullable=True, default=None
)
```

### New: `WorkspaceAgentDecisionConfig` in `apps/control-plane/src/platform/workspaces/models.py`

```python
class WorkspaceAgentDecisionConfig(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "workspaces_agent_decision_configs"
    __table_args__ = (
        UniqueConstraint("workspace_id", "agent_fqn",
                         name="uq_wksp_agent_decision_cfg"),
        Index("ix_wksp_agent_decision_cfg_workspace", "workspace_id"),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_fqn: Mapped[str] = mapped_column(Text(), nullable=False)
    response_decision_strategy: Mapped[str] = mapped_column(
        String(64), nullable=False, default="llm_relevance"
    )
    response_decision_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB(), nullable=False, default=dict
    )
    subscribed_at: Mapped[datetime] = mapped_column(
        TZDateTime(), nullable=False, server_default=func.now()
    )

    workspace: Mapped["Workspace"] = relationship(
        "platform.workspaces.models.Workspace",
        back_populates="agent_decision_configs",
    )
```

### New: `WorkspaceGoalDecisionRationale` in `apps/control-plane/src/platform/interactions/models.py`

```python
class WorkspaceGoalDecisionRationale(Base, UUIDMixin):
    __tablename__ = "workspace_goal_decision_rationales"
    __table_args__ = (
        UniqueConstraint("message_id", "agent_fqn", name="uq_wgdr_message_agent"),
        Index("ix_wgdr_goal", "goal_id", "created_at"),
        Index("ix_wgdr_workspace", "workspace_id", "agent_fqn"),
    )

    created_at: Mapped[datetime] = mapped_column(
        TZDateTime(), nullable=False, server_default=func.now()
    )
    workspace_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    goal_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_goals.id", ondelete="CASCADE"),
        nullable=False,
    )
    message_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspace_goal_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_fqn: Mapped[str] = mapped_column(Text(), nullable=False)
    strategy_name: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(8), nullable=False)  # respond | skip
    score: Mapped[float | None] = mapped_column(Float(), nullable=True)
    matched_terms: Mapped[list[str]] = mapped_column(
        ARRAY(Text()), nullable=False, default=list
    )
    rationale: Mapped[str] = mapped_column(Text(), nullable=False, default="")
    error: Mapped[str | None] = mapped_column(Text(), nullable=True)
```

---

## Entities and Relationships

```
Workspace (1) ──── (N) WorkspaceGoal
                         ├── state: WorkspaceGoalState [NEW]
                         ├── auto_complete_timeout_seconds [NEW]
                         └── last_message_at [NEW]

Workspace (1) ──── (N) WorkspaceAgentDecisionConfig  [NEW TABLE]
                         ├── agent_fqn (TEXT)
                         ├── response_decision_strategy (VARCHAR 64)
                         ├── response_decision_config (JSONB)
                         └── subscribed_at (TIMESTAMPTZ, tie-break)

WorkspaceGoal (1) ──── (N) WorkspaceGoalMessage  [existing, unchanged]

WorkspaceGoalMessage (1) ──── (N) WorkspaceGoalDecisionRationale  [NEW TABLE]
                                     ├── agent_fqn (TEXT)
                                     ├── strategy_name (VARCHAR 64)
                                     ├── decision: respond | skip
                                     ├── score (FLOAT4, nullable)
                                     ├── matched_terms (TEXT[])
                                     ├── rationale (TEXT)
                                     └── error (TEXT, nullable)
```

---

## State Machine: WorkspaceGoalState

```
READY ──[first message posted]──► WORKING ──[admin complete OR auto-complete]──► COMPLETE
  │                                                                                    │
  │         (no direct READY → COMPLETE transition)                                   │
  └─────────────────────────────────────────────────────────────────────────────────  X
                                                               (COMPLETE is terminal — no transitions out)
```

**Invariants**:
- New goals always start in READY (server_default).
- READY → WORKING: triggered by `post_goal_message()`, atomic with the INSERT of the first message.
- WORKING → COMPLETE: triggered by explicit admin API call OR auto-completion scanner.
- COMPLETE → any: forbidden. Returns 409 Conflict.
- Concurrent message post vs. COMPLETE transition: protected by `SELECT FOR UPDATE` on the goal row.

---

## Strategy Configuration Schemas (JSONB)

Each strategy name maps to a required `response_decision_config` JSONB shape:

| Strategy | Required keys | Optional keys |
|----------|--------------|---------------|
| `llm_relevance` | `threshold` (float 0–1) | `model`, `prompt_template` |
| `allow_blocklist` | (none — empty config = default skip) | `allowlist` (str[]), `blocklist` (str[]), `default` (respond\|skip) |
| `keyword` | `keywords` (str[], min 1) | `mode` (any_of\|all_of, default any_of), `case_sensitive` (bool) |
| `embedding_similarity` | `threshold` (float 0–1) | `collection` (str), `reference_ids` (str[]) |
| `best_match` | (none — applies across all agents) | `score_aggregation` (max\|mean, default max) |

Missing required keys → strategy fails safe to "skip" with config error logged (FR-021).

---

## Pydantic Schemas (new)

**Request/Response schemas** (in `workspaces/schemas.py` or `interactions/schemas.py`):

```python
class GoalStateTransitionRequest(BaseModel):
    target_state: Literal["complete"]
    reason: str | None = None

class GoalStateTransitionResponse(BaseModel):
    goal_id: UUID
    previous_state: str
    new_state: str
    automatic: bool = False
    transitioned_at: datetime

class AgentDecisionConfigUpsert(BaseModel):
    response_decision_strategy: str = "llm_relevance"
    response_decision_config: dict[str, Any] = {}

class AgentDecisionConfigResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    agent_fqn: str
    response_decision_strategy: str
    response_decision_config: dict[str, Any]
    subscribed_at: datetime
    created_at: datetime
    updated_at: datetime

class DecisionRationaleResponse(BaseModel):
    id: UUID
    goal_id: UUID
    message_id: UUID
    agent_fqn: str
    strategy_name: str
    decision: Literal["respond", "skip"]
    score: float | None
    matched_terms: list[str]
    rationale: str
    error: str | None
    created_at: datetime

class DecisionRationaleListResponse(BaseModel):
    items: list[DecisionRationaleResponse]
    total: int
```
