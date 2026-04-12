# Data Model: Fleet Management and Learning

**Feature**: 033-fleet-management-learning  
**Date**: 2026-04-12  
**Phase**: 1 — Design

---

## SQLAlchemy Models

### `fleets/models.py`

```python
from enum import Enum
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from platform.common.models.base import Base
from platform.common.models.mixins import (
    UUIDMixin, TimestampMixin, SoftDeleteMixin,
    WorkspaceScopedMixin
)


class FleetStatus(str, Enum):
    ACTIVE = "active"
    DEGRADED = "degraded"
    PAUSED = "paused"
    ARCHIVED = "archived"


class FleetTopologyType(str, Enum):
    HIERARCHICAL = "hierarchical"
    PEER_TO_PEER = "peer_to_peer"
    HYBRID = "hybrid"


class FleetMemberRole(str, Enum):
    LEAD = "lead"
    WORKER = "worker"
    OBSERVER = "observer"


class FleetMemberAvailability(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class Fleet(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, WorkspaceScopedMixin):
    """A named, workspace-scoped group of agents with topology and lifecycle state."""
    __tablename__ = "fleets"

    name: Mapped[str] = mapped_column(index=True)
    status: Mapped[FleetStatus] = mapped_column(default=FleetStatus.ACTIVE)
    topology_type: Mapped[FleetTopologyType]           # denormalized for quick query
    quorum_min: Mapped[int] = mapped_column(default=1) # minimum available members to stay active
    # Unique constraint: (workspace_id, name) — enforced at DB level


class FleetMember(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """Link between a Fleet and an agent (by FQN) with role and availability."""
    __tablename__ = "fleet_members"

    fleet_id: Mapped[UUID] = mapped_column(index=True)   # FK → fleets.id
    agent_fqn: Mapped[str]                               # e.g. "finance-ops:kyc-verifier"
    role: Mapped[FleetMemberRole]
    availability: Mapped[FleetMemberAvailability] = mapped_column(
        default=FleetMemberAvailability.AVAILABLE
    )
    joined_at: Mapped[datetime]
    # Unique constraint: (fleet_id, agent_fqn)


class FleetTopologyVersion(Base, UUIDMixin, TimestampMixin):
    """Immutable versioned record of fleet topology configuration."""
    __tablename__ = "fleet_topology_versions"

    fleet_id: Mapped[UUID] = mapped_column(index=True)
    topology_type: Mapped[FleetTopologyType]
    version: Mapped[int]
    config: Mapped[dict] = mapped_column(JSONB)
    # config for hierarchical: {"lead_fqn": "ns:agent"}
    # config for hybrid: {"sub_groups": [{"lead_fqn": ..., "member_fqns": [...]}]}
    # config for peer_to_peer: {}
    is_current: Mapped[bool] = mapped_column(default=True)
    # Partial unique index: (fleet_id) WHERE is_current = true


class FleetPolicyBinding(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """Binds a policy to a fleet, governing all member behavior."""
    __tablename__ = "fleet_policy_bindings"

    fleet_id: Mapped[UUID] = mapped_column(index=True)
    policy_id: Mapped[UUID]    # references policies.policy_policies — no FK, cross-boundary
    bound_by: Mapped[UUID]     # user_id who performed the binding
    # Unique constraint: (fleet_id, policy_id)


class ObserverAssignment(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """Links an observer agent to a fleet; observer receives execution stream events."""
    __tablename__ = "observer_assignments"

    fleet_id: Mapped[UUID] = mapped_column(index=True)
    observer_fqn: Mapped[str]    # agent FQN of the observer
    is_active: Mapped[bool] = mapped_column(default=True)
    # Unique constraint: (fleet_id, observer_fqn) WHERE is_active = true


class FleetGovernanceChain(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """Versioned OJE (Observer-Judge-Enforcer) chain configuration for a fleet."""
    __tablename__ = "fleet_governance_chains"

    fleet_id: Mapped[UUID] = mapped_column(index=True)
    version: Mapped[int]
    observer_fqns: Mapped[list] = mapped_column(JSONB)     # list of FQN strings
    judge_fqns: Mapped[list] = mapped_column(JSONB)        # list of FQN strings
    enforcer_fqns: Mapped[list] = mapped_column(JSONB)     # list of FQN strings
    policy_binding_ids: Mapped[list] = mapped_column(JSONB) # UUIDs of policies judges evaluate against
    is_current: Mapped[bool] = mapped_column(default=True)
    is_default: Mapped[bool] = mapped_column(default=False)  # true = platform-provided defaults
    # Partial unique index: (fleet_id) WHERE is_current = true


class FleetOrchestrationRules(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """Immutable versioned set of orchestration rules for a fleet."""
    __tablename__ = "fleet_orchestration_rules"

    fleet_id: Mapped[UUID] = mapped_column(index=True)
    version: Mapped[int]
    delegation: Mapped[dict] = mapped_column(JSONB)
    # {"strategy": "capability_match|round_robin|priority", "config": {...}}
    aggregation: Mapped[dict] = mapped_column(JSONB)
    # {"strategy": "merge|vote|first_wins", "config": {...}}
    escalation: Mapped[dict] = mapped_column(JSONB)
    # {"timeout_seconds": int, "failure_count": int, "escalate_to": "lead|human"}
    conflict_resolution: Mapped[dict] = mapped_column(JSONB)
    # {"strategy": "majority_vote|lead_decision|human_arbitration"}
    retry: Mapped[dict] = mapped_column(JSONB)
    # {"max_retries": int, "then": "reassign|fail"}
    max_parallelism: Mapped[int] = mapped_column(default=1)
    is_current: Mapped[bool] = mapped_column(default=True)
    # Partial unique index: (fleet_id) WHERE is_current = true
```

