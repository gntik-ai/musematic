# Data Model: Judge/Enforcer Governance Pipeline

**Feature**: 061-judge-enforcer-governance  
**Migration**: 048  
**Date**: 2026-04-18

---

## Section 1: Alembic Migration 048

**File**: `apps/control-plane/migrations/versions/048_governance_pipeline.py`  
**Revision**: `"048_governance_pipeline"`  
**Down Revision**: `"047_notifications_alerts"`

### New Tables

```sql
-- Enum types
CREATE TYPE verdicttype AS ENUM ('COMPLIANT', 'WARNING', 'VIOLATION', 'ESCALATE_TO_HUMAN');
CREATE TYPE enforcementactiontype AS ENUM ('block', 'quarantine', 'notify', 'revoke_cert', 'log_and_continue');

-- Governance Verdicts: immutable audit record per judge evaluation
CREATE TABLE governance_verdicts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    judge_agent_fqn VARCHAR(512) NOT NULL,
    verdict_type verdicttype NOT NULL,
    policy_id UUID REFERENCES policies(id) ON DELETE SET NULL,
    evidence JSONB NOT NULL,
    rationale TEXT NOT NULL,
    recommended_action VARCHAR(64),
    source_event_id UUID,
    fleet_id UUID REFERENCES fleets(id) ON DELETE SET NULL,
    workspace_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_governance_verdicts_workspace_id ON governance_verdicts(workspace_id);
CREATE INDEX ix_governance_verdicts_fleet_id ON governance_verdicts(fleet_id);
CREATE INDEX ix_governance_verdicts_verdict_type ON governance_verdicts(verdict_type);
CREATE INDEX ix_governance_verdicts_created_at ON governance_verdicts(created_at);

-- Enforcement Actions: immutable audit record per enforcer execution
CREATE TABLE enforcement_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    enforcer_agent_fqn VARCHAR(512) NOT NULL,
    verdict_id UUID NOT NULL REFERENCES governance_verdicts(id) ON DELETE CASCADE,
    action_type enforcementactiontype NOT NULL,
    target_agent_fqn VARCHAR(512),
    outcome JSONB,
    workspace_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_enforcement_actions_verdict_id ON enforcement_actions(verdict_id);
CREATE INDEX ix_enforcement_actions_action_type ON enforcement_actions(action_type);
CREATE INDEX ix_enforcement_actions_workspace_id ON enforcement_actions(workspace_id);
CREATE INDEX ix_enforcement_actions_created_at ON enforcement_actions(created_at);

-- Workspace Governance Chains: versioned, mirrors fleet_governance_chains structure
CREATE TABLE workspace_governance_chains (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    observer_fqns JSONB NOT NULL DEFAULT '[]',
    judge_fqns JSONB NOT NULL DEFAULT '[]',
    enforcer_fqns JSONB NOT NULL DEFAULT '[]',
    policy_binding_ids JSONB NOT NULL DEFAULT '[]',
    verdict_to_action_mapping JSONB NOT NULL DEFAULT '{}',
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_workspace_governance_chains_version ON workspace_governance_chains(workspace_id, version);
CREATE UNIQUE INDEX uq_workspace_governance_chains_current
    ON workspace_governance_chains(workspace_id)
    WHERE is_current = true;
CREATE INDEX ix_workspace_governance_chains_workspace_id ON workspace_governance_chains(workspace_id);
```

### Modified Tables

```sql
-- Add verdict_to_action_mapping to existing fleet governance chains
ALTER TABLE fleet_governance_chains
    ADD COLUMN verdict_to_action_mapping JSONB NOT NULL DEFAULT '{}';
```

---

## Section 2: SQLAlchemy Models

### New: `governance/models.py`

```python
from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from sqlalchemy import JSONB, Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from platform.common.models.base import Base, TimestampMixin, UUIDMixin


class VerdictType(StrEnum):
    COMPLIANT = "COMPLIANT"
    WARNING = "WARNING"
    VIOLATION = "VIOLATION"
    ESCALATE_TO_HUMAN = "ESCALATE_TO_HUMAN"


class ActionType(StrEnum):
    block = "block"
    quarantine = "quarantine"
    notify = "notify"
    revoke_cert = "revoke_cert"
    log_and_continue = "log_and_continue"


TERMINAL_VERDICT_TYPES: frozenset[str] = frozenset(
    {VerdictType.VIOLATION, VerdictType.ESCALATE_TO_HUMAN}
)


class GovernanceVerdict(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "governance_verdicts"
    __table_args__ = (
        Index("ix_governance_verdicts_workspace_id", "workspace_id"),
        Index("ix_governance_verdicts_fleet_id", "fleet_id"),
        Index("ix_governance_verdicts_verdict_type", "verdict_type"),
        Index("ix_governance_verdicts_created_at", "created_at"),
    )

    judge_agent_fqn: Mapped[str] = mapped_column(String(512), nullable=False)
    verdict_type: Mapped[str] = mapped_column(String(32), nullable=False)
    policy_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("policies.id", ondelete="SET NULL"),
        nullable=True,
    )
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_action: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_event_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    fleet_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("fleets.id", ondelete="SET NULL"),
        nullable=True,
    )
    workspace_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )

    enforcement_actions: Mapped[list[EnforcementAction]] = relationship(
        "EnforcementAction",
        back_populates="verdict",
        cascade="all, delete-orphan",
        lazy="noload",
    )


class EnforcementAction(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "enforcement_actions"
    __table_args__ = (
        Index("ix_enforcement_actions_verdict_id", "verdict_id"),
        Index("ix_enforcement_actions_action_type", "action_type"),
        Index("ix_enforcement_actions_workspace_id", "workspace_id"),
        Index("ix_enforcement_actions_created_at", "created_at"),
    )

    enforcer_agent_fqn: Mapped[str] = mapped_column(String(512), nullable=False)
    verdict_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("governance_verdicts.id", ondelete="CASCADE"),
        nullable=False,
    )
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_agent_fqn: Mapped[str | None] = mapped_column(String(512), nullable=True)
    outcome: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    workspace_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )

    verdict: Mapped[GovernanceVerdict] = relationship(
        "GovernanceVerdict", back_populates="enforcement_actions", lazy="noload"
    )
```

