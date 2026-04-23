from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from platform.common.config import PlatformSettings
from platform.fleet_learning.adaptation import FleetAdaptationEngineService
from platform.fleet_learning.models import (
    AutonomyLevel,
    CommunicationStyle,
    CrossFleetTransferRequest,
    DecisionSpeed,
    FleetAdaptationLog,
    FleetAdaptationRule,
    FleetPerformanceProfile,
    FleetPersonalityProfile,
    RiskTolerance,
    TransferRequestStatus,
)
from platform.fleet_learning.performance import FleetPerformanceProfileService
from platform.fleet_learning.personality import FleetPersonalityProfileService
from platform.fleet_learning.schemas import (
    AdaptationAction,
    AdaptationCondition,
    CrossFleetTransferCreate,
    FleetAdaptationRuleCreate,
    FleetPersonalityProfileCreate,
)
from platform.fleet_learning.service import FleetLearningService
from platform.fleet_learning.transfer import CrossFleetTransferService
from platform.fleets.health import FleetHealthProjectionService
from platform.fleets.models import (
    Fleet,
    FleetGovernanceChain,
    FleetMember,
    FleetMemberAvailability,
    FleetMemberRole,
    FleetOrchestrationRules,
    FleetPolicyBinding,
    FleetStatus,
    FleetTopologyType,
    FleetTopologyVersion,
    ObserverAssignment,
)
from platform.fleets.schemas import (
    AggregationRules,
    ConflictResolutionRules,
    DelegationRules,
    EscalationRules,
    FleetCreate,
    FleetOrchestrationRulesCreate,
    RetryRules,
)
from platform.fleets.service import FleetOrchestrationModifierService, FleetService
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from tests.auth_support import FakeAsyncRedisClient, RecordingProducer


def fleet_settings() -> PlatformSettings:
    return PlatformSettings()


def _stamp(entity: Any) -> Any:
    now = datetime.now(UTC)
    if getattr(entity, "id", None) is None:
        entity.id = uuid4()
    if hasattr(entity, "created_at") and getattr(entity, "created_at", None) is None:
        entity.created_at = now
    if hasattr(entity, "updated_at") and getattr(entity, "updated_at", None) is None:
        entity.updated_at = now
    if hasattr(entity, "joined_at") and getattr(entity, "joined_at", None) is None:
        entity.joined_at = now
    if hasattr(entity, "triggered_at") and getattr(entity, "triggered_at", None) is None:
        entity.triggered_at = now
    if hasattr(entity, "deleted_at") and getattr(entity, "deleted_at", None) is None:
        entity.deleted_at = None
    return entity


def build_fleet(
    *,
    workspace_id: UUID | None = None,
    name: str = "Core Fleet",
    status: FleetStatus = FleetStatus.active,
    topology_type: FleetTopologyType = FleetTopologyType.hierarchical,
    quorum_min: int = 1,
) -> Fleet:
    return _stamp(
        Fleet(
            workspace_id=workspace_id or uuid4(),
            name=name,
            status=status,
            topology_type=topology_type,
            quorum_min=quorum_min,
        )
    )


def build_member(
    *,
    fleet_id: UUID,
    workspace_id: UUID,
    agent_fqn: str = "agent:worker",
    role: FleetMemberRole = FleetMemberRole.worker,
    availability: FleetMemberAvailability = FleetMemberAvailability.available,
) -> FleetMember:
    return _stamp(
        FleetMember(
            fleet_id=fleet_id,
            workspace_id=workspace_id,
            agent_fqn=agent_fqn,
            role=role,
            availability=availability,
        )
    )


def build_topology_version(
    *,
    fleet_id: UUID,
    topology_type: FleetTopologyType = FleetTopologyType.hierarchical,
    version: int = 1,
    config: dict[str, Any] | None = None,
    is_current: bool = True,
) -> FleetTopologyVersion:
    return _stamp(
        FleetTopologyVersion(
            fleet_id=fleet_id,
            topology_type=topology_type,
            version=version,
            config=config or {},
            is_current=is_current,
        )
    )


def build_policy_binding(
    *,
    fleet_id: UUID,
    workspace_id: UUID,
    policy_id: UUID | None = None,
    bound_by: UUID | None = None,
) -> FleetPolicyBinding:
    return _stamp(
        FleetPolicyBinding(
            fleet_id=fleet_id,
            workspace_id=workspace_id,
            policy_id=policy_id or uuid4(),
            bound_by=bound_by or uuid4(),
        )
    )