---

### `fleet_learning/models.py`

```python
from enum import Enum
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from platform.common.models.base import Base
from platform.common.models.mixins import (
    UUIDMixin, TimestampMixin, WorkspaceScopedMixin
)


class TransferRequestStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    APPLIED = "applied"
    REJECTED = "rejected"


class CommunicationStyle(str, Enum):
    VERBOSE = "verbose"
    CONCISE = "concise"
    STRUCTURED = "structured"


class DecisionSpeed(str, Enum):
    FAST = "fast"
    DELIBERATE = "deliberate"
    CONSENSUS_SEEKING = "consensus_seeking"


class RiskTolerance(str, Enum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class AutonomyLevel(str, Enum):
    SUPERVISED = "supervised"
    SEMI_AUTONOMOUS = "semi_autonomous"
    FULLY_AUTONOMOUS = "fully_autonomous"


class FleetPerformanceProfile(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """Aggregated fleet-level performance metrics for a time period (from ClickHouse)."""
    __tablename__ = "fleet_performance_profiles"

    fleet_id: Mapped[UUID] = mapped_column(index=True)
    period_start: Mapped[datetime]
    period_end: Mapped[datetime]
    avg_completion_time_ms: Mapped[float]
    success_rate: Mapped[float]           # 0.0–1.0
    cost_per_task: Mapped[float]
    avg_quality_score: Mapped[float]      # 0.0–1.0
    throughput_per_hour: Mapped[float]
    member_metrics: Mapped[dict] = mapped_column(JSONB)
    # {"fqn": {"avg_completion_time_ms": float, "success_rate": float,
    #           "cost_per_task": float, "quality_score": float}}
    flagged_member_fqns: Mapped[list] = mapped_column(JSONB, default=list)


class FleetAdaptationRule(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """Condition-action pair that auto-adjusts orchestration rules from performance data."""
    __tablename__ = "fleet_adaptation_rules"

    fleet_id: Mapped[UUID] = mapped_column(index=True)
    name: Mapped[str]
    condition: Mapped[dict] = mapped_column(JSONB)
    # {"metric": "avg_completion_time_ms", "operator": "gt", "threshold": 30000}
    # operator: "gt" | "lt" | "gte" | "lte" | "eq"
    action: Mapped[dict] = mapped_column(JSONB)
    # {"type": "set_max_parallelism", "value": 3}
    # {"type": "set_delegation_strategy", "value": "round_robin"}
    # {"type": "set_escalation_timeout", "value": 60}
    priority: Mapped[int] = mapped_column(default=0)  # higher = evaluated first
    is_active: Mapped[bool] = mapped_column(default=True)


class FleetAdaptationLog(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """Audit record of an applied adaptation action with before/after state."""
    __tablename__ = "fleet_adaptation_log"

    fleet_id: Mapped[UUID] = mapped_column(index=True)
    adaptation_rule_id: Mapped[UUID]       # FK → fleet_adaptation_rules.id
    triggered_at: Mapped[datetime]
    before_rules_version: Mapped[int]
    after_rules_version: Mapped[int]
    performance_snapshot: Mapped[dict] = mapped_column(JSONB)
    # snapshot of metrics that triggered the rule (subset of FleetPerformanceProfile)
    is_reverted: Mapped[bool] = mapped_column(default=False)
    reverted_at: Mapped[datetime | None] = mapped_column(default=None)


class CrossFleetTransferRequest(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """Request to share an orchestration pattern from one fleet to another."""
    __tablename__ = "cross_fleet_transfer_requests"

    source_fleet_id: Mapped[UUID] = mapped_column(index=True)
    target_fleet_id: Mapped[UUID] = mapped_column(index=True)
    status: Mapped[TransferRequestStatus] = mapped_column(
        default=TransferRequestStatus.PROPOSED
    )
    pattern_definition: Mapped[dict | None] = mapped_column(JSONB, default=None)
    # inline for payloads ≤50KB; NULL when stored in MinIO
    pattern_minio_key: Mapped[str | None] = mapped_column(default=None)
    # MinIO key: fleet-patterns/{transfer_id}/pattern.json
    proposed_by: Mapped[UUID]              # user_id
    approved_by: Mapped[UUID | None] = mapped_column(default=None)
    rejected_reason: Mapped[str | None] = mapped_column(default=None)
    applied_at: Mapped[datetime | None] = mapped_column(default=None)
    reverted_at: Mapped[datetime | None] = mapped_column(default=None)


class FleetPersonalityProfile(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """Versioned fleet-level behavioral attributes influencing orchestration defaults."""
    __tablename__ = "fleet_personality_profiles"

    fleet_id: Mapped[UUID] = mapped_column(index=True)
    communication_style: Mapped[CommunicationStyle]
    decision_speed: Mapped[DecisionSpeed]
    risk_tolerance: Mapped[RiskTolerance]
    autonomy_level: Mapped[AutonomyLevel]
    version: Mapped[int]
    is_current: Mapped[bool] = mapped_column(default=True)
    # Partial unique index: (fleet_id) WHERE is_current = true
```