### New: `workspaces/models.py` (additive — append to file)

```python
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
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    observer_fqns: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    judge_fqns: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    enforcer_fqns: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    policy_binding_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    verdict_to_action_mapping: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
```

### Modified: `fleets/models.py` — FleetGovernanceChain (additive field)

```python
# Append after is_default field in FleetGovernanceChain:
verdict_to_action_mapping: Mapped[dict] = mapped_column(
    JSONB,
    nullable=False,
    default=dict,
    server_default=text("'{}'::jsonb"),
)
```

---

## Section 3: Pydantic Schemas

### New: `governance/schemas.py`

```python
class VerdictListQuery(BaseModel):
    target_agent_fqn: str | None = None
    policy_id: UUID | None = None
    verdict_type: str | None = None     # VerdictType value
    fleet_id: UUID | None = None
    workspace_id: UUID | None = None
    from_time: datetime | None = None
    to_time: datetime | None = None
    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = None           # opaque cursor for keyset pagination

class GovernanceVerdictRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    judge_agent_fqn: str
    verdict_type: str
    policy_id: UUID | None
    rationale: str
    recommended_action: str | None
    source_event_id: UUID | None
    fleet_id: UUID | None
    workspace_id: UUID | None
    created_at: datetime

class GovernanceVerdictDetail(GovernanceVerdictRead):
    evidence: dict
    enforcement_action: EnforcementActionRead | None = None

class EnforcementActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    enforcer_agent_fqn: str
    verdict_id: UUID
    action_type: str
    target_agent_fqn: str | None
    outcome: dict | None
    workspace_id: UUID | None
    created_at: datetime

class VerdictListResponse(BaseModel):
    items: list[GovernanceVerdictRead]
    total: int
    next_cursor: str | None = None

class EnforcementActionListResponse(BaseModel):
    items: list[EnforcementActionRead]
    total: int
    next_cursor: str | None = None
```

### Modified: `fleets/schemas.py` — FleetGovernanceChainUpdate + Response (additive fields)

```python
# In FleetGovernanceChainUpdate — add optional field:
verdict_to_action_mapping: dict[str, str] = Field(default_factory=dict)

# In FleetGovernanceChainResponse — add field:
verdict_to_action_mapping: dict[str, str]
```

### New: `workspaces/schemas.py` additions

```python
class WorkspaceGovernanceChainUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observer_fqns: list[str]
    judge_fqns: list[str]
    enforcer_fqns: list[str]
    policy_binding_ids: list[UUID] = Field(default_factory=list)
    verdict_to_action_mapping: dict[str, str] = Field(default_factory=dict)

    @field_validator("observer_fqns", "judge_fqns", "enforcer_fqns")
    @classmethod
    def normalize_fqn_lists(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]

class WorkspaceGovernanceChainResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    workspace_id: UUID
    version: int
    observer_fqns: list[str]
    judge_fqns: list[str]
    enforcer_fqns: list[str]
    policy_binding_ids: list[UUID]
    verdict_to_action_mapping: dict[str, str]
    is_current: bool
    is_default: bool
    created_at: datetime

class WorkspaceGovernanceChainListResponse(BaseModel):
    items: list[WorkspaceGovernanceChainResponse]
    total: int
```

---

## Section 4: Governance Events

### New: `governance/events.py`

```python
class GovernanceEventType(StrEnum):
    verdict_issued = "governance.verdict.issued"
    enforcement_executed = "governance.enforcement.executed"

class VerdictIssuedPayload(BaseModel):
    verdict_id: UUID
    judge_agent_fqn: str
    verdict_type: str
    policy_id: UUID | None
    fleet_id: UUID | None
    workspace_id: UUID | None
    source_event_id: UUID | None
    recommended_action: str | None

class EnforcementExecutedPayload(BaseModel):
    action_id: UUID
    verdict_id: UUID
    enforcer_agent_fqn: str
    action_type: str
    target_agent_fqn: str | None
    workspace_id: UUID | None
    outcome: dict | None
```