def build_observer_assignment(
    *,
    fleet_id: UUID,
    workspace_id: UUID,
    observer_fqn: str = "observer:default",
    is_active: bool = True,
) -> ObserverAssignment:
    return _stamp(
        ObserverAssignment(
            fleet_id=fleet_id,
            workspace_id=workspace_id,
            observer_fqn=observer_fqn,
            is_active=is_active,
        )
    )


def build_governance_chain(
    *,
    fleet_id: UUID,
    workspace_id: UUID,
    version: int = 1,
    is_current: bool = True,
    is_default: bool = False,
) -> FleetGovernanceChain:
    return _stamp(
        FleetGovernanceChain(
            fleet_id=fleet_id,
            workspace_id=workspace_id,
            version=version,
            observer_fqns=["observer:default"],
            judge_fqns=["judge:default"],
            enforcer_fqns=["enforcer:default"],
            policy_binding_ids=[],
            verdict_to_action_mapping={},
            is_current=is_current,
            is_default=is_default,
        )
    )


def build_orchestration_rules(
    *,
    fleet_id: UUID,
    workspace_id: UUID,
    version: int = 1,
    is_current: bool = True,
    delegation: dict[str, Any] | None = None,
) -> FleetOrchestrationRules:
    return _stamp(
        FleetOrchestrationRules(
            fleet_id=fleet_id,
            workspace_id=workspace_id,
            version=version,
            delegation=delegation or {"strategy": "round_robin", "config": {}},
            aggregation={"strategy": "first_wins", "config": {}},
            escalation={
                "timeout_seconds": 300,
                "failure_count": 3,
                "escalate_to": "lead",
            },
            conflict_resolution={"strategy": "majority_vote"},
            retry={"max_retries": 2, "then": "reassign"},
            max_parallelism=1,
            is_current=is_current,
        )
    )


def build_profile(
    *,
    fleet_id: UUID,
    workspace_id: UUID,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    avg_completion_time_ms: float = 1200.0,
    success_rate: float = 0.95,
    cost_per_task: float = 0.5,
    avg_quality_score: float = 0.9,
    throughput_per_hour: float = 12.0,
    member_metrics: dict[str, Any] | None = None,
    flagged_member_fqns: list[str] | None = None,
) -> FleetPerformanceProfile:
    end = period_end or datetime.now(UTC)
    start = period_start or (end - timedelta(days=1))
    return _stamp(
        FleetPerformanceProfile(
            fleet_id=fleet_id,
            workspace_id=workspace_id,
            period_start=start,
            period_end=end,
            avg_completion_time_ms=avg_completion_time_ms,
            success_rate=success_rate,
            cost_per_task=cost_per_task,
            avg_quality_score=avg_quality_score,
            throughput_per_hour=throughput_per_hour,
            member_metrics=member_metrics or {},
            flagged_member_fqns=flagged_member_fqns or [],
        )
    )


def build_adaptation_rule(
    *,
    fleet_id: UUID,
    workspace_id: UUID,
    name: str = "Scale Up",
    condition: dict[str, Any] | None = None,
    action: dict[str, Any] | None = None,
    priority: int = 10,
    is_active: bool = True,
) -> FleetAdaptationRule:
    return _stamp(
        FleetAdaptationRule(
            fleet_id=fleet_id,
            workspace_id=workspace_id,
            name=name,
            condition=condition
            or {"metric": "avg_completion_time_ms", "operator": "gt", "threshold": 30.0},
            action=action or {"type": "set_max_parallelism", "value": 3},
            priority=priority,
            is_active=is_active,
        )
    )


def build_adaptation_log(
    *,
    fleet_id: UUID,
    workspace_id: UUID,
    adaptation_rule_id: UUID | None = None,
    before_rules_version: int = 1,
    after_rules_version: int = 2,
    is_reverted: bool = False,
) -> FleetAdaptationLog:
    return _stamp(
        FleetAdaptationLog(
            fleet_id=fleet_id,
            workspace_id=workspace_id,
            adaptation_rule_id=adaptation_rule_id or uuid4(),
            before_rules_version=before_rules_version,
            after_rules_version=after_rules_version,
            performance_snapshot={"avg_completion_time_ms": 42.0},
            is_reverted=is_reverted,
        )
    )


def build_transfer_request(
    *,
    workspace_id: UUID,
    source_fleet_id: UUID,
    target_fleet_id: UUID,
    status: TransferRequestStatus = TransferRequestStatus.proposed,
    pattern_definition: dict[str, Any] | None = None,
    pattern_minio_key: str | None = None,
) -> CrossFleetTransferRequest:
    return _stamp(
        CrossFleetTransferRequest(
            workspace_id=workspace_id,
            source_fleet_id=source_fleet_id,
            target_fleet_id=target_fleet_id,
            status=status,
            pattern_definition=pattern_definition
            or {"rules_snapshot": {"delegation": {"strategy": "round_robin", "config": {}}}},
            pattern_minio_key=pattern_minio_key,
            proposed_by=uuid4(),
        )
    )