---

## Pydantic Schemas

### `fleets/schemas.py` (key schemas)

```python
# Fleet
class FleetCreate(BaseModel):
    name: str
    topology_type: FleetTopologyType
    quorum_min: int = 1
    topology_config: dict = {}
    member_fqns: list[str] = []  # optional initial members (added as "worker" role)

class FleetUpdate(BaseModel):
    quorum_min: int | None = None

class FleetResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    status: FleetStatus
    topology_type: FleetTopologyType
    quorum_min: int
    created_at: datetime
    updated_at: datetime

# FleetMember
class FleetMemberCreate(BaseModel):
    agent_fqn: str
    role: FleetMemberRole = FleetMemberRole.WORKER

class FleetMemberRoleUpdate(BaseModel):
    role: FleetMemberRole

class FleetMemberResponse(BaseModel):
    id: UUID
    fleet_id: UUID
    agent_fqn: str
    role: FleetMemberRole
    availability: FleetMemberAvailability
    joined_at: datetime

# Topology
class FleetTopologyUpdateRequest(BaseModel):
    topology_type: FleetTopologyType
    config: dict = {}

class FleetTopologyVersionResponse(BaseModel):
    id: UUID
    fleet_id: UUID
    topology_type: FleetTopologyType
    version: int
    config: dict
    is_current: bool
    created_at: datetime

# Governance chain
class FleetGovernanceChainUpdate(BaseModel):
    observer_fqns: list[str]
    judge_fqns: list[str]
    enforcer_fqns: list[str]
    policy_binding_ids: list[UUID] = []

class FleetGovernanceChainResponse(BaseModel):
    id: UUID
    fleet_id: UUID
    version: int
    observer_fqns: list[str]
    judge_fqns: list[str]
    enforcer_fqns: list[str]
    policy_binding_ids: list[UUID]
    is_current: bool
    is_default: bool
    created_at: datetime

# Orchestration rules
class DelegationRules(BaseModel):
    strategy: Literal["capability_match", "round_robin", "priority"]
    config: dict = {}

class AggregationRules(BaseModel):
    strategy: Literal["merge", "vote", "first_wins"]
    config: dict = {}

class EscalationRules(BaseModel):
    timeout_seconds: int = 300
    failure_count: int = 3
    escalate_to: Literal["lead", "human"] = "lead"

class ConflictResolutionRules(BaseModel):
    strategy: Literal["majority_vote", "lead_decision", "human_arbitration"]

class RetryRules(BaseModel):
    max_retries: int = 2
    then: Literal["reassign", "fail"] = "reassign"

class FleetOrchestrationRulesCreate(BaseModel):
    delegation: DelegationRules
    aggregation: AggregationRules
    escalation: EscalationRules = EscalationRules()
    conflict_resolution: ConflictResolutionRules
    retry: RetryRules = RetryRules()
    max_parallelism: int = 1

class FleetOrchestrationRulesResponse(BaseModel):
    id: UUID
    fleet_id: UUID
    version: int
    delegation: dict
    aggregation: dict
    escalation: dict
    conflict_resolution: dict
    retry: dict
    max_parallelism: int
    is_current: bool
    created_at: datetime

# Health projection (from Redis, not DB)
class MemberHealthStatus(BaseModel):
    agent_fqn: str
    availability: FleetMemberAvailability
    role: FleetMemberRole

class FleetHealthProjectionResponse(BaseModel):
    fleet_id: UUID
    status: FleetStatus
    health_pct: float          # 0.0–1.0 (available members / total members)
    quorum_met: bool
    available_count: int
    total_count: int
    member_statuses: list[MemberHealthStatus]
    last_updated: datetime
```