---

## Section 5: Service Interfaces

### `governance/services/pipeline_config.py`

```python
@dataclass
class ChainConfig:
    observer_fqns: list[str]
    judge_fqns: list[str]        # ordered: index 0 = first judge
    enforcer_fqns: list[str]
    policy_binding_ids: list[UUID]
    verdict_to_action_mapping: dict[str, str]
    scope: Literal["workspace", "fleet"]

class PipelineConfigService:
    async def resolve_chain(
        self,
        fleet_id: UUID | None,
        workspace_id: UUID | None,
    ) -> ChainConfig | None:
        # Workspace-level chain takes precedence (FR-013)
        # Returns None if no chain configured (default no-enforcement posture)

    async def validate_chain_update(
        self,
        observer_fqns: list[str],
        judge_fqns: list[str],
        enforcer_fqns: list[str],
    ) -> None:
        # FR-011: all judge_fqns must have AgentRoleType.judge
        # FR-012: all referenced FQNs must exist in registry
        # FR-025: no FQN appears in both judge_fqns and enforcer_fqns as self-referential loop
```

### `governance/services/judge_service.py`

```python
class JudgeService:
    async def process_signal(
        self,
        signal_envelope: EventEnvelope,
        fleet_id: UUID | None,
        workspace_id: UUID | None,
    ) -> list[GovernanceVerdict]:
        # FR-003: route to first judge in chain
        # FR-004: evaluate; emit verdict with all required fields
        # FR-005: persist all verdicts
        # FR-006: publish verdict_issued event
        # FR-021: judge unavailable timeout → ESCALATE_TO_HUMAN
        # FR-020: missing policy → ESCALATE_TO_HUMAN
        # FR-023: verdict missing required fields → reject + re-route as ESCALATE_TO_HUMAN
        # US5: layered judge chain — terminal verdict stops iteration

    async def process_fleet_anomaly_signal(
        self,
        fleet_id: UUID,
        chain: Any,   # FleetGovernanceChainResponse
        signal: dict,
    ) -> dict:
        # oje_service interface for FleetGovernanceChainService.trigger_oje_pipeline()
```

### `governance/services/enforcer_service.py`

```python
class EnforcerService:
    async def process_verdict(
        self,
        verdict: GovernanceVerdict,
        chain_config: ChainConfig,
    ) -> EnforcementAction:
        # FR-007: look up verdict_to_action_mapping
        # FR-008: execute action (block/quarantine/notify/revoke_cert/log_and_continue)
        # FR-009: publish enforcement_executed event
        # FR-010: unmapped verdict type → default log_and_continue
        # FR-022: idempotent per-verdict (check for existing action before executing)
        # FR-026: target deleted → persist with outcome noting missing target, no mutation
```

---

## Section 6: Config Settings

### `common/config.py` addition — GovernanceSettings

```python
class GovernanceSettings(BaseModel):
    rate_limit_per_observer_per_minute: int = 100
    retention_days: int = 90
    gc_interval_hours: int = 24
    judge_timeout_seconds: int = 30   # FR-021: timeout before ESCALATE_TO_HUMAN
```

Mount as `governance: GovernanceSettings` in `PlatformSettings`.

---

## Section 7: Project File Structure

```text
apps/control-plane/src/platform/

# NEW — governance bounded context
governance/
├── __init__.py
├── models.py                    ← GovernanceVerdict, EnforcementAction, VerdictType, ActionType
├── schemas.py                   ← Pydantic request/response schemas
├── events.py                    ← GovernanceEventType, payload classes, publish functions
├── exceptions.py                ← GovernanceError, VerdictNotFoundError, ChainConfigError
├── repository.py                ← GovernanceRepository (async SQLAlchemy)
├── dependencies.py              ← get_governance_service()
├── services/
│   ├── __init__.py
│   ├── pipeline_config.py       ← PipelineConfigService (chain resolution + validation)
│   ├── judge_service.py         ← JudgeService (signal evaluation + verdict issuance)
│   └── enforcer_service.py      ← EnforcerService (action execution)
├── consumers.py                 ← ObserverSignalConsumer, VerdictConsumer
└── router.py                    ← Audit query endpoints

# MODIFIED — fleets bounded context (additive)
fleets/models.py                 ← Add verdict_to_action_mapping field to FleetGovernanceChain
fleets/schemas.py                ← Add verdict_to_action_mapping to Update/Response schemas
fleets/governance.py             ← Wire JudgeService as oje_service

# MODIFIED — workspaces bounded context (additive)
workspaces/models.py             ← Add WorkspaceGovernanceChain model
workspaces/schemas.py            ← Add WorkspaceGovernanceChain schemas
workspaces/governance.py         ← NEW: WorkspaceGovernanceChainService
workspaces/router.py             ← Add workspace governance chain endpoints

# MODIFIED — infrastructure
migrations/versions/048_governance_pipeline.py  ← New migration
main.py                          ← Wire consumers + APScheduler retention GC
common/config.py                 ← Add GovernanceSettings
```