def build_personality_profile(
    *,
    fleet_id: UUID,
    workspace_id: UUID,
    version: int = 1,
    is_current: bool = True,
    communication_style: CommunicationStyle = CommunicationStyle.concise,
    decision_speed: DecisionSpeed = DecisionSpeed.deliberate,
    risk_tolerance: RiskTolerance = RiskTolerance.moderate,
    autonomy_level: AutonomyLevel = AutonomyLevel.semi_autonomous,
) -> FleetPersonalityProfile:
    return _stamp(
        FleetPersonalityProfile(
            fleet_id=fleet_id,
            workspace_id=workspace_id,
            communication_style=communication_style,
            decision_speed=decision_speed,
            risk_tolerance=risk_tolerance,
            autonomy_level=autonomy_level,
            version=version,
            is_current=is_current,
        )
    )


def build_fleet_create(
    *,
    name: str = " Fleet Alpha ",
    topology_type: FleetTopologyType = FleetTopologyType.hierarchical,
    quorum_min: int = 2,
    lead_fqn: str = "agent:lead",
    member_fqns: list[str] | None = None,
) -> FleetCreate:
    return FleetCreate(
        name=name,
        topology_type=topology_type,
        quorum_min=quorum_min,
        topology_config={"lead_fqn": lead_fqn} if lead_fqn else {},
        member_fqns=member_fqns or ["agent:worker-1", "agent:worker-2"],
    )


def build_rules_create(
    *,
    max_parallelism: int = 1,
    strategy: str = "round_robin",
) -> FleetOrchestrationRulesCreate:
    return FleetOrchestrationRulesCreate(
        delegation=DelegationRules(strategy=strategy, config={}),
        aggregation=AggregationRules(strategy="first_wins", config={}),
        escalation=EscalationRules(timeout_seconds=300, failure_count=3, escalate_to="lead"),
        conflict_resolution=ConflictResolutionRules(strategy="majority_vote"),
        retry=RetryRules(max_retries=2, then="reassign"),
        max_parallelism=max_parallelism,
    )


def build_adaptation_rule_create(
    *,
    threshold: float = 30.0,
    action_type: str = "set_max_parallelism",
    action_value: Any = 3,
) -> FleetAdaptationRuleCreate:
    return FleetAdaptationRuleCreate(
        name="Scale Up",
        condition=AdaptationCondition(
            metric="avg_completion_time_ms",
            operator="gt",
            threshold=threshold,
        ),
        action=AdaptationAction(type=action_type, value=action_value),
        priority=10,
    )


def build_transfer_create(target_fleet_id: UUID) -> CrossFleetTransferCreate:
    return CrossFleetTransferCreate(
        target_fleet_id=target_fleet_id,
        pattern_definition={
            "description": "Share pattern",
            "rules_snapshot": build_rules_create(max_parallelism=2).model_dump(mode="json"),
            "orchestration_rules_version": 1,
        },
    )


def build_personality_create(
    *,
    communication_style: CommunicationStyle = CommunicationStyle.concise,
    decision_speed: DecisionSpeed = DecisionSpeed.deliberate,
    risk_tolerance: RiskTolerance = RiskTolerance.moderate,
    autonomy_level: AutonomyLevel = AutonomyLevel.semi_autonomous,
) -> FleetPersonalityProfileCreate:
    return FleetPersonalityProfileCreate(
        communication_style=communication_style,
        decision_speed=decision_speed,
        risk_tolerance=risk_tolerance,
        autonomy_level=autonomy_level,
    )