### `fleet_learning/schemas.py` (key schemas)

```python
# Performance profile
class FleetPerformanceProfileQuery(BaseModel):
    start: datetime
    end: datetime

class FleetPerformanceProfileResponse(BaseModel):
    id: UUID
    fleet_id: UUID
    period_start: datetime
    period_end: datetime
    avg_completion_time_ms: float
    success_rate: float
    cost_per_task: float
    avg_quality_score: float
    throughput_per_hour: float
    member_metrics: dict
    flagged_member_fqns: list[str]
    created_at: datetime

# Adaptation rules
class AdaptationCondition(BaseModel):
    metric: Literal[
        "avg_completion_time_ms", "success_rate",
        "cost_per_task", "avg_quality_score", "throughput_per_hour"
    ]
    operator: Literal["gt", "lt", "gte", "lte", "eq"]
    threshold: float

class AdaptationAction(BaseModel):
    type: Literal[
        "set_max_parallelism", "set_delegation_strategy",
        "set_escalation_timeout", "set_aggregation_strategy"
    ]
    value: Any

class FleetAdaptationRuleCreate(BaseModel):
    name: str
    condition: AdaptationCondition
    action: AdaptationAction
    priority: int = 0

class FleetAdaptationRuleResponse(BaseModel):
    id: UUID
    fleet_id: UUID
    name: str
    condition: dict
    action: dict
    priority: int
    is_active: bool
    created_at: datetime

class FleetAdaptationLogResponse(BaseModel):
    id: UUID
    fleet_id: UUID
    adaptation_rule_id: UUID
    triggered_at: datetime
    before_rules_version: int
    after_rules_version: int
    performance_snapshot: dict
    is_reverted: bool
    reverted_at: datetime | None

# Cross-fleet transfer
class CrossFleetTransferCreate(BaseModel):
    target_fleet_id: UUID
    pattern_definition: dict  # inline pattern (≤50KB)

class TransferApproveRequest(BaseModel):
    pass  # approved_by extracted from JWT

class TransferRejectRequest(BaseModel):
    reason: str | None = None

class CrossFleetTransferResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    source_fleet_id: UUID
    target_fleet_id: UUID
    status: TransferRequestStatus
    pattern_definition: dict | None
    pattern_minio_key: str | None
    proposed_by: UUID
    approved_by: UUID | None
    rejected_reason: str | None
    applied_at: datetime | None
    reverted_at: datetime | None
    created_at: datetime

# Personality profile
class FleetPersonalityProfileCreate(BaseModel):
    communication_style: CommunicationStyle
    decision_speed: DecisionSpeed
    risk_tolerance: RiskTolerance
    autonomy_level: AutonomyLevel

class FleetPersonalityProfileResponse(BaseModel):
    id: UUID
    fleet_id: UUID
    communication_style: CommunicationStyle
    decision_speed: DecisionSpeed
    risk_tolerance: RiskTolerance
    autonomy_level: AutonomyLevel
    version: int
    is_current: bool
    created_at: datetime

# Orchestration modifier (internal — not exposed via REST)
class OrchestrationModifier(BaseModel):
    max_wait_ms: int | None = None      # fast=0, deliberate=5000, consensus_seeking=None
    require_quorum_for_decision: bool = False  # consensus_seeking=True
    auto_approve: bool = False          # fully_autonomous=True
    escalate_unverified: bool = False   # conservative risk_tolerance=True
```

