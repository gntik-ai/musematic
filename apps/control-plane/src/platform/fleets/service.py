from __future__ import annotations

from platform.common.events.envelope import CorrelationContext, EventEnvelope
from platform.fleets.events import (
    FleetArchivedPayload,
    FleetCreatedPayload,
    FleetEventType,
    FleetMemberPayload,
    FleetRulesUpdatedPayload,
    FleetTopologyChangedPayload,
    publish_fleet_event,
)
from platform.fleets.exceptions import (
    FleetNameConflictError,
    FleetNotFoundError,
    FleetStateError,
    QuorumNotMetError,
)
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
from platform.fleets.repository import (
    FleetGovernanceChainRepository,
    FleetMemberRepository,
    FleetOrchestrationRulesRepository,
    FleetPolicyBindingRepository,
    FleetRepository,
    FleetTopologyVersionRepository,
    ObserverAssignmentRepository,
)
from platform.fleets.schemas import (
    FleetCreate,
    FleetListResponse,
    FleetMemberCreate,
    FleetMemberListResponse,
    FleetMemberResponse,
    FleetOrchestrationRulesCreate,
    FleetOrchestrationRulesListResponse,
    FleetOrchestrationRulesResponse,
    FleetPolicyBindingResponse,
    FleetResponse,
    FleetTopologyUpdateRequest,
    FleetTopologyVersionListResponse,
    FleetTopologyVersionResponse,
    FleetUpdate,
    ObserverAssignmentResponse,
    OrchestrationModifier,
    default_modifier,
)
from typing import Any
from uuid import UUID, uuid4


def make_correlation(workspace_id: UUID, *, fleet_id: UUID | None = None) -> CorrelationContext:
    return CorrelationContext(
        workspace_id=workspace_id,
        fleet_id=fleet_id,
        correlation_id=uuid4(),
    )


def _rules_payload(data: FleetOrchestrationRulesCreate) -> dict[str, Any]:
    return data.model_dump(mode="json")


class FleetOrchestrationModifierService:
    def __init__(self, *, personality_service: Any | None = None) -> None:
        self.personality_service = personality_service

    async def get_modifier(self, fleet_id: UUID) -> OrchestrationModifier:
        if self.personality_service is None:
            return default_modifier()
        getter = getattr(self.personality_service, "get_modifier", None)
        if getter is None:
            return default_modifier()
        modifier = await getter(fleet_id)
        return (
            modifier
            if isinstance(modifier, OrchestrationModifier)
            else OrchestrationModifier.model_validate(modifier)
        )