class FleetRepositoryStub:
    def __init__(self) -> None:
        self.fleets: dict[UUID, Fleet] = {}

    async def create(self, fleet: Fleet) -> Fleet:
        self.fleets[fleet.id] = _stamp(fleet)
        return fleet

    async def get_by_id(self, fleet_id: UUID, workspace_id: UUID | None = None) -> Fleet | None:
        fleet = self.fleets.get(fleet_id)
        if fleet is None or fleet.deleted_at is not None:
            return None
        if workspace_id is not None and fleet.workspace_id != workspace_id:
            return None
        return fleet

    async def get_by_name_and_workspace(
        self,
        workspace_id: UUID,
        name: str,
        *,
        exclude_fleet_id: UUID | None = None,
    ) -> Fleet | None:
        for fleet in self.fleets.values():
            if (
                fleet.workspace_id == workspace_id
                and fleet.name == name
                and fleet.deleted_at is None
                and fleet.id != exclude_fleet_id
            ):
                return fleet
        return None

    async def list_by_workspace(
        self,
        workspace_id: UUID,
        *,
        status: FleetStatus | None = None,
        page: int,
        page_size: int,
    ) -> tuple[list[Fleet], int]:
        items = [
            fleet
            for fleet in self.fleets.values()
            if fleet.workspace_id == workspace_id
            and fleet.deleted_at is None
            and (status is None or fleet.status == status)
        ]
        items.sort(key=lambda fleet: (fleet.created_at, fleet.id), reverse=True)
        total = len(items)
        start = (page - 1) * page_size
        end = start + page_size
        return items[start:end], total

    async def list_active(self) -> list[Fleet]:
        return [
            fleet
            for fleet in self.fleets.values()
            if fleet.deleted_at is None
            and fleet.status in {FleetStatus.active, FleetStatus.degraded}
        ]

    async def list_with_active_rules(self) -> list[Fleet]:
        return await self.list_active()

    async def soft_delete(self, fleet: Fleet) -> Fleet:
        fleet.deleted_at = datetime.now(UTC)
        return fleet

    async def update(self, fleet: Fleet, **fields: Any) -> Fleet:
        for key, value in fields.items():
            setattr(fleet, key, value)
        fleet.updated_at = datetime.now(UTC)
        return fleet


class FleetMemberRepositoryStub:
    def __init__(self) -> None:
        self.members: dict[UUID, FleetMember] = {}

    async def get_by_fleet(self, fleet_id: UUID) -> list[FleetMember]:
        items = [member for member in self.members.values() if member.fleet_id == fleet_id]
        items.sort(key=lambda member: (member.joined_at, member.id))
        return items

    async def get_by_id(self, member_id: UUID, fleet_id: UUID | None = None) -> FleetMember | None:
        member = self.members.get(member_id)
        if member is None:
            return None
        if fleet_id is not None and member.fleet_id != fleet_id:
            return None
        return member

    async def get_by_fleet_and_fqn(self, fleet_id: UUID, agent_fqn: str) -> FleetMember | None:
        return next(
            (
                member
                for member in self.members.values()
                if member.fleet_id == fleet_id and member.agent_fqn == agent_fqn
            ),
            None,
        )

    async def get_lead(self, fleet_id: UUID) -> FleetMember | None:
        return next(
            (
                member
                for member in self.members.values()
                if member.fleet_id == fleet_id and member.role == FleetMemberRole.lead
            ),
            None,
        )

    async def add(self, member: FleetMember) -> FleetMember:
        self.members[member.id] = _stamp(member)
        return member

    async def remove(self, member: FleetMember) -> None:
        self.members.pop(member.id, None)

    async def update_role(self, member: FleetMember, role: Any) -> FleetMember:
        member.role = role
        return member

    async def get_by_agent_fqn_across_fleets(self, agent_fqn: str) -> list[FleetMember]:
        return [member for member in self.members.values() if member.agent_fqn == agent_fqn]


class FleetTopologyVersionRepositoryStub:
    def __init__(self) -> None:
        self.versions: dict[UUID, list[FleetTopologyVersion]] = {}

    async def get_current(self, fleet_id: UUID) -> FleetTopologyVersion | None:
        return next(
            (version for version in self.versions.get(fleet_id, []) if version.is_current),
            None,
        )

    async def create_version(self, version: FleetTopologyVersion) -> FleetTopologyVersion:
        current = await self.get_current(version.fleet_id)
        if current is not None:
            current.is_current = False
        self.versions.setdefault(version.fleet_id, []).append(_stamp(version))
        return version

    async def list_history(self, fleet_id: UUID) -> list[FleetTopologyVersion]:
        items = list(self.versions.get(fleet_id, []))
        items.sort(key=lambda item: (item.version, item.created_at), reverse=True)
        return items