---

## Service Interfaces

### `fleets/service.py`

```python
class FleetService:
    async def create_fleet(workspace_id: UUID, request: FleetCreate, current_user_id: UUID) -> FleetResponse
    async def get_fleet(fleet_id: UUID, workspace_id: UUID) -> FleetResponse
    async def list_fleets(workspace_id: UUID, pagination: PaginationParams) -> Page[FleetResponse]
    async def update_fleet(fleet_id: UUID, workspace_id: UUID, request: FleetUpdate) -> FleetResponse
    async def archive_fleet(fleet_id: UUID, workspace_id: UUID) -> FleetResponse
    async def add_member(fleet_id: UUID, workspace_id: UUID, request: FleetMemberCreate) -> FleetMemberResponse
    async def remove_member(fleet_id: UUID, member_id: UUID, workspace_id: UUID) -> None
    async def update_member_role(fleet_id: UUID, member_id: UUID, role: FleetMemberRole, workspace_id: UUID) -> FleetMemberResponse
    async def list_members(fleet_id: UUID, workspace_id: UUID) -> list[FleetMemberResponse]
    async def update_topology(fleet_id: UUID, workspace_id: UUID, request: FleetTopologyUpdateRequest) -> FleetTopologyVersionResponse
    async def get_topology_history(fleet_id: UUID, workspace_id: UUID) -> list[FleetTopologyVersionResponse]
    async def bind_policy(fleet_id: UUID, workspace_id: UUID, policy_id: UUID, user_id: UUID) -> FleetPolicyBindingResponse
    async def unbind_policy(fleet_id: UUID, binding_id: UUID, workspace_id: UUID) -> None
    async def assign_observer(fleet_id: UUID, workspace_id: UUID, observer_fqn: str) -> ObserverAssignmentResponse
    async def remove_observer(fleet_id: UUID, assignment_id: UUID, workspace_id: UUID) -> None
    async def get_orchestration_rules(fleet_id: UUID, workspace_id: UUID) -> FleetOrchestrationRulesResponse
    async def update_orchestration_rules(fleet_id: UUID, workspace_id: UUID, request: FleetOrchestrationRulesCreate) -> FleetOrchestrationRulesResponse
    async def get_rules_history(fleet_id: UUID, workspace_id: UUID) -> list[FleetOrchestrationRulesResponse]
    async def get_governance_chain(fleet_id: UUID, workspace_id: UUID) -> FleetGovernanceChainResponse
    async def update_governance_chain(fleet_id: UUID, workspace_id: UUID, request: FleetGovernanceChainUpdate) -> FleetGovernanceChainResponse

class FleetHealthProjectionService:
    async def get_health(fleet_id: UUID, workspace_id: UUID) -> FleetHealthProjectionResponse
    async def handle_member_availability_change(agent_fqn: str, is_available: bool, timestamp: datetime) -> None
    async def refresh_health(fleet_id: UUID) -> None  # recomputes from Redis member keys

class FleetOrchestrationModifierService:
    async def get_modifier(fleet_id: UUID) -> OrchestrationModifier  # reads personality from DB, returns modifier
```