class FleetService:
    def __init__(
        self,
        *,
        fleet_repo: FleetRepository,
        member_repo: FleetMemberRepository,
        topology_repo: FleetTopologyVersionRepository,
        policy_repo: FleetPolicyBindingRepository,
        observer_repo: ObserverAssignmentRepository,
        governance_repo: FleetGovernanceChainRepository,
        rules_repo: FleetOrchestrationRulesRepository,
        settings: Any,
        producer: Any | None,
        registry_service: Any | None = None,
        modifier_service: FleetOrchestrationModifierService | None = None,
        health_service: Any | None = None,
        runtime_controller: Any | None = None,
    ) -> None:
        self.fleet_repo = fleet_repo
        self.member_repo = member_repo
        self.topology_repo = topology_repo
        self.policy_repo = policy_repo
        self.observer_repo = observer_repo
        self.governance_repo = governance_repo
        self.rules_repo = rules_repo
        self.settings = settings
        self.producer = producer
        self.registry_service = registry_service
        self.modifier_service = modifier_service or FleetOrchestrationModifierService()
        self.health_service = health_service
        self.runtime_controller = runtime_controller

    async def create_fleet(
        self,
        workspace_id: UUID,
        request: FleetCreate,
        current_user_id: UUID,
    ) -> FleetResponse:
        if await self.fleet_repo.get_by_name_and_workspace(workspace_id, request.name) is not None:
            raise FleetNameConflictError(request.name)

        fleet = await self.fleet_repo.create(
            Fleet(
                workspace_id=workspace_id,
                name=request.name,
                status=FleetStatus.active,
                topology_type=request.topology_type,
                quorum_min=request.quorum_min,
            )
        )
        await self.topology_repo.create_version(
            FleetTopologyVersion(
                fleet_id=fleet.id,
                topology_type=request.topology_type,
                version=1,
                config=request.topology_config,
                is_current=True,
            )
        )
        await self.governance_repo.create_version(
            FleetGovernanceChain(
                fleet_id=fleet.id,
                workspace_id=workspace_id,
                version=1,
                observer_fqns=["platform:default-observer"],
                judge_fqns=["platform:default-judge"],
                enforcer_fqns=["platform:default-enforcer"],
                policy_binding_ids=[],
                verdict_to_action_mapping={},
                is_current=True,
                is_default=True,
            )
        )
        await self.rules_repo.create_version(
            FleetOrchestrationRules(
                fleet_id=fleet.id,
                workspace_id=workspace_id,
                version=1,
                delegation={"strategy": "round_robin", "config": {}},
                aggregation={"strategy": "first_wins", "config": {}},
                escalation={
                    "timeout_seconds": 300,
                    "failure_count": 3,
                    "escalate_to": "lead",
                },
                conflict_resolution={"strategy": "majority_vote"},
                retry={"max_retries": 2, "then": "reassign"},
                max_parallelism=1,
                is_current=True,
            )
        )
        member_fqns = list(request.member_fqns)
        lead_fqn = str(request.topology_config.get("lead_fqn", "")).strip()
        if (
            request.topology_type is FleetTopologyType.hierarchical
            and lead_fqn
            and lead_fqn not in member_fqns
        ):
            member_fqns.append(lead_fqn)
        for agent_fqn in member_fqns:
            await self._ensure_agent_exists(workspace_id, agent_fqn)
            role = (
                FleetMemberRole.lead
                if request.topology_type is FleetTopologyType.hierarchical and agent_fqn == lead_fqn
                else FleetMemberRole.worker
            )
            await self.member_repo.add(
                FleetMember(
                    fleet_id=fleet.id,
                    workspace_id=workspace_id,
                    agent_fqn=agent_fqn,
                    role=role,
                    availability=FleetMemberAvailability.available,
                )
            )
        await publish_fleet_event(
            self.producer,
            FleetEventType.fleet_created,
            FleetCreatedPayload(
                fleet_id=fleet.id,
                workspace_id=workspace_id,
                name=fleet.name,
                topology_type=fleet.topology_type.value,
            ),
            make_correlation(workspace_id, fleet_id=fleet.id),
        )
        return FleetResponse.model_validate(fleet)

    async def get_fleet(self, fleet_id: UUID, workspace_id: UUID) -> FleetResponse:
        fleet = await self._require_fleet(fleet_id, workspace_id)
        return FleetResponse.model_validate(fleet)

    async def list_fleets(
        self,
        workspace_id: UUID,
        *,
        status: FleetStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> FleetListResponse:
        items, total = await self.fleet_repo.list_by_workspace(
            workspace_id,
            status=status,
            page=page,
            page_size=page_size,
        )
        total_pages = (total + page_size - 1) // page_size if page_size else 0
        return FleetListResponse(
            items=[FleetResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    async def list_active_fleets(self) -> list[Fleet]:
        return await self.fleet_repo.list_active()

    async def update_fleet(
        self,
        fleet_id: UUID,
        workspace_id: UUID,
        request: FleetUpdate,
    ) -> FleetResponse:
        fleet = await self._require_fleet(fleet_id, workspace_id)
        if request.quorum_min is not None:
            fleet.quorum_min = request.quorum_min
        await self.fleet_repo.update(fleet)
        return FleetResponse.model_validate(fleet)

    async def archive_fleet(self, fleet_id: UUID, workspace_id: UUID) -> FleetResponse:
        fleet = await self._require_fleet(fleet_id, workspace_id)
        if fleet.status not in {FleetStatus.active, FleetStatus.degraded, FleetStatus.paused}:
            raise FleetStateError("Fleet cannot be archived from its current state")
        fleet.status = FleetStatus.archived
        await self.fleet_repo.soft_delete(fleet)
        current_chain = await self.governance_repo.get_current(fleet.id)
        if current_chain is not None:
            current_chain.is_current = False
        current_rules = await self.rules_repo.get_current(fleet.id)
        if current_rules is not None:
            current_rules.is_current = False
        await publish_fleet_event(
            self.producer,
            FleetEventType.fleet_archived,
            FleetArchivedPayload(fleet_id=fleet.id, workspace_id=workspace_id),
            make_correlation(workspace_id, fleet_id=fleet.id),
        )
        return FleetResponse.model_validate(fleet)

    async def add_member(
        self,
        fleet_id: UUID,
        workspace_id: UUID,
        request: FleetMemberCreate,
    ) -> FleetMemberResponse:
        fleet = await self._require_fleet(fleet_id, workspace_id)
        await self._ensure_agent_exists(workspace_id, request.agent_fqn)
        if await self.member_repo.get_by_fleet_and_fqn(fleet.id, request.agent_fqn) is not None:
            raise FleetStateError(
                "Agent is already a member of this fleet", code="FLEET_MEMBER_EXISTS"
            )
        if (
            fleet.topology_type is FleetTopologyType.hierarchical
            and request.role is FleetMemberRole.lead
            and await self.member_repo.get_lead(fleet.id) is not None
        ):
            raise FleetStateError(
                "Hierarchical fleets can only have one lead",
                code="FLEET_LEAD_ALREADY_EXISTS",
            )
        member = await self.member_repo.add(
            FleetMember(
                fleet_id=fleet.id,
                workspace_id=workspace_id,
                agent_fqn=request.agent_fqn,
                role=request.role,
                availability=FleetMemberAvailability.available,
            )
        )
        await publish_fleet_event(
            self.producer,
            FleetEventType.fleet_member_added,
            FleetMemberPayload(
                fleet_id=fleet.id,
                workspace_id=workspace_id,
                agent_fqn=member.agent_fqn,
                role=member.role.value,
            ),
            make_correlation(workspace_id, fleet_id=fleet.id),
        )
        return FleetMemberResponse.model_validate(member)

    async def remove_member(self, fleet_id: UUID, member_id: UUID, workspace_id: UUID) -> None:
        fleet = await self._require_fleet(fleet_id, workspace_id)
        member = await self.member_repo.get_by_id(member_id, fleet.id)
        if member is None:
            raise FleetStateError("Fleet member was not found", code="FLEET_MEMBER_NOT_FOUND")
        members = await self.member_repo.get_by_fleet(fleet.id)
        remaining = len([item for item in members if item.id != member.id])
        if remaining < fleet.quorum_min:
            raise QuorumNotMetError()
        await self.member_repo.remove(member)
        await publish_fleet_event(
            self.producer,
            FleetEventType.fleet_member_removed,
            FleetMemberPayload(
                fleet_id=fleet.id,
                workspace_id=workspace_id,
                agent_fqn=member.agent_fqn,
            ),
            make_correlation(workspace_id, fleet_id=fleet.id),
        )

    async def update_member_role(
        self,
        fleet_id: UUID,
        member_id: UUID,
        workspace_id: UUID,
        role: FleetMemberRole,
    ) -> FleetMemberResponse:
        fleet = await self._require_fleet(fleet_id, workspace_id)
        member = await self.member_repo.get_by_id(member_id, fleet.id)
        if member is None:
            raise FleetStateError("Fleet member was not found", code="FLEET_MEMBER_NOT_FOUND")
        if fleet.topology_type is FleetTopologyType.hierarchical and role is FleetMemberRole.lead:
            current_lead = await self.member_repo.get_lead(fleet.id)
            if current_lead is not None and current_lead.id != member.id:
                raise FleetStateError(
                    "Hierarchical fleets can only have one lead",
                    code="FLEET_LEAD_ALREADY_EXISTS",
                )
        updated = await self.member_repo.update_role(member, role)
        return FleetMemberResponse.model_validate(updated)

    async def list_members(self, fleet_id: UUID, workspace_id: UUID) -> FleetMemberListResponse:
        await self._require_fleet(fleet_id, workspace_id)
        items = await self.member_repo.get_by_fleet(fleet_id)
        return FleetMemberListResponse(
            items=[FleetMemberResponse.model_validate(item) for item in items],
            total=len(items),
        )

    async def get_fleet_members(
        self,
        fleet_id: UUID,
        workspace_id: UUID | None = None,
    ) -> list[FleetMemberResponse]:
        if workspace_id is not None:
            await self._require_fleet(fleet_id, workspace_id)
        items = await self.member_repo.get_by_fleet(fleet_id)
        return [FleetMemberResponse.model_validate(item) for item in items]

    async def update_topology(
        self,
        fleet_id: UUID,
        workspace_id: UUID,
        request: FleetTopologyUpdateRequest,
    ) -> FleetTopologyVersionResponse:
        fleet = await self._require_fleet(fleet_id, workspace_id)
        current = await self.topology_repo.get_current(fleet.id)
        version_number = 1 if current is None else current.version + 1
        version = await self.topology_repo.create_version(
            FleetTopologyVersion(
                fleet_id=fleet.id,
                topology_type=request.topology_type,
                version=version_number,
                config=request.config,
                is_current=True,
            )
        )
        if (
            fleet.topology_type is FleetTopologyType.hierarchical
            and request.topology_type is not FleetTopologyType.hierarchical
        ):
            for member in await self.member_repo.get_by_fleet(fleet.id):
                if member.role is FleetMemberRole.lead:
                    member.role = FleetMemberRole.worker
        elif request.topology_type is FleetTopologyType.hierarchical:
            lead_fqn = str(request.config.get("lead_fqn", "")).strip()
            if lead_fqn:
                lead = await self.member_repo.get_by_fleet_and_fqn(fleet.id, lead_fqn)
                if lead is not None:
                    lead.role = FleetMemberRole.lead
        fleet.topology_type = request.topology_type
        await publish_fleet_event(
            self.producer,
            FleetEventType.fleet_topology_changed,
            FleetTopologyChangedPayload(
                fleet_id=fleet.id,
                workspace_id=workspace_id,
                version=version.version,
                topology_type=version.topology_type.value,
            ),
            make_correlation(workspace_id, fleet_id=fleet.id),
        )
        return FleetTopologyVersionResponse.model_validate(version)

    async def get_topology_history(
        self,
        fleet_id: UUID,
        workspace_id: UUID,
    ) -> FleetTopologyVersionListResponse:
        await self._require_fleet(fleet_id, workspace_id)
        items = await self.topology_repo.list_history(fleet_id)
        return FleetTopologyVersionListResponse(
            items=[FleetTopologyVersionResponse.model_validate(item) for item in items],
            total=len(items),
        )

    async def bind_policy(
        self,
        fleet_id: UUID,
        workspace_id: UUID,
        policy_id: UUID,
        user_id: UUID,
    ) -> FleetPolicyBindingResponse:
        await self._require_fleet(fleet_id, workspace_id)
        existing = await self.policy_repo.get_by_policy(fleet_id, policy_id)
        if existing is not None:
            raise FleetStateError(
                "Policy is already bound to fleet", code="FLEET_POLICY_ALREADY_BOUND"
            )
        binding = await self.policy_repo.bind(
            FleetPolicyBinding(
                fleet_id=fleet_id,
                workspace_id=workspace_id,
                policy_id=policy_id,
                bound_by=user_id,
            )
        )
        return FleetPolicyBindingResponse.model_validate(binding)

    async def unbind_policy(self, fleet_id: UUID, binding_id: UUID, workspace_id: UUID) -> None:
        await self._require_fleet(fleet_id, workspace_id)
        binding = await self.policy_repo.get_by_id(binding_id, fleet_id)
        if binding is None:
            raise FleetStateError(
                "Policy binding was not found", code="FLEET_POLICY_BINDING_NOT_FOUND"
            )
        await self.policy_repo.unbind(binding)

    async def assign_observer(
        self,
        fleet_id: UUID,
        workspace_id: UUID,
        observer_fqn: str,
    ) -> ObserverAssignmentResponse:
        await self._require_fleet(fleet_id, workspace_id)
        await self._ensure_agent_exists(workspace_id, observer_fqn)
        if await self.observer_repo.get_active_by_fleet_and_fqn(fleet_id, observer_fqn) is not None:
            raise FleetStateError(
                "Observer is already assigned to fleet",
                code="FLEET_OBSERVER_ALREADY_ASSIGNED",
            )
        assignment = await self.observer_repo.assign(
            ObserverAssignment(
                fleet_id=fleet_id,
                workspace_id=workspace_id,
                observer_fqn=observer_fqn,
                is_active=True,
            )
        )
        return ObserverAssignmentResponse.model_validate(assignment)

    async def remove_observer(
        self, fleet_id: UUID, assignment_id: UUID, workspace_id: UUID
    ) -> None:
        await self._require_fleet(fleet_id, workspace_id)
        assignment = await self.observer_repo.get_by_id(assignment_id, fleet_id)
        if assignment is None:
            raise FleetStateError(
                "Observer assignment was not found",
                code="FLEET_OBSERVER_ASSIGNMENT_NOT_FOUND",
            )
        await self.observer_repo.deactivate(assignment)

    async def get_orchestration_rules(
        self,
        fleet_id: UUID,
        workspace_id: UUID | None = None,
    ) -> FleetOrchestrationRulesResponse:
        if workspace_id is not None:
            await self._require_fleet(fleet_id, workspace_id)
        rules = await self.rules_repo.get_current(fleet_id)
        if rules is None:
            raise FleetStateError(
                "Fleet orchestration rules were not found", code="FLEET_RULES_NOT_FOUND"
            )
        return FleetOrchestrationRulesResponse.model_validate(rules)

    async def update_orchestration_rules(
        self,
        fleet_id: UUID,
        workspace_id: UUID,
        request: FleetOrchestrationRulesCreate,
    ) -> FleetOrchestrationRulesResponse:
        await self._require_fleet(fleet_id, workspace_id)
        current = await self.rules_repo.get_current(fleet_id)
        version_number = 1 if current is None else current.version + 1
        created = await self.rules_repo.create_version(
            FleetOrchestrationRules(
                fleet_id=fleet_id,
                workspace_id=workspace_id,
                version=version_number,
                delegation=request.delegation.model_dump(mode="json"),
                aggregation=request.aggregation.model_dump(mode="json"),
                escalation=request.escalation.model_dump(mode="json"),
                conflict_resolution=request.conflict_resolution.model_dump(mode="json"),
                retry=request.retry.model_dump(mode="json"),
                max_parallelism=request.max_parallelism,
                is_current=True,
            )
        )
        await publish_fleet_event(
            self.producer,
            FleetEventType.fleet_orchestration_rules_updated,
            FleetRulesUpdatedPayload(
                fleet_id=fleet_id,
                workspace_id=workspace_id,
                version=created.version,
            ),
            make_correlation(workspace_id, fleet_id=fleet_id),
        )
        return FleetOrchestrationRulesResponse.model_validate(created)

    async def get_rules_history(
        self,
        fleet_id: UUID,
        workspace_id: UUID,
    ) -> FleetOrchestrationRulesListResponse:
        await self._require_fleet(fleet_id, workspace_id)
        items = await self.rules_repo.list_history(fleet_id)
        return FleetOrchestrationRulesListResponse(
            items=[FleetOrchestrationRulesResponse.model_validate(item) for item in items],
            total=len(items),
        )

    async def get_governance_chain(self, fleet_id: UUID, workspace_id: UUID) -> Any:
        await self._require_fleet(fleet_id, workspace_id)
        chain = await self.governance_repo.get_current(fleet_id)
        if chain is None:
            raise FleetStateError(
                "Fleet governance chain was not found", code="FLEET_GOVERNANCE_NOT_FOUND"
            )
        return chain

    async def get_orchestration_modifier(self, fleet_id: UUID) -> OrchestrationModifier:
        return await self.modifier_service.get_modifier(fleet_id)

    async def record_member_failure(self, fleet_id: UUID, agent_fqn: str) -> None:
        if self.health_service is not None:
            await self.health_service.handle_member_availability_change(
                agent_fqn, is_available=False
            )
        recorder = getattr(self.runtime_controller, "record_member_failure", None)
        if recorder is not None:
            result = recorder(fleet_id=str(fleet_id), agent_fqn=agent_fqn)
            if hasattr(result, "__await__"):
                await result

    async def _require_fleet(self, fleet_id: UUID, workspace_id: UUID) -> Fleet:
        fleet = await self.fleet_repo.get_by_id(fleet_id, workspace_id)
        if fleet is None:
            raise FleetNotFoundError(fleet_id)
        return fleet

    async def _ensure_agent_exists(self, workspace_id: UUID, agent_fqn: str) -> None:
        resolver = getattr(self.registry_service, "get_agent_by_fqn", None)
        if resolver is None:
            return
        result = await resolver(agent_fqn, workspace_id)
        if result is None:
            raise FleetStateError(
                f"Unknown agent FQN '{agent_fqn}'",
                code="FLEET_MEMBER_UNKNOWN_AGENT",
            )


def _extract_agent_fqn(payload: dict[str, Any]) -> str | None:
    for key in ("agent_fqn", "source_agent_fqn", "participant_identity"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    runtime = payload.get("runtime")
    if isinstance(runtime, dict):
        value = runtime.get("agent_fqn")
        if isinstance(value, str) and value:
            return value
    return None


async def route_execution_event_to_observers(
    envelope: EventEnvelope,
    *,
    member_repo: FleetMemberRepository,
    producer: Any | None,
) -> None:
    agent_fqn = _extract_agent_fqn(envelope.payload)
    if not agent_fqn or producer is None:
        return
    memberships = await member_repo.get_by_agent_fqn_across_fleets(agent_fqn)
    if not memberships:
        return
    send_raw = getattr(producer, "_ensure_producer", None)
    if send_raw is None:
        return
    kafka_producer = await send_raw()
    for membership in memberships:
        correlation = envelope.correlation_context.model_copy(
            update={
                "workspace_id": membership.workspace_id,
                "fleet_id": membership.fleet_id,
            }
        )
        forwarded = envelope.model_copy(update={"correlation_context": correlation})
        await kafka_producer.send_and_wait(
            "fleet.events",
            forwarded.model_dump_json().encode("utf-8"),
            key=str(membership.fleet_id).encode("utf-8"),
        )