class FleetPolicyBindingRepositoryStub:
    def __init__(self) -> None:
        self.bindings: dict[UUID, FleetPolicyBinding] = {}

    async def get_by_id(
        self, binding_id: UUID, fleet_id: UUID | None = None
    ) -> FleetPolicyBinding | None:
        binding = self.bindings.get(binding_id)
        if binding is None:
            return None
        if fleet_id is not None and binding.fleet_id != fleet_id:
            return None
        return binding

    async def get_by_policy(self, fleet_id: UUID, policy_id: UUID) -> FleetPolicyBinding | None:
        return next(
            (
                binding
                for binding in self.bindings.values()
                if binding.fleet_id == fleet_id and binding.policy_id == policy_id
            ),
            None,
        )

    async def bind(self, binding: FleetPolicyBinding) -> FleetPolicyBinding:
        self.bindings[binding.id] = _stamp(binding)
        return binding

    async def unbind(self, binding: FleetPolicyBinding) -> None:
        self.bindings.pop(binding.id, None)

    async def list_by_fleet(self, fleet_id: UUID) -> list[FleetPolicyBinding]:
        return [binding for binding in self.bindings.values() if binding.fleet_id == fleet_id]


class ObserverAssignmentRepositoryStub:
    def __init__(self) -> None:
        self.assignments: dict[UUID, ObserverAssignment] = {}

    async def get_by_id(
        self,
        assignment_id: UUID,
        fleet_id: UUID | None = None,
    ) -> ObserverAssignment | None:
        assignment = self.assignments.get(assignment_id)
        if assignment is None:
            return None
        if fleet_id is not None and assignment.fleet_id != fleet_id:
            return None
        return assignment

    async def get_active_by_fleet_and_fqn(
        self,
        fleet_id: UUID,
        observer_fqn: str,
    ) -> ObserverAssignment | None:
        return next(
            (
                assignment
                for assignment in self.assignments.values()
                if assignment.fleet_id == fleet_id
                and assignment.observer_fqn == observer_fqn
                and assignment.is_active
            ),
            None,
        )

    async def assign(self, assignment: ObserverAssignment) -> ObserverAssignment:
        self.assignments[assignment.id] = _stamp(assignment)
        return assignment

    async def deactivate(self, assignment: ObserverAssignment) -> ObserverAssignment:
        assignment.is_active = False
        return assignment

    async def list_active_by_fleet(self, fleet_id: UUID) -> list[ObserverAssignment]:
        return [
            assignment
            for assignment in self.assignments.values()
            if assignment.fleet_id == fleet_id and assignment.is_active
        ]


class FleetGovernanceChainRepositoryStub:
    def __init__(self) -> None:
        self.chains: dict[UUID, list[FleetGovernanceChain]] = {}

    async def get_current(self, fleet_id: UUID) -> FleetGovernanceChain | None:
        return next(
            (chain for chain in self.chains.get(fleet_id, []) if chain.is_current),
            None,
        )

    async def create_version(self, chain: FleetGovernanceChain) -> FleetGovernanceChain:
        current = await self.get_current(chain.fleet_id)
        if current is not None:
            current.is_current = False
        self.chains.setdefault(chain.fleet_id, []).append(_stamp(chain))
        return chain

    async def list_history(self, fleet_id: UUID) -> list[FleetGovernanceChain]:
        items = list(self.chains.get(fleet_id, []))
        items.sort(key=lambda item: (item.version, item.created_at), reverse=True)
        return items


class FleetOrchestrationRulesRepositoryStub:
    def __init__(self) -> None:
        self.rules: dict[UUID, list[FleetOrchestrationRules]] = {}

    async def get_current(self, fleet_id: UUID) -> FleetOrchestrationRules | None:
        return next(
            (rule for rule in self.rules.get(fleet_id, []) if rule.is_current),
            None,
        )

    async def create_version(self, rules: FleetOrchestrationRules) -> FleetOrchestrationRules:
        current = await self.get_current(rules.fleet_id)
        if current is not None:
            current.is_current = False
        self.rules.setdefault(rules.fleet_id, []).append(_stamp(rules))
        return rules

    async def list_history(self, fleet_id: UUID) -> list[FleetOrchestrationRules]:
        items = list(self.rules.get(fleet_id, []))
        items.sort(key=lambda item: (item.version, item.created_at), reverse=True)
        return items

    async def get_by_version(self, fleet_id: UUID, version: int) -> FleetOrchestrationRules | None:
        return next(
            (item for item in self.rules.get(fleet_id, []) if item.version == version),
            None,
        )

    async def set_current_version(
        self, fleet_id: UUID, version: int
    ) -> FleetOrchestrationRules | None:
        target = await self.get_by_version(fleet_id, version)
        if target is None:
            return None
        for item in self.rules.get(fleet_id, []):
            item.is_current = item.id == target.id
        return target