### `fleet_learning/service.py`

```python
class FleetPerformanceProfileService:
    async def compute_profile(fleet_id: UUID, workspace_id: UUID, period_start: datetime, period_end: datetime) -> FleetPerformanceProfileResponse
    async def compute_all_profiles(period_start: datetime, period_end: datetime) -> None  # APScheduler job
    async def get_profile(fleet_id: UUID, workspace_id: UUID, query: FleetPerformanceProfileQuery) -> FleetPerformanceProfileResponse
    async def get_profile_history(fleet_id: UUID, workspace_id: UUID) -> list[FleetPerformanceProfileResponse]

class FleetAdaptationEngineService:
    async def create_rule(fleet_id: UUID, workspace_id: UUID, request: FleetAdaptationRuleCreate) -> FleetAdaptationRuleResponse
    async def list_rules(fleet_id: UUID, workspace_id: UUID) -> list[FleetAdaptationRuleResponse]
    async def update_rule(fleet_id: UUID, rule_id: UUID, workspace_id: UUID, request: FleetAdaptationRuleCreate) -> FleetAdaptationRuleResponse
    async def deactivate_rule(fleet_id: UUID, rule_id: UUID, workspace_id: UUID) -> None
    async def evaluate_rules_for_fleet(fleet_id: UUID) -> list[FleetAdaptationLogResponse]
    async def evaluate_all_fleets() -> None  # APScheduler job, runs after compute_all_profiles
    async def list_log(fleet_id: UUID, workspace_id: UUID) -> list[FleetAdaptationLogResponse]
    async def revert_adaptation(log_id: UUID, workspace_id: UUID) -> FleetAdaptationLogResponse

class CrossFleetTransferService:
    async def propose(source_fleet_id: UUID, workspace_id: UUID, request: CrossFleetTransferCreate, proposed_by: UUID) -> CrossFleetTransferResponse
    async def approve(transfer_id: UUID, workspace_id: UUID, approved_by: UUID) -> CrossFleetTransferResponse
    async def reject(transfer_id: UUID, workspace_id: UUID, rejected_by: UUID, request: TransferRejectRequest) -> CrossFleetTransferResponse
    async def apply(transfer_id: UUID, workspace_id: UUID) -> CrossFleetTransferResponse
    async def revert(transfer_id: UUID, workspace_id: UUID) -> CrossFleetTransferResponse
    async def list_for_fleet(fleet_id: UUID, workspace_id: UUID) -> list[CrossFleetTransferResponse]
    async def get(transfer_id: UUID, workspace_id: UUID) -> CrossFleetTransferResponse

class FleetPersonalityProfileService:
    async def get(fleet_id: UUID, workspace_id: UUID) -> FleetPersonalityProfileResponse
    async def update(fleet_id: UUID, workspace_id: UUID, request: FleetPersonalityProfileCreate) -> FleetPersonalityProfileResponse
    async def get_modifier(fleet_id: UUID) -> OrchestrationModifier  # called by FleetOrchestrationModifierService
```

---

## Redis Keys

| Key | Type | TTL | Purpose |
|-----|------|-----|---------|
| `fleet:health:{fleet_id}` | String (JSON) | 90s | Fleet health projection blob (health_pct, quorum_met, member_statuses) |
| `fleet:member:avail:{fleet_id}:{agent_fqn}` | String | 120s | Member availability ("1" = available, refreshed by heartbeat consumer) |

---

## Kafka Events

### Produced on `fleet.events` (key: `fleet_id`)