class FleetPerformanceProfileRepositoryStub:
    def __init__(self) -> None:
        self.profiles: dict[UUID, list[FleetPerformanceProfile]] = {}

    async def insert(self, profile: FleetPerformanceProfile) -> FleetPerformanceProfile:
        self.profiles.setdefault(profile.fleet_id, []).append(_stamp(profile))
        return profile

    async def get_latest(self, fleet_id: UUID) -> FleetPerformanceProfile | None:
        items = self.profiles.get(fleet_id, [])
        return max(items, key=lambda item: (item.period_end, item.created_at), default=None)

    async def get_by_range(
        self,
        fleet_id: UUID,
        *,
        start: datetime,
        end: datetime,
    ) -> FleetPerformanceProfile | None:
        items = [
            item
            for item in self.profiles.get(fleet_id, [])
            if item.period_start <= end and item.period_end >= start
        ]
        return max(items, key=lambda item: (item.period_end, item.created_at), default=None)

    async def list_by_range(
        self,
        fleet_id: UUID,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[FleetPerformanceProfile]:
        items = list(self.profiles.get(fleet_id, []))
        if start is not None:
            items = [item for item in items if item.period_end >= start]
        if end is not None:
            items = [item for item in items if item.period_start <= end]
        items.sort(key=lambda item: (item.period_end, item.created_at), reverse=True)
        return items


class FleetAdaptationRuleRepositoryStub:
    def __init__(self) -> None:
        self.rules: dict[UUID, FleetAdaptationRule] = {}

    async def create(self, rule: FleetAdaptationRule) -> FleetAdaptationRule:
        self.rules[rule.id] = _stamp(rule)
        return rule

    async def get_by_id(
        self, rule_id: UUID, fleet_id: UUID | None = None
    ) -> FleetAdaptationRule | None:
        rule = self.rules.get(rule_id)
        if rule is None:
            return None
        if fleet_id is not None and rule.fleet_id != fleet_id:
            return None
        return rule

    async def list_active_by_priority(self, fleet_id: UUID) -> list[FleetAdaptationRule]:
        items = [
            rule for rule in self.rules.values() if rule.fleet_id == fleet_id and rule.is_active
        ]
        items.sort(key=lambda item: (-item.priority, item.created_at))
        return items

    async def list_by_fleet(self, fleet_id: UUID) -> list[FleetAdaptationRule]:
        items = [rule for rule in self.rules.values() if rule.fleet_id == fleet_id]
        items.sort(key=lambda item: (-item.priority, item.created_at))
        return items

    async def update(self, rule: FleetAdaptationRule) -> FleetAdaptationRule:
        return rule

    async def deactivate(self, rule: FleetAdaptationRule) -> FleetAdaptationRule:
        rule.is_active = False
        return rule

    async def list_fleet_ids_with_active_rules(self) -> list[UUID]:
        return list({rule.fleet_id for rule in self.rules.values() if rule.is_active})


class FleetAdaptationLogRepositoryStub:
    def __init__(self) -> None:
        self.logs: dict[UUID, FleetAdaptationLog] = {}

    async def create(self, log: FleetAdaptationLog) -> FleetAdaptationLog:
        self.logs[log.id] = _stamp(log)
        return log

    async def list_by_fleet(
        self,
        fleet_id: UUID,
        *,
        is_reverted: bool | None = None,
    ) -> list[FleetAdaptationLog]:
        items = [log for log in self.logs.values() if log.fleet_id == fleet_id]
        if is_reverted is not None:
            items = [log for log in items if log.is_reverted is is_reverted]
        items.sort(key=lambda item: (item.triggered_at, item.created_at), reverse=True)
        return items

    async def get_by_id(self, log_id: UUID) -> FleetAdaptationLog | None:
        return self.logs.get(log_id)

    async def mark_reverted(self, log: FleetAdaptationLog) -> FleetAdaptationLog:
        log.is_reverted = True
        log.reverted_at = datetime.now(UTC)
        return log


class CrossFleetTransferRepositoryStub:
    def __init__(self) -> None:
        self.transfers: dict[UUID, CrossFleetTransferRequest] = {}

    async def create(self, request: CrossFleetTransferRequest) -> CrossFleetTransferRequest:
        self.transfers[request.id] = _stamp(request)
        return request

    async def get_by_id(self, transfer_id: UUID) -> CrossFleetTransferRequest | None:
        return self.transfers.get(transfer_id)

    async def update_status(self, request: CrossFleetTransferRequest) -> CrossFleetTransferRequest:
        self.transfers[request.id] = request
        return request

    async def list_for_fleet(
        self,
        fleet_id: UUID,
        *,
        role: str | None = None,
        status: TransferRequestStatus | None = None,
    ) -> list[CrossFleetTransferRequest]:
        items = list(self.transfers.values())
        if role == "source":
            items = [item for item in items if item.source_fleet_id == fleet_id]
        elif role == "target":
            items = [item for item in items if item.target_fleet_id == fleet_id]
        else:
            items = [
                item
                for item in items
                if item.source_fleet_id == fleet_id or item.target_fleet_id == fleet_id
            ]
        if status is not None:
            items = [item for item in items if item.status == status]
        items.sort(key=lambda item: item.created_at, reverse=True)
        return items


class FleetPersonalityProfileRepositoryStub:
    def __init__(self) -> None:
        self.profiles: dict[UUID, list[FleetPersonalityProfile]] = {}

    async def get_current(self, fleet_id: UUID) -> FleetPersonalityProfile | None:
        return next(
            (profile for profile in self.profiles.get(fleet_id, []) if profile.is_current),
            None,
        )

    async def create_version(self, profile: FleetPersonalityProfile) -> FleetPersonalityProfile:
        current = await self.get_current(profile.fleet_id)
        if current is not None:
            current.is_current = False
        self.profiles.setdefault(profile.fleet_id, []).append(_stamp(profile))
        return profile

    async def list_history(self, fleet_id: UUID) -> list[FleetPersonalityProfile]:
        items = list(self.profiles.get(fleet_id, []))
        items.sort(key=lambda item: (item.version, item.created_at), reverse=True)
        return items


@dataclass
class ClickHouseStub:
    query_responses: list[list[dict[str, Any]]] = field(default_factory=list)
    query_calls: list[tuple[str, dict[str, Any] | None]] = field(default_factory=list)

    async def execute_query(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.query_calls.append((sql, params))
        return self.query_responses.pop(0) if self.query_responses else []


@dataclass
class ObjectStorageStub:
    buckets: set[str] = field(default_factory=set)
    objects: dict[tuple[str, str], bytes] = field(default_factory=dict)

    async def create_bucket_if_not_exists(self, bucket: str) -> None:
        self.buckets.add(bucket)

    async def put_object(
        self,
        bucket: str,
        key: str,
        data: bytes,
        *,
        content_type: str | None = None,
    ) -> None:
        del content_type
        self.objects[(bucket, key)] = data

    async def get_object(self, bucket: str, key: str) -> bytes:
        return self.objects[(bucket, key)]


@dataclass
class RegistryServiceStub:
    known_fqns: set[str] = field(default_factory=set)

    async def get_agent_by_fqn(self, agent_fqn: str, workspace_id: UUID) -> object | None:
        del workspace_id
        return SimpleNamespace(agent_fqn=agent_fqn) if agent_fqn in self.known_fqns else None


@dataclass
class RuntimeControllerStub:
    failures: list[dict[str, str]] = field(default_factory=list)

    async def record_member_failure(self, *, fleet_id: str, agent_fqn: str) -> None:
        self.failures.append({"fleet_id": fleet_id, "agent_fqn": agent_fqn})


@dataclass
class OJEPipelineServiceStub:
    calls: list[tuple[UUID, object, dict[str, object]]] = field(default_factory=list)

    async def process_fleet_anomaly_signal(
        self,
        fleet_id: UUID,
        chain: object,
        signal: dict[str, object],
    ) -> dict[str, object]:
        self.calls.append((fleet_id, chain, signal))
        return {"status": "processed", "fleet_id": str(fleet_id)}


@dataclass
class RawForwardProducerStub:
    messages: list[dict[str, Any]] = field(default_factory=list)

    async def send_and_wait(self, topic: str, value: bytes, *, key: bytes) -> None:
        self.messages.append({"topic": topic, "value": value, "key": key})


class ForwardingProducerStub(RecordingProducer):
    def __init__(self) -> None:
        super().__init__()
        self.raw = RawForwardProducerStub()

    async def _ensure_producer(self) -> RawForwardProducerStub:
        return self.raw


class QueryResultStub:
    def __init__(self, *, one: Any = None, many: list[Any] | None = None) -> None:
        self._one = one
        self._many = many or []

    def scalar_one_or_none(self) -> Any:
        return self._one

    def scalars(self) -> SimpleNamespace:
        return SimpleNamespace(all=lambda: list(self._many))


class SessionStub:
    def __init__(
        self,
        *,
        execute_results: list[QueryResultStub] | None = None,
        scalar_results: list[Any] | None = None,
    ) -> None:
        self.execute_results = list(execute_results or [])
        self.scalar_results = list(scalar_results or [])
        self.executed: list[Any] = []
        self.scalar_calls: list[Any] = []
        self.added: list[Any] = []
        self.deleted: list[Any] = []
        self.flush_count = 0

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def execute(self, statement: Any) -> QueryResultStub:
        self.executed.append(statement)
        return self.execute_results.pop(0)

    async def scalar(self, statement: Any) -> Any:
        self.scalar_calls.append(statement)
        return self.scalar_results.pop(0)

    async def flush(self) -> None:
        self.flush_count += 1

    async def delete(self, value: Any) -> None:
        self.deleted.append(value)


def build_fleet_service_stack(
    *,
    known_fqns: set[str] | None = None,
    producer: RecordingProducer | None = None,
    redis_client: FakeAsyncRedisClient | None = None,
    runtime_controller: RuntimeControllerStub | None = None,
) -> tuple[FleetService, SimpleNamespace]:
    fleet_repo = FleetRepositoryStub()
    member_repo = FleetMemberRepositoryStub()
    topology_repo = FleetTopologyVersionRepositoryStub()
    policy_repo = FleetPolicyBindingRepositoryStub()
    observer_repo = ObserverAssignmentRepositoryStub()
    governance_repo = FleetGovernanceChainRepositoryStub()
    rules_repo = FleetOrchestrationRulesRepositoryStub()
    registry_service = RegistryServiceStub(known_fqns=set(known_fqns or set()))
    event_producer = producer or RecordingProducer()
    health_service = FleetHealthProjectionService(
        fleet_repo=fleet_repo,
        member_repo=member_repo,
        redis_client=redis_client or FakeAsyncRedisClient(),
        producer=event_producer,
    )
    service = FleetService(
        fleet_repo=fleet_repo,
        member_repo=member_repo,
        topology_repo=topology_repo,
        policy_repo=policy_repo,
        observer_repo=observer_repo,
        governance_repo=governance_repo,
        rules_repo=rules_repo,
        settings=fleet_settings(),
        producer=event_producer,
        registry_service=registry_service,
        modifier_service=FleetOrchestrationModifierService(),
        health_service=health_service,
        runtime_controller=runtime_controller,
    )
    return service, SimpleNamespace(
        fleet_repo=fleet_repo,
        member_repo=member_repo,
        topology_repo=topology_repo,
        policy_repo=policy_repo,
        observer_repo=observer_repo,
        governance_repo=governance_repo,
        rules_repo=rules_repo,
        registry_service=registry_service,
        producer=event_producer,
        health_service=health_service,
    )


def build_fleet_learning_stack(
    *,
    fleet_service: FleetService,
    producer: RecordingProducer | None = None,
    clickhouse: ClickHouseStub | None = None,
    object_storage: ObjectStorageStub | None = None,
) -> tuple[FleetLearningService, SimpleNamespace]:
    performance_repo = FleetPerformanceProfileRepositoryStub()
    rule_repo = FleetAdaptationRuleRepositoryStub()
    log_repo = FleetAdaptationLogRepositoryStub()
    transfer_repo = CrossFleetTransferRepositoryStub()
    personality_repo = FleetPersonalityProfileRepositoryStub()
    rules_repo = FleetOrchestrationRulesRepositoryStub()
    topology_repo = FleetTopologyVersionRepositoryStub()
    event_producer = producer or RecordingProducer()
    clickhouse_client = clickhouse or ClickHouseStub()
    object_storage_client = object_storage or ObjectStorageStub()

    performance = FleetPerformanceProfileService(
        repository=performance_repo,
        clickhouse=clickhouse_client,
        fleet_service=fleet_service,
    )
    adaptation = FleetAdaptationEngineService(
        rule_repo=rule_repo,
        log_repo=log_repo,
        profile_repo=performance_repo,
        rules_repo=rules_repo,
        fleet_service=fleet_service,
        producer=event_producer,
    )
    transfer = CrossFleetTransferService(
        repository=transfer_repo,
        rules_repo=rules_repo,
        topology_repo=topology_repo,
        object_storage=object_storage_client,
        fleet_service=fleet_service,
        producer=event_producer,
    )
    personality = FleetPersonalityProfileService(repository=personality_repo)
    service = FleetLearningService(
        performance_service=performance,
        adaptation_service=adaptation,
        transfer_service=transfer,
        personality_service=personality,
    )
    return service, SimpleNamespace(
        performance_repo=performance_repo,
        rule_repo=rule_repo,
        log_repo=log_repo,
        transfer_repo=transfer_repo,
        personality_repo=personality_repo,
        rules_repo=rules_repo,
        topology_repo=topology_repo,
        producer=event_producer,
        clickhouse=clickhouse_client,
        object_storage=object_storage_client,
        performance=performance,
        adaptation=adaptation,
        transfer=transfer,
        personality=personality,
    )