| Event Type | Payload Fields | Trigger |
|---|---|---|
| `fleet.created` | fleet_id, workspace_id, name, topology_type | FleetService.create_fleet |
| `fleet.archived` | fleet_id, workspace_id | FleetService.archive_fleet |
| `fleet.status.changed` | fleet_id, status, previous_status, reason | FleetHealthProjectionService (quorum breach / recovery) |
| `fleet.member.added` | fleet_id, agent_fqn, role | FleetService.add_member |
| `fleet.member.removed` | fleet_id, agent_fqn | FleetService.remove_member |
| `fleet.topology.changed` | fleet_id, version, topology_type | FleetService.update_topology |
| `fleet.orchestration_rules.updated` | fleet_id, version | FleetService.update_orchestration_rules |
| `fleet.governance_chain.updated` | fleet_id, version, is_default | FleetService.update_governance_chain |
| `fleet.adaptation.applied` | fleet_id, rule_id, before_version, after_version | FleetAdaptationEngineService.evaluate_rules_for_fleet |
| `fleet.transfer.status_changed` | transfer_id, source_fleet_id, target_fleet_id, status | CrossFleetTransferService (on each status transition) |

### Produced on `fleet.health` (key: `fleet_id`)

| Event Type | Payload Fields | Trigger |
|---|---|---|
| `fleet.health.updated` | fleet_id, workspace_id, health_pct, quorum_met, status, available_count, total_count, member_statuses | FleetHealthProjectionService.refresh_health |

### Consumed by fleet worker

| Topic | Filter | Handler |
|---|---|---|
| `runtime.lifecycle` | event_type: `runtime.heartbeat_missed` or `runtime.started` | `FleetHealthProjectionService.handle_member_availability_change` |
| `workflow.runtime` | all events | `ObserverRoutingService.route_execution_event` (filter by fleet membership, re-publish to `fleet.events` for observer agents) |

---

## Source File Structure

```text
apps/control-plane/src/platform/fleets/
├── __init__.py
├── models.py           # 7 SQLAlchemy models + 4 enums
├── schemas.py          # All Pydantic request/response schemas
├── repository.py       # Async SQLAlchemy queries for all fleets/ models
├── service.py          # FleetService + FleetOrchestrationModifierService
├── health.py           # FleetHealthProjectionService (Redis-backed)
├── governance.py       # FleetGovernanceChainService (chain CRUD, OJE delegation)
├── router.py           # FastAPI router — all fleets/ REST endpoints
├── events.py           # Fleet event types + publisher
├── exceptions.py       # FleetError, FleetNotFoundError, FleetStateError, QuorumNotMetError
└── dependencies.py     # get_fleet_service, get_health_service FastAPI dependencies

apps/control-plane/src/platform/fleet_learning/
├── __init__.py
├── models.py           # 5 SQLAlchemy models + 5 enums
├── schemas.py          # All Pydantic request/response schemas
├── repository.py       # Async SQLAlchemy queries for all fleet_learning/ models
├── performance.py      # FleetPerformanceProfileService (ClickHouse aggregation)
├── adaptation.py       # FleetAdaptationEngineService (rule eval, revert)
├── transfer.py         # CrossFleetTransferService (propose/approve/apply/revert)
├── personality.py      # FleetPersonalityProfileService (CRUD, versioning, modifier)
├── service.py          # FleetLearningService (orchestrates learning services)
├── router.py           # FastAPI router — all fleet_learning/ REST endpoints
├── events.py           # Fleet learning event types + publisher
├── exceptions.py       # FleetLearningError, AdaptationError, TransferError
└── dependencies.py     # get_fleet_learning_service FastAPI dependencies

apps/control-plane/migrations/versions/
└── 033_fleet_management.py  # All 12 tables in dependency order
```

---

## Migration Table Order (033_fleet_management.py)

```
1. fleets
2. fleet_members
3. fleet_topology_versions
4. fleet_policy_bindings
5. observer_assignments
6. fleet_governance_chains
7. fleet_orchestration_rules
8. fleet_performance_profiles
9. fleet_adaptation_rules
10. fleet_adaptation_log
11. cross_fleet_transfer_requests
12. fleet_personality_profiles
```
